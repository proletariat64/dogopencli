"""Issue #82 release prerequisites through the existing public CLI seam.

The empty historical inquiries are not runnable list contracts. These tests
exercise the gate without inventing native records or passing production UAT.
"""

import json
from dataclasses import replace

import pytest

from dogopencli import catalog, helptree
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import leaves
from dogopencli.plugins.liquidity.operations_batch import SWAP_ORDERS

pytest_plugins = ["test_liquidity_cli_sit"]

OPERATIONS = ("executions",)
TRADE_SCOPE = ["--from-date", "20260901", "--to-date", "20261001"]


@pytest.fixture
def swap_candidate_catalog(monkeypatch):
    """Candidate behavior is testable without bypassing the production gate."""
    declarations = {
        path: replace(node, children=()) for path, node in catalog.NODES.items()
    }
    leaf = leaves.ListLeaf((SWAP_ORDERS,))
    monkeypatch.setitem(leaves.LIST_LEAVES, SWAP_ORDERS.path, leaf)
    monkeypatch.delitem(
        leaves.DEFERRED_BY_PATH, (*SWAP_ORDERS.path, "list"), raising=False
    )
    monkeypatch.setattr(leaves, "LIST_SPECS", (*leaves.LIST_SPECS, SWAP_ORDERS))
    for node in (
        leaves.list_query_node(leaf),
        leaves.refresh_list_node(leaf),
        *leaves.group_nodes(),
    ):
        declarations[node.path] = node
    nodes = catalog.build_catalog(declarations.values())
    monkeypatch.setattr(catalog, "NODES", nodes)
    monkeypatch.setattr(helptree, "NODES", nodes)


def swap(index, **overrides):
    return {
        "dealId": f"synthetic-swap-{index:03d}",
        "tntInstId": "GUAPW3SG",
        "tradeDate": "20260930",
        "nearLegValueDate": "20261002",
        "farLegValueDate": "20261102",
        "nearLegDebitCcy": "USD",
        "nearLegCreditCcy": "EUR",
        "nearLegDebitAmount": "123.4500",
        "nearLegCreditAmount": "111.0000",
        "farLegDebitAmount": "111.0000",
        "farLegCreditAmount": "123.4500",
        "nearLegFxRate": "0.899149",
        "farLegFxRate": "0.899149",
        "status": "source-state",
        "gmtCreate": 1759190400000,
        "gmtModified": 1759190400000,
        "gmtSend": None,
        "gmtReturn": None,
        "needReview": False,
        "nodeNum": 0,
        **overrides,
    }


def swap_page(rows, total):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"success": True, "swapOrderVOList": rows, "count": total},
        },
    }


def swap_listing(rows):
    def answer(payload, index):
        assert set(payload) == {"tntInstId", "swapOrderQueryVO"}
        assert payload["tntInstId"] == "GUAPW3SG"
        scope = json.loads(payload["swapOrderQueryVO"])
        assert scope["tntInstId"] == "GUAPW3SG"
        assert scope["nearLegDebitEntity"] == []
        assert scope["nearLegCreditEntity"] == []
        assert scope["pageSize"] == 10
        assert scope["tradeStartDate"] == "20260901"
        assert scope["tradeEndDate"] == "20261001"
        assert scope["nearLegStartDate"] == scope["nearLegEndDate"] == ""
        assert scope["farLegStartDate"] == scope["farLegEndDate"] == ""
        offset = scope["rowStart"]
        return swap_page(rows[offset : offset + 10], len(rows))

    return answer


def swap_query(*tail):
    return [
        "liquidity",
        "operations",
        "swaps",
        "list",
        *(TRADE_SCOPE if "--live" in tail else ()),
        *tail,
    ]


def swap_refresh(*tail):
    return ["refresh", "liquidity", "operations", "swaps", *TRADE_SCOPE, *tail]


