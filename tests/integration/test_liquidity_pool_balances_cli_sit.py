"""Issue #98 pool balances: native shape, synthetic values, public CLI seam."""

import copy
import json
from pathlib import Path

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
QUERY = ["liquidity", "cash", "pool-balances", "list", "--limit", "0"]
REFRESH = ["refresh", "liquidity", "cash", "pool-balances"]
FIXTURE = Path(__file__).parents[1] / "fixtures/liquidity/pool-balances.json"


def pool():
    return json.loads(FIXTURE.read_text())


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


def seed(setup, run_cli, rows=None):
    rows = [pool()] if rows is None else rows
    setup.state.business_handler = lambda payload, index: response(rows)
    code, out, err = run_cli(REFRESH)
    assert code == 0, err
    return parse(out)


def test_public_refresh_live_offline_preserves_native_values_and_cache(setup, run_cli):
    code, out, _ = run_cli(QUERY)
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    seed(setup, run_cli)
    assert setup.state.business_requests == [
        {
            "tntInstId": "GUAPW3SG",
            "cashPoolCategory": "BANK",
            "rowStart": 0,
            "pageSize": 100,
        }
    ]
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any(
        "/cashPoolList.json" in e and "application/json" in e and "POST" in e
        for e in expressions
    )
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli([*QUERY, "--live", "--require-complete"])
    assert code == 0, err
    live = parse(out)
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    count = len(setup.state.business_requests)
    code, out, err = run_cli([*QUERY, "--require-complete"])
    assert code == 0, err
    offline = parse(out)
    assert offline["data"] == live["data"]
    assert len(setup.state.business_requests) == count
    meta = offline["meta"]
    assert meta["kind"] == "runtimes"
    assert meta["source"] == "cache"
    assert meta["complete"] is True
    assert meta["source_observed_from"] is None
    assert meta["capability"] == "liquidity.cash.pool-balances.list"
    row = offline["data"][0]
    member = row["cashPoolMemberVOS"][0]
    assert row["currentBalance"] == "321.123400"
    assert row["currentAviBalance"] == "300.123400"
    assert row["mainCurrency"] == "HKD"
    assert row["cashPoolType"] == "SYNTHETIC"
    assert member["currentBalance"] == "-100.123400"
    assert member["equvCurrentAviBalance"] == "-14.123400"
    assert member["currency"] == "HKD" and member["bankCurrency"] == "USD"
    assert "valueDate" not in member
    assert "gmtModified" not in row and "cashPoolCapacity" not in row
    assert "creditAmount" not in member and "cashPoolSwapRuleVOS" not in member


def test_unknowns_zero_and_balance_order_are_not_incompleteness(setup, run_cli):
    row = pool()
    row.update(
        mainCurrency="", valueDate=None, currentBalance="0", currentAviBalance="20"
    )
    member = row["cashPoolMemberVOS"][0]
    member.update(
        currency="",
        bankCurrency=None,
        currentBalance=None,
        currentAviBalance="",
        closeBalance=0,
        isShare="N",
    )
    seed(setup, run_cli, [row])
    code, out, err = run_cli([*QUERY, "--require-complete"])
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["complete"] is True
    got = result["data"][0]
    assert got["valueDate"] is None and got["mainCurrency"] == ""
    assert got["currentAviBalance"] == "20"
    for key in (
        "currency",
        "bankCurrency",
        "currentBalance",
        "currentAviBalance",
        "closeBalance",
        "isShare",
    ):
        assert got["cashPoolMemberVOS"][0][key] == member[key]


@pytest.mark.parametrize(
    "member,field,value",
    [
        (False, "currentBalance", "NaN"),
        (True, "equvCurrentAviBalance", "not-money"),
        (True, "closeBalance", True),
        (False, "valueDate", "2026-02-30"),
        (False, "valueDate", "20261004"),
        (False, "mainCurrency", "US"),
        (True, "currency", "usd"),
        (True, "bankCurrency", 123),
        (False, "id", True),
        (True, "id", ""),
        (True, "cashPoolId", "wrong-pool"),
        (False, "tntInstId", "OTHER"),
        (True, "tntInstId", "OTHER"),
        (False, "cashPoolCategory", "INTERNAL"),
    ],
)
def test_malformed_source_refuses_live_and_refresh_preserving_cache(
    setup, run_cli, member, field, value
):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    row = pool()
    target = row["cashPoolMemberVOS"][0] if member else row
    target[field] = value
    setup.state.business_handler = lambda payload, index: response([row])
    for command in ([*QUERY, "--live"], REFRESH):
        code, out, _ = run_cli(command)
        assert code == 1
        assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
        assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    assert run_cli(QUERY)[0] == 0


