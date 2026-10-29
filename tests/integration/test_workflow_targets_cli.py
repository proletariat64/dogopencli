"""Saved target intent and frozen execution through the public CLI."""

from test_workflow_cli import call
from test_workflow_history_cli import create

pytest_plugins = ["integration.leaves.liquidity.test_cash_balances_cli"]


def test_bounded_target_reuses_exact_saved_work_across_later_runs(
    run_cli, installed, monkeypatch
):
    from leaves.liquidity.test_cash_balances_cli import page

    from dogopencli import workflow

    _, browser, config = installed
    monkeypatch.setattr(workflow, "now", lambda: "2026-09-20T12:00:00+00:00")
    original = create(run_cli)
    target = call(run_cli, "target", "create", "--plan", original["id"])
    first = call(run_cli, "target", "plan", "--target", target["id"])
    assert first["plans"] == [original["id"]]
    browser.business_script.append(page([]))
    call(run_cli, "target", "run", "--execution", first["id"])
    monkeypatch.setattr(workflow, "now", lambda: "2026-10-29T12:00:00+00:00")
    later = call(run_cli, "target", "plan", "--target", target["id"])
    assert later["plans"] == [original["id"]]
    call(run_cli, "target", "run", "--execution", later["id"])
    assert len(browser.business_requests) == 1
    assert call(run_cli, "plan", "show", "--plan", original["id"]) == original
    before = {p: p.read_bytes() for p in config.rglob("*") if p.is_file()}
    status = call(run_cli, "target", "show", "--target", target["id"])
    assert status["target"] == target
    assert status["executions"][-1]["complete"] is True
    assert {p: p.read_bytes() for p in config.rglob("*") if p.is_file()} == before


def test_following_explicitly_freezes_cutoff_and_refreshes_lookback(
    run_cli, installed, monkeypatch
):
    from leaves.liquidity.test_cash_balances_cli import page

    from dogopencli import workflow

    _, browser, _ = installed
    monkeypatch.setattr(workflow, "now", lambda: "2026-09-20T12:00:00+00:00")
    original = create(run_cli)
    target = call(
        run_cli,
        "target",
        "create",
        "--plan",
        original["id"],
        "--policy",
        "following",
        "--timezone",
        "Asia/Shanghai",
        "--lookback-days",
        "2",
    )
    first = call(run_cli, "target", "plan", "--target", target["id"])
    assert first["cutoff"] == "20260920"
    monkeypatch.setattr(workflow, "now", lambda: "2026-09-22T12:00:00+00:00")
    browser.business_script.append(page([]))
    call(run_cli, "target", "run", "--execution", first["id"])
    assert browser.business_requests[-1]["endDate"] == "20260920"
    later = call(run_cli, "target", "plan", "--target", target["id"])
    assert later["cutoff"] == "20260922"
    native = call(run_cli, "plan", "show", "--plan", later["plans"][0])
    assert [p["range"] for p in native["packages"]] == [
        {"from": "20260921", "to": "20260922"}
    ]
    browser.business_script.append(page([]))
    call(run_cli, "target", "run", "--execution", later["id"])
    repeated = call(run_cli, "target", "plan", "--target", target["id"])
    refresh = call(run_cli, "plan", "show", "--plan", repeated["plans"][0])
    assert [p["range"] for p in refresh["packages"]] == [
        {"from": "20260921", "to": "20260922"}
    ]
    assert call(run_cli, "target", "show", "--target", target["id"])["target"] == target


