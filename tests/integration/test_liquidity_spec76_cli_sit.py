"""Spec #76 candidates: public CLI, fake CDP and independent SQLite caches."""

import json
from dataclasses import replace

import pytest

from dogopencli import catalog, helptree
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import leaves
from dogopencli.plugins.liquidity.cash_forecast import (
    ACCEPTED_LIST_SPECS,
    CASH_BALANCES,
    CASH_CREDIT_LINES,
    CASH_GROUP_BALANCES,
    CASH_GROUPS,
    CASH_POOLS,
    CASH_POOLS_GET,
    CASH_STATEMENTS_EOD,
    FORECAST_RESULTS,
)

# Reuse synthetic browser/config fixtures without registering a real transport.
pytest_plugins = ["test_liquidity_cli_sit"]


@pytest.fixture(autouse=True)
def candidate_catalog(monkeypatch):
    """Test candidate declarations without changing the production UAT gate."""
    declarations = {
        path: replace(node, children=()) for path, node in catalog.NODES.items()
    }
    grouped = {}
    for item in ACCEPTED_LIST_SPECS:
        grouped.setdefault(item.path, []).append(item)
    for variants in grouped.values():
        item = variants[0]
        leaf = leaves.ListLeaf(tuple(variants))
        monkeypatch.setitem(leaves.LIST_LEAVES, item.path, leaf)
        monkeypatch.delitem(
            leaves.DEFERRED_BY_PATH, (*item.path, "list"), raising=False
        )
        for node in (leaves.list_query_node(leaf), leaves.refresh_list_node(leaf)):
            declarations[node.path] = node
    leaf = leaves.DetailLeaf(CASH_POOLS_GET)
    monkeypatch.setattr(leaves, "DETAIL_SPECS", (*leaves.DETAIL_SPECS, CASH_POOLS_GET))
    monkeypatch.setattr(
        leaves, "LIST_SPECS", (*leaves.LIST_SPECS, *ACCEPTED_LIST_SPECS)
    )
    monkeypatch.setitem(leaves.DETAIL_LEAVES, leaf.path, leaf)
    monkeypatch.delitem(leaves.DEFERRED_BY_PATH, leaf.path, raising=False)
    for node in (
        leaves.detail_query_node(leaf),
        leaves.refresh_detail_node(leaf),
        *leaves.group_nodes(),
    ):
        declarations[node.path] = node
    nodes = catalog.build_catalog(declarations.values())
    monkeypatch.setattr(catalog, "NODES", nodes)
    monkeypatch.setattr(helptree, "NODES", nodes)


def synthetic_balance_id(row):
    account = [row.get(field) for field in ("entity", "aliasName", "currency")]
    return f"synthetic:{json.dumps(account, separators=(',', ':'), ensure_ascii=True)}"


def expected_balance_record(entity, alias, currency, balance):
    return {
        "balance_record_id": synthetic_balance_id(
            {"entity": entity, "aliasName": alias, "currency": currency}
        ),
        "account_holder_entity_id": entity,
        "account_alias": alias,
        "currency": currency,
        "current_balance": balance,
    }


def response(item, rows, total=None):
    if item is CASH_BALANCES:
        rows = [
            row if "balId" in row else {**row, "balId": synthetic_balance_id(row)}
            for row in rows
        ]
    total = len(rows) if total is None else total
    if item.envelope == "success":
        body = {"success": True, "data": {"data": rows, "totalCount": total}}
    else:
        key = item.container[-1]
        body = {
            "resultFlag": True,
            "count": total,
            "result": {"success": True, key: rows, "count": total},
        }
    return {"status": 200, "body": body}


