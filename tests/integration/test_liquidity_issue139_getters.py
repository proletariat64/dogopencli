"""Qualified inquiry objects through public CLI, fake CDP and real SQLite."""

from decimal import Decimal

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]


def rfq(identity="SYN-CHILD"):
    return {
        "success": True,
        "data": {
            "inquiryTaskId": identity,
            "inquiryType": "TARGET_RFQ",
            "currency": "USD",
            "ticketSize": Decimal("0.1234567890123456789"),
            "inquiryMemo": "synthetic memo",
            "inquiryOrderListVOList": [
                {
                    "inquiryId": "SYN-INQUIRY",
                    "quotationNum": "0",
                    "inquiryStatus": "UNKNOWN",
                    "inquiryTime": None,
                }
            ],
        },
    }


def command(refresh=False, identity="SYN-CHILD"):
    path = ["liquidity", "investment", "rfqs"]
    return [
        *(["refresh", *path, "detail"] if refresh else path),
        "get",
        "--inquiry-sub-task-id",
        identity,
    ]


def test_rfq_child_native_request_and_offline_roundtrip(setup, run_cli):
    native = rfq()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, err = run_cli(command(True))
    assert code == 0, (out, err)
    assert setup.state.business_requests == [{"inquiryTaskId": "SYN-CHILD"}]
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any(
        "/rfq/subInquiryTask/queryInquiryTaskDetail.json" in e and 'method: "GET"' in e
        for e in expressions
    )
    setup.state.running = False
    code, out, err = run_cli(command())
    assert code == 0, (out, err)
    expected = {
        key: value for key, value in native["data"].items() if key != "inquiryMemo"
    }
    assert parse(out)["data"] == expected
    assert "synthetic memo" not in out
    assert "0.1234567890123456789" in out


def quotas():
    return {
        "resultFlag": True,
        "result": {
            "success": True,
            "count": 0,
            "data": {
                "dynamicQuotas": [
                    {
                        "dateRange": {"begin": 1, "end": 2},
                        "individualLimit": {
                            "currency": "USD",
                            "hasLimit": True,
                            "limit": Decimal("0.1234567890123456789"),
                        },
                    }
                ],
                "staticQuotas": [
                    {"quotaId": "", "currency": "USD", "usedQuota": "0.0000"},
                    {"quotaId": "", "currency": "USD", "usedQuota": "0.0000"},
                ],
            },
        },
    }


def quota_command(refresh=False, alias="SYN-ALIAS", route="SYN-ROUTE"):
    path = ["liquidity", "network", "route-quotas"]
    return [
        *(["refresh", *path, "detail"] if refresh else path),
        "get",
        "--route-id",
        route,
        "--account-alias",
        alias,
    ]


def test_quotas_context_aggregate_preserves_duplicates_and_metadata(setup, run_cli):
    native = quotas()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, err = run_cli(quota_command(True))
    assert code == 0, (out, err)
    assert setup.state.business_requests == [
        {"routeId": "SYN-ROUTE", "aliasName": "SYN-ALIAS", "tntInstId": "GUAPW3SG"}
    ]
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any(
        "https://iliquidity.alipay.com/queryWhaleRouteDetail.json" in e
        and 'method: "GET"' in e
        for e in expressions
    )
    assert parse(out)["meta"]["request_scope"] == setup.state.business_requests[0]
    setup.state.running = False
    code, out, err = run_cli(quota_command())
    assert code == 0, (out, err)
    result = parse(out)
    assert result["data"] == native["result"]["data"]
    assert result["meta"]["native_context_echo"] == {
        "routeId": "absent",
        "aliasName": "absent",
        "tntInstId": "absent",
    }
    assert result["meta"]["complete"] is True
    assert result["meta"]["request_scope"] == setup.state.business_requests[0]
    assert "0.1234567890123456789" in out
    assert "routeId" not in result["data"]


