"""Scoped history reconciliation through installed leaves and offline public CLI."""

import json

import pytest
from test_workflow_cli import call

pytest_plugins = ["integration.leaves.liquidity.test_cash_balances_cli"]


@pytest.fixture
def keyed(installed, monkeypatch):
    from dogopencli import workflow

    _, browser, config = installed
    adapter = config / "plugins/liquidity/cash.balances/adapter.py"
    adapter.write_text(
        adapter.read_text()
        + """
# Test-only declared source facts; these do not qualify the native balance leaf.
def keyed_contract(parameters):
    return {"identity": ["entity", "bankId", "aliasName", "currency", "valueDate"],
            "namespace": {"variant": "synthetic-history", "business": "balances"},
            "cross_range_equivalence": True,
            "ordering": {"mode": "source_version",
                         "field": "updateTime", "comparison": "lexical"}}
Adapter.keyed_contract = staticmethod(keyed_contract)
"""
    )
    from datetime import datetime, timedelta, timezone

    ticks = iter(range(1000))
    monkeypatch.setattr(
        workflow,
        "now",
        lambda: (
            datetime(2026, 10, 29, tzinfo=timezone.utc) + timedelta(seconds=next(ticks))
        ).isoformat(),
    )
    return browser, config


def export(run_cli, browser, rows, start="20260918", end="20260920", alias="ACCOUNT"):
    from leaves.liquidity.test_cash_balances_cli import page

    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.cash.balances",
        "--parameters",
        json.dumps({"account-alias": alias, "from-date": start, "to-date": end}),
    )
    browser.business_script.append(page(rows))
    return call(run_cli, "export", "run", "--plan", plan["id"])


def merge(run_cli, artifact):
    plan = call(
        run_cli, "import", "plan", "--export", artifact["id"], "--action", "keyed"
    )
    return call(run_cli, "import", "apply", "--plan", plan["id"])


def current(run_cli, artifact):
    return call(run_cli, "current", "show", "--export", artifact["id"])


def test_keyed_overlap_preserves_absent_history_orders_versions_and_replays_offline(
    run_cli, keyed
):
    from leaves.liquidity.test_cash_balances_cli import row

    from dogopencli.browser import cdp

    browser, _ = keyed
    old = row(valueDate="20260918", closeBalance="1.00")
    retained = row(valueDate="20260919", closeBalance="2.00")
    first = export(run_cli, browser, [old, retained])
    assert merge(run_cli, first)["inserted_count"] == 2
    revised = row(
        valueDate="20260918", closeBalance="3.00", updateTime="2026-09-21 08:00:00"
    )
    second = export(run_cli, browser, [revised], end="20260918")
    assert merge(run_cli, second)["updated_count"] == 1
    assert current(run_cli, second)["records"] == [revised, retained]
    older = export(run_cli, browser, [old], end="20260918")
    assert merge(run_cli, older)["unchanged_count"] == 1
    assert current(run_cli, older)["records"] == [revised, retained]
    cdp.set_transport_factory(lambda *a, **k: pytest.fail("Import must remain offline"))
    assert merge(run_cli, second)["replayed"] is True
    assert current(run_cli, first)["records"] == [revised, retained]
    assert call(run_cli, "observation", "show", "--export", first["id"])["records"] == [
        old,
        retained,
    ]


def test_equal_version_conflict_is_atomic_and_preserve_remains_available(
    run_cli, keyed
):
    from leaves.liquidity.test_cash_balances_cli import row

    browser, _ = keyed
    first = export(run_cli, browser, [row()])
    merge(run_cli, first)
    other = export(run_cli, browser, [row(closeBalance="999.00")])
    code, output, _ = run_cli(
        ["workflow", "import", "plan", "--export", other["id"], "--action", "keyed"]
    )
    assert code == 1
    assert "Equal-version conflict" in json.loads(output)["error"]["message"]
    assert current(run_cli, first)["records"] == [row()]
    plan = call(
        run_cli, "import", "plan", "--export", other["id"], "--action", "preserve"
    )
    call(run_cli, "import", "apply", "--plan", plan["id"])
    assert call(run_cli, "observation", "show", "--export", other["id"])["records"] == [
        row(closeBalance="999.00")
    ]


