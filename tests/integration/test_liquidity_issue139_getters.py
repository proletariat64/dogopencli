"""Qualified inquiry objects through public CLI, fake CDP and real SQLite."""

from decimal import Decimal

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]


@pytest.fixture(autouse=True)
def native_details_do_not_create_cache(setup, request):
    yield
    if request.node.originalname not in {
        "test_populated_parent_list_does_not_substitute_native_get",
        "test_native_get_does_not_touch_parent_list_cache",
        "test_asset_list_cache_cannot_satisfy_or_be_changed_by_native_get",
    }:
        assert not setup.cache_path.exists()


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


def command(identity="SYN-CHILD"):
    return ["liquidity", "investment", "rfqs", "get", "--inquiry-sub-task-id", identity]


def test_rfq_child_native_request_and_precision(setup, run_cli):
    native = rfq()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, err = run_cli(command())
    assert code == 0, (out, err)
    assert setup.state.business_requests == [{"inquiryTaskId": "SYN-CHILD"}]
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any(
        "/rfq/subInquiryTask/queryInquiryTaskDetail.json" in e and 'method: "GET"' in e
        for e in expressions
    )
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


def quota_command(alias="SYN-ALIAS", route="SYN-ROUTE"):
    return [
        "liquidity",
        "network",
        "route-quotas",
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
    code, out, err = run_cli(quota_command())
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
def test_native_get_and_auth_failure_never_publish(setup, run_cli, leaf):
    invoke, factory = leaf
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(),
    }
    code, out, err = run_cli([*invoke()])
    assert code == 0, (out, err)
    assert parse(out)["meta"]["source"] == "live"
    assert not setup.cache_path.exists()
    setup.state.business_handler = lambda payload, index: {"status": 401, "body": {}}
    code, out, _ = run_cli(invoke())
    assert code == 1 and parse(out)["error"]["code"] == "AUTH_REQUIRED"
    assert parse(out)["data"] is None
    assert not setup.cache_path.exists()


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
def test_rfq_hard_identity_and_member_failures_refuse_invalid_response(
    setup, run_cli, field, value
):
    native = rfq()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(command())[0] == 0
    assert not setup.cache_path.exists()
    native["data"][field] = value
    code, out, _ = run_cli(command())
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


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
def test_quota_malformed_arrays_and_conflicting_echoes_refuse_invalid_response(
    setup, run_cli, field, value
):
    native = quotas()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(quota_command())[0] == 0
    assert not setup.cache_path.exists()
    native["result"]["data"][field] = value
    code, out, _ = run_cli(quota_command())
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("missing", ["dynamicQuotas", "staticQuotas"])
def test_quota_missing_component_is_never_fabricated_empty(setup, run_cli, missing):
    native = quotas()
    del native["result"]["data"][missing]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, _ = run_cli([*quota_command()])
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
    code, out, _ = run_cli([*quota_command()])
    assert code == 1
    assert parse(out)["error"]["code"] == (
        "INVALID_RESPONSE" if marker == "inner-missing" else "BUSINESS_QUERY_FAILED"
    )