@pytest.mark.parametrize("path", [("investment", "rfqs"), ("network", "route-quotas")])
def test_getter_description_declares_nested_native_schema(setup, run_cli, path):
    code, out, err = run_cli(["describe", "liquidity", *path, "get"])
    assert code == 0, (out, err)
    described = parse(out)
    schema = described["data_schema"]
    assert schema["additionalProperties"] is False
    assert described["read_guide"]["live_verified"] == "2026-10-07"
    if path[0] == "investment":
        properties = schema["properties"]
        assert properties["inquiryTaskId"]["x-observed-type"] == "str"
        assert "child" in properties["inquiryTaskId"]["description"]
        orders = properties["inquiryOrderListVOList"]["items"]
        assert orders["properties"]["inquiryId"]["x-observed-type"] == "str"
        assert "processId" not in orders["properties"]
        assert "inquiryMemo" not in properties
    else:
        assert schema["required"] == ["dynamicQuotas", "staticQuotas"]
        assert "quotaId" in schema["properties"]["staticQuotas"]["items"]["properties"]
        assert described["read_guide"]["identity"] == ["routeId", "aliasName"]
    assert setup.state.transports == []


LEAVES = ((command, rfq), (quota_command, quotas))


@pytest.mark.parametrize("leaf", LEAVES)
def test_offline_miss_live_isolation_and_refresh_failure_preserves_cache(
    setup, run_cli, leaf
):
    invoke, factory = leaf
    code, out, _ = run_cli(invoke())
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert "detail get" in out
    assert setup.state.transports == []
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(),
    }
    assert run_cli(invoke(True))[0] == 0
    code, out, err = run_cli(invoke())
    assert code == 0, (out, err)
    cached = parse(out)
    prior = setup.cache_path.read_bytes()
    code, out, err = run_cli([*invoke(), "--live", "--require-complete"])
    assert code == 0, (out, err)
    assert parse(out)["meta"]["source"] == "live"
    assert setup.cache_path.read_bytes() == prior
    setup.state.business_handler = lambda payload, index: {"status": 401, "body": {}}
    for args in (invoke(True), [*invoke(), "--live"]):
        code, out, _ = run_cli(args)
        assert code == 1 and parse(out)["error"]["code"] == "AUTH_REQUIRED"
        assert parse(out)["data"] is None
        assert setup.cache_path.read_bytes() == prior
    setup.state.running = False
    assert parse(run_cli(invoke())[1])["data"] == cached["data"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("inquiryTaskId", "SYN-PARENT"),
        ("inquiryTaskId", 7),
        ("inquiryType", "OTHER"),
        ("inquiryOrderListVOList", None),
        ("inquiryOrderListVOList", {}),
        ("inquiryOrderListVOList", [{"inquiryId": ""}]),
        ("inquiryOrderListVOList", [{"inquiryId": 7}]),
        ("inquiryOrderListVOList", [{"inquiryId": "DUP"}, {"inquiryId": "DUP"}]),
    ],
)
def test_rfq_hard_identity_and_member_failures_preserve_valid_cache(
    setup, run_cli, field, value
):
    native = rfq()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(command(True))[0] == 0
    prior = setup.cache_path.read_bytes()
    native["data"][field] = value
    code, out, _ = run_cli(command(True))
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == prior


@pytest.mark.parametrize(
    "field,value",
    [
        ("dynamicQuotas", None),
        ("staticQuotas", {}),
        ("staticQuotas", [None]),
        ("routeId", "OTHER"),
        ("aliasName", "OTHER"),
        ("tntInstId", "OTHER"),
        ("aliasName", 7),
    ],
)
def test_quota_malformed_arrays_and_conflicting_echoes_preserve_cache(
    setup, run_cli, field, value
):
    native = quotas()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(quota_command(True))[0] == 0
    prior = setup.cache_path.read_bytes()
    native["result"]["data"][field] = value
    code, out, _ = run_cli(quota_command(True))
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == prior


@pytest.mark.parametrize("missing", ["dynamicQuotas", "staticQuotas"])
def test_quota_missing_component_is_never_fabricated_empty(setup, run_cli, missing):
    native = quotas()
    del native["result"]["data"][missing]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, _ = run_cli([*quota_command(), "--live"])
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("marker", ["false", "missing", "numeric", "inner-missing"])
def test_quota_strict_success_markers(setup, run_cli, marker):
    native = quotas()
    if marker == "false":
        native["result"]["success"] = False
    elif marker == "missing":
        del native["resultFlag"]
    elif marker == "numeric":
        native["resultFlag"] = 1
    else:
        del native["result"]["success"]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, _ = run_cli([*quota_command(), "--live"])
    assert code == 1
    assert parse(out)["error"]["code"] == (
        "INVALID_RESPONSE" if marker == "inner-missing" else "BUSINESS_QUERY_FAILED"
    )