def test_apply_rechecks_conflict_under_transaction_and_rolls_back_new_rows(
    run_cli, keyed
):
    from leaves.liquidity.test_cash_balances_cli import row

    browser, _ = keyed
    first = export(run_cli, browser, [row()])
    delayed = call(
        run_cli, "import", "plan", "--export", first["id"], "--action", "keyed"
    )
    competing = export(run_cli, browser, [row(closeBalance="222.00")])
    merge(run_cli, competing)
    code, output, _ = run_cli(["workflow", "import", "apply", "--plan", delayed["id"]])
    assert code == 1
    assert "Equal-version conflict" in json.loads(output)["error"]["message"]
    assert current(run_cli, first)["records"] == [row(closeBalance="222.00")]
    code, _, _ = run_cli(["workflow", "observation", "show", "--export", first["id"]])
    assert code == 1


def test_native_unknown_cross_range_equivalence_blocks_only_keyed_merge(
    run_cli, installed
):
    from leaves.liquidity.test_cash_balances_cli import row

    _, browser, _ = installed
    artifact = export(run_cli, browser, [row()])
    code, output, _ = run_cli(
        ["workflow", "import", "plan", "--export", artifact["id"], "--action", "keyed"]
    )
    assert code == 1
    assert "preserve the exact observation" in json.loads(output)["error"]["message"]
    plan = call(
        run_cli, "import", "plan", "--export", artifact["id"], "--action", "preserve"
    )
    assert call(run_cli, "import", "apply", "--plan", plan["id"])["inserted_count"] == 1


def test_latest_observed_uses_capture_order_and_keeps_provenance_offline(
    run_cli, keyed
):
    from leaves.liquidity.test_cash_balances_cli import row

    from dogopencli.browser import cdp

    browser, config = keyed
    adapter = config / "plugins/liquidity/cash.balances/adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            '"mode": "source_version",\n'
            '                         "field": "updateTime", "comparison": "lexical"',
            '"mode": "latest_observed"',
        )
    )
    first = export(run_cli, browser, [row(closeBalance="1.00")])
    second = export(run_cli, browser, [row(closeBalance="2.00")])
    receipt = merge(run_cli, second)
    assert receipt["ordering"] == {"mode": "latest_observed"}
    assert merge(run_cli, first)["unchanged_count"] == 1
    cdp.set_transport_factory(
        lambda *a, **k: pytest.fail("Readback must remain offline")
    )
    result = current(run_cli, first)
    assert result["records"] == [row(closeBalance="2.00")]
    assert result["provenance"] == [
        {"export_id": second["id"], "captured_at": second["completed_at"]}
    ]


def test_native_identity_and_variant_namespace_isolate_current_records(run_cli, keyed):
    from leaves.liquidity.test_cash_balances_cli import row

    browser, config = keyed
    first = export(run_cli, browser, [row()])
    merge(run_cli, first)
    other_account = row(aliasName="SECOND", closeBalance="5.00")
    second = export(run_cli, browser, [other_account], alias="SECOND")
    merge(run_cli, second)
    assert current(run_cli, first)["records"] == [row(), other_account]
    adapter = config / "plugins/liquidity/cash.balances/adapter.py"
    adapter.write_text(
        adapter.read_text().replace("synthetic-history", "synthetic-variant")
    )
    variant = export(run_cli, browser, [row(closeBalance="7.00")])
    merge(run_cli, variant)
    assert current(run_cli, variant)["records"] == [row(closeBalance="7.00")]
    assert current(run_cli, first)["records"] == [row(), other_account]


def test_failed_receipt_write_rolls_back_current_changes_and_observation(
    run_cli, keyed
):
    import duckdb
    from leaves.liquidity.test_cash_balances_cli import row

    browser, _ = keyed
    first = export(run_cli, browser, [row()])
    merge(run_cli, first)
    later = export(
        run_cli, browser, [row(closeBalance="8.00", updateTime="2026-09-22 08:00:00")]
    )
    plan = call(run_cli, "import", "plan", "--export", later["id"], "--action", "keyed")
    # A local constraint fails the receipt write after current records were updated.
    with duckdb.connect(first["binding"]["database"]) as db:
        db.execute(
            "CREATE UNIQUE INDEX reject_second_receipt ON "
            "_dogopencli_keyed_receipts(relation_name)"
        )
    code, output, _ = run_cli(["workflow", "import", "apply", "--plan", plan["id"]])
    assert code == 1 and json.loads(output)["error"]["code"] == "WORKFLOW_ERROR"
    assert current(run_cli, first)["records"] == [row()]
    code, _, _ = run_cli(["workflow", "observation", "show", "--export", later["id"]])
    assert code == 1
    with duckdb.connect(first["binding"]["database"]) as db:
        db.execute("DROP INDEX reject_second_receipt")
    assert call(run_cli, "import", "apply", "--plan", plan["id"])["updated_count"] == 1