@pytest.mark.parametrize("resource", OPERATIONS)
def test_operations_query_does_not_bypass_missing_native_evidence(
    setup, run_cli, resource
):
    # A reachable browser cannot waive the per-leaf release prerequisites.
    code, out, err = run_cli(["liquidity", "operations", resource, "list"])
    result = parse(out)
    assert code == 1, err
    assert result["data"] is None
    assert result["error"]["code"] == "LEAF_DISABLED"
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("resource", OPERATIONS)
def test_operations_blocker_is_discoverable_without_business_environment(
    setup, run_cli, resource
):
    setup.state.reachable = False
    help_code, help_out, help_err = run_cli(
        ["help", "liquidity", "operations", resource, "list"]
    )
    assert help_code == 0, help_err
    help_doc = parse(help_out)
    assert help_doc["kind"] == "runtimes"
    assert help_doc["summary"] == "Disabled inquiry."
    assert all(value is False for value in help_doc["effects"].values())

    code, out, err = run_cli(["describe", "liquidity", "operations", resource, "list"])
    assert code == 0, err
    guide = parse(out)["read_guide"]
    assert guide["kind"] == "runtimes"
    assert guide["release_status"] == "deferred"
    assert guide["errors"] == ["UNSUPPORTED_CAPABILITY"]
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("resource", OPERATIONS)
def test_operations_no_refresh_or_get_is_enabled_by_discovery(setup, run_cli, resource):
    for argv in (
        ["refresh", "liquidity", "operations", resource],
        ["liquidity", "operations", resource, "get"],
        ["liquidity", "operations", resource, "list", "--live"],
    ):
        code, out, _ = run_cli(argv)
        result = parse(out)
        assert code != 0
        assert result["data"] is None
        assert result["error"]["code"] in {
            "INVALID_ARGUMENT",
            "LEAF_DISABLED",
        }
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


def test_swap_unbounded_default_and_get_remain_non_executing(setup, run_cli):
    for argv, expected_code, expected_error in (
        (
            ["liquidity", "operations", "swaps", "list"],
            1,
            "CACHE_MISS",
        ),
        (
            ["refresh", "liquidity", "operations", "swaps"],
            2,
            "INVALID_ARGUMENT",
        ),
        (
            ["liquidity", "operations", "swaps", "get"],
            1,
            "LEAF_DISABLED",
        ),
    ):
        code, out, _ = run_cli(argv)
        result = parse(out)
        assert code == expected_code
        assert result["data"] is None
        assert result["error"]["code"] == expected_error
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


def test_registered_scoped_swaps_refresh_live_and_disconnected_cache_are_exact(
    setup, run_cli
):
    rows = [swap(i) for i in range(12)]
    rows[0].update({"memo": None, "errorMsg": "", "unknownAdditiveField": "keep"})
    setup.state.business_handler = swap_listing(rows)
    code, out, err = run_cli(swap_refresh("--require-complete"))
    assert code == 0, err
    refresh = parse(out)
    assert refresh["data"]["row_count"] == 12
    assert refresh["meta"]["complete"] is True
    assert refresh["meta"]["published"] is True
    assert [
        json.loads(body["swapOrderQueryVO"])["rowStart"]
        for body in setup.state.business_requests
    ] == [0, 10]
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(swap_query("--live", "--limit", "0", "--require-complete"))
    assert code == 0, err
    live = parse(out)
    assert live["data"] == rows
    assert live["meta"]["complete"] is True
    assert live["meta"]["fetched_at"] is not None
    assert live["meta"]["source_observed_from"] is None
    assert live["meta"]["source"] == "live"
    assert live["meta"]["reported_total"] == 12
    assert setup.cache_path.read_bytes() == before
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(swap_query("--limit", "0", "--require-complete"))
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == rows
    assert cached["meta"]["scope"] == refresh["meta"]["scope"]
    assert cached["meta"]["fetched_at"] == refresh["meta"]["fetched_at"]
    assert cached["meta"]["complete"] is True
    assert cached["meta"]["source"] == "cache"
    assert len(setup.state.business_requests) == count
    for entry in ("help", "describe"):
        code, out, err = run_cli([entry, "liquidity", "operations", "swaps", "list"])
        assert code == 0, err
        doc = parse(out)
        if entry == "describe":
            assert doc["read_guide"]["identity"] == ["dealId"]
            assert doc["read_guide"]["live_verified"] == "2026-10-03"
            assert (
                doc["read_guide"]["offline_profile"] == "single temporary leaf result"
            )
            assert (
                doc["data_schema"]["properties"]["nearLegCreditAmount"][
                    "x-observed-type"
                ]
                == "str"
            )
            assert doc["read_guide"]["variants"][0]["data_schema"] == doc["data_schema"]
    assert len(setup.state.business_requests) == count