CASES = [
    (
        CASH_BALANCES,
        ["--entity", "E1", "--account-alias", "A1"],
        {
            "entity": "E1",
            "aliasName": "A1",
            "currency": "USD",
            "curBalance": "123.4500",
            "statementCreateTime": "",
            "timeZone": "GMT+08",
        },
    ),
    (
        CASH_GROUPS,
        ["--group-code", "G1"],
        {
            "id": "G1",
            "groupName": "group",
            "currentBalance": "900",
            "memberList": [{"id": "M1", "aliasName": "A1", "currentBalance": "900"}],
        },
    ),
    (
        CASH_GROUP_BALANCES,
        ["--group-code", "G1"],
        {
            "id": "G1",
            "currentBalance": "123.4500",
            "memberList": [
                {
                    "id": "M1",
                    "aliasName": "A1",
                    "currentBalanceTime": "",
                    "forecastTime": None,
                    "equiCurrentBalance": "123.4500",
                }
            ],
        },
    ),
    (
        CASH_POOLS,
        [],
        {
            "id": "P1",
            "cashPoolCategory": "BANK",
            "cashPoolName": "pool",
            "curBalance": "900",
            "cashPoolMemberVOS": [
                {"id": "M1", "aliasName": "A1", "availableAmount": "900"}
            ],
        },
    ),
    (
        CASH_CREDIT_LINES,
        [],
        {
            "id": "C1",
            "currency": "USD",
            "amount": "123.4500",
            "usedAmount": "900",
            "bankAccountCreditLineList": [
                {"id": "M1", "aliasName": "A1", "usedAmount": "900"}
            ],
        },
    ),
    (
        CASH_STATEMENTS_EOD,
        [
            "--entity",
            "E1",
            "--account-alias",
            "A1",
            "--currency",
            "USD",
            "--from-date",
            "20260930",
            "--to-date",
            "20260930",
        ],
        {
            "instId": "E1",
            "bankAccountAliasName": "A1",
            "currency": "USD",
            "valueDate": "20260930",
            "bankTransNo": "T1",
            "fundDirection": "Dr",
            "amount": "123.4500",
        },
    ),
    (
        FORECAST_RESULTS,
        ["--from-date", "20261001", "--to-date", "20261001", "--account-alias", "A1"],
        {
            "id": "F1",
            "bankAccountAliasName": "A1",
            "currency": "USD",
            "valueDate": "20261001",
            "baseValueDate": "20260930",
            "forecastBalance": "123.4500",
            "gmtCreate": 100,
            "recordCreateTime": "unconverted",
        },
    ),
]


@pytest.mark.parametrize("item,options,row", CASES, ids=[s.leaf for s, _, _ in CASES])
def test_candidate_refresh_live_and_browser_disconnected_offline(
    setup, run_cli, item, options, row
):
    setup.state.business_handler = lambda payload, index: response(item, [row])
    query = ["liquidity", *item.path, "list", *options, "--all"]
    code, out, err = run_cli(["refresh", "liquidity", *item.path, *options])
    assert code == 0, err
    assert parse(out)["meta"]["kind"] == item.kind
    assert len(setup.state.business_requests) == 1  # never enrich each row
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli([*query, "--live", "--require-complete"])
    assert code == 0, err
    live = parse(out)
    assert live["meta"]["source"] == "live"
    assert setup.cache_path.read_bytes() == before
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli([*query, "--require-complete"])
    assert code == 0, err
    offline = parse(out)
    assert offline["data"] == live["data"]
    assert offline["meta"]["kind"] == item.kind
    assert offline["meta"]["source"] == "cache"
    assert len(setup.state.business_requests) == count
    if item is CASH_GROUPS:
        assert "currentBalance" not in offline["data"][0]
        assert "currentBalance" not in offline["data"][0]["memberList"][0]
    if item is CASH_CREDIT_LINES:
        assert "usedAmount" not in offline["data"][0]
        assert "usedAmount" not in offline["data"][0]["bankAccountCreditLineList"][0]
    if item is FORECAST_RESULTS:
        assert offline["data"][0]["forecastBalance"] == "123.4500"
        assert offline["meta"]["source_observed_from"] is None