def test_identical_latest_observation_advances_order_without_changing_values(
    run_cli, keyed
):
    from leaves.liquidity.test_cash_balances_cli import row

    browser, config = keyed
    adapter = config / "plugins/liquidity/cash.balances/adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            '"mode": "source_version"', '"mode": "latest_observed"'
        )
    )
    first = export(run_cli, browser, [row(closeBalance="1.00")])
    delayed = export(run_cli, browser, [row(closeBalance="2.00")])
    latest = export(run_cli, browser, [row(closeBalance="1.00")])
    merge(run_cli, first)
    assert merge(run_cli, latest)["unchanged_count"] == 1
    assert merge(run_cli, delayed)["unchanged_count"] == 1
    assert current(run_cli, first)["records"] == [row(closeBalance="1.00")]
    assert current(run_cli, first)["provenance"][0]["export_id"] == latest["id"]


def test_full_publication_readback_uses_its_action_even_with_native_key_facts(
    run_cli, keyed
):
    from leaves.liquidity.test_cash_balances_cli import row

    browser, _ = keyed
    artifact = export(run_cli, browser, [row()])
    plan = call(
        run_cli,
        "import",
        "plan",
        "--export",
        artifact["id"],
        "--action",
        "replace-full",
    )
    call(run_cli, "import", "apply", "--plan", plan["id"])
    assert current(run_cli, artifact)["records"] == [row()]
    code, output, _ = run_cli(
        ["workflow", "import", "plan", "--export", artifact["id"], "--action", "keyed"]
    )
    assert code == 1
    assert "ownership is ambiguous" in json.loads(output)["error"]["message"]


def test_status_distinguishes_keyed_commit_from_latest_export_attempt(run_cli, keyed):
    from leaves.liquidity.test_cash_balances_cli import row

    browser, _ = keyed
    first = export(run_cli, browser, [row()])
    merge(run_cli, first)
    newer = export(run_cli, browser, [])
    status = call(run_cli, "status")
    assert status["last_successful_export"]["id"] == newer["id"]
    assert status["keyed_imports"][0]["export_id"] == first["id"]
    assert status["keyed_imports"][0]["inserted_count"] == 1


def test_committed_empty_export_replans_after_source_contract_changes(run_cli, keyed):
    from leaves.liquidity.test_cash_balances_cli import row

    from dogopencli.browser import cdp

    browser, config = keyed
    first = export(run_cli, browser, [])
    uncommitted = export(run_cli, browser, [])
    saved = call(
        run_cli, "import", "plan", "--export", first["id"], "--action", "keyed"
    )
    call(run_cli, "import", "apply", "--plan", saved["id"])
    adapter = config / "plugins/liquidity/cash.balances/adapter.py"
    adapter.write_text(
        adapter.read_text().replace('"identity": ["entity",', '"identity": [')
    )
    later = export(run_cli, browser, [row()])
    assert merge(run_cli, later)["inserted_count"] == 1
    cdp.set_transport_factory(lambda *a, **k: pytest.fail("Replay must remain offline"))
    assert call(run_cli, "import", "apply", "--plan", saved["id"])["replayed"] is True
    replay = merge(run_cli, first)
    assert replay["replayed"] is True
    assert replay["inserted_count"] == replay["updated_count"] == 0
    assert current(run_cli, later)["records"] == [row()]
    code, output, _ = run_cli(
        [
            "workflow",
            "import",
            "plan",
            "--export",
            uncommitted["id"],
            "--action",
            "keyed",
        ]
    )
    assert code == 1
    assert "contract differs" in json.loads(output)["error"]["message"]

    import duckdb

    with duckdb.connect(first["binding"]["database"]) as db:
        saved_header = json.loads(
            db.execute(
                "SELECT artifact FROM _dogopencli_observations WHERE export_id=?",
                [first["id"]],
            ).fetchone()[0]
        )
        saved_header["keyed_contract"]["identity"] = ["tampered"]
        db.execute(
            "UPDATE _dogopencli_observations SET artifact=? WHERE export_id=?",
            [json.dumps(saved_header), first["id"]],
        )
    code, output, _ = run_cli(
        ["workflow", "import", "plan", "--export", first["id"], "--action", "keyed"]
    )
    assert code == 1
    assert "differs from keyed receipt" in json.loads(output)["error"]["message"]
