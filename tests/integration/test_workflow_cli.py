"""Durable observation journeys at the public CLI and CDP boundaries."""

import json
import os
from pathlib import Path

import pytest

pytest_plugins = ["integration.test_leaf_pilots_cli"]


def call(run_cli, *args):
    code, out, _ = run_cli(["workflow", *args])
    assert code == 0, out
    return json.loads(out)["data"]


def test_plan_and_status_are_offline_and_write_only_plan_state(run_cli, pilots):
    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    assert plan["parameters"] == {}
    assert plan["mode"] == "full"
    assert call(run_cli, "plan", "show", "--plan", plan["id"]) == plan
    status = call(run_cli, "status")
    assert status["plans"][0]["id"] == plan["id"]
    assert status["exports"] == []
    for path, content in before.items():
        assert path.read_bytes() == content
    assert not pilots.business_requests


def payment_page(rows):
    return {
        "status": 200,
        "body": {
            "success": True,
            "pageNo": 0,
            "pageSize": 10000,
            "totalCount": len(rows),
            "resultDataList": rows,
        },
    }


def test_export_retains_full_exact_records_before_preview_and_survives_later_exports(
    run_cli, pilots
):
    rows = [
        {"id": str(i), "amount": "0.000000000000000001", "nested": [False, {"x": None}]}
        for i in range(103)
    ]
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    pilots.business_script.append(payment_page(rows))
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        "--limit",
        "1",
        "--fields",
        "id",
    )
    assert exported["records"] == [{"id": "0"}]
    saved = call(run_cli, "export", "show", "--export", exported["id"])
    assert saved["records"] == rows
    assert saved["record_count"] == 103
    assert saved["state"] == "complete_nonempty"
    pilots.business_script.append(payment_page([]))
    empty = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    assert empty["state"] == "complete_empty"
    assert call(run_cli, "export", "show", "--export", exported["id"]) == saved


def test_import_preserves_exact_observations_offline_and_replay_is_noop(
    run_cli, pilots
):
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    rows = [{"id": "one", "nested": {"amount": "1.0000000000000000001"}}]
    pilots.business_script.append(payment_page(rows))
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    import_plan = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    assert import_plan["existing_count"] == 0
    assert import_plan["new_count"] == 1
    assert import_plan["current_effect"] == "unchanged"
    pilots.business_script.append(payment_page([]))
    call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    config_file = Path(os.environ["DOGOPENCLI_CONFIG"])
    adapter = config_file.parent / "plugins/payment/sla.baselines/adapter.py"
    adapter.write_text('raise RuntimeError("Later adapter is unavailable")')
    config_file.write_text(
        config_file.read_text() + '\n[duckdog]\npath="later-missing.duckdb"\n'
    )
    from dogopencli.browser import cdp

    def offline(*args, **kwargs):
        raise AssertionError("Import must be offline")

    cdp.set_transport_factory(offline)
    applied = call(run_cli, "import", "apply", "--plan", import_plan["id"])
    assert applied["inserted_count"] == 1
    stored = call(run_cli, "observation", "show", "--export", exported["id"])
    assert stored["records"] == rows
    assert stored["scope"] == exported["metadata"]["scope"]
    regenerated = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    assert regenerated["new_count"] == 0
    assert (
        call(run_cli, "import", "apply", "--plan", regenerated["id"])["replayed"]
        is True
    )
    assert call(run_cli, "observation", "show", "--export", exported["id"]) == stored
    status = call(run_cli, "status")
    assert status["committed_observations"][0]["export_id"] == exported["id"]
    assert status["committed_observations"][0]["record_count"] == 1


