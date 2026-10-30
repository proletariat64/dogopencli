"""Historical replacement through installed leaves and offline public CLI."""

import json

import pytest
from test_workflow_cli import call
from test_workflow_keyed_cli import export
from test_workflow_keyed_cli import keyed as keyed_fixture

keyed = keyed_fixture

pytest_plugins = ["integration.leaves.liquidity.test_cash_balances_cli"]


@pytest.fixture
def ranged(keyed):
    browser, config = keyed
    adapter = config / "plugins/liquidity/cash.balances/adapter.py"
    adapter.write_text(
        adapter.read_text()
        + """
# Synthetic source explicitly establishes replacement, not the native balance leaf.
def range_replacement_contract(parameters):
    return {"namespace": {"account": parameters["account_alias"], "variant": "range"},
            "field": "valueDate", "from": parameters["from_date"],
            "to": parameters["to_date"], "format": "%Y%m%d",
            "interpretation": "calendar_date", "boundary": "inclusive"}
Adapter.range_replacement_contract = staticmethod(range_replacement_contract)
"""
    )
    return browser, config


def prepare(run_cli, artifact, action="replace-range"):
    return call(
        run_cli, "import", "plan", "--export", artifact["id"], "--action", action
    )


def apply(run_cli, plan):
    return call(run_cli, "import", "apply", "--plan", plan["id"])


def current(run_cli, artifact):
    return call(run_cli, "current", "show", "--export", artifact["id"])


def test_range_overlap_empty_preserves_external_rows_scopes_and_replay(run_cli, ranged):
    from leaves.liquidity.test_cash_balances_cli import row

    from dogopencli.browser import cdp

    browser, _ = ranged
    left, middle, right = [
        row(valueDate=d) for d in ("20260918", "20260919", "20260920")
    ]
    first = export(run_cli, browser, [left, middle, right])
    plan = prepare(run_cli, first)
    assert plan["expected_current"] is None
    assert plan["existing_count"] == 0
    assert plan["new_count"] == 3
    apply(run_cli, plan)
    other_row = row(aliasName="SECOND")
    other = export(run_cli, browser, [other_row], alias="SECOND")
    apply(run_cli, prepare(run_cli, other))
    revised = row(valueDate="20260919", closeBalance="9.00")
    second = export(run_cli, browser, [revised], start="20260919", end="20260919")
    plan = prepare(run_cli, second)
    assert plan["expected_current"] == first["id"]
    assert plan["existing_count"] == 1
    assert plan["retained_count"] == 2
    apply(run_cli, plan)
    assert current(run_cli, second)["records"] == [left, revised, right]
    empty = export(run_cli, browser, [], start="20260919", end="20260919")
    apply(run_cli, prepare(run_cli, empty))
    assert current(run_cli, first)["records"] == [left, right]
    assert current(run_cli, other)["records"] == [other_row]
    cdp.set_transport_factory(
        lambda *a, **k: pytest.fail("Range import/readback must be offline")
    )
    assert apply(run_cli, prepare(run_cli, first))["replayed"] is True
    assert current(run_cli, first)["records"] == [left, right]
    assert call(run_cli, "observation", "show", "--export", first["id"])["records"] == [
        left,
        middle,
        right,
    ]
    assert len(call(run_cli, "status")["range_publications"]) == 2


def test_range_stale_plan_and_commit_failure_leave_current_visible(run_cli, ranged):
    import duckdb
    from leaves.liquidity.test_cash_balances_cli import row

    browser, _ = ranged
    first = export(run_cli, browser, [row()])
    apply(run_cli, prepare(run_cli, first))
    delayed = export(run_cli, browser, [])
    stale = prepare(run_cli, delayed)
    later = export(run_cli, browser, [row(closeBalance="9.00")])
    plan = prepare(run_cli, later)
    with duckdb.connect(first["binding"]["database"]) as db:
        db.execute(
            "CREATE UNIQUE INDEX reject_range_receipt ON "
            "_dogopencli_range_receipts(relation_name)"
        )
    code, output, _ = run_cli(["workflow", "import", "apply", "--plan", plan["id"]])
    assert code == 1, output
    assert current(run_cli, first)["records"] == [row()]
    assert current(run_cli, first)["export_id"] == first["id"]
    code, _, _ = run_cli(["workflow", "observation", "show", "--export", later["id"]])
    assert code == 1
    with duckdb.connect(first["binding"]["database"]) as db:
        db.execute("DROP INDEX reject_range_receipt")
    apply(run_cli, plan)
    code, output, _ = run_cli(["workflow", "import", "apply", "--plan", stale["id"]])
    assert code == 1
    assert "Stale replacement plan" in json.loads(output)["error"]["message"]
    assert current(run_cli, first)["records"] == [row(closeBalance="9.00")]


