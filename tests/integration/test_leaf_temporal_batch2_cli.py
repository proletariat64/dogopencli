"""Batch2 temporal leaf declarations through installed public CLI."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POOLS = (
    "cash.notional_pool_reports",
    "cash.physical_pool_reports",
    "cash.sweeping_reports",
)


def install(run_cli, name, domain="liquidity"):
    root = (
        ROOT / "leaf_packages" / domain / name
        if domain == "liquidity"
        else ROOT / "src/dogopencli/leaf_packages" / domain / name
    )
    code, out, error = run_cli(["plugins", "install", str(root)])
    assert code == 0, out + error


@pytest.mark.parametrize("name", POOLS)
def test_pool_calendar_history_preserves_month_end_and_native_parameters(run_cli, name):
    install(run_cli, name)
    params = {"from-date": "2026-01-31", "to-date": "2026-02-27", "timezone": "GMT+08"}
    args = [
        "workflow",
        "plan",
        "create",
        "--leaf",
        "liquidity." + name,
        "--mode",
        "history",
        "--parameters",
        json.dumps(params),
    ]
    code, out, error = run_cli(args)
    assert code == 0, out + error
    plan = json.loads(out)["data"]
    assert plan["desired_range"] == {"from": "2026-01-31", "to": "2026-02-27"}
    assert plan["native_scope"]["valueDateStart"] == "20260131"
    assert plan["native_scope"]["valueDateEnd"] == "20260227"
    params["to-date"] = "2026-02-28"
    code, out, error = run_cli([*args[:-1], json.dumps(params)])
    assert code == 2, out + error
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    code, out, error = run_cli(
        [
            "liquidity",
            "list",
            name,
            "--start-date",
            "2026-01-31",
            "--end-date",
            "2026-02-27",
            "--live",
        ]
    )
    assert code == 2, out + error


def test_forecast_calendar_axis_freezes_daily_clock_defaults(run_cli):
    install(run_cli, "forecast.results")
    params = {"from-date": "20261015", "to-date": "2026-10-16"}
    code, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity.forecast.results",
            "--mode",
            "history",
            "--parameters",
            json.dumps(params),
        ]
    )
    assert code == 0, out + error
    plan = json.loads(out)["data"]
    assert plan["parameters"]["record_from_time"] == "000000"
    assert plan["parameters"]["record_to_time"] == "235959"
    assert plan["contract"]["time_basis"] == "valueDate"
    assert plan["packages"][0]["native_scope"]["recordStartTime"] == "000000"
    assert plan["packages"][0]["native_scope"]["recordEndTime"] == "235959"


@pytest.mark.parametrize(
    "name,params,expected",
    [
        (
            "operations.automatic_tasks",
            {"from-time": "2026-10-16T09:00:00", "to-time": "2026-10-16T09:00:01"},
            {"from": "2026-10-16T01:00:00.000Z", "to": "2026-10-16T01:00:01.000Z"},
        ),
        (
            "operations.rule_status",
            {
                "from-time": "2026-10-16T09:00:00+08:00",
                "to-time": "2026-10-16T09:00:00+08:00",
            },
            {"from": "2026-10-16T01:00:00.000Z", "to": "2026-10-16T01:00:00.999Z"},
        ),
        (
            "risk.account_outflow",
            {
                "from-time": "2026-10-16T09:00:00.123+08:00",
                "to-time": "2026-10-16T01:00:01.001Z",
            },
            {"from": "2026-10-16T01:00:00.123Z", "to": "2026-10-16T01:00:01.001Z"},
        ),
    ],
)
def test_instant_leaves_declare_exact_effective_bounds(run_cli, name, params, expected):
    install(run_cli, name)
    code, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity." + name,
            "--mode",
            "history",
            "--parameters",
            json.dumps(params),
        ]
    )
    assert code == 0, out + error
    plan = json.loads(out)["data"]
    assert plan["desired_range"] == expected
    assert plan["contract"]["interpretation"] == "instant"


def test_fx_mixed_date_and_millisecond_bounds_have_one_public_parameter_pair(run_cli):
    install(run_cli, "trade", "fx")
    params = {"from-time": "2026-10-16", "to-time": "2026-10-17T09:30:00.123+08:00"}
    code, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "fx.trade",
            "--mode",
            "history",
            "--parameters",
            json.dumps(params),
        ]
    )
    assert code == 0, out + error
    plan = json.loads(out)["data"]
    assert plan["desired_range"] == {
        "from": "2026-10-15T16:00:00.000Z",
        "to": "2026-10-17T01:30:00.123Z",
    }
    assert set(plan["parameters"]) >= {"from_time", "to_time"}
    code, out, error = run_cli(
        [
            "fx",
            "list",
            "trade",
            "--transact-from",
            "2026-10-16",
            "--transact-to",
            "2026-10-16",
            "--live",
        ]
    )
    assert code == 2, out + error


@pytest.mark.parametrize(
    "params",
    [
        {"trade-id": ["ID"], "bcode": ["B1"]},
        {"trade-id": ["ID"], "customer-id": ["CUSTOMER"]},
        {"trade-id": ["ID"], "scene": "SCENE"},
        {"bcode": ["ANY"]},
    ],
)
def test_fx_freeze_does_not_make_invalid_original_scope_valid(run_cli, params):
    install(run_cli, "trade", "fx")
    code, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "fx.trade",
            "--parameters",
            json.dumps(params),
        ]
    )
    assert code == 2, out + error
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("params", [{}, {"bcode": ["B1"]}])
def test_fx_yesterday_defaults_materialize_before_full_plan_persistence(
    run_cli, params
):
    install(run_cli, "trade", "fx")
    code, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "fx.trade",
            "--parameters",
            json.dumps(params),
        ]
    )
    assert code == 0, out + error
    plan = json.loads(out)["data"]
    assert plan["parameters"]["from_time"].endswith("T16:00:00.000Z")
    assert plan["parameters"]["to_time"].endswith("T15:59:59.999Z")
    native = plan["native_scope"]["transactTimeRange"]
    assert native["end"] - native["start"] == 86399999
    code, out, error = run_cli(["workflow", "plan", "show", "--plan", plan["id"]])
    assert code == 0, out + error
    assert json.loads(out)["data"]["parameters"] == plan["parameters"]


def test_fx_id_only_full_inquiry_remains_without_time_range(run_cli):
    install(run_cli, "trade", "fx")
    params = {"trade-id": ["ID"]}
    args = [
        "workflow",
        "plan",
        "create",
        "--leaf",
        "fx.trade",
        "--parameters",
        json.dumps(params),
    ]
    code, out, error = run_cli(args)
    assert code == 0, out + error
    plan = json.loads(out)["data"]
    assert plan["native_scope"] == {"uniqueIds": ["ID"]}
    assert "from_time" not in plan["parameters"] and "to_time" not in plan["parameters"]
    code, out, error = run_cli([*args, "--mode", "history"])
    assert code == 2, out + error


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-16T01:00:00.1234Z",
        "2026-10-16T01:00:00-00:00",
        "2026-10-16T01:00:00.123",
        "2026-10-16T01:00:00+24:00",
    ],
)
def test_fx_rejects_unrepresentable_public_instants(run_cli, value):
    install(run_cli, "trade", "fx")
    params = {"from-time": value, "to-time": "2026-10-17T00:00:00Z"}
    code, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "fx.trade",
            "--parameters",
            json.dumps(params),
        ]
    )
    assert code == 2, out + error


@pytest.mark.parametrize(
    "upper,expected",
    [
        ("2026-10-16", "2026-10-16T15:59:59.999Z"),
        ("2026-10-16T01:00:01Z", "2026-10-16T01:00:01.000Z"),
        ("2026-10-16T01:00:01.1Z", "2026-10-16T01:00:01.100Z"),
        ("2026-10-16T01:00:01.12Z", "2026-10-16T01:00:01.120Z"),
    ],
)
def test_fx_date_expands_but_explicit_upper_instant_remains_exact(
    run_cli, upper, expected
):
    install(run_cli, "trade", "fx")
    params = {"from-time": "2026-10-16", "to-time": upper}
    code, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "fx.trade",
            "--mode",
            "history",
            "--parameters",
            json.dumps(params),
        ]
    )
    assert code == 0, out + error
    assert json.loads(out)["data"]["desired_range"]["to"] == expected


@pytest.mark.parametrize(
    "name,params,window",
    [
        (
            "operations.automatic_tasks",
            {"from-time": "2026-10-16T09:00:00", "to-time": "2026-10-16T09:00:01"},
            {"from": "2026-10-16T01:00:00.000Z", "to": "2026-10-16T01:00:00.500Z"},
        ),
        (
            "operations.rule_status",
            {"from-time": "2026-10-16T01:00:00Z", "to-time": "2026-10-16T01:00:01Z"},
            {"from": "2026-10-16T01:00:00.000Z", "to": "2026-10-16T01:00:00.000Z"},
        ),
    ],
)
def test_whole_second_native_scopes_reject_unrepresentable_sdk_windows(
    run_cli, name, params, window
):
    install(run_cli, name)
    code, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity." + name,
            "--mode",
            "history",
            "--parameters",
            json.dumps(params),
            "--windows",
            json.dumps([window]),
        ]
    )
    assert code == 2, out + error
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_outflow_rejects_unknown_offset_before_plan(run_cli):
    install(run_cli, "risk.account_outflow")
    code, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity.risk.account_outflow",
            "--parameters",
            json.dumps(
                {
                    "from-time": "2026-10-16T00:00:00-00:00",
                    "to-time": "2026-10-16T01:00:00Z",
                }
            ),
        ]
    )
    assert code == 2, out + error


def test_forecast_calendar_packages_keep_explicit_daily_clock_filter(run_cli):
    install(run_cli, "forecast.results")
    params = {
        "from-date": "20261015",
        "to-date": "20261016",
        "record-from-time": "08:00:00",
        "record-to-time": "090000",
    }
    windows = [
        {"from": "2026-10-15", "to": "2026-10-15"},
        {"from": "2026-10-16", "to": "2026-10-16"},
    ]
    code, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity.forecast.results",
            "--mode",
            "history",
            "--parameters",
            json.dumps(params),
            "--windows",
            json.dumps(windows),
        ]
    )
    assert code == 0, out + error
    plan = json.loads(out)["data"]
    for package in plan["packages"]:
        assert package["parameters"]["record_from_time"] == "08:00:00"
        assert package["parameters"]["record_to_time"] == "090000"
        assert package["native_scope"]["recordStartTime"] == "080000"
        assert package["native_scope"]["recordEndTime"] == "090000"
