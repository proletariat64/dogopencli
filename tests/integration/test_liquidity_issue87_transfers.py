"""Issue #87 transfer candidate acceptance through the existing public CLI seam.

Synthetic values follow observed native field shapes. Candidate registration
exercises public behavior while the production release gate remains closed.
"""

import json
from dataclasses import replace

import pytest

from dogopencli import catalog, helptree
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import leaves
from dogopencli.plugins.liquidity.transfer_list import RELEASED, TRANSFER_ORDERS

pytest_plugins = ["test_liquidity_cli_sit"]

TRANSACTION_SCOPE = ["--from-date", "20260901", "--to-date", "20261001"]


@pytest.fixture
def transfer_candidate_catalog(monkeypatch):
    """Candidate behavior is testable without bypassing the production gate."""
    declarations = {
        path: replace(node, children=()) for path, node in catalog.NODES.items()
    }
    leaf = leaves.ListLeaf((TRANSFER_ORDERS,))
    monkeypatch.setitem(leaves.LIST_LEAVES, TRANSFER_ORDERS.path, leaf)
    monkeypatch.delitem(
        leaves.DEFERRED_BY_PATH, (*TRANSFER_ORDERS.path, "list"), raising=False
    )
    monkeypatch.setattr(
        leaves,
        "LIST_SPECS",
        (
            *tuple(
                spec for spec in leaves.LIST_SPECS if spec.name != TRANSFER_ORDERS.name
            ),
            TRANSFER_ORDERS,
        ),
    )
    for node in (
        leaves.list_query_node(leaf),
        leaves.refresh_list_node(leaf),
        *leaves.group_nodes(),
    ):
        declarations[node.path] = node
    nodes = catalog.build_catalog(declarations.values())
    monkeypatch.setattr(catalog, "NODES", nodes)
    monkeypatch.setattr(helptree, "NODES", nodes)


def transfer(index, **overrides):
    return {
        "orderNo": f"synthetic-transfer-{index:03d}",
        "orderId": f"internal-{index}",
        "reportId": "associated-report",
        "tntInstId": "GUAPW3SG",
        "gmtCreate": "2026-10-01 08:06:29（GMT+08）",
        "gmtModified": "",
        "debitValueDate": "20260930",
        "creditValueDate": "20261001",
        "debitEntity": "entity-D",
        "creditEntity": "entity-C",
        "debitBankId": "bank-D",
        "creditBankId": "bank-C",
        "debitCurrency": "USD",
        "creditCurrency": "EUR",
        "debitAmount": "123.4500",
        "creditAmount": "111.0000",
        "orderStatus": "unknown-instruction-state",
        "receiptStatus": "unknown-bank-state",
        "executeResult": "unknown-execution-state",
        "gmtReturnFinnet": None,
        **overrides,
    }


def transfer_page(rows, total):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": total,
            "result": {"success": True, "data": rows, "count": total},
        },
    }


def transfer_listing(rows):
    def answer(payload, index):
        assert set(payload) == {"tntInstId", "transferOrderQueryRequestVO"}
        assert payload["tntInstId"] == "GUAPW3SG"
        scope = json.loads(payload["transferOrderQueryRequestVO"])
        assert set(scope) == {
            "tntInstId",
            "debitEntity",
            "creditEntity",
            "transactionStartDate",
            "transactionEndDate",
            "debitStartDate",
            "debitEndDate",
            "creditStartDate",
            "creditEndDate",
            "pageSize",
            "rowStart",
        }
        assert scope["tntInstId"] == "GUAPW3SG"
        assert scope["debitEntity"] == scope["creditEntity"] == []
        assert scope["pageSize"] == 10
        assert scope["transactionStartDate"] == "2026-09-01 00:00:00"
        assert scope["transactionEndDate"] == "2026-10-01 23:59:59"
        assert scope["debitStartDate"] == scope["debitEndDate"] == ""
        assert scope["creditStartDate"] == scope["creditEndDate"] == ""
        offset = scope["rowStart"]
        return transfer_page(rows[offset : offset + 10], len(rows))

    return answer


def transfer_query(*tail):
    return ["liquidity", "operations", "transfers", "list", *TRANSACTION_SCOPE, *tail]


def transfer_refresh(*tail):
    return [
        "refresh",
        "liquidity",
        "operations",
        "transfers",
        *TRANSACTION_SCOPE,
        *tail,
    ]