def test_scoped_swaps_empty_refresh_does_not_create_slot(
    setup, run_cli, swap_candidate_catalog
):
    setup.state.business_handler = swap_listing([])
    code, out, err = run_cli(swap_query("--live", "--limit", "0"))
    assert code == 0, err
    assert parse(out)["data"] == []
    assert parse(out)["meta"]["complete"] is True
    assert not setup.cache_path.exists()
    code, out, err = run_cli(swap_refresh("--require-complete"))
    assert code == 0, err
    assert parse(out)["meta"]["published"] is False
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, _ = run_cli(swap_query("--limit", "0"))
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert not setup.cache_path.exists()
    assert len(setup.state.business_requests) == count


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["--from-date", "20260901"],
        ["--to-date", "20261001"],
        ["--from-date", "20260230", "--to-date", "20261001"],
        ["--from-date", "2026-02-30", "--to-date", "20261001"],
        ["--from-date", "20261002", "--to-date", "20261001"],
    ],
)
def test_scoped_swaps_require_valid_paired_trade_scope_before_access(
    setup, run_cli, swap_candidate_catalog, options
):
    for argv in (
        ["liquidity", "operations", "swaps", "list", *options, "--live"],
        ["refresh", "liquidity", "operations", "swaps", *options],
    ):
        code, out, _ = run_cli(argv)
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"dealId": None},
        {"dealId": ""},
        {"dealId": True},
        {"dealId": 1},
        {"tradeDate": "20261002"},
        {"tradeDate": "20260230"},
        {"tradeDate": None},
        {"tntInstId": "OTHER"},
        {"nearLegValueDate": "20260230"},
        {"nearLegCreditAmount": 1.2},
        {"nearLegCreditAmount": True},
        {"nearLegCreditAmount": "NaN"},
        {"gmtCreate": True},
        {"needReview": "false"},
    ],
)
def test_scoped_swaps_invalid_native_record_fails_and_preserves_cache(
    setup, run_cli, swap_candidate_catalog, overrides
):
    setup.state.business_handler = swap_listing([swap(0)])
    code, _, err = run_cli(swap_refresh())
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = swap_listing([swap(0, **overrides)])
    for argv in (swap_query("--live"), swap_refresh()):
        code, out, _ = run_cli(argv)
        result = parse(out)
        assert code == 1
        assert result["data"] is None
        assert result["error"]["code"] == "INVALID_RESPONSE"
        assert setup.cache_path.read_bytes() == before