def test_latest_balances_default_width_100_collects_short_final_page(setup, run_cli):
    rows = [
        {
            "entity": "Z21",
            "aliasName": f"A{i:03d}",
            "currency": "USD",
            "curBalance": "1.00",
        }
        for i in range(101)
    ]
    setup.state.business_handler = lambda payload, index: response(
        CASH_BALANCES,
        rows[payload["rowStart"] : payload["rowStart"] + payload["pageSize"]],
        101,
    )
    code, out, err = run_cli(
        ["liquidity", "cash", "balances", "list", "--entity", "Z21", "--live", "--all"]
    )
    assert code == 0, err
    assert parse(out)["data"] == [
        expected_balance_record(
            row["entity"], row["aliasName"], row["currency"], row["curBalance"]
        )
        for row in rows
    ]
    assert [p["rowStart"] for p in setup.state.business_requests] == [0, 100]
    assert all(p["pageSize"] == 100 for p in setup.state.business_requests)
    assert "page 2/2" in err
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("width", [1, 50, 100])
def test_latest_width_override_refresh_and_offline_share_scope(setup, run_cli, width):
    rows = [
        {
            "entity": "E1",
            "aliasName": f"A{i:03d}",
            "currency": "USD",
            "curBalance": "1.00",
        }
        for i in range(51)
    ]
    setup.state.business_handler = lambda payload, index: response(
        CASH_BALANCES,
        rows[payload["rowStart"] : payload["rowStart"] + payload["pageSize"]],
        51,
    )
    query = ["liquidity", "cash", "balances", "list", "--entity", "E1", "--all"]
    code, out, err = run_cli([*query, "--live", "--page-size", str(width)])
    assert code == 0, err
    live = parse(out)
    assert live["data"] == [
        expected_balance_record(
            row["entity"], row["aliasName"], row["currency"], row["curBalance"]
        )
        for row in rows
    ]
    assert [p["rowStart"] for p in setup.state.business_requests] == list(
        range(0, 51, width)
    )
    setup.state.business_requests.clear()
    code, out, err = run_cli(
        [
            "refresh",
            "liquidity",
            "cash",
            "balances",
            "--entity",
            "E1",
            "--page-size",
            str(width),
        ]
    )
    assert code == 0, err
    assert parse(out)["meta"]["scope"] == live["meta"]["scope"]
    assert [p["rowStart"] for p in setup.state.business_requests] == list(
        range(0, 51, width)
    )
    assert all(p["pageSize"] == width for p in setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(query)
    assert code == 0, err
    assert parse(out)["data"] == live["data"]


def test_latest_entity_ids_are_deduplicated_sorted_and_stable_offline(setup, run_cli):
    row = {"entity": "E1", "aliasName": "A1", "currency": "USD", "curBalance": "1"}
    setup.state.business_handler = lambda payload, index: response(CASH_BALANCES, [row])
    code, _, err = run_cli(
        [
            "refresh",
            "liquidity",
            "cash",
            "balances",
            "--entity",
            "E2",
            "--entity",
            "E1",
            "--entity",
            "E2",
        ]
    )
    assert code == 0, err
    assert setup.state.business_requests[-1]["entitys"] == ["E1", "E2"]
    setup.state.reachable = False
    code, out, err = run_cli(
        [
            "liquidity",
            "cash",
            "balances",
            "list",
            "--entity",
            "E1",
            "--entity",
            "E2",
        ]
    )
    assert code == 0, err
    assert parse(out)["data"] == [expected_balance_record("E1", "A1", "USD", "1")]


@pytest.mark.parametrize("bad_entity", ["E2", "", None, ["E1"]])
def test_latest_scope_mismatch_is_hard_failure_and_preserves_cache(
    setup, run_cli, bad_entity
):
    row = {"entity": "E1", "aliasName": "A1", "currency": "USD", "curBalance": "1"}
    setup.state.business_handler = lambda payload, index: response(CASH_BALANCES, [row])
    refresh = ["refresh", "liquidity", "cash", "balances", "--entity", "E1"]
    query = ["liquidity", "cash", "balances", "list", "--entity", "E1"]
    assert run_cli(refresh)[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = lambda payload, index: response(
        CASH_BALANCES, [{**row, "entity": bad_entity}]
    )
    for command in (
        [*query, "--live"],
        [*query, "--live", "--require-complete"],
        refresh,
    ):
        code, out, _ = run_cli(command)
        assert code == 1
        assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
        assert parse(out)["data"] is None
        assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    code, out, err = run_cli(query)
    assert code == 0, err
    assert parse(out)["data"] == [expected_balance_record("E1", "A1", "USD", "1")]


@pytest.mark.parametrize("mode", ["live", "refresh"])
@pytest.mark.parametrize("bad_alias", ["A2", "a1", "A1 "])
def test_latest_explicit_alias_scope_failure_preserves_prior_capture(
    setup, run_cli, mode, bad_alias
):
    row = {"entity": "E1", "aliasName": "A1", "currency": "USD", "curBalance": "1"}
    options = ["--entity", "E1", "--account-alias", "A1"]
    refresh = ["refresh", "liquidity", "cash", "balances", *options]
    query = ["liquidity", "cash", "balances", "list", *options]
    setup.state.business_handler = lambda payload, index: response(CASH_BALANCES, [row])
    assert run_cli(refresh)[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = lambda payload, index: response(
        CASH_BALANCES, [{**row, "aliasName": bad_alias}]
    )
    command = [*query, "--live"] if mode == "live" else refresh
    code, out, _ = run_cli(command)
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert parse(out)["data"] is None
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    count = len(setup.state.business_requests)
    code, out, err = run_cli(query)
    assert code == 0, err
    assert parse(out)["data"] == [expected_balance_record("E1", "A1", "USD", "1")]
    assert len(setup.state.business_requests) == count


@pytest.mark.parametrize("filtered", [True, False], ids=["multi-alias", "unfiltered"])
def test_latest_allowed_aliases_survive_live_refresh_and_offline(
    setup, run_cli, filtered
):
    rows = [
        {"entity": "E1", "aliasName": alias, "currency": "USD", "curBalance": "1"}
        for alias in ("A1", "a2:/opaque")
    ]
    options = ["--entity", "E1"]
    if filtered:
        options += ["--account-alias", "A1", "--account-alias", "a2:/opaque"]
    query = ["liquidity", "cash", "balances", "list", *options, "--all"]
    setup.state.business_handler = lambda payload, index: response(CASH_BALANCES, rows)
    code, out, err = run_cli([*query, "--live"])
    assert code == 0, err
    assert parse(out)["data"] == [
        expected_balance_record("E1", alias, "USD", "1")
        for alias in ("A1", "a2:/opaque")
    ]
    assert not setup.cache_path.exists()
    code, _, err = run_cli(["refresh", "liquidity", "cash", "balances", *options])
    assert code == 0, err
    setup.state.reachable = False
    count = len(setup.state.business_requests)
    code, out, err = run_cli(query)
    assert code == 0, err
    assert parse(out)["data"] == [
        expected_balance_record("E1", alias, "USD", "1")
        for alias in ("A1", "a2:/opaque")
    ]
    assert len(setup.state.business_requests) == count


@pytest.mark.parametrize("width", ["0", "-1", "101", "500", "1.5", "many"])
def test_latest_invalid_width_rejected_before_any_source(setup, run_cli, width):
    for command in (
        ["liquidity", "cash", "balances", "list", "--live"],
        ["refresh", "liquidity", "cash", "balances"],
    ):
        code, out, _ = run_cli([*command, "--page-size", width])
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert not setup.state.transports
    assert not setup.cache_path.exists()


def test_latest_cached_width_rejected_even_without_config(setup, run_cli, monkeypatch):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(setup.tmp_path / "absent.toml"))
    code, out, _ = run_cli(
        [
            "liquidity",
            "cash",
            "balances",
            "list",
            "--page-size",
            "50",
        ]
    )
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert "requires --live or refresh" in parse(out)["error"]["message"]
    assert not setup.state.transports
    assert not setup.cache_path.exists()


def test_latest_399_arrivals_396_identities_remain_incomplete(setup, run_cli):
    rows = [
        {"entity": "E1", "aliasName": f"A{i:03d}", "currency": "USD", "curBalance": "1"}
        for i in range(396)
    ]
    query = ["liquidity", "cash", "balances", "list", "--entity", "E1", "--all"]
    refresh = ["refresh", "liquidity", "cash", "balances", "--entity", "E1"]
    arrivals = [*rows, *rows[:3]]
    setup.state.business_handler = lambda payload, index: response(
        CASH_BALANCES,
        arrivals[payload["rowStart"] : payload["rowStart"] + payload["pageSize"]],
        399,
    )
    code, out, err = run_cli([*query, "--live"])
    assert code == 0, err
    envelope = parse(out)
    assert envelope["data"] == [
        expected_balance_record("E1", f"A{i:03d}", "USD", "1") for i in range(396)
    ]
    assert envelope["meta"]["complete"] is False
    assert envelope["meta"]["reported_total"] == 399
    assert envelope["meta"]["collected_total"] == 396
    assert "INCOMPLETE_RESULT" in err
    code, out, _ = run_cli([*query, "--live", "--require-complete"])
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    # Usable partial refresh persists its evidence; strict refresh cannot replace it.
    assert run_cli(refresh)[0] == 0
    before = setup.cache_path.read_bytes()
    code, out, _ = run_cli([*refresh, "--require-complete"])
    assert code == 1
    assert parse(out)["meta"]["published"] is False
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    code, out, _ = run_cli(query)
    assert code == 0
    assert parse(out)["data"] == [
        expected_balance_record("E1", f"A{i:03d}", "USD", "1") for i in range(396)
    ]
    assert parse(out)["meta"]["complete"] is False
    assert run_cli([*query, "--require-complete"])[0] == 1


@pytest.mark.parametrize(
    "fault", ["changed_total", "empty", "oversize", "conflict", "budget"]
)
def test_latest_effective_width_guards_preserve_cache(setup, run_cli, fault):
    row = {"entity": "E1", "aliasName": "A1", "currency": "USD", "curBalance": "1"}
    refresh = [
        "refresh",
        "liquidity",
        "cash",
        "balances",
        "--entity",
        "E1",
        "--page-size",
        "1",
    ]
    setup.state.business_handler = lambda payload, index: response(CASH_BALANCES, [row])
    assert run_cli(refresh)[0] == 0
    before = setup.cache_path.read_bytes()

    def faulty(payload, index):
        if fault == "budget":
            return response(CASH_BALANCES, [row], 1001)
        if fault == "oversize":
            return response(CASH_BALANCES, [row, {**row, "aliasName": "A2"}], 2)
        if payload["rowStart"] == 0:
            return response(CASH_BALANCES, [row], 2)
        if fault == "changed_total":
            return response(CASH_BALANCES, [{**row, "aliasName": "A2"}], 3)
        if fault == "empty":
            return response(CASH_BALANCES, [], 2)
        return response(CASH_BALANCES, [{**row, "curBalance": "2"}], 2)

    setup.state.business_handler = faulty
    code, out, _ = run_cli(refresh)
    assert code == 1
    assert parse(out)["error"]["code"] == (
        "TIMEOUT" if fault == "budget" else "INVALID_RESPONSE"
    )
    assert setup.cache_path.read_bytes() == before


def test_latest_page_size_help_is_leaf_only(run_cli):
    for command in (
        ["help", "liquidity", "cash", "balances", "list"],
        ["help", "refresh", "liquidity", "cash", "balances"],
    ):
        code, out, _ = run_cli(command)
        assert code == 0
        width = next(o for o in parse(out)["options"] if o["name"] == "page_size")
        assert width["default"] == 100
    for command in (
        ["liquidity", "cash", "accounts", "list", "--live"],
        ["refresh", "liquidity", "cash", "accounts"],
    ):
        code, out, _ = run_cli([*command, "--page-size", "50"])
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_settings_runtime_same_endpoint_have_independent_scope_caches(setup, run_cli):
    row = {"id": "G1", "groupName": "group", "currentBalance": "1", "memberList": []}
    setup.state.business_handler = lambda payload, index: response(CASH_GROUPS, [row])
    for resource in ["groups", "group-balances"]:
        code, out, err = run_cli(["refresh", "liquidity", "cash", resource])
        assert code == 0, err
    setup.state.reachable = False
    code, out, _ = run_cli(["liquidity", "cash", "groups", "list"])
    settings = parse(out)
    assert code == 0
    code, out, _ = run_cli(["liquidity", "cash", "group-balances", "list"])
    runtime = parse(out)
    assert code == 0
    assert settings["meta"]["scope"] != runtime["meta"]["scope"]
    assert "currentBalance" not in settings["data"][0]
    assert runtime["data"][0]["currentBalance"] == "1"


def test_pool_native_get_failure_preserves_independent_list_and_detail(setup, run_cli):
    pool = {
        "id": "P1",
        "cashPoolCategory": "BANK",
        "cashPoolName": "first",
        "cashPoolMemberVOS": [],
    }
    setup.state.business_handler = lambda payload, index: response(CASH_POOLS, [pool])
    code, _, err = run_cli(["refresh", "liquidity", "cash", "pools"])
    assert code == 0, err
    assert len(setup.state.business_requests) == 1
    code, out, _ = run_cli(["liquidity", "cash", "pools", "get", "--pool-id", "P1"])
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": pool},
    }
    code, out, err = run_cli(
        ["refresh", "liquidity", "cash", "pools", "detail", "get", "--pool-id", "P1"]
    )
    assert code == 0, err
    assert setup.state.business_requests[-1] == {
        "id": "P1",
        "tntInstId": "GUAPW3SG",
        "inUse": "Y",
        "cashPoolCategory": "BANK",
    }
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {**pool, "id": "P2"}},
    }
    code, out, _ = run_cli(
        ["refresh", "liquidity", "cash", "pools", "detail", "get", "--pool-id", "P1"]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    setup.state.reachable = False
    for query in [["list"], ["get", "--pool-id", "P1"]]:
        code, out, err = run_cli(["liquidity", "cash", "pools", *query])
        assert code == 0, err
        data = parse(out)["data"]
        assert (data[0] if isinstance(data, list) else data)["cashPoolName"] == "first"


def test_credit_unstable_order_partial_live_and_failed_refresh_keep_cache(
    setup, run_cli
):
    row = {
        "id": "C1",
        "currency": "USD",
        "amount": "1.0000",
        "bankAccountCreditLineList": [],
    }
    setup.state.business_handler = lambda payload, index: response(
        CASH_CREDIT_LINES, [row]
    )
    code, _, err = run_cli(["refresh", "liquidity", "cash", "credit-lines"])
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    # First page full, second page repeats one identity due to unstable ordering.
    def overlap(payload, index):
        import json

        offset = json.loads(payload["bankCreditLineQuery"])["rowStart"]
        rows = [{**row, "id": f"C{i}"} for i in range(100)] if offset == 0 else [row]
        return response(CASH_CREDIT_LINES, rows, 101)

    setup.state.business_handler = overlap
    code, out, _ = run_cli(
        ["liquidity", "cash", "credit-lines", "list", "--live", "--all"]
    )
    assert code == 0
    envelope = parse(out)
    assert envelope["meta"]["complete"] is False
    assert len(envelope["data"]) == 100
    assert envelope["error"] is None
    code, out, _ = run_cli(
        ["liquidity", "cash", "credit-lines", "list", "--live", "--require-complete"]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    code, out, _ = run_cli(
        ["refresh", "liquidity", "cash", "credit-lines", "--require-complete"]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before


def test_withdrawn_getters_are_not_active_help_or_describe(run_cli):
    for path in [("cash", "groups"), ("cash", "credit-lines"), ("forecast", "results")]:
        code, out, _ = run_cli(["help", "liquidity", *path])
        assert code == 0
        assert "get" not in [
            child["command"][-1]
            if isinstance(child.get("command"), list)
            else child.get("name")
            for child in parse(out)["children"]
        ]
        assert ("liquidity", *path, "get") not in catalog.NODES


def test_forecast_7504_7502_uses_accounts_partial_contract_and_preserves_cache(
    setup, run_cli
):
    import json

    options = ["--from-date", "20261001", "--to-date", "20261001"]
    query = ["liquidity", "forecast", "results", "list", *options, "--all"]
    refresh = ["refresh", "liquidity", "forecast", "results", *options]
    seed = {
        "id": "previous-complete",
        "valueDate": "20261001",
        "baseValueDate": "20260930",
        "currency": "USD",
        "forecastBalance": "0.0000",
    }
    setup.state.business_handler = lambda payload, index: response(
        FORECAST_RESULTS, [seed]
    )
    code, _, err = run_cli(refresh)
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    offsets = []

    # Synthetic overlap reproduces the totals, not a claimed production root cause.
    def overlap(payload, index):
        scope = json.loads(payload[FORECAST_RESULTS.vo_field])
        assert scope["pageSize"] == 5000  # never silently reduce the native width
        assert scope.get("aliasName") is None  # full, not account-filtered
        offset = scope["rowStart"]
        offsets.append(offset)
        assert offset in (0, 5000)
        identities = range(5000) if offset == 0 else [*range(5000, 7502), 0, 1]
        rows = [{**seed, "id": f"synthetic-{i}"} for i in identities]
        return response(FORECAST_RESULTS, rows, 7504)

    setup.state.business_handler = overlap
    code, out, err = run_cli([*query, "--live"])
    envelope = parse(out)
    assert code == 0
    assert envelope["error"] is None
    assert "INCOMPLETE_RESULT" in err
    assert envelope["meta"]["complete"] is False
    assert envelope["meta"]["reported_total"] == 7504
    assert envelope["meta"]["collected_total"] == 7502
    assert envelope["meta"]["matched_total"] == 7502
    assert envelope["meta"]["returned_count"] == 7502
    assert len(envelope["data"]) == 7502
    assert envelope["meta"]["warnings"][0]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before

    code, out, _ = run_cli([*query, "--live", "--require-complete"])
    envelope = parse(out)
    assert code == 1
    assert envelope["error"]["code"] == "INCOMPLETE_RESULT"
    assert envelope["data"] is None
    assert setup.cache_path.read_bytes() == before

    code, out, _ = run_cli([*refresh, "--require-complete"])
    envelope = parse(out)
    assert code == 1
    assert envelope["error"]["code"] == "INCOMPLETE_RESULT"
    assert envelope["meta"]["complete"] is False
    assert envelope["meta"]["published"] is False
    assert envelope["meta"]["reported_total"] == 7504
    assert envelope["meta"]["collected_total"] == 7502
    assert setup.cache_path.read_bytes() == before
    assert offsets == [0, 5000] * 3

    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(query)
    assert code == 0, err
    assert parse(out)["data"] == [seed]
    assert parse(out)["meta"]["complete"] is True
    assert len(setup.state.business_requests) == count


@pytest.mark.parametrize(
    "item,options,row",
    [case for case in CASES if case[0] in (CASH_STATEMENTS_EOD, FORECAST_RESULTS)],
    ids=["eod", "forecast"],
)
@pytest.mark.parametrize(
    "bad_date", [None, "", "20260230", "2026-10-01", "20251001", "20271231"]
)
def test_dated_response_must_fit_verified_window_before_live_or_publication(
    setup, run_cli, item, options, row, bad_date
):
    query = ["liquidity", *item.path, "list", *options, "--all"]
    refresh = ["refresh", "liquidity", *item.path, *options]
    setup.state.business_handler = lambda payload, index: response(item, [row])
    code, _, err = run_cli(refresh)
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    malformed = {**row, "valueDate": bad_date}
    setup.state.business_handler = lambda payload, index: response(item, [malformed])
    for command in ([*query, "--live"], refresh):
        code, out, _ = run_cli(command)
        envelope = parse(out)
        assert code == 1
        assert envelope["error"]["code"] == "INVALID_RESPONSE"
        assert envelope["data"] is None
        assert setup.cache_path.read_bytes() == before
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(query)
    assert code == 0, err
    assert parse(out)["data"] == [row]
    assert parse(out)["meta"]["complete"] is True
    assert len(setup.state.business_requests) == count


def test_forecast_changing_total_fails_closed_in_every_mode_and_keeps_cache(
    setup, run_cli
):
    import json

    options = ["--from-date", "20261001", "--to-date", "20261001"]
    query = ["liquidity", "forecast", "results", "list", *options, "--all"]
    refresh = ["refresh", "liquidity", "forecast", "results", *options]
    seed = {"id": "retained", "valueDate": "20261001", "forecastBalance": "0"}
    setup.state.business_handler = lambda payload, index: response(
        FORECAST_RESULTS, [seed]
    )
    code, _, err = run_cli(refresh)
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    def changing(payload, index):
        vo = json.loads(payload[FORECAST_RESULTS.vo_field])
        assert vo["pageSize"] == 5000
        offset = vo["rowStart"]
        rows = [{**seed, "id": f"synthetic-{offset + i}"} for i in range(5000)]
        return response(FORECAST_RESULTS, rows, 20135 if offset == 0 else 20200)

    setup.state.business_handler = changing
    for command in (
        [*query, "--live"],
        [*query, "--live", "--require-complete"],
        refresh,
    ):
        code, out, _ = run_cli(command)
        envelope = parse(out)
        assert code == 1
        assert envelope["error"]["code"] == "INVALID_RESPONSE"
        assert envelope["error"]["message"] == "backend total changed during collection"
        assert envelope["data"] is None
        assert setup.cache_path.read_bytes() == before
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(query)
    assert code == 0, err
    assert parse(out)["data"] == [seed]
    assert parse(out)["meta"]["complete"] is True
    assert len(setup.state.business_requests) == count


def test_forecast_record_clocks_colon_compact_equivalence_and_defaults(setup, run_cli):
    import json

    window = ["--from", "20261001", "--to", "20261001"]
    query = ["liquidity", "forecast", "results", "list", *window]
    refresh = ["refresh", "liquidity", "forecast", "results", *window]
    row = {"id": "F1", "valueDate": "20261001", "forecastBalance": "1.0000"}
    setup.state.business_handler = lambda payload, index: response(
        FORECAST_RESULTS, [row]
    )
    colon = ["--record-from-time", "09:15:00", "--record-to-time", "17:30:00"]
    code, _, err = run_cli([*refresh, *colon])
    assert code == 0, err
    vo = json.loads(setup.state.business_requests[-1][FORECAST_RESULTS.vo_field])
    assert vo["recordStartTime"] == "091500"
    assert vo["recordEndTime"] == "173000"
    # The compact legacy spelling reads the identical cached scope offline.
    setup.state.reachable = False
    compact = ["--record-from-time", "091500", "--record-to-time", "173000"]
    code, out, err = run_cli([*query, *compact])
    assert code == 0, err
    assert parse(out)["data"] == [row]

    # Omitted clocks keep the full-day defaults 00:00:00/23:59:59.
    setup.state.reachable = True
    code, _, err = run_cli(refresh)
    assert code == 0, err
    vo = json.loads(setup.state.business_requests[-1][FORECAST_RESULTS.vo_field])
    assert vo["recordStartTime"] == "000000"
    assert vo["recordEndTime"] == "235959"
    setup.state.reachable = False
    code, out, err = run_cli(query)
    assert code == 0, err
    assert parse(out)["data"] == [row]

    # Help declares the canonical defaults.
    help_doc = parse(run_cli(["help", *query[:4]])[1])
    defaults = {option["name"]: option.get("default") for option in help_doc["options"]}
    assert defaults["record_from_time"] == "00:00:00"
    assert defaults["record_to_time"] == "23:59:59"


@pytest.mark.parametrize(
    "clocks",
    [
        ["--record-from-time", "25:00:00"],
        ["--record-from-time", "09:15:00.5"],
        ["--record-from-time", "0915"],
        ["--record-from-time", "17:30:00", "--record-to-time", "09:15:00"],
        ["--record-from-time", "173000", "--record-to-time", "09:15:00"],
    ],
)
def test_forecast_record_clock_rejections_precede_browser_and_cache(
    setup, run_cli, clocks
):
    window = ["--from", "20261001", "--to", "20261001"]
    for command in (
        ["liquidity", "forecast", "results", "list", *window, *clocks, "--live"],
        ["refresh", "liquidity", "forecast", "results", *window, *clocks],
    ):
        code, out, _ = run_cli(command)
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert not setup.state.transports
    assert not setup.cache_path.exists()


def test_forecast_record_clocks_stay_independent_from_the_date_window(setup, run_cli):
    row = {"id": "F1", "valueDate": "20261001", "forecastBalance": "1.0000"}
    setup.state.business_handler = lambda payload, index: response(
        FORECAST_RESULTS, [row]
    )
    # A narrow clock span on a single-day window is valid.
    code, _, err = run_cli(
        [
            "refresh",
            "liquidity",
            "forecast",
            "results",
            "--from",
            "20261001",
            "--to",
            "20261001",
            "--record-from-time",
            "12:00:00",
            "--record-to-time",
            "13:00:00",
        ]
    )
    assert code == 0, err
    # A reversed date window stays invalid regardless of valid clocks.
    code, out, _ = run_cli(
        [
            "liquidity",
            "forecast",
            "results",
            "list",
            "--from",
            "20261002",
            "--to",
            "20261001",
            "--record-from-time",
            "12:00:00",
            "--record-to-time",
            "13:00:00",
            "--live",
        ]
    )
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
