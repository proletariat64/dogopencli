"""Frozen acquisition gaps repaired through public independent stages."""

from test_workflow_cli import call
from test_workflow_history_cli import create

pytest_plugins = ["integration.leaves.liquidity.test_cash_balances_cli"]


def test_repair_freezes_baseline_and_imports_exact_disjoint_results_offline(
    run_cli, installed
):
    from leaves.liquidity.test_cash_balances_cli import page, row

    _, browser, config = installed
    baseline = create(
        run_cli,
        "--windows",
        '[{"from":"20260918","to":"20260918"},{"from":"20260920","to":"20260920"}]',
    )
    browser.business_script.extend([page([row()]), page([])])
    code, _, _ = run_cli(["workflow", "export", "run", "--plan", baseline["id"]])
    assert code == 1
    before = {path: path.read_bytes() for path in (config / "workflow").rglob("*.json")}
    repair = call(run_cli, "repair", "plan", "--plan", baseline["id"])
    assert repair["baseline_gaps"] == [{"from": "20260919", "to": "20260919"}]
    assert len(repair["packages"]) == 1
    assert repair["packages"][0]["parameters"]["account_alias"] == ["ACCOUNT"]
    browser.business_script.append(page([row(valueDate="20260919")]))
    repaired = call(run_cli, "export", "run", "--plan", repair["id"])
    assert repaired["complete"] is True
    assert len(repaired["selected_exports"]) == 3
    assert all(path.read_bytes() == content for path, content in before.items())
    count = len(browser.business_requests)
    prepared = call(
        run_cli, "import", "plan", "--repair", repair["id"], "--action", "preserve"
    )
    imported = call(run_cli, "import", "apply", "--plan", prepared["id"])
    assert len(imported["receipts"]) == 3
    replay = call(run_cli, "import", "apply", "--plan", prepared["id"])
    assert all(item["replayed"] for item in replay["receipts"])
    assert len(browser.business_requests) == count
    stored = [
        call(run_cli, "observation", "show", "--export", identity)["records"]
        for identity in prepared["export_ids"]
    ]
    assert sum(map(len, stored)) == 2
    status_before = {
        path: path.read_bytes() for path in config.rglob("*") if path.is_file()
    }
    status = call(run_cli, "repair", "show", "--repair", repair["id"])
    assert status["baseline_gaps"] == [{"from": "20260919", "to": "20260919"}]
    assert status["uncovered_ranges"] == []
    assert {
        path: path.read_bytes() for path in config.rglob("*") if path.is_file()
    } == status_before
    assert call(run_cli, "status")["repairs"][0]["complete"] is True


def test_repair_retries_failed_gap_without_requerying_baseline_success(
    run_cli, installed
):
    from leaves.liquidity.test_cash_balances_cli import page, row

    _, browser, _ = installed
    baseline = create(run_cli, "--windows", '[{"from":"20260920","to":"20260920"}]')
    browser.business_script.append(page([]))
    run_cli(["workflow", "export", "run", "--plan", baseline["id"]])
    repair = call(run_cli, "repair", "plan", "--plan", baseline["id"])
    assert repair["baseline_gaps"] == [{"from": "20260918", "to": "20260919"}]
    browser.business_script.append({"status": 500, "body": {}})
    code, _, _ = run_cli(["workflow", "export", "run", "--plan", repair["id"]])
    assert code == 1
    code, output, _ = run_cli(
        ["workflow", "import", "plan", "--repair", repair["id"], "--action", "preserve"]
    )
    assert code == 2, output
    browser.business_script.append(page([row()]))
    completed = call(run_cli, "export", "run", "--plan", repair["id"])
    assert completed["complete"] is True
    assert len(completed["packages"][0]["attempts"]) == 2
    assert len(browser.business_requests) == 3


def test_full_repair_retries_new_capture_without_stitching_incomplete_rows(
    run_cli, installed
):
    from leaves.liquidity.test_cash_balances_cli import page, row

    _, browser, _ = installed
    baseline = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.cash.balances",
        "--parameters",
        '{"account-alias":"ACCOUNT","from-date":"20260918","to-date":"20260918"}',
    )
    browser.business_script.append(page([row()], total=2))
    original = call(run_cli, "export", "run", "--plan", baseline["id"])
    assert original["state"] == "incomplete"
    repair = call(run_cli, "repair", "plan", "--plan", baseline["id"])
    browser.business_script.append(page([]))
    repaired = call(run_cli, "export", "run", "--plan", repair["id"])
    assert repaired["complete"] is True
    selected = repaired["selected_exports"]
    assert len(selected) == 1
    assert selected[0]["export_id"] != original["id"]
    result = call(run_cli, "export", "show", "--export", selected[0]["export_id"])
    assert result["state"] == "complete_empty"
    assert result["records"] == []
    assert result["repair_plan"] == repair["id"]
    assert call(run_cli, "export", "show", "--export", original["id"])["records"] == [
        row()
    ]


def test_ambiguous_overlapping_baseline_cannot_select_a_repair(run_cli, installed):
    from leaves.liquidity.test_cash_balances_cli import page

    _, browser, _ = installed
    baseline = create(
        run_cli,
        "--windows",
        '[{"from":"20260918","to":"20260918"},{"from":"20260918","to":"20260918"}]',
    )
    browser.business_script.extend([page([]), page([])])
    run_cli(["workflow", "export", "run", "--plan", baseline["id"]])
    code, output, _ = run_cli(["workflow", "repair", "plan", "--plan", baseline["id"]])
    assert code == 2
    assert "overlapping baseline" in output