def test_incomplete_and_failed_attempts_do_not_hide_last_success_or_import(
    run_cli, pilots, monkeypatch
):
    from datetime import datetime, timedelta, timezone

    from dogopencli import workflow

    ticks = iter(range(100))
    monkeypatch.setattr(
        workflow,
        "now",
        lambda: (
            datetime(2026, 10, 29, tzinfo=timezone.utc) + timedelta(seconds=next(ticks))
        ).isoformat(),
    )
    plan = call(run_cli, "plan", "create", "--leaf", "collection.cost")
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": 0,
                "resultDataList": [],
            },
        }
    )
    complete = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    empty_plan = call(
        run_cli, "import", "plan", "--export", complete["id"], "--action", "preserve"
    )
    assert (
        call(run_cli, "import", "apply", "--plan", empty_plan["id"])["inserted_count"]
        == 0
    )
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": 1001,
                "resultDataList": [
                    {"itemId": "one", "itemType": "FUND_IN_CHANNEL_TRANS_FEE"}
                ],
            },
        }
    )
    partial = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    assert partial["state"] == "incomplete"
    code, out, _ = run_cli(
        [
            "workflow",
            "import",
            "plan",
            "--export",
            partial["id"],
            "--action",
            "preserve",
        ]
    )
    assert code == 1 and json.loads(out)["error"]["code"] == "WORKFLOW_ERROR"
    pilots.business_script.append({"status": 401, "body": {}})
    code, out, _ = run_cli(
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
    assert status["latest_attempt"]["state"] == "failed"
    assert status["last_successful_export"]["id"] == complete["id"]
    assert status["committed_observations"][0]["export_id"] == complete["id"]
    assert (
        call(run_cli, "observation", "show", "--export", complete["id"])["records"]
        == []
    )


def test_plan_reuses_native_semantic_validation_without_browser(run_cli, pilots):
    from dogopencli.domain_contracts import FX_STARTUP_URL

    pilots.href = FX_STARTUP_URL
    code, out, _ = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "fx.trade",
            "--parameters",
            '{"from-time":"bad-date"}',
        ]
    )
    assert code == 2, out
    assert not pilots.business_requests


def test_distinct_exports_preserve_equal_rows_and_decimal_values(
    run_cli, tmp_path, monkeypatch
):
    from decimal import Decimal

    from fake_cdp import FakeBrowser
    from leaves.liquidity.test_cash_balances_cli import page, row

    from dogopencli.browser import cdp
    from dogopencli.jsonutil import parse

    config = tmp_path / "config.toml"
    config.write_text(
        f'[auth]\nprofile="{tmp_path / "chrome"}"\ncdp_url="http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    browser = FakeBrowser(
        href="https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    )
    cdp.set_transport_factory(browser.transport)
    try:
        source = (
            Path(__file__).resolve().parents[2]
            / "leaf_packages/liquidity/cash.balances"
        )
        code, out, _ = run_cli(["plugins", "install", str(source)])
        assert code == 0, out
        plan = call(
            run_cli,
            "plan",
            "create",
            "--leaf",
            "liquidity.cash.balances",
            "--parameters",
            '{"account-alias":"ACCOUNT","from-date":"20260918","to-date":"20260918"}',
        )
        native_row = row(unknown={"precise": Decimal("123.000000000000000001")})
        for _ in range(2):
            browser.business_script.append(page([native_row]))
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
                "preserve",
            )
            assert prepared["new_count"] == 1
            call(run_cli, "import", "apply", "--plan", prepared["id"])
            code, output, _ = run_cli(
                ["workflow", "observation", "show", "--export", exported["id"]]
            )
            assert code == 0, output
            assert parse(output)["data"]["records"] == [native_row]
        status = call(run_cli, "status")
        assert (
            sum(item["record_count"] for item in status["committed_observations"]) == 2
        )
    finally:
        cdp.set_transport_factory(None)


def test_import_rejects_changed_exact_input_and_preserves_committed_observations(
    run_cli, pilots
):
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    rows = [{"id": "stable", "amount": "1.0000"}]
    pilots.business_script.append(payment_page(rows))
    first = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    first_import = call(
        run_cli, "import", "plan", "--export", first["id"], "--action", "preserve"
    )
    call(run_cli, "import", "apply", "--plan", first_import["id"])
    pilots.business_script.append(payment_page([{"id": "new"}]))
    second = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    prepared = call(
        run_cli, "import", "plan", "--export", second["id"], "--action", "preserve"
    )
    path = (
        Path(os.environ["DOGOPENCLI_CONFIG"]).parent
        / "workflow/exports"
        / second["id"]
        / "records.json"
    )
    original = path.read_text()
    value = json.loads(original)
    value[0]["id"] = "changed"
    path.write_text(json.dumps(value))
    code, output, _ = run_cli(["workflow", "import", "apply", "--plan", prepared["id"]])
    assert code == 1 and json.loads(output)["error"]["code"] == "WORKFLOW_ERROR"
    assert (
        call(run_cli, "observation", "show", "--export", first["id"])["records"] == rows
    )
    assert len(call(run_cli, "status")["committed_observations"]) == 1
    path.write_text(original)
    assert (
        call(run_cli, "import", "apply", "--plan", prepared["id"])["inserted_count"]
        == 1
    )