def test_quotas_use_each_compound_native_context_and_empty_components_are_valid(
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
        code, out, err = run_cli(quota_command(alias, route))
        assert code == 0, (out, err)
        assert parse(out)["data"]["staticQuotas"][0]["usedQuota"] == str(index)
        assert setup.state.business_requests[-1] == {
            "routeId": route,
            "aliasName": alias,
            "tntInstId": "GUAPW3SG",
        }
    native = quotas()
    native["result"]["data"] = {"dynamicQuotas": [], "staticQuotas": []}
    setup.state.business_handler = lambda payload, count: {
        "status": 200,
        "body": native,
    }
    code, out, err = run_cli(quota_command())
    assert code == 0, (out, err)
    assert parse(out)["data"] == native["result"]["data"]
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("invoke", [command, quota_command])
@pytest.mark.parametrize(
    "extra",
    [
        ["--id", "x"],
        ["--live"],
        ["--require-fresh"],
        ["--require-complete"],
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
        lambda: command(""),
        lambda: quota_command(""),
        lambda: quota_command(route=" "),
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
def test_native_get_does_not_touch_parent_list_cache(setup, run_cli, leaf):
    invoke, factory = leaf
    if invoke is command:
        from test_liquidity_rfqs_cli_sit import refresh, response, subtask

        row = subtask("SYN-CHILD")
    else:
        from test_liquidity_realtime_network_cli_sit import network, refresh, response

        row = network()
    setup.state.business_handler = lambda payload, index: response([row])
    assert run_cli(refresh())[0] == 0
    prior = setup.cache_path.read_bytes()
    count = len(setup.state.business_requests)
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(),
    }
    code, out, err = run_cli(invoke())
    assert code == 0, (out, err)
    assert parse(out)["meta"]["source"] == "live"
    assert len(setup.state.business_requests) == count + 1
    assert setup.cache_path.read_bytes() == prior


def test_rfq_public_projection_excludes_free_text_and_workflow_identity(setup, run_cli):
    native = rfq()
    native["data"]["inquiryOrderListVOList"][0]["processId"] = "PRIVATE-PROCESS"
    native["data"]["inquiryOrderListVOList"][0]["bankId"] = "SYN-BANK"
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(command())[0] == 0
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
    code, out, err = run_cli([*quota_command()])
    assert code == 0, (out, err)
    result = parse(out)
    assert result["data"]["routeId"] == "SYN-ROUTE"
    assert result["data"]["aliasName"] == ""
    assert result["data"]["tntInstId"] is None
    assert set(result["meta"]["native_context_echo"].values()) == {"present"}


@pytest.mark.parametrize("leaf", LEAVES)
def test_fields_and_table_remain_available(setup, run_cli, leaf):
    invoke, factory = leaf
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(),
    }
    assert run_cli(invoke())[0] == 0
    field = "inquiryTaskId" if invoke is command else "dynamicQuotas"
    code, out, err = run_cli([*invoke(), "--fields", field])
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
    code, out, _ = run_cli([*command()])
    assert code == 1
    assert parse(out)["error"]["code"] == (
        "INVALID_RESPONSE"
        if document.get("success") is True
        else "BUSINESS_QUERY_FAILED"
    )
    assert parse(out)["data"] is None


@pytest.mark.parametrize("leaf", LEAVES)
def test_browser_failure_never_replays_previous_native_result(setup, run_cli, leaf):
    invoke, factory = leaf
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(),
    }
    assert run_cli(invoke())[0] == 0
    assert not setup.cache_path.exists()
    setup.state.running = False
    code, out, _ = run_cli([*invoke()])
    assert code == 1 and parse(out)["error"]["code"] == "BROWSER_UNAVAILABLE"
    assert parse(out)["data"] is None
    assert not setup.cache_path.exists()


def test_quota_future_native_member_fields_survive_native_projection(setup, run_cli):
    native = quotas()
    data = native["result"]["data"]
    data["dynamicQuotas"][0]["futureNativeScope"] = {
        "value": "0.00000100",
        "items": [None, 0, ""],
    }
    data["staticQuotas"][0]["futureNativeLimit"] = Decimal("0.123456789012345678901")
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, err = run_cli([*quota_command()])
    assert code == 0, (out, err)
    assert parse(out)["data"] == data
    assert parse(out)["meta"]["native_context_echo"] == dict.fromkeys(
        ("routeId", "aliasName", "tntInstId"), "absent"
    )
    assert run_cli(quota_command())[0] == 0
    code, out, err = run_cli(quota_command())
    assert code == 0, (out, err)
    assert parse(out)["data"] == data
    assert "routeId" not in parse(out)["data"]
    code, out, err = run_cli(
        ["describe", "liquidity", "network", "route-quotas", "get"]
    )
    assert code == 0, (out, err)
    properties = parse(out)["data_schema"]["properties"]
    assert properties["dynamicQuotas"]["items"]["additionalProperties"] is True
    assert properties["staticQuotas"]["items"]["additionalProperties"] is True