def test_scoped_swaps_overlap_warns_and_strict_mode_preserves_complete_cache(
    setup, run_cli, swap_candidate_catalog
):
    setup.state.business_handler = swap_listing([swap(0)])
    code, _, err = run_cli(swap_refresh())
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    def overlap(payload, index):
        scope = json.loads(payload["swapOrderQueryVO"])
        rows = (
            [swap(i) for i in range(10)]
            if scope["rowStart"] == 0
            else [swap(0), swap(10)]
        )
        return swap_page(rows, 12)

    setup.state.business_handler = overlap
    code, out, err = run_cli(swap_query("--live", "--limit", "0"))
    result = parse(out)
    assert code == 0
    assert result["error"] is None
    assert "INCOMPLETE_RESULT" in err
    assert len(result["data"]) == 11
    assert result["meta"]["complete"] is False
    assert result["meta"]["reported_total"] == 12
    assert result["meta"]["collected_total"] == 11
    assert result["meta"]["missing_count"] == 1
    assert setup.cache_path.read_bytes() == before
    for argv in (
        swap_query("--live", "--limit", "0", "--require-complete"),
        swap_refresh("--require-complete"),
    ):
        code, out, _ = run_cli(argv)
        result = parse(out)
        assert code == 1
        assert result["data"] is None
        assert result["error"]["code"] == "INCOMPLETE_RESULT"
        assert result["meta"]["complete"] is False
        assert setup.cache_path.read_bytes() == before

    code, out, err = run_cli(swap_refresh())
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["published"] is True
    assert parse(out)["meta"]["complete"] is False
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(swap_query("--limit", "0"))
    result = parse(out)
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    assert result["meta"]["complete"] is False
    assert result["meta"]["collected_total"] == 11
    assert len(result["data"]) == 11
    assert len(setup.state.business_requests) == count


@pytest.mark.parametrize("defect", ["identity-conflict", "total-drift"])
def test_scoped_swaps_hard_pagination_failure_never_publishes_partial(
    setup, run_cli, swap_candidate_catalog, defect
):
    setup.state.business_handler = swap_listing([swap(0)])
    code, _, err = run_cli(swap_refresh())
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    def failure(payload, index):
        scope = json.loads(payload["swapOrderQueryVO"])
        if scope["rowStart"] == 0:
            return swap_page([swap(i) for i in range(10)], 12)
        if defect == "identity-conflict":
            return swap_page([swap(0, nearLegCreditAmount="999.0000"), swap(10)], 12)
        return swap_page([swap(10), swap(11)], 13)

    setup.state.business_handler = failure
    for argv in (swap_query("--live", "--limit", "0"), swap_refresh()):
        code, out, _ = run_cli(argv)
        result = parse(out)
        assert code == 1
        assert result["data"] is None
        assert result["error"]["code"] == "INVALID_RESPONSE"
        assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("failed_flag", ["outer", "inner"])
def test_scoped_swaps_business_envelope_failure_preserves_cache(
    setup, run_cli, swap_candidate_catalog, failed_flag
):
    setup.state.business_handler = swap_listing([swap(0)])
    code, _, err = run_cli(swap_refresh())
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    response = swap_page([swap(0)], 1)
    if failed_flag == "outer":
        response["body"]["resultFlag"] = False
    else:
        response["body"]["result"]["success"] = False
    setup.state.business_handler = lambda payload, index: response
    for argv in (swap_query("--live"), swap_refresh()):
        code, out, _ = run_cli(argv)
        result = parse(out)
        assert code == 1
        assert result["data"] is None
        assert result["error"]["code"] == "BUSINESS_QUERY_FAILED"
        assert setup.cache_path.read_bytes() == before


def test_scoped_swaps_empty_later_scope_preserves_last_slot(
    setup, run_cli, swap_candidate_catalog
):
    def listing(payload, index):
        scope = json.loads(payload["swapOrderQueryVO"])
        rows = [swap(0)] if scope["tradeStartDate"] == "20260901" else []
        return swap_page(rows, len(rows))

    setup.state.business_handler = listing
    code, _, err = run_cli(swap_refresh())
    assert code == 0, err
    empty_scope = ["--from-date", "20261003", "--to-date", "20261003"]
    code, out, err = run_cli(
        ["refresh", "liquidity", "operations", "swaps", *empty_scope]
    )
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is True
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(swap_query("--limit", "0"))
    assert code == 0, err
    populated = parse(out)
    assert populated["data"] == [swap(0)]
    code, out, err = run_cli(
        ["liquidity", "operations", "swaps", "list", *empty_scope, "--limit", "0"]
    )
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert len(setup.state.business_requests) == count