def test_transaction_failure_retains_current_rows_and_no_partial_observation(
    run_cli, pilots
):
    import duckdb

    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    pilots.business_script.append(payment_page([{"id": "stable"}]))
    first = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    prepared = call(
        run_cli, "import", "plan", "--export", first["id"], "--action", "preserve"
    )
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    database = plan["binding"]["database"]
    relation = plan["binding"]["relation"]
    with duckdb.connect(database) as db:
        db.execute(f'INSERT INTO "{relation}" VALUES (?)', ['{"id":"current"}'])
        # A local storage constraint fails after the batch receipt INSERT.
        db.execute(
            "CREATE UNIQUE INDEX reject_extra_row ON "
            "_dogopencli_observation_rows(ordinal)"
        )
    pilots.business_script.append(payment_page([{"id": "later"}]))
    second = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    prepared = call(
        run_cli, "import", "plan", "--export", second["id"], "--action", "preserve"
    )
    code, out, _ = run_cli(["workflow", "import", "apply", "--plan", prepared["id"]])
    assert code == 1 and json.loads(out)["error"]["code"] == "WORKFLOW_ERROR"
    assert call(run_cli, "observation", "show", "--export", first["id"])["records"] == [
        {"id": "stable"}
    ]
    assert len(call(run_cli, "status")["committed_observations"]) == 1
    code, _, _ = run_cli(["workflow", "observation", "show", "--export", second["id"]])
    assert code == 1
    with duckdb.connect(database, read_only=True) as db:
        assert db.execute(f'SELECT _record FROM "{relation}"').fetchall() == [
            ('{"id":"current"}',)
        ]


def test_import_rejects_foreign_destination_ownership(run_cli, pilots):
    import duckdb

    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    pilots.business_script.append(payment_page([{"id": "one"}]))
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    with duckdb.connect(plan["binding"]["database"]) as db:
        db.execute(
            "UPDATE _dogopencli_leaf_ownership SET leaf_id='foreign.owner' "
            "WHERE relation_name=?",
            [plan["binding"]["relation"]],
        )
    code, out, _ = run_cli(["workflow", "import", "apply", "--plan", prepared["id"]])
    assert code == 1 and json.loads(out)["error"]["code"] == "WORKFLOW_ERROR"
    with duckdb.connect(plan["binding"]["database"], read_only=True) as db:
        assert not db.execute(
            "SELECT 1 FROM information_schema.tables WHERE "
            "table_name='_dogopencli_observations'"
        ).fetchone()


def test_import_preserves_repeated_native_cashflow_occurrences(run_cli, pilots):
    from decimal import Decimal

    from leaves.liquidity.test_forecast_accuracy_cli import base, details, metric, row

    from dogopencli.jsonutil import parse

    pilots.href = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    source = (
        Path(__file__).resolve().parents[2]
        / "leaf_packages/liquidity/forecast.accuracy"
    )
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 0, output
    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.forecast.accuracy",
        "--parameters",
        '{"account-alias":"ACCOUNT","record-date":"2026-03-08"}',
    )
    occurrence = {
        "cashFlowAmount": {
            "amount": Decimal("1.234567890123456789"),
            "currency": "USD",
        },
        "unknown": [None, False],
    }
    pilots.business_script.extend(
        [base([row()]), metric(), details([occurrence] * 103)]
    )
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        "--fields",
        "id",
    )
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    code, output, _ = run_cli(
        ["workflow", "observation", "show", "--export", exported["id"]]
    )
    assert code == 0, output
    assert parse(output)["data"]["records"][0]["cashflow_details"] == [occurrence] * 103


