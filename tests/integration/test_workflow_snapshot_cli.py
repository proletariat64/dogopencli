"""Explicit current publication through installed leaves and offline readback."""

import pytest
from integration.test_workflow_cli import call, payment_page

pytest_plugins = ["integration.test_leaf_pilots_cli"]


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from dogopencli import workflow

    ticks = iter(range(1000))
    monkeypatch.setattr(
        workflow,
        "now",
        lambda: (
            datetime(2026, 10, 29, tzinfo=timezone.utc) + timedelta(seconds=next(ticks))
        ).isoformat(),
    )


def test_full_snapshot_initial_publication_preserves_nested_rows(run_cli, pilots):
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    rows = [
        {"id": value, "nested": {"values": [None, False, "1.000"]}}
        for value in ("one", "two")
    ]
    pilots.business_script.append(payment_page(rows))
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    preview = call(
        run_cli,
        "import",
        "plan",
        "--export",
        exported["id"],
        "--action",
        "replace-full",
    )
    assert preview["existing_count"] == 0
    assert preview["new_count"] == 2
    assert preview["expected_current"] is None
    assert preview["current_effect"] == "replace_exact_scope"
    receipt = call(run_cli, "import", "apply", "--plan", preview["id"])
    assert receipt["current_export_id"] == exported["id"]
    current = call(run_cli, "current", "show", "--export", exported["id"])
    assert current["records"] == rows
    assert current["export_id"] == exported["id"]
    regenerated = call(
        run_cli,
        "import",
        "plan",
        "--export",
        exported["id"],
        "--action",
        "replace-full",
    )
    assert (
        call(run_cli, "import", "apply", "--plan", regenerated["id"])["replayed"]
        is True
    )


def snapshot(run_cli, pilots, plan, rows):
    pilots.business_script.append(payment_page(rows))
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    prepared = call(
        run_cli,
        "import",
        "plan",
        "--export",
        exported["id"],
        "--action",
        "replace-full",
    )
    return exported, prepared


def stored_rows(binding):
    import duckdb

    with duckdb.connect(binding["database"], read_only=True) as db:
        return [
            row[0]
            for row in db.execute(
                f'SELECT _record FROM "{binding["relation"]}" ORDER BY _record'
            ).fetchall()
        ]


def test_replacement_empty_and_stale_plan_preserve_other_scopes_and_exports(
    run_cli, pilots
):
    import json

    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "payment.sla.baselines",
        "--parameters",
        '{"biz-legal-entity":"A"}',
    )
    first, prepared = snapshot(run_cli, pilots, plan, [{"id": "one"}])
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    other_plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "payment.sla.baselines",
        "--parameters",
        '{"biz-legal-entity":"B"}',
    )
    other, prepared = snapshot(run_cli, pilots, other_plan, [{"id": "one"}])
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    empty, stale = snapshot(run_cli, pilots, plan, [])
    second, prepared = snapshot(run_cli, pilots, plan, [{"id": "two"}])
    assert prepared["expected_current"] == first["id"]
    assert prepared["existing_count"] == 1
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    code, out, _ = run_cli(["workflow", "import", "apply", "--plan", stale["id"]])
    assert code == 1
    assert "Stale replacement plan" in json.loads(out)["error"]["message"]
    assert stored_rows(plan["binding"]) == ['{"id":"one"}', '{"id":"two"}']
    prepared = call(
        run_cli, "import", "plan", "--export", empty["id"], "--action", "replace-full"
    )
    assert prepared["expected_current"] == second["id"]
    assert prepared["new_count"] == 0
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    assert call(run_cli, "current", "show", "--export", first["id"])["records"] == []
    assert stored_rows(plan["binding"]) == ['{"id":"one"}']
    assert (
        call(run_cli, "current", "show", "--export", other["id"])["export_id"]
        == other["id"]
    )
    assert call(run_cli, "observation", "show", "--export", first["id"])["records"] == [
        {"id": "one"}
    ]
    assert call(run_cli, "export", "show", "--export", first["id"])["records"] == [
        {"id": "one"}
    ]
    # Replaying an old publication never moves the current pointer backwards.
    replay = call(
        run_cli, "import", "plan", "--export", first["id"], "--action", "replace-full"
    )
    assert call(run_cli, "import", "apply", "--plan", replay["id"])["replayed"] is True
    assert stored_rows(plan["binding"]) == ['{"id":"one"}']