def test_registered_scoped_transfers_refresh_live_and_disconnected_cache_are_exact(
    setup, run_cli, transfer_candidate_catalog
):
    rows = [transfer(i) for i in range(12)]
    rows[0].update({"gmtReturnFinnet": 0, "creditAmount": ""})
    setup.state.business_handler = transfer_listing(rows)
    code, out, err = run_cli(transfer_refresh("--require-complete"))
    assert code == 0, err
    refresh = parse(out)
    assert refresh["data"]["row_count"] == 12
    assert refresh["meta"]["complete"] is True
    assert refresh["meta"]["published"] is True
    assert [
        json.loads(body["transferOrderQueryRequestVO"])["rowStart"]
        for body in setup.state.business_requests
    ] == [0, 10]
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(transfer_query("--live", "--all", "--require-complete"))
    assert code == 0, err
    live = parse(out)
    assert live["data"] == rows
    assert live["meta"]["complete"] is True
    assert live["meta"]["fetched_at"] is not None
    assert live["meta"]["source_observed_from"] is None
    assert live["meta"]["source"] == "live"
    assert live["meta"]["reported_total"] == 12
    assert setup.cache_path.read_bytes() == before
    setup.state.business_handler = transfer_listing([])
    code, out, err = run_cli(transfer_query("--live", "--all"))
    assert code == 0, err
    assert parse(out)["data"] == []
    assert setup.cache_path.read_bytes() == before
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(transfer_query("--all", "--require-complete"))
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == rows
    assert cached["meta"]["scope"] == refresh["meta"]["scope"]
    assert cached["meta"]["fetched_at"] == refresh["meta"]["fetched_at"]
    assert cached["meta"]["complete"] is True
    assert cached["meta"]["source"] == "cache"
    assert len(setup.state.business_requests) == count
    for entry in ("help", "describe"):
        code, out, err = run_cli(
            [entry, "liquidity", "operations", "transfers", "list"]
        )
        assert code == 0, err
        doc = parse(out)
        if entry == "describe":
            assert doc["read_guide"]["identity"] == ["orderNo"]
            assert "exact query scope" in " ".join(doc["read_guide"]["notes"])
            assert doc["read_guide"]["offline_profile"] == "history"
            assert (
                doc["data_schema"]["properties"]["creditAmount"]["x-observed-type"]
                == "str | null"
            )
            assert doc["read_guide"]["variants"][0]["data_schema"] == doc["data_schema"]
    assert len(setup.state.business_requests) == count


def test_scoped_transfers_complete_empty_capture_is_not_cache_miss(
    setup, run_cli, transfer_candidate_catalog
):
    setup.state.business_handler = transfer_listing([])
    code, out, err = run_cli(transfer_query("--live", "--all"))
    assert code == 0, err
    assert parse(out)["data"] == []
    assert parse(out)["meta"]["complete"] is True
    assert not setup.cache_path.exists()
    code, out, err = run_cli(transfer_refresh("--require-complete"))
    assert code == 0, err
    assert parse(out)["meta"]["published"] is True
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(transfer_query("--all", "--require-complete"))
    assert code == 0, err
    result = parse(out)
    assert result["data"] == []
    assert result["error"] is None
    assert result["meta"]["complete"] is True
    assert result["meta"]["reported_total"] == 0
    assert result["meta"]["retained_coverage"][0]["row_count"] == 0
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
def test_scoped_transfers_require_valid_paired_trade_scope_before_access(
    setup, run_cli, transfer_candidate_catalog, options
):
    for argv in (
        ["liquidity", "operations", "transfers", "list", *options, "--live"],
        ["refresh", "liquidity", "operations", "transfers", *options],
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
        {"orderNo": None},
        {"orderNo": ""},
        {"orderNo": True},
        {"orderNo": 1},
        {"tntInstId": "OTHER"},
        {"creditAmount": 1.2},
        {"creditAmount": True},
        {"creditAmount": "NaN"},
        {"gmtCreate": True},
        {"gmtReturnFinnet": "0"},
        {"gmtReturnFinnet": True},
    ],
)
def test_scoped_transfers_invalid_native_record_fails_and_preserves_cache(
    setup, run_cli, transfer_candidate_catalog, overrides
):
    setup.state.business_handler = transfer_listing([transfer(0)])
    code, _, err = run_cli(transfer_refresh())
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = transfer_listing([transfer(0, **overrides)])
    for argv in (transfer_query("--live"), transfer_refresh()):
        code, out, _ = run_cli(argv)
        result = parse(out)
        assert code == 1
        assert result["data"] is None
        assert result["error"]["code"] == "INVALID_RESPONSE"
        assert setup.cache_path.read_bytes() == before