@pytest.mark.parametrize("conflict", ["member", "pool"])
def test_duplicate_identity_conflict_keeps_cache(setup, run_cli, conflict):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    row = pool()
    other = copy.deepcopy(row)
    other["currentBalance"] = "99"
    if conflict == "member":
        row["cashPoolMemberVOS"].append(copy.deepcopy(row["cashPoolMemberVOS"][0]))
        rows = [row]
    else:
        rows = [row, other]
    setup.state.business_handler = lambda payload, index: response(rows)
    code, out, _ = run_cli(REFRESH)
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == before


def test_partial_strict_rollback_default_publication_and_empty_capture(setup, run_cli):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    rows = []
    for i in range(100):
        row = pool()
        row["id"] = f"synthetic-pool-{i}"
        row["cashPoolMemberVOS"][0]["cashPoolId"] = row["id"]
        rows.append(row)
    # A full page followed by overlap leaves one missing pool; safe rows remain usable.
    setup.state.business_handler = lambda payload, index: response(
        rows if payload["rowStart"] == 0 else rows[:1], 101
    )
    code, out, _ = run_cli([*REFRESH, "--require-complete"])
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(REFRESH)
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is False
    setup.state.reachable = False
    code, out, err = run_cli(QUERY)
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert len(parse(out)["data"]) == 100
    assert parse(out)["meta"]["complete"] is False
    assert run_cli([*QUERY, "--require-complete"])[0] == 1
    setup.state.reachable = True
    before_empty = setup.cache_path.read_bytes()
    empty = seed(setup, run_cli, [])
    assert empty["data"]["published"] is False
    assert empty["data"]["row_count"] == 0
    assert setup.cache_path.read_bytes() == before_empty
    setup.state.reachable = False
    code, out, err = run_cli(QUERY)
    assert code == 0 and len(parse(out)["data"]) == 100
    assert parse(out)["meta"]["complete"] is False
    assert run_cli([*QUERY, "--require-complete"])[0] == 1


def test_pool_settings_list_and_native_detail_remain_independent(setup, run_cli):
    row = pool()
    setup.state.business_handler = lambda payload, index: response([row])
    assert run_cli(["refresh", "liquidity", "cash", "pools"])[0] == 0
    listing = ["liquidity", "cash", "pools", "list"]
    before_list = parse(run_cli(listing)[1])["data"]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": row},
    }
    before_get = setup.cache_path.read_bytes()
    code, out, err = run_cli(
        ["liquidity", "cash", "pools", "get", "--pool-id", row["id"]]
    )
    assert code == 0, err
    assert "currentBalance" not in parse(out)["data"]
    assert setup.cache_path.read_bytes() == before_get
    seed(setup, run_cli)
    setup.state.reachable = False
    assert parse(run_cli(listing)[1])["data"] == before_list
    assert "currentBalance" not in before_list[0]
    assert (
        run_cli(["liquidity", "cash", "pools", "get", "--pool-id", row["id"]])[0] == 1
    )
    code, out, _ = run_cli(QUERY)
    assert (
        code == 0 and parse(out)["data"][0]["currentBalance"] == row["currentBalance"]
    )


def test_describe_help_expose_scope_units_and_unknown_times_without_browser(
    setup, run_cli
):
    code, out, err = run_cli(["describe", "liquidity", "cash", "pool-balances", "list"])
    assert code == 0, err
    description = parse(out)
    schema = description["data_schema"]
    assert schema["x-member-observation-time"] == "unknown"
    assert (
        schema["properties"]["currentBalance"]["x-currency"]
        == "USD (native UI pool summary display)"
    )
    assert (
        schema["properties"]["cashPoolMemberVOS[].equvCurrentBalance"]["x-currency"]
        == "bankCurrency"
    )
    assert (
        schema["properties"]["cashPoolMemberVOS[].currentAviBalance"]["x-currency"]
        == "currency"
    )
    assert description["read_guide"]["kind"] == "runtimes"
    code, out, err = run_cli(["help", "liquidity", "cash", "pool-balances"])
    assert code == 0, err
    assert "history" not in out and "get" not in [
        c.get("name") for c in parse(out).get("children", [])
    ]
    assert setup.state.transports == []