def test_failed_replacement_rolls_back_rows_receipt_and_pointer(run_cli, pilots):
    import duckdb

    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    first, prepared = snapshot(run_cli, pilots, plan, [{"id": "stable"}])
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    second, prepared = snapshot(run_cli, pilots, plan, [{"id": "later"}])
    with duckdb.connect(plan["binding"]["database"]) as db:
        # Force a failure after current-row writes but before pointer commit.
        db.execute(
            "CREATE UNIQUE INDEX one_publication ON "
            "_dogopencli_publication_receipts ((substring(receipt, 1, 1)))"
        )
    code, output, _ = run_cli(["workflow", "import", "apply", "--plan", prepared["id"]])
    assert code == 1, output
    assert stored_rows(plan["binding"]) == ['{"id":"stable"}']
    assert (
        call(run_cli, "current", "show", "--export", second["id"])["export_id"]
        == first["id"]
    )
    assert len(call(run_cli, "status")["current_publications"]) == 1
    code, _, _ = run_cli(["workflow", "observation", "show", "--export", second["id"]])
    assert code == 1
    with duckdb.connect(plan["binding"]["database"]) as db:
        db.execute("DROP INDEX one_publication")
    assert (
        call(run_cli, "import", "apply", "--plan", prepared["id"])["replayed"] is False
    )
    assert stored_rows(plan["binding"]) == ['{"id":"later"}']


def test_incomplete_and_failed_refresh_cannot_replace_committed_current(
    run_cli, pilots
):
    import json

    from dogopencli.browser import cdp

    plan = call(run_cli, "plan", "create", "--leaf", "collection.cost")
    row = {"itemId": "stable", "itemType": "FUND_IN_CHANNEL_TRANS_FEE"}
    complete_page = payment_page([row])
    complete_page["body"]["pageSize"] = 1000
    pilots.business_script.append(complete_page)
    first = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    prepared = call(
        run_cli, "import", "plan", "--export", first["id"], "--action", "replace-full"
    )
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    partial_page = payment_page([row])
    partial_page["body"].update(pageSize=1000, totalCount=1001)
    pilots.business_script.append(partial_page)
    partial = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    assert partial["state"] == "incomplete"
    code, output, _ = run_cli(
        [
            "workflow",
            "import",
            "plan",
            "--export",
            partial["id"],
            "--action",
            "replace-full",
        ]
    )
    assert code == 1
    assert "complete export" in json.loads(output)["error"]["message"]
    pilots.business_script.append({"status": 401, "body": {}})
    code, _, _ = run_cli(
        [
            "workflow",
            "export",
            "run",
            "--run",
            call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        ]
    )
    assert code == 1
    status = call(run_cli, "status")
    failed = status["latest_attempt"]
    assert failed["state"] == "failed"
    code, _, _ = run_cli(
        [
            "workflow",
            "import",
            "plan",
            "--export",
            failed["id"],
            "--action",
            "replace-full",
        ]
    )
    assert code == 1
    assert status["current_publications"][0]["export_id"] == first["id"]
    assert stored_rows(plan["binding"]) == [
        '{"itemId":"stable","itemType":"FUND_IN_CHANNEL_TRANS_FEE"}'
    ]

    def offline(*args, **kwargs):
        raise AssertionError("Current readback and replay must be offline")

    cdp.set_transport_factory(offline)
    assert call(run_cli, "current", "show", "--export", first["id"])["records"] == [row]
    assert (
        call(run_cli, "import", "apply", "--plan", prepared["id"])["replayed"] is True
    )


def test_preserved_export_can_be_explicitly_published_without_duplicating_observation(
    run_cli, pilots
):
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    exported, publication = snapshot(run_cli, pilots, plan, [{"id": "one"}])
    preserved = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    call(run_cli, "import", "apply", "--plan", preserved["id"])
    applied = call(run_cli, "import", "apply", "--plan", publication["id"])
    assert applied["replayed"] is False
    current = call(run_cli, "current", "show", "--export", exported["id"])
    assert current["receipt"]["action"] == "replace-full"
    assert current["records"] == [{"id": "one"}]
    assert len(call(run_cli, "status")["committed_observations"]) == 1