def test_scoped_transfers_overlap_warns_and_strict_mode_preserves_complete_cache(
    setup, run_cli, transfer_candidate_catalog
):
    setup.state.business_handler = transfer_listing([transfer(0)])
    code, _, err = run_cli(transfer_refresh())
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    def overlap(payload, index):
        scope = json.loads(payload["transferOrderQueryRequestVO"])
        rows = (
            [transfer(i) for i in range(10)]
            if scope["rowStart"] == 0
            else [transfer(0), transfer(10)]
        )
        return transfer_page(rows, 12)

    setup.state.business_handler = overlap
    code, out, err = run_cli(transfer_query("--live", "--all"))
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
        transfer_query("--live", "--all", "--require-complete"),
        transfer_refresh("--require-complete"),
    ):
        code, out, _ = run_cli(argv)
        result = parse(out)
        assert code == 1
        assert result["data"] is None
        assert result["error"]["code"] == "INCOMPLETE_RESULT"
        assert result["meta"]["complete"] is False
        assert setup.cache_path.read_bytes() == before

    code, out, err = run_cli(transfer_refresh())
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["published"] is True
    assert parse(out)["meta"]["complete"] is False
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(transfer_query("--all"))
    result = parse(out)
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    assert result["meta"]["complete"] is False
    assert result["meta"]["collected_total"] == 11
    assert len(result["data"]) == 11
    assert len(setup.state.business_requests) == count


@pytest.mark.parametrize("defect", ["identity-conflict", "total-drift"])
def test_scoped_transfers_hard_pagination_failure_never_publishes_partial(
    setup, run_cli, transfer_candidate_catalog, defect
):
    setup.state.business_handler = transfer_listing([transfer(0)])
    code, _, err = run_cli(transfer_refresh())
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    def failure(payload, index):
        scope = json.loads(payload["transferOrderQueryRequestVO"])
        if scope["rowStart"] == 0:
            return transfer_page([transfer(i) for i in range(10)], 12)
        if defect == "identity-conflict":
            return transfer_page(
                [transfer(0, creditAmount="999.0000"), transfer(10)], 12
            )
        return transfer_page([transfer(10), transfer(11)], 13)

    setup.state.business_handler = failure
    for argv in (transfer_query("--live", "--all"), transfer_refresh()):
        code, out, _ = run_cli(argv)
        result = parse(out)
        assert code == 1
        assert result["data"] is None
        assert result["error"]["code"] == "INVALID_RESPONSE"
        assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("failed_flag", ["outer", "inner"])
def test_scoped_transfers_business_envelope_failure_preserves_cache(
    setup, run_cli, transfer_candidate_catalog, failed_flag
):
    setup.state.business_handler = transfer_listing([transfer(0)])
    code, _, err = run_cli(transfer_refresh())
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    response = transfer_page([transfer(0)], 1)
    if failed_flag == "outer":
        response["body"]["resultFlag"] = False
    else:
        response["body"]["result"]["success"] = False
    setup.state.business_handler = lambda payload, index: response
    for argv in (transfer_query("--live"), transfer_refresh()):
        code, out, _ = run_cli(argv)
        result = parse(out)
        assert code == 1
        assert result["data"] is None
        assert result["error"]["code"] == "BUSINESS_QUERY_FAILED"
        assert setup.cache_path.read_bytes() == before


def test_scoped_transfers_distinct_date_scopes_keep_independent_captures(
    setup, run_cli, transfer_candidate_catalog
):
    def listing(payload, index):
        scope = json.loads(payload["transferOrderQueryRequestVO"])
        rows = (
            [transfer(0)]
            if scope["transactionStartDate"] == "2026-09-01 00:00:00"
            else []
        )
        return transfer_page(rows, len(rows))

    setup.state.business_handler = listing
    code, _, err = run_cli(transfer_refresh())
    assert code == 0, err
    empty_scope = ["--from-date", "20261003", "--to-date", "20261003"]
    code, out, err = run_cli(
        ["refresh", "liquidity", "operations", "transfers", *empty_scope]
    )
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is True
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(transfer_query("--all"))
    assert code == 0, err
    populated = parse(out)
    assert populated["data"] == [transfer(0)]
    code, out, err = run_cli(
        ["liquidity", "operations", "transfers", "list", *empty_scope, "--all"]
    )
    assert code == 0, err
    empty = parse(out)
    assert empty["data"] == []
    assert empty["meta"]["complete"] is True
    assert empty["meta"]["scope"] != populated["meta"]["scope"]
    assert len(setup.state.business_requests) == count