def test_quota_scopes_do_not_collide_and_both_empty_components_are_valid(
    setup, run_cli
):
    contexts = [("SYN-A", "SYN-R1"), ("SYN-B", "SYN-R1"), ("SYN-A", "SYN-R2")]
    for index, (alias, route) in enumerate(contexts):
        native = quotas()
        native["result"]["data"]["staticQuotas"][0]["usedQuota"] = str(index)
        setup.state.business_handler = lambda payload, count, native=native: {
            "status": 200,
            "body": native,
        }
        assert run_cli(quota_command(True, alias, route))[0] == 0
    setup.state.running = False
    requests = len(setup.state.business_requests)
    for index, (alias, route) in enumerate(contexts):
        code, out, err = run_cli(quota_command(False, alias, route))
        assert code == 0, (out, err)
        assert parse(out)["data"]["staticQuotas"][0]["usedQuota"] == str(index)
    assert len(setup.state.business_requests) == requests
    setup.state.running = True
    native = quotas()
    native["result"]["data"] = {"dynamicQuotas": [], "staticQuotas": []}
    setup.state.business_handler = lambda payload, count: {
        "status": 200,
        "body": native,
    }
    code, out, err = run_cli([*quota_command(), "--live"])
    assert code == 0, (out, err)
    assert parse(out)["data"] == native["result"]["data"]


@pytest.mark.parametrize("invoke", [command, quota_command])
@pytest.mark.parametrize(
    "extra",
    [
        ["--id", "x"],
        ["--all"],
        ["--limit", "1"],
        ["--offset", "0"],
        ["--endpoint", "/x"],
    ],
)
def test_unknown_options_rejected_before_browser(setup, run_cli, invoke, extra):
    code, out, _ = run_cli([*invoke(), *extra])
    assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


@pytest.mark.parametrize(
    "invoke",
    [
        lambda: command(True, ""),
        lambda: quota_command(True, ""),
        lambda: quota_command(True, route=" "),
    ],
)
def test_blank_identity_rejected_before_browser(setup, run_cli, invoke):
    code, out, _ = run_cli(invoke())
    assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


def test_routes_remains_unsupported_and_quota_help_declares_exact_context(
    setup, run_cli
):
    code, out, _ = run_cli(["liquidity", "network", "routes", "get"])
    assert code == 1 and parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    code, out, err = run_cli(["help", "liquidity", "network", "route-quotas", "get"])
    assert code == 0, (out, err)
    assert "--route-id" in out and "--account-alias" in out
    assert setup.state.transports == []


@pytest.mark.parametrize("leaf", LEAVES)
def test_list_and_detail_refreshes_remain_independent(setup, run_cli, leaf):
    invoke, factory = leaf
    if invoke is command:
        from test_liquidity_rfqs_cli_sit import query, refresh, response, subtask

        row = subtask("SYN-CHILD")
    else:
        from test_liquidity_realtime_network_cli_sit import (
            network,
            query,
            refresh,
            response,
        )

        row = network()
    setup.state.business_handler = lambda payload, index: response([row])
    assert run_cli(refresh())[0] == 0
    parent = parse(run_cli(query())[1])
    requests = len(setup.state.business_requests)
    transports = len(setup.state.transports)
    code, out, _ = run_cli(invoke())
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert len(setup.state.business_requests) == requests
    assert len(setup.state.transports) == transports
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(),
    }
    assert run_cli(invoke(True))[0] == 0
    parent_after = parse(run_cli(query())[1])
    assert parent_after["data"] == parent["data"]
    assert parent_after["meta"]["snapshot_id"] == parent["meta"]["snapshot_id"]
    detail = parse(run_cli(invoke())[1])
    setup.state.business_handler = lambda payload, index: response([])
    assert run_cli(refresh())[0] == 0
    setup.state.running = False
    assert parse(run_cli(query())[1])["data"] == []
    detail_after = parse(run_cli(invoke())[1])
    assert detail_after["data"] == detail["data"]
    assert (
        detail_after["meta"]["detail_fetched_at"] == detail["meta"]["detail_fetched_at"]
    )