def test_all_installed_enrollment_freezes_list_selection_and_keeps_limits_visible(
    run_cli, installed
):
    import json

    from leaves.liquidity.test_cash_balances_cli import page

    _, browser, _ = installed
    code, out, _ = run_cli(
        ["plugins", "install", "bundled:liquidity.reference.entities"]
    )
    assert code == 0, out
    target = call(run_cli, "target", "enroll", "--mode", "history")
    assert target["selection"] == "all-installed"
    assert {item["leaf"] for item in target["diagnostics"]} == {
        "liquidity.cash.balances",
        "liquidity.reference.entities",
    }
    assert any("date" in item["message"].lower() for item in target["diagnostics"]), (
        target
    )
    assert any(
        "no native history" in item["message"].lower() for item in target["diagnostics"]
    )
    configured = call(
        run_cli,
        "target",
        "enroll",
        "--mode",
        "history",
        "--scopes",
        '{"liquidity.cash.balances":{"account-alias":"ACCOUNT","from-date":"20260918","to-date":"20260920"}}',
    )
    execution = call(run_cli, "target", "plan", "--target", configured["id"])
    browser.business_script.append(page([]))
    code, output, _ = run_cli(
        ["workflow", "target", "run", "--execution", execution["id"]]
    )
    assert code == 1, output
    assert json.loads(output)["meta"]["execution"]["packages"][0]["complete"] is True
    before = call(run_cli, "target", "show", "--target", configured["id"])
    code, out, _ = run_cli(["plugins", "install", "bundled:payment.sla.baselines"])
    assert code == 0, out
    assert call(run_cli, "target", "show", "--target", configured["id"]) == before
    assert not any(
        p.get("leaf") == "payment.sla.baselines" for p in configured["diagnostics"]
    )
    repeated = call(run_cli, "target", "plan", "--target", configured["id"])
    assert repeated["plans"] == execution["plans"]
    count = len(browser.business_requests)
    code, _, _ = run_cli(["workflow", "target", "run", "--execution", repeated["id"]])
    assert code == 1
    assert len(browser.business_requests) == count


def test_enrolled_export_failures_keep_independent_success_and_status_offline(
    run_cli, installed
):
    import json

    from leaves.liquidity.test_cash_balances_cli import page

    from dogopencli.browser import cdp

    _, browser, config = installed
    code, out, _ = run_cli(
        ["plugins", "install", "bundled:liquidity.reference.entities"]
    )
    assert code == 0, out
    target = call(
        run_cli,
        "target",
        "enroll",
        "--scopes",
        '{"liquidity.cash.balances":{"account-alias":"ACCOUNT",'
        '"from-date":"20260918","to-date":"20260920"}}',
    )
    execution = call(run_cli, "target", "plan", "--target", target["id"])
    browser.business_script.extend(
        [
            {"status": 500, "body": {}},
            {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": 0,
                    "result": {"entityMaintVOList": []},
                },
            },
        ]
    )
    code, out, _ = run_cli(
        ["workflow", "target", "run", "--execution", execution["id"]]
    )
    assert code == 1, out
    result = json.loads(out)["meta"]["execution"]
    assert [p["complete"] for p in result["packages"]] == [False, True]
    successful_id = result["packages"][1]["last_successful_export"]["id"]
    browser.business_script.append(page([]))
    result = call(run_cli, "target", "run", "--execution", execution["id"])
    assert result["complete"] is True
    assert result["packages"][1]["last_successful_export"]["id"] == successful_id
    assert len(browser.business_requests) == 3
    prepared = call(
        run_cli, "import", "plan", "--export", successful_id, "--action", "preserve"
    )
    call(run_cli, "import", "apply", "--plan", prepared["id"])

    def offline(*args, **kwargs):
        raise AssertionError("Status must not authenticate")

    cdp.set_transport_factory(offline)
    before = {p: p.read_bytes() for p in config.rglob("*") if p.is_file()}
    status = call(run_cli, "status")
    assert status["targets"][0]["executions"][0]["complete"] is True
    assert status["committed_observations"][0]["export_id"] == successful_id
    assert status["committed_observations"][0]["record_count"] == 0
    code, out, _ = run_cli(["workflow", "target", "--help"])
    assert code == 0, out
    assert {p: p.read_bytes() for p in config.rglob("*") if p.is_file()} == before


def test_full_observation_following_freezes_each_explicit_refresh(
    run_cli, installed, monkeypatch
):
    from dogopencli import workflow

    _, browser, _ = installed
    code, out, _ = run_cli(
        ["plugins", "install", "bundled:liquidity.reference.entities"]
    )
    assert code == 0, out
    original = call(run_cli, "plan", "create", "--leaf", "liquidity.reference.entities")
    target = call(
        run_cli, "target", "create", "--plan", original["id"], "--policy", "following"
    )
    monkeypatch.setattr(workflow, "now", lambda: "2026-10-29T01:00:00+00:00")
    first = call(run_cli, "target", "plan", "--target", target["id"])
    monkeypatch.setattr(workflow, "now", lambda: "2026-10-29T02:00:00+00:00")
    second = call(run_cli, "target", "plan", "--target", target["id"])
    assert first["cutoff"] == "2026-10-29T01:00:00+00:00"
    assert second["cutoff"] == "2026-10-29T02:00:00+00:00"
    assert first["plans"] != second["plans"]
    assert first["coverage_basis"] == "full_observations"
    assert "desired_range" not in first
    for execution in (first, second):
        plan = call(run_cli, "plan", "show", "--plan", execution["plans"][0])
        assert plan["native_scope"] == original["native_scope"]
        assert plan["parameters"] == original["parameters"]
        browser.business_script.append(
            {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": 0,
                    "result": {"entityMaintVOList": []},
                },
            }
        )
        call(run_cli, "target", "run", "--execution", execution["id"])
    assert len(browser.business_requests) == 2
    call(run_cli, "target", "run", "--execution", first["id"])
    assert len(browser.business_requests) == 2