@pytest.mark.parametrize(
    "first_action,second_action",
    [
        ("keyed", "replace-range"),
        ("replace-range", "keyed"),
        ("replace-full", "replace-range"),
        ("replace-range", "replace-full"),
        ("keyed", "replace-full"),
    ],
)
def test_mixed_current_actions_reject_planning_and_recheck_under_lock(
    run_cli, ranged, first_action, second_action
):
    from leaves.liquidity.test_cash_balances_cli import row

    browser, _ = ranged
    first = export(run_cli, browser, [row()])
    second = export(run_cli, browser, [row(closeBalance="2.00")])
    delayed = prepare(run_cli, second, second_action)
    apply(run_cli, prepare(run_cli, first, first_action))
    code, output, _ = run_cli(
        [
            "workflow",
            "import",
            "plan",
            "--export",
            second["id"],
            "--action",
            second_action,
        ]
    )
    assert code == 1, output
    code, output, _ = run_cli(["workflow", "import", "apply", "--plan", delayed["id"]])
    assert code == 1, output
    assert "ownership" in json.loads(output)["error"]["message"]
    assert current(run_cli, first)["records"] == [row()]
    # Preservation is always a separate observation and cannot change current rows.
    apply(run_cli, prepare(run_cli, second, "preserve"))
    assert current(run_cli, first)["records"] == [row()]
    assert call(run_cli, "observation", "show", "--export", second["id"])[
        "records"
    ] == [row(closeBalance="2.00")]


def test_unknown_or_outside_native_coverage_blocks_only_replacement(run_cli, keyed):

    browser, _ = keyed
    unknown = export(run_cli, browser, [])
    code, output, _ = run_cli(
        [
            "workflow",
            "import",
            "plan",
            "--export",
            unknown["id"],
            "--action",
            "replace-range",
        ]
    )
    assert code == 1
    assert (
        "explicit native range replacement coverage"
        in json.loads(output)["error"]["message"]
    )
    apply(run_cli, prepare(run_cli, unknown, "preserve"))


def test_range_binding_uses_frozen_export_after_adapter_change_and_preserve(
    run_cli, ranged
):
    from leaves.liquidity.test_cash_balances_cli import row

    from dogopencli.browser import cdp

    browser, config = ranged
    artifact = export(run_cli, browser, [row()])
    apply(run_cli, prepare(run_cli, artifact, "preserve"))
    plan = prepare(run_cli, artifact)
    adapter = config / "plugins/liquidity/cash.balances/adapter.py"
    adapter.write_text(
        adapter.read_text().replace('"variant": "range"', '"variant": "different"')
    )
    cdp.set_transport_factory(
        lambda *a, **k: pytest.fail("Frozen import must stay offline")
    )
    assert apply(run_cli, plan)["replayed"] is False
    assert current(run_cli, artifact)["records"] == [row()]
    assert len(call(run_cli, "status")["committed_observations"]) == 1


def test_changed_range_semantics_cannot_open_overlapping_current_namespace(
    run_cli, ranged
):
    from leaves.liquidity.test_cash_balances_cli import row

    browser, config = ranged
    first = export(run_cli, browser, [row()])
    apply(run_cli, prepare(run_cli, first))
    adapter = config / "plugins/liquidity/cash.balances/adapter.py"
    adapter.write_text(
        adapter.read_text().replace('"field": "valueDate"', '"field": "updateTime"')
    )
    changed = export(run_cli, browser, [])
    code, output, _ = run_cli(
        [
            "workflow",
            "import",
            "plan",
            "--export",
            changed["id"],
            "--action",
            "replace-range",
        ]
    )
    assert code == 1
    assert "semantics" in json.loads(output)["error"]["message"]
    assert current(run_cli, first)["records"] == [row()]


