"""Bounded native history through installed leaves and the public CLI."""

import json

import pytest
from test_workflow_cli import call

pytest_plugins = ["integration.leaves.liquidity.test_cash_balances_cli"]


def create(run_cli, *flags):
    return call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.cash.balances",
        "--mode",
        "history",
        "--parameters",
        '{"account-alias":"ACCOUNT","from-date":"2026-09-18","to-date":"20260920"}',
        *flags,
    )


def test_history_freezes_exact_queries_and_reports_interior_unqueried_scope(
    run_cli,
    installed,
    monkeypatch,
):
    from dogopencli import workflow

    _, browser, config = installed
    monkeypatch.setattr(workflow, "now", lambda: "2026-10-29T00:00:00+00:00")
    plan = create(
        run_cli,
        "--windows",
        '[{"from":"2026-09-18","to":"2026-09-18"},{"from":"2026-09-20","to":"2026-09-20"}]',
    )
    assert plan["mode"] == "history"
    assert plan["desired_range"] == {"from": "2026-09-18", "to": "2026-09-20"}
    assert plan["cutoff"] == "20260920"
    assert plan["created_at"] == "2026-10-29T00:00:00+00:00"
    before = {p: p.read_bytes() for p in config.rglob("*") if p.is_file()}
    status = call(run_cli, "history", "show", "--plan", plan["id"])
    assert status["unqueried_ranges"] == [{"from": "2026-09-18", "to": "2026-09-20"}]
    assert status["unplanned_ranges"] == [{"from": "2026-09-19", "to": "2026-09-19"}]
    assert [p["state"] for p in status["packages"]] == ["unqueried", "unqueried"]
    assert status["current_history_effect"] == "separate_observations"
    assert status["complete"] is False
    assert not browser.business_requests
    assert {p: p.read_bytes() for p in config.rglob("*") if p.is_file()} == before
    assert "history" in call(run_cli, "status")


def test_history_resumes_successes_retains_failure_and_imports_exact_packages(
    run_cli,
    installed,
):
    from leaves.liquidity.test_cash_balances_cli import page, row

    _, browser, _ = installed
    plan = create(
        run_cli,
        "--windows",
        '[{"from":"2026-09-18","to":"2026-09-18"},'
        '{"from":"2026-09-19","to":"2026-09-19"},'
        '{"from":"2026-09-20","to":"2026-09-20"}]',
    )
    browser.business_script.extend(
        [
            page([row()]),
            {"status": 500, "body": {}},
            page([]),
        ]
    )
    code, output, _ = run_cli(["workflow", "export", "run", "--plan", plan["id"]])
    assert code == 1, output
    status = call(run_cli, "history", "show", "--plan", plan["id"])
    assert [p["state"] for p in status["packages"]] == [
        "complete_nonempty",
        "failed",
        "complete_empty",
    ]
    assert status["uncovered_ranges"] == [{"from": "2026-09-19", "to": "2026-09-19"}]
    original_id = status["packages"][0]["export_id"]
    original = call(run_cli, "export", "show", "--export", original_id)
    count = len(browser.business_requests)
    browser.business_script.append(page([row(valueDate="20260919")]))
    resumed = call(run_cli, "export", "run", "--plan", plan["id"])
    assert resumed["complete"] is True
    assert len(browser.business_requests) == count + 1
    assert resumed["packages"][0]["export_id"] == original_id
    assert len(resumed["packages"][1]["attempts"]) == 2
    assert call(run_cli, "export", "show", "--export", original_id) == original
    for package in resumed["packages"]:
        prepared = call(
            run_cli,
            "import",
            "plan",
            "--export",
            package["export_id"],
            "--action",
            "preserve",
        )
        call(run_cli, "import", "apply", "--plan", prepared["id"])
    assert call(run_cli, "observation", "show", "--export", original_id)["records"] == [
        row()
    ]
    status = call(run_cli, "status")
    assert len(status["committed_observations"]) == 3
    assert status["plan_status"] == [
        {"plan_id": plan["id"], "state": "complete_nonempty"}
    ]


def test_overlapping_complete_range_never_hides_failed_requested_package(
    run_cli, installed
):
    from leaves.liquidity.test_cash_balances_cli import page

    _, browser, _ = installed
    plan = create(
        run_cli,
        "--windows",
        '[{"from":"2026-09-18","to":"2026-09-20"},{"from":"2026-09-19","to":"2026-09-19"}]',
    )
    browser.business_script.extend([page([]), {"status": 500, "body": {}}])
    code, output, _ = run_cli(["workflow", "export", "run", "--plan", plan["id"]])
    assert code == 1, output
    status = call(run_cli, "history", "show", "--plan", plan["id"])
    assert status["complete"] is False
    assert [p["state"] for p in status["packages"]] == ["complete_empty", "failed"]
    assert status["overlapping_packages"] == [
        [plan["packages"][0]["id"], plan["packages"][1]["id"]]
    ]
    assert status["current_history_effect"] == "separate_observations"