def test_transfer_registration_matches_release_evidence(setup, run_cli):
    released = TRANSFER_ORDERS.name in RELEASED
    assert (TRANSFER_ORDERS.path in leaves.LIST_LEAVES) is released
    assert ((*TRANSFER_ORDERS.path, "list") in leaves.DEFERRED_BY_PATH) is not released
    if released:
        code, out, err = run_cli(
            ["describe", "liquidity", "operations", "transfers", "list"]
        )
        assert code == 0, err
        assert parse(out)["read_guide"]["identity"] == ["orderNo"]
        assert setup.state.business_requests == []
        return
    code, out, _ = run_cli(["liquidity", "operations", "transfers", "list"])
    assert code == 1
    assert parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert setup.state.business_requests == []


def test_transfer_projection_excludes_sensitive_and_additive_fields(
    setup, run_cli, transfer_candidate_catalog
):
    native = transfer(
        0,
        debitAccountNo="private-account",
        creditAccountName="private-name",
        debitAliasName="private-alias",
        operator="private-operator",
        memo="private-free-text",
        paymentDetail="private-free-text",
        transFerOrderLogVoList=[{"content": "private-log"}],
        contactInfoList=[{"emailAddress": "private-contact"}],
        unknownAdditiveField="unverified-field",
    )
    setup.state.business_handler = transfer_listing([native])
    assert run_cli(transfer_refresh())[0] == 0
    setup.state.reachable = False
    code, out, err = run_cli(transfer_query("--all"))
    assert code == 0, err
    assert parse(out)["data"] == [transfer(0)]
    assert b"private-" not in setup.cache_path.read_bytes()


def test_transfer_list_refresh_keeps_existing_detail_cache_independent(
    setup, run_cli, transfer_candidate_catalog
):
    detail = {"orderNo": "synthetic-transfer-000", "nativeDetailOnly": "retained"}
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"baseResult": {"success": True, "data": detail}},
    }
    detail_refresh = [
        "refresh",
        "liquidity",
        "operations",
        "transfers",
        "detail",
        "get",
        "--order-no",
        detail["orderNo"],
    ]
    detail_query = [
        "liquidity",
        "operations",
        "transfers",
        "get",
        "--order-no",
        detail["orderNo"],
    ]
    code, _, err = run_cli(detail_refresh)
    assert code == 0, err
    code, out, err = run_cli(detail_query)
    assert code == 0, err
    before = parse(out)
    setup.state.business_handler = transfer_listing([transfer(0)])
    code, _, err = run_cli(transfer_refresh())
    assert code == 0, err
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(detail_query)
    assert code == 0, err
    after = parse(out)
    assert after["data"] == before["data"] == detail
    assert after["meta"]["detail_fetched_at"] == before["meta"]["detail_fetched_at"]
    assert len(setup.state.business_requests) == count


@pytest.mark.parametrize("defect", ["count-disagreement", "malformed", "permission"])
def test_transfer_hard_response_errors_preserve_old_cache(
    setup, run_cli, transfer_candidate_catalog, defect
):
    setup.state.business_handler = transfer_listing([transfer(0)])
    assert run_cli(transfer_refresh())[0] == 0
    before = setup.cache_path.read_bytes()
    response = transfer_page([transfer(0)], 1)
    if defect == "count-disagreement":
        response["body"]["count"] = 2
    elif defect == "malformed":
        response["body"]["result"]["data"] = {}
    else:
        response = {"status": 403, "body": {}}
    setup.state.business_handler = lambda payload, index: response
    for argv in (transfer_query("--live"), transfer_refresh()):
        code, out, _ = run_cli(argv)
        assert code == 1
        assert parse(out)["data"] is None
        assert parse(out)["error"]["code"] in {
            "INVALID_RESPONSE",
            "BUSINESS_QUERY_FAILED",
        }
        assert setup.cache_path.read_bytes() == before


def test_transfer_auth_expiry_preserves_old_cache(
    setup, run_cli, transfer_candidate_catalog
):
    from fake_cdp import SSO_URL
    from test_liquidity_cli_sit import LIQUIDITY_URL, route_probes

    setup.state.business_handler = transfer_listing([transfer(0)])
    assert run_cli(transfer_refresh())[0] == 0
    before = setup.cache_path.read_bytes()
    route_probes(setup.state, (LIQUIDITY_URL, LIQUIDITY_URL, SSO_URL))
    setup.state.business_handler = lambda payload, index: {"error": "AbortError"}
    code, out, _ = run_cli(transfer_refresh())
    assert code == 1
    assert parse(out)["error"]["code"] == "AUTH_REQUIRED"
    assert setup.cache_path.read_bytes() == before