def test_durable_get_preserves_declared_root_before_projection(run_cli, pilots):
    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "payment.sla.baselines",
        "--operation",
        "get",
        "--identity",
        "one",
    )
    assert not pilots.business_requests
    root = {"id": "one", "nested": [False, {"amount": "1.000000000000000001"}]}
    pilots.business_script.append(
        {"status": 200, "body": {"success": True, "resultData": root}}
    )
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        "--fields",
        "id",
    )
    saved = call(run_cli, "export", "show", "--export", exported["id"])
    assert saved["records"] == [root]
    assert saved["operation"] == "get"
    assert saved["metadata"]["detail_scope"] == "native_root"
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    assert call(run_cli, "observation", "show", "--export", exported["id"])[
        "records"
    ] == [root]


def test_durable_list_detail_composes_all_rows_before_preview(run_cli, pilots):
    plan = call(
        run_cli, "plan", "create", "--leaf", "payment.sla.baselines", "--with-detail"
    )
    pilots.business_script.extend(
        [
            payment_page([{"id": "one"}, {"id": "two"}]),
            {
                "status": 200,
                "body": {
                    "success": True,
                    "resultData": {"id": "one", "value": [False]},
                },
            },
            {
                "status": 200,
                "body": {"success": True, "resultData": {"id": "two", "value": [None]}},
            },
        ]
    )
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        "--limit",
        "1",
        "--fields",
        "id",
    )
    saved = call(run_cli, "export", "show", "--export", exported["id"])
    assert saved["records"] == [
        {"record": {"id": "one"}, "detail": {"id": "one", "value": [False]}},
        {"record": {"id": "two"}, "detail": {"id": "two", "value": [None]}},
    ]
    assert len(exported["records"]) == 1
    assert saved["metadata"]["with_detail"] is True


def test_get_publication_cannot_replace_wider_list_current_scope(run_cli, pilots):
    list_plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    rows = [{"id": "one"}, {"id": "two"}]
    pilots.business_script.append(payment_page(rows))
    listed = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", list_plan["id"])["id"],
    )
    publication = call(
        run_cli, "import", "plan", "--export", listed["id"], "--action", "replace-full"
    )
    call(run_cli, "import", "apply", "--plan", publication["id"])
    get_plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "payment.sla.baselines",
        "--operation",
        "get",
        "--identity",
        "one",
    )
    pilots.business_script.append(
        {
            "status": 200,
            "body": {"success": True, "resultData": {"id": "one", "detail": True}},
        }
    )
    detail = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", get_plan["id"])["id"],
    )
    publication = call(
        run_cli, "import", "plan", "--export", detail["id"], "--action", "replace-full"
    )
    call(run_cli, "import", "apply", "--plan", publication["id"])
    assert call(run_cli, "current", "show", "--export", listed["id"])["records"] == rows
    assert call(run_cli, "current", "show", "--export", detail["id"])["records"] == [
        {"id": "one", "detail": True}
    ]


@pytest.mark.parametrize("change", ["endpoint", "binding", "parameters"])
def test_saved_list_detail_rejects_changed_detail_contract_before_queries(
    run_cli, pilots, change
):
    plan = call(
        run_cli, "plan", "create", "--leaf", "payment.sla.baselines", "--with-detail"
    )
    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    plugin = root / "plugins/payment/sla.baselines"
    if change == "endpoint":
        adapter = plugin / "adapter.py"
        adapter.write_text(
            adapter.read_text().replace(
                "/api/fundOutSlaBaseline/getFundOutSlaBaselineDetail",
                "/api/fundOutSlaBaseline/getFundOutSlaBaselineDetailChanged",
            )
        )
    else:
        path = plugin / "leaf.json"
        manifest = json.loads(path.read_text())
        if change == "binding":
            manifest["operations"]["get"]["list_binding"]["identity_field"] = "other_id"
        else:
            manifest["operations"]["get"]["parameters"] = [
                {
                    "name": "view",
                    "type": "string",
                    "required": False,
                    "default": "new",
                    "description": "Native detail view.",
                }
            ]
        path.write_text(json.dumps(manifest))
    pilots.business_script.append(payment_page([]))
    code, output, _ = run_cli(
        [
            "workflow",
            "export",
            "run",
            "--run",
            call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        ]
    )
    assert code != 0, output
    assert "detail" in json.loads(output)["error"]["message"].lower()
    assert not pilots.business_requests
    assert call(run_cli, "plan", "show", "--plan", plan["id"]) == plan