@pytest.mark.parametrize(
    "leaf,path",
    [
        (LEAVES[0], ("investment", "rfqs", "get")),
        (LEAVES[1], ("network", "route-quotas", "get")),
    ],
)
def test_schema_version_change_is_offline_cache_miss(
    setup, run_cli, monkeypatch, leaf, path
):
    from dataclasses import replace

    from dogopencli.plugins.liquidity.leaves import DETAIL_LEAVES, DetailLeaf

    invoke, factory = leaf
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(),
    }
    assert run_cli(invoke(True))[0] == 0
    original = DETAIL_LEAVES[path]
    monkeypatch.setitem(
        DETAIL_LEAVES,
        path,
        DetailLeaf(replace(original.spec, schema_version="synthetic-next")),
    )
    prior = setup.cache_path.read_bytes()
    requests = len(setup.state.business_requests)
    setup.state.running = False
    code, out, _ = run_cli(invoke())
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert len(setup.state.business_requests) == requests
    assert setup.cache_path.read_bytes() == prior
    monkeypatch.setitem(DETAIL_LEAVES, path, original)
    assert run_cli(invoke())[0] == 0


def test_rfq_public_projection_excludes_free_text_and_workflow_identity(setup, run_cli):
    native = rfq()
    native["data"]["inquiryOrderListVOList"][0]["processId"] = "PRIVATE-PROCESS"
    native["data"]["inquiryOrderListVOList"][0]["bankId"] = "SYN-BANK"
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(command(True))[0] == 0
    code, out, err = run_cli(command())
    assert code == 0, (out, err)
    assert "synthetic memo" not in out and "PRIVATE-PROCESS" not in out
    assert parse(out)["data"]["inquiryOrderListVOList"][0]["bankId"] == "SYN-BANK"


def test_quota_native_matching_blank_null_echoes_stay_native(setup, run_cli):
    native = quotas()
    native["result"]["data"].update(routeId="SYN-ROUTE", aliasName="", tntInstId=None)
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, err = run_cli([*quota_command(), "--live"])
    assert code == 0, (out, err)
    result = parse(out)
    assert result["data"]["routeId"] == "SYN-ROUTE"
    assert result["data"]["aliasName"] == ""
    assert result["data"]["tntInstId"] is None
    assert set(result["meta"]["native_context_echo"].values()) == {"present"}


@pytest.mark.parametrize("leaf", LEAVES)
def test_policies_fields_and_table_remain_available(setup, run_cli, leaf):
    invoke, factory = leaf
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(),
    }
    assert run_cli(invoke(True))[0] == 0
    field = "inquiryTaskId" if invoke is command else "dynamicQuotas"
    code, out, err = run_cli(
        [*invoke(), "--require-fresh", "--require-complete", "--fields", field]
    )
    assert code == 0, (out, err)
    assert list(parse(out)["data"]) == [field]
    assert run_cli([*invoke(), "--format", "table"])[0] == 0


@pytest.mark.parametrize(
    "document",
    [
        {"success": False, "data": {}},
        {"success": 1, "data": {}},
        {"data": {}},
        {"success": True, "data": None},
    ],
)
def test_rfq_business_marker_and_null_success_refuse_without_not_found(
    setup, run_cli, document
):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": document,
    }
    code, out, _ = run_cli([*command(), "--live"])
    assert code == 1
    assert parse(out)["error"]["code"] == (
        "INVALID_RESPONSE"
        if document.get("success") is True
        else "BUSINESS_QUERY_FAILED"
    )
    assert parse(out)["data"] is None


@pytest.mark.parametrize("leaf", LEAVES)
def test_browser_failure_never_falls_back_to_valid_capture(setup, run_cli, leaf):
    invoke, factory = leaf
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(),
    }
    assert run_cli(invoke(True))[0] == 0
    prior = setup.cache_path.read_bytes()
    setup.state.running = False
    code, out, _ = run_cli([*invoke(), "--live"])
    assert code == 1 and parse(out)["error"]["code"] == "BROWSER_UNAVAILABLE"
    assert parse(out)["data"] is None
    assert setup.cache_path.read_bytes() == prior