@pytest.mark.parametrize(
    "windows",
    [
        "[]",
        "{}",
        "bad-json",
        '[{"from":"2026-09-17","to":"2026-09-18"}]',
        '[{"from":"2026-09-20","to":"2026-09-19"}]',
        '[{"from":"2026-09-19","to":"2026-09-31"}]',
        '[{"from":"2026-09-19","to":"2026-09-19","extra":true}]',
    ],
)
def test_history_rejects_invalid_or_outside_windows_offline(
    run_cli, installed, windows
):
    _, browser, config = installed
    code, out, _ = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity.cash.balances",
            "--mode",
            "history",
            "--parameters",
            '{"account-alias":"ACCOUNT","from-date":"20260918","to-date":"20260920"}',
            "--windows",
            windows,
        ]
    )
    assert code == 2, out
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests
    assert not (config / "workflow/plans").exists()


def test_interruption_retains_completed_package_and_unqueried_tail(run_cli, installed):
    from leaves.liquidity.test_cash_balances_cli import page, row

    _, browser, _ = installed
    plan = create(
        run_cli,
        "--windows",
        '[{"from":"2026-09-18","to":"2026-09-18"},{"from":"2026-09-19","to":"2026-09-19"},{"from":"2026-09-20","to":"2026-09-20"}]',
    )

    def interrupted(body, _):
        if body["startDate"] == "20260919":
            raise KeyboardInterrupt
        return page([row()])

    browser.business_handler = interrupted
    code, output, _ = run_cli(["workflow", "export", "run", "--plan", plan["id"]])
    assert code == 130, output
    state = call(run_cli, "history", "show", "--plan", plan["id"])
    assert [item["state"] for item in state["packages"]] == [
        "complete_nonempty",
        "failed",
        "unqueried",
    ]
    assert state["packages"][1]["attempts"][0]["error"]["code"] == "INTERRUPTED"
    assert state["unqueried_ranges"] == [{"from": "2026-09-20", "to": "2026-09-20"}]
    browser.business_handler = lambda body, _: page([row(valueDate=body["startDate"])])
    resumed = call(run_cli, "export", "run", "--plan", plan["id"])
    assert resumed["complete"] is True
    assert len(browser.business_requests) == 4


def test_selected_package_exposes_incomplete_and_unqueried_separately(
    run_cli, installed
):
    from leaves.liquidity.test_cash_balances_cli import page, row

    _, browser, _ = installed
    plan = create(
        run_cli,
        "--windows",
        '[{"from":"2026-09-18","to":"2026-09-18"},{"from":"2026-09-19","to":"2026-09-20"}]',
    )
    browser.business_script.append(page([row()], total=2))
    code, out, _ = run_cli(
        [
            "workflow",
            "export",
            "run",
            "--plan",
            plan["id"],
            "--package",
            plan["packages"][0]["id"],
        ]
    )
    assert code == 1, out
    state = call(run_cli, "history", "show", "--plan", plan["id"])
    assert [item["state"] for item in state["packages"]] == ["incomplete", "unqueried"]
    assert state["unqueried_ranges"] == [{"from": "2026-09-19", "to": "2026-09-20"}]
    artifact = call(
        run_cli, "export", "show", "--export", state["packages"][0]["export_id"]
    )
    assert artifact["record_count"] == 1
    assert artifact["history_plan"] == plan["id"]
    assert artifact["native_range"] == {"from": "2026-09-18", "to": "2026-09-18"}
    code, out, _ = run_cli(
        [
            "workflow",
            "import",
            "plan",
            "--export",
            artifact["id"],
            "--action",
            "preserve",
        ]
    )
    assert code == 1, out
    assert len(browser.business_requests) == 1


def test_default_history_package_preserves_native_range_without_daily_stitching(
    run_cli, installed
):
    from leaves.liquidity.test_cash_balances_cli import page

    _, browser, _ = installed
    plan = create(run_cli)
    assert len(plan["packages"]) == 1
    browser.business_script.append(page([]))
    completed = call(run_cli, "export", "run", "--plan", plan["id"])
    assert completed["complete"] is True
    assert browser.business_requests[0]["startDate"] == "20260918"
    assert browser.business_requests[0]["endDate"] == "20260920"
    count = len(browser.business_requests)
    call(run_cli, "export", "run", "--plan", plan["id"])
    assert len(browser.business_requests) == count


def test_full_observation_needs_no_history_contract_or_date(run_cli, installed):
    _, browser, _ = installed
    code, output, _ = run_cli(
        ["plugins", "install", "bundled:liquidity.reference.entities"]
    )
    assert code == 0, output
    full = call(run_cli, "plan", "create", "--leaf", "liquidity.reference.entities")
    assert full["mode"] == "full"
    assert "contract" not in full and "cutoff" not in full
    code, output, _ = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity.reference.entities",
            "--mode",
            "history",
        ]
    )
    assert code == 2, output
    assert "no native history range contract" in json.loads(output)["error"]["message"]
    assert not browser.business_requests


def test_changed_native_time_contract_requires_new_plan_before_requests(
    run_cli, installed
):
    _, browser, config = installed
    plan = create(run_cli)
    adapter = config / "plugins/liquidity/cash.balances/leaf.json"
    adapter.write_text(
        adapter.read_text().replace(
            '"time_basis": "valueDate"', '"time_basis": "updateTime"'
        )
    )
    code, output, _ = run_cli(["workflow", "export", "run", "--plan", plan["id"]])
    assert code == 1, output
    assert not browser.business_requests
    status = call(run_cli, "history", "show", "--plan", plan["id"])
    assert status["packages"][0]["state"] == "failed"
    assert (
        "history contract changed"
        in status["packages"][0]["attempts"][0]["error"]["message"]
    )