def test_enrollment_excludes_get_only_and_names_required_native_scope(
    run_cli, installed, tmp_path
):
    import json
    import shutil
    from pathlib import Path

    source = tmp_path / "get-only"
    bundled = (
        Path(__file__).resolve().parents[2]
        / "src/dogopencli/leaf_packages/payment/sla.baselines"
    )
    shutil.copytree(bundled, source)
    manifest = json.loads((source / "leaf.json").read_text())
    del manifest["operations"]["list"]
    del manifest["dataset"]
    del manifest["collection"]
    del manifest["operations"]["get"]["list_binding"]
    (source / "leaf.json").write_text(json.dumps(manifest))
    code, out, _ = run_cli(["plugins", "install", str(source)])
    assert code == 0, out
    target = call(run_cli, "target", "enroll")
    assert target["excluded"] == [
        {"leaf": "payment.sla.baselines", "reason": "Get-only dataset"}
    ]
    assert target["enrolled_leaves"] == ["liquidity.cash.balances"]
    assert target["diagnostics"][0]["leaf"] == "liquidity.cash.balances"
    assert "date" in target["diagnostics"][0]["message"].lower()


def test_following_retries_incomplete_interval_despite_newer_row_date(
    run_cli, installed, monkeypatch
):
    from leaves.liquidity.test_cash_balances_cli import page

    from dogopencli import workflow

    _, browser, _ = installed
    monkeypatch.setattr(workflow, "now", lambda: "2026-09-20T12:00:00+00:00")
    original = create(run_cli)
    target = call(
        run_cli,
        "target",
        "create",
        "--plan",
        original["id"],
        "--policy",
        "following",
        "--timezone",
        "UTC",
    )
    first = call(run_cli, "target", "plan", "--target", target["id"])
    # A native incomplete export is not successful interval evidence, even
    # when its maximum row date reaches the cutoff.
    browser.business_script.append(page([{"valueDate": "20260920"}], total=2))
    code, _, _ = run_cli(["workflow", "target", "run", "--execution", first["id"]])
    assert code == 1
    retry = call(run_cli, "target", "plan", "--target", target["id"])
    native = call(run_cli, "plan", "show", "--plan", retry["plans"][0])
    assert native["desired_range"] == {"from": "20260918", "to": "20260920"}
    browser.business_script.append(page([]))
    call(run_cli, "target", "run", "--execution", retry["id"])
    finished = call(run_cli, "target", "plan", "--target", target["id"])
    assert finished["plans"] == []
    count = len(browser.business_requests)
    assert call(run_cli, "target", "run", "--execution", finished["id"])["complete"]
    assert len(browser.business_requests) == count


def test_following_reuses_seed_history_and_preserves_interior_gap(
    run_cli, installed, monkeypatch
):
    from leaves.liquidity.test_cash_balances_cli import page

    from dogopencli import workflow

    _, browser, _ = installed
    monkeypatch.setattr(workflow, "now", lambda: "2026-09-20T12:00:00+00:00")
    original = create(
        run_cli,
        "--windows",
        '[{"from":"20260918","to":"20260918"},{"from":"20260920","to":"20260920"}]',
    )
    browser.business_script.extend([page([]), page([])])
    code, _, _ = run_cli(["workflow", "export", "run", "--plan", original["id"]])
    assert code == 1
    target = call(
        run_cli,
        "target",
        "create",
        "--plan",
        original["id"],
        "--policy",
        "following",
        "--timezone",
        "UTC",
    )
    frozen = call(run_cli, "target", "plan", "--target", target["id"])
    native = call(run_cli, "plan", "show", "--plan", frozen["plans"][0])
    assert native["desired_range"] == {"from": "20260919", "to": "20260919"}
    browser.business_script.append(page([]))
    assert call(run_cli, "target", "run", "--execution", frozen["id"])["complete"]
    assert [r["startDate"] for r in browser.business_requests] == [
        "20260918",
        "20260920",
        "20260919",
    ]
