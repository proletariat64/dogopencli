"""Public leaf date codecs preserve accepted formats and native scope."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

CASES = [
    ("cash.balances", {"account_alias": ["ACCOUNT"]}, "compact"),
    (
        "cash.statements.end_of_day",
        {"entity": ["ENTITY"], "account_alias": ["ACCOUNT"], "currency": "USD"},
        "compact",
    ),
    (
        "cash.statements.intraday",
        {"inst_id": "ENTITY", "account_alias": "ACCOUNT", "currency": "USD"},
        "compact",
    ),
    (
        "forecast.account_cashflows",
        {"alias": "ACCOUNT", "entity": "ENTITY", "bank": "BANK"},
        "compact",
    ),
    (
        "forecast.account_demands",
        {"alias": "ACCOUNT", "entity": "ENTITY", "bank": "BANK"},
        "compact",
    ),
    (
        "forecast.account_demands_intraday",
        {"alias": "ACCOUNT", "entity": "ENTITY", "bank": "BANK"},
        "compact",
    ),
    ("forecast.account_t3", {"account_alias": "ACCOUNT"}, "compact"),
    ("forecast.cashflows", {"account_alias": "ACCOUNT", "currency": "USD"}, "compact"),
    ("investment.benchmark_values", {}, "iso"),
    ("investment.interest_rates", {"source": "market"}, "compact"),
    ("investment.quotes", {}, "compact"),
    ("investment.strategy_results", {"task_type": "FUND_DECISION_TASK"}, "iso"),
    ("operations.asset_trades", {}, "iso"),
    ("operations.fx_settlement_demands", {}, "iso"),
    ("operations.swaps", {}, "iso"),
]


def adapter(name):
    path = ROOT / "leaf_packages/liquidity" / name / "adapter.py"
    module_name = "calendar_" + name.replace(".", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module.adapter


@pytest.mark.parametrize("name,selectors,format_name", CASES)
def test_leaf_round_trip_preserves_leap_day_and_native_scope(
    name, selectors, format_name
):
    leaf = adapter(name)
    public_day = "20240229" if format_name == "compact" else "2024-02-29"
    parameters = {**selectors, "from_date": public_day, "to_date": public_day}
    original = dict(parameters)
    bounds = leaf.history_bounds(parameters)
    assert bounds == {"from": "2024-02-29", "to": "2024-02-29"}
    converted = leaf.history_parameters(bounds)
    assert set(converted) == {"from_date", "to_date"}
    assert leaf.scope({**selectors, **converted}) == leaf.scope(parameters)
    assert leaf.history_bounds({**selectors, **converted}) == bounds
    assert parameters == original


@pytest.mark.parametrize("name,selectors,format_name", CASES)
def test_installed_leaf_plans_iso_history_without_changing_public_date_format(
    run_cli, name, selectors, format_name
):
    source = ROOT / "leaf_packages/liquidity" / name
    code, output, error = run_cli(["plugins", "install", str(source)])
    assert code == 0, output + error
    day = "20240229" if format_name == "compact" else "2024-02-29"
    parameters = {key.replace("_", "-"): value for key, value in selectors.items()}
    parameters.update({"from-date": day, "to-date": day})
    code, output, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity." + name,
            "--mode",
            "history",
            "--parameters",
            json.dumps(parameters),
            "--windows",
            '[{"from":"2024-02-29","to":"2024-02-29"}]',
        ]
    )
    assert code == 0, output + error
    plan = json.loads(output)["data"]
    assert plan["desired_range"] == {"from": "2024-02-29", "to": "2024-02-29"}
    assert plan["contract"]["format"] == "%Y-%m-%d"
    assert plan["packages"][0]["range"] == {"from": "2024-02-29", "to": "2024-02-29"}
    for key, value in selectors.items():
        assert plan["packages"][0]["parameters"][key] == value


@pytest.mark.parametrize("source", ["market", "bank"])
def test_both_rate_sources_plan_their_declared_calendar_scope(run_cli, source):
    code, output, error = run_cli(
        [
            "plugins",
            "install",
            str(ROOT / "leaf_packages/liquidity/investment.interest_rates"),
        ]
    )
    assert code == 0, output + error
    code, output, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity.investment.interest_rates",
            "--mode",
            "history",
            "--parameters",
            json.dumps(
                {"source": source, "from-date": "2024-02-28", "to-date": "20240229"}
            ),
        ]
    )
    assert code == 0, output + error
    plan = json.loads(output)["data"]
    assert plan["desired_range"] == {"from": "2024-02-28", "to": "2024-02-29"}
    assert plan["packages"][0]["parameters"]["source"] == source


@pytest.mark.parametrize("source", ["expectation-rule", "expection"])
def test_rule_rate_sources_keep_full_planning_without_calendar_support(run_cli, source):
    code, output, error = run_cli(
        [
            "plugins",
            "install",
            str(ROOT / "leaf_packages/liquidity/investment.interest_rates"),
        ]
    )
    assert code == 0, output + error
    base = [
        "workflow",
        "plan",
        "create",
        "--leaf",
        "liquidity.investment.interest_rates",
        "--parameters",
        json.dumps({"source": source}),
    ]
    code, output, error = run_cli(base)
    assert code == 0, output + error
    assert json.loads(output)["data"]["mode"] == "full"
    code, output, error = run_cli([*base, "--mode", "history"])
    assert code != 0
    assert json.loads(output)["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "name,selectors,start,end,accepted",
    [
        (
            "forecast.account_demands_intraday",
            {"alias": "ACCOUNT", "entity": "ENTITY", "bank": "BANK"},
            "20240228",
            "20240229",
            False,
        ),
        ("operations.fx_settlement_demands", {}, "2024-01-01", "2024-02-01", True),
        ("operations.fx_settlement_demands", {}, "2024-01-01", "2024-02-02", False),
    ],
)
def test_native_window_limits_apply_before_history_transport(
    run_cli, name, selectors, start, end, accepted
):
    code, output, error = run_cli(
        ["plugins", "install", str(ROOT / "leaf_packages/liquidity" / name)]
    )
    assert code == 0, output + error
    parameters = {key.replace("_", "-"): value for key, value in selectors.items()}
    parameters.update({"from-date": start, "to-date": end})
    code, output, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity." + name,
            "--mode",
            "history",
            "--parameters",
            json.dumps(parameters),
        ]
    )
    assert (code == 0) is accepted, output + error
    if not accepted:
        assert json.loads(output)["error"]["code"] == "INVALID_ARGUMENT"
