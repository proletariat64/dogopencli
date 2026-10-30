"""Executable calendar sample and unchanged full-observation packages."""

from pathlib import Path

import pytest

from dogopencli.leaves.package import validate_package

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools/leaf-dev/example-history"
pytest_plugins = ["integration.test_leaf_handbook"]

# Explicit source-audit scope: no temporal enrollment is required for these leaves.
FULL_OBSERVATION_LEAVES = (
    "collection.account_isolation",
    "collection.card_template",
    "collection.clearing_system",
    "collection.cost",
    "collection.sla.configs",
    "collection.va.capacity",
    "collection.va.rules",
    "liquidity.cash.accounts",
    "liquidity.cash.credit_lines",
    "liquidity.cash.credit_usage",
    "liquidity.cash.group_balances",
    "liquidity.cash.pool_balances",
    "liquidity.cash.pools",
    "liquidity.cash.waterlevels",
    "liquidity.forecast.adjustments",
    "liquidity.investment.benchmarks",
    "liquidity.investment.compound_ledger",
    "liquidity.investment.products",
    "liquidity.investment.transactions",
    "liquidity.network.account_capabilities",
    "liquidity.network.realtime",
    "liquidity.operations.account_strategies",
    "liquidity.operations.decisions.history",
    "liquidity.operations.forwards",
    "liquidity.operations.prefunds",
    "liquidity.operations.strategy_rules",
    "liquidity.reference.banks",
    "liquidity.reference.blacklist.account",
    "liquidity.reference.blacklist.bank",
    "liquidity.reference.entities",
    "liquidity.reference.whitelist.entity",
    "liquidity.risk.account_capacity",
    "liquidity.risk.credit_usage",
    "liquidity.risk.deposit_concentration",
    "liquidity.risk.sla",
    "liquidity.risk.thresholds",
    "liquidity.rules.action_mapping",
    "liquidity.rules.forecast",
    "liquidity.rules.funding",
    "liquidity.rules.fx_settlement",
    "liquidity.rules.operation",
    "liquidity.rules.realtime",
    "liquidity.rules.transfer",
    "liquidity.rules.waterlevel",
    "payment.channel",
    "payment.cost",
    "payment.ptr.cases",
    "payment.rules.bank_switch",
    "payment.rules.cost_reduction",
    "payment.rules.retry",
    "payment.rules.same_bank_transfer",
    "payment.sla.baselines",
)


@pytest.mark.parametrize("identity", FULL_OBSERVATION_LEAVES)
def test_full_observation_package_needs_no_temporal_declaration(identity):
    domain, name = identity.split(".", 1)
    source = ROOT / "leaf_packages" / domain / name
    if not source.exists():
        source = ROOT / "src/dogopencli/leaf_packages" / domain / name
    with validate_package(source) as package:
        assert "history" not in package.manifest["operations"]["list"]


@pytest.mark.parametrize("sample_source", [SOURCE], indirect=True)
def test_calendar_sample_keeps_compact_leaf_inputs_and_iso_plan(handbook):
    cli, browser, _ = handbook
    plan = cli(
        "workflow",
        "plan",
        "create",
        "--leaf",
        "collection.sample.calendar",
        "--mode",
        "history",
        "--parameters",
        '{"from-date":"20260228","to-date":"20260301"}',
        "--windows",
        '[{"from":"2026-03-01","to":"2026-03-01"}]',
    )["data"]
    assert not browser.business_requests
    assert plan["desired_range"] == {"from": "2026-02-28", "to": "2026-03-01"}
    assert plan["packages"][0]["parameters"] == {
        "from_date": "20260301",
        "to_date": "20260301",
    }
    rows = [{"id": "one", "valueDate": "20260301", "amount": "1.0000"}]
    browser.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "rows": rows,
                "pageNo": 0,
                "pageSize": 2,
                "total": 1,
            },
        }
    )
    # Desired February 28 remains uncovered even though selected March 1 succeeds.
    cli("workflow", "export", "run", "--plan", plan["id"], code=1)
    status = cli("workflow", "history", "show", "--plan", plan["id"])["data"]
    assert status["uncovered_ranges"] == [{"from": "2026-02-28", "to": "2026-02-28"}]
    export_id = status["packages"][0]["export_id"]
    exported = cli("workflow", "export", "show", "--export", export_id)["data"]
    assert exported["records"] == rows
    assert browser.business_requests == [
        {"fromDate": "20260301", "toDate": "20260301", "pageNo": 0, "pageSize": 2}
    ]
    prepared = cli(
        "workflow", "import", "plan", "--export", export_id, "--action", "preserve"
    )["data"]
    before = len(browser.business_requests)
    cli("workflow", "import", "apply", "--plan", prepared["id"])
    assert (
        cli("workflow", "observation", "show", "--export", export_id)["data"]["records"]
        == rows
    )
    assert len(browser.business_requests) == before