def test_failed_and_incomplete_refresh_cannot_clear_owned_history(run_cli, ranged):
    from leaves.liquidity.test_cash_balances_cli import page, row

    browser, _ = ranged
    first = export(run_cli, browser, [row()])
    apply(run_cli, prepare(run_cli, first))
    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.cash.balances",
        "--parameters",
        '{"account-alias":"ACCOUNT","from-date":"20260918","to-date":"20260918"}',
    )
    browser.business_script.append(page([row(valueDate="20260920")]))
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
    failed = call(run_cli, "status")["latest_attempt"]
    assert failed["state"] == "failed"
    browser.business_script.append(page([row()], total=2))
    partial = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    assert partial["state"] == "incomplete"
    for artifact in (failed, partial):
        code, output, _ = run_cli(
            [
                "workflow",
                "import",
                "plan",
                "--export",
                artifact["id"],
                "--action",
                "replace-range",
            ]
        )
        assert code == 1
        assert "complete export" in json.loads(output)["error"]["message"]
    assert current(run_cli, first)["records"] == [row()]


def test_range_writer_contention_is_safe_and_retry_remains_exact(run_cli, ranged):
    import fcntl

    from leaves.liquidity.test_cash_balances_cli import row

    browser, config = ranged
    first = export(run_cli, browser, [row()])
    plan = prepare(run_cli, first)
    with (config / "leaf-registry.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        code, output, _ = run_cli(["workflow", "import", "apply", "--plan", plan["id"]])
        assert code == 1
        assert json.loads(output)["error"]["code"] == "LOCKED"
    assert apply(run_cli, plan)["replayed"] is False
    assert current(run_cli, first)["records"] == [row()]


def test_preserve_after_range_reports_observation_effect_without_republication(
    run_cli, ranged
):
    from leaves.liquidity.test_cash_balances_cli import row

    browser, _ = ranged
    artifact = export(run_cli, browser, [row()])
    apply(run_cli, prepare(run_cli, artifact))
    preserved = apply(run_cli, prepare(run_cli, artifact, "preserve"))
    assert preserved["replayed"] is True
    assert preserved["action"] == "preserve"
    assert preserved["current_effect"] == "unchanged"
    assert current(run_cli, artifact)["records"] == [row()]


def test_range_replay_in_new_process_uses_committed_receipt(run_cli, ranged):
    import multiprocessing

    from leaves.liquidity.test_cash_balances_cli import row

    from dogopencli.browser import cdp

    browser, _ = ranged
    artifact = export(run_cli, browser, [row()])
    plan = prepare(run_cli, artifact)
    apply(run_cli, plan)
    empty = export(run_cli, browser, [])
    apply(run_cli, prepare(run_cli, empty))
    cdp.set_transport_factory(
        lambda *a, **k: pytest.fail("Restarted import must be offline")
    )
    context = multiprocessing.get_context("fork")
    received, sent = context.Pipe(duplex=False)

    def restart():
        sent.send(run_cli(["workflow", "import", "apply", "--plan", plan["id"]]))
        sent.close()

    process = context.Process(target=restart)
    process.start()
    sent.close()
    try:
        assert received.poll(20), "Restarted importer did not finish"
        code, output, _ = received.recv()
        process.join(20)
        assert process.exitcode == 0
        assert code == 0, output
        result = json.loads(output)["data"]
        assert result["replayed"] is True
        assert result["inserted_count"] == 0
    finally:
        received.close()
        if process.is_alive():
            process.terminate()
            process.join(5)
    assert current(run_cli, artifact)["export_id"] == empty["id"]
    assert current(run_cli, artifact)["records"] == []


@pytest.mark.parametrize("action", ["replace-range", "keyed"])
def test_import_status_requires_exact_action_receipt_after_preserve(
    run_cli, ranged, action
):
    from leaves.liquidity.test_cash_balances_cli import row

    from dogopencli.browser import cdp

    browser, _ = ranged
    artifact = export(run_cli, browser, [row()])
    apply(run_cli, prepare(run_cli, artifact, "preserve"))
    plan = prepare(run_cli, artifact, action)
    cdp.set_transport_factory(
        lambda *a, **k: pytest.fail("Observation and import must stay offline")
    )
    pending = call(run_cli, "import", "status", "--plan", plan["id"])
    assert pending["effective_state"] == "pending"
    assert pending["result"]["action_completed"] is False

    apply(run_cli, plan)
    committed = call(run_cli, "import", "status", "--plan", plan["id"])
    assert committed["result"]["action"] == action
    assert committed["effective_state"] == "completed"
    assert committed["attempt"]["state"] == "completed"
    assert committed["result"]["action_completed"] is True
    assert committed["progress"]["committed_rows"] == 1
    assert committed["observation"]["completion_verification"]["source"] == (
        "database_receipts"
    )
    assert apply(run_cli, plan)["replayed"] is True
    replayed = call(run_cli, "import", "status", "--plan", plan["id"])
    assert replayed["effective_state"] == "completed"
    assert replayed["result"]["action_completed"] is True
