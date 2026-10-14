"""Three independently requested native objects through CLI, fake CDP and SQLite."""

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


def demand(identity="SYN-TASK"):
    return {
        "resultFlag": True,
        "result": {
            "success": True,
            "riskActionVO": {
                "taskId": identity,
                "tntInstId": "",
                "source": "FUND_REQUIRE",
                "amount": "1.230000",
                "decisionAmount": None,
                "operationAmount": 0,
                "instructionStatus": "unknown",
                "createTime": "2026-10-07 01:02:03",
                "updateTime": "2026-10-07 04:05:06",
                "accountNo": "PRIVATE",
                "decisionReports": [{"tntInstId": "GUAPW3SG", "operator": "PRIVATE"}],
            },
        },
    }


def command(identity="SYN-TASK"):
    return ["liquidity", "operations", "demands", "get", "--task-id", identity]


def test_demand_native_get_preserves_projected_record(setup, run_cli):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": demand(),
    }
    code, out, err = run_cli(command())
    assert code == 0, (out, err)
    assert setup.state.business_requests == [
        {"tntInstId": "GUAPW3SG", "taskId": "SYN-TASK"}
    ]
    code, out, err = run_cli(command())
    assert code == 0, (out, err)
    result = parse(out)
    expected = demand()["result"]["riskActionVO"]
    del expected["accountNo"]
    del expected["decisionReports"]
    assert result["data"] == expected
    assert result["meta"]["source"] == "live"
    assert "PRIVATE" not in out


def test_network_get_is_native_unpinned_settings(setup, run_cli):
    native = {
        "id": "SYN-NET",
        "routeId": "SYN-ROUTE",
        "version": 7,
        "singlePaymentLimit": "0.000000100",
        "networkStatus": "UNKNOWN",
        "operationTime": None,
        "successRate": "PRIVATE",
        "operator": "PRIVATE",
    }
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": native},
    }
    path = ["liquidity", "network", "realtime"]
    code, out, err = run_cli([*path, "get", "--network-id", "SYN-NET"])
    assert code == 0, (out, err)
    assert setup.state.business_requests == [{"id": "SYN-NET"}]
    code, out, err = run_cli([*path, "get", "--network-id", "SYN-NET"])
    assert code == 0, (out, err)
    result = parse(out)
    assert result["data"] == {
        **{
            key: value
            for key, value in native.items()
            if key not in ("successRate", "operator")
        },
        "operationHistory": None,
        "routeDetails": None,
    }
    assert result["meta"]["kind"] == "settings"
    assert result["meta"]["source_version"] == 7


def quotation(identity="SYN-QUOTE"):
    return {
        "baseResult": {
            "success": True,
            "data": {
                "quotationDetail": {
                    "quotationId": identity,
                    "bankId": "SYN-BANK",
                    "quote": "-0.1234500",
                    "quotationTime": "2026-10-07 08:00:00",
                    "quotationStatus": "UNRECOGNIZED",
                    "attachmentUrl": "PRIVATE",
                },
                "productDetail": {
                    "currency": "USD",
                    "quote": "1.00000000",
                    "tenor": "O/N",
                    "actualMaturityDate": None,
                    "curMaxLimitAvailable": 0,
                    "operator": "PRIVATE",
                },
                "operationLog": "PRIVATE",
            },
        }
    }


def test_quotation_form_nested_native_identity_and_projection(setup, run_cli):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": quotation(),
    }
    path = ["liquidity", "investment", "quotes"]
    code, out, err = run_cli([*path, "get", "--quotation-order-id", "SYN-QUOTE"])
    assert code == 0, (out, err)
    assert setup.state.business_requests == [{"quotationOrderId": "SYN-QUOTE"}]
    expressions = [
        e
        for transport in setup.state.transports
        for e in transport.expressions
        if "fetch(" in e
    ]
    assert any(
        "/queryQuotationOrder.json" in e and "application/x-www-form-urlencoded" in e
        for e in expressions
    )
    code, out, err = run_cli([*path, "get", "--quotation-order-id", "SYN-QUOTE"])
    assert code == 0, (out, err)
    data = parse(out)["data"]
    assert data["quotationDetail"]["quotationId"] == "SYN-QUOTE"
    assert "quotationOrderId" not in data
    assert data["quotationDetail"]["quote"] == "-0.1234500"
    assert data["productDetail"]["tenor"] == "O/N"
    assert data["productDetail"]["actualMaturityDate"] is None
    assert "PRIVATE" not in out


LEAVES = (
    (("operations", "demands"), "task-id", "SYN-TASK", demand),
    (
        ("network", "realtime"),
        "network-id",
        "SYN-NET",
        lambda identity="SYN-NET": {
            "success": True,
            "data": {"id": identity, "version": 7},
        },
    ),
    (("investment", "quotes"), "quotation-order-id", "SYN-QUOTE", quotation),
)


def invocation(leaf, *, identity=None):
    path, flag, default, _ = leaf
    return [
        "liquidity",
        *path,
        "get",
        "--" + flag,
        default if identity is None else identity,
    ]


@pytest.mark.parametrize("leaf", LEAVES)
def test_native_get_validates_each_requested_identity_without_publication(
    setup, run_cli, leaf
):
    _, _, identity, factory = leaf
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(identity),
    }
    code, out, err = run_cli([*invocation(leaf)])
    assert code == 0, (out, err)
    assert parse(out)["meta"]["source"] == "live"
    assert not setup.cache_path.exists()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory("wrong"),
    }
    code, out, _ = run_cli(invocation(leaf))
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert parse(out)["data"] is None
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory("SECOND"),
    }
    code, out, err = run_cli(invocation(leaf, identity="SECOND"))
    assert code == 0, (out, err)
    assert parse(out)["meta"]["identity"]
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_identity_rejected_without_network(setup, run_cli, leaf, bad):
    code, out, _ = run_cli(invocation(leaf, identity=bad))
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.business_requests == []
    assert setup.state.transports == []


@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize(
    "extra",
    [
        ["--id", "x"],
        ["--live"],
        ["--require-fresh"],
        ["--require-complete"],
        ["--version", "1"],
        ["--all"],
        ["--limit", "1"],
        ["--offset", "0"],
    ],
)
def test_unknown_parameters_rejected_without_network(setup, run_cli, leaf, extra):
    if leaf[0] == ("network", "realtime") and extra == ["--require-complete"]:
        setup.state.business_handler = lambda payload, index: {
            "status": 200,
            "body": leaf[3](),
        }
        code, out, _ = run_cli([*invocation(leaf), *extra])
        assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
        return
    code, out, _ = run_cli([*invocation(leaf), *extra])
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


@pytest.mark.parametrize("leaf", LEAVES)
def test_missing_identity_and_auth_browser_failures(setup, run_cli, leaf):
    code, out, _ = run_cli(invocation(leaf)[:-2])
    assert code == 2
    assert setup.state.transports == []
    setup.state.running = False
    code, out, _ = run_cli([*invocation(leaf)])
    assert code == 1
    assert parse(out)["error"]["code"] == "BROWSER_UNAVAILABLE"
    assert setup.state.business_requests == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("taskId", 1),
        ("source", "FUND_DECISION_TASK"),
        ("source", None),
        ("tntInstId", "OTHER"),
    ],
)
def test_demand_identity_source_tenant_conflicts_refuse_invalid_response(
    setup, run_cli, field, value
):
    native = demand()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(command())[0] == 0
    assert not setup.cache_path.exists()
    native["result"]["riskActionVO"][field] = value
    code, out, _ = run_cli(command())
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "document",
    [
        {
            "resultFlag": True,
            "result": {
                "riskActionVO": {"taskId": "SYN-TASK", "source": "FUND_REQUIRE"}
            },
        },
        {
            "resultFlag": True,
            "result": {
                "success": 1,
                "riskActionVO": {"taskId": "SYN-TASK", "source": "FUND_REQUIRE"},
            },
        },
        {"resultFlag": True, "result": {"success": True, "riskActionVO": None}},
    ],
)
def test_demand_requires_inner_boolean_success_and_object(setup, run_cli, document):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": document,
    }
    code, out, _ = run_cli(command())
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("product", [None, "absent"])
def test_quote_optional_product_section_preserves_absence_and_null(
    setup, run_cli, product
):
    native = quotation()
    data = native["baseResult"]["data"]
    if product == "absent":
        del data["productDetail"]
    else:
        data["productDetail"] = product
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, err = run_cli([*invocation(LEAVES[2])])
    assert code == 0, (out, err)
    result = parse(out)["data"]
    assert ("productDetail" in result) == (product is None)
    if product is None:
        assert result["productDetail"] is None


@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize("failure", ["false", "missing", "null", "wrong-type", "auth"])
def test_hard_failures_preserve_valid_object(setup, run_cli, leaf, failure):
    path, _, identity, factory = leaf
    native = factory(identity)
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(invocation(leaf))[0] == 0
    assert not setup.cache_path.exists()
    wrapper = (
        native["result"]
        if path[0] == "operations"
        else native.get("baseResult", native)
    )
    if failure == "false":
        wrapper["success"] = False
    elif failure == "missing":
        if path[0] == "operations":
            del native["resultFlag"]
        else:
            del wrapper["success"]
    elif failure == "null":
        wrapper["riskActionVO" if path[0] == "operations" else "data"] = None
    elif failure == "wrong-type":
        if path[0] == "operations":
            wrapper["riskActionVO"]["taskId"] = 42
        elif path[0] == "network":
            wrapper["data"]["id"] = 42
        else:
            wrapper["data"]["quotationDetail"]["quotationId"] = 42
    elif failure == "auth":
        setup.state.business_handler = lambda payload, index: {
            "status": 401,
            "body": {},
        }
    code, out, _ = run_cli(invocation(leaf))
    assert code == 1
    expected = (
        "AUTH_REQUIRED"
        if failure == "auth"
        else (
            "BUSINESS_QUERY_FAILED"
            if failure in ("false", "missing")
            else "INVALID_RESPONSE"
        )
    )
    assert parse(out)["error"]["code"] == expected
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("section", ["missing", None, [], {"quotationId": None}])
def test_quote_requires_native_nested_identity_section(setup, run_cli, section):
    native = quotation()
    data = native["baseResult"]["data"]
    if section == "missing":
        del data["quotationDetail"]
    else:
        data["quotationDetail"] = section
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, _ = run_cli([*invocation(LEAVES[2])])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"


def test_fractional_json_precision_and_request_tenant_metadata(setup, run_cli):
    native = (
        '{"resultFlag":true,"result":{"success":true,"riskActionVO":{"taskId":"'
        'SYN-TASK","source":"FUND_REQUIRE","tntInstId":"","amount":0.123456789012345678901,"version":0}}}'
    )
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, err = run_cli(command())
    assert code == 0, (out, err)
    refreshed = parse(out)
    assert refreshed["meta"]["source_version"] == 0
    assert refreshed["meta"]["request_scope"] == {"tntInstId": "GUAPW3SG"}
    code, out, err = run_cli(command())
    assert code == 0, (out, err)
    assert "0.123456789012345678901" in out
    assert parse(out)["data"]["tntInstId"] == ""
    assert parse(out)["meta"]["request_scope"] == {"tntInstId": "GUAPW3SG"}


@pytest.mark.parametrize("leaf", LEAVES)
def test_getter_help_describe_and_display_options(setup, run_cli, leaf):
    path, flag, identity, factory = leaf
    for prefix in ("help", "describe"):
        code, out, err = run_cli([prefix, "liquidity", *path, "get"])
        assert code == 0, (out, err)
        assert "--" + flag in out
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(identity),
    }
    assert run_cli(invocation(leaf))[0] == 0
    code, out, err = run_cli(
        [
            *invocation(leaf),
            "--format",
            "table",
        ]
    )
    assert code == 0, (out, err)
    field = (
        "taskId"
        if path[0] == "operations"
        else ("id" if path[0] == "network" else "quotationDetail")
    )
    code, out, err = run_cli([*invocation(leaf), "--fields", field])
    assert code == 0, (out, err)
    assert list(parse(out)["data"]) == [field]


@pytest.mark.parametrize("leaf", LEAVES)
def test_populated_parent_list_does_not_substitute_native_get(setup, run_cli, leaf):
    path, _, identity, detail_factory = leaf
    if path[0] == "operations":
        from test_liquidity_funding_demands import SCOPE, listing
        from test_liquidity_funding_demands import demand as list_row

        options = SCOPE
        setup.state.business_handler = listing([list_row(taskId=identity)])
    elif path[0] == "network":
        from test_liquidity_realtime_network_cli_sit import network, response

        options = []
        setup.state.business_handler = lambda payload, index: response(
            [network(identity)]
        )
    else:
        from test_liquidity_quotes_cli_sit import BOUNDS, quote, response

        options = BOUNDS
        setup.state.business_handler = lambda payload, index: response(
            [quote(identity)]
        )
    assert run_cli(["refresh", "liquidity", *path, *options])[0] == 0
    prior = setup.cache_path.read_bytes()
    count = len(setup.state.business_requests)
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": detail_factory(identity),
    }
    code, out, err = run_cli(invocation(leaf))
    assert code == 0, (out, err)
    assert parse(out)["meta"]["source"] == "live"
    assert len(setup.state.business_requests) == count + 1
    assert setup.cache_path.read_bytes() == prior


@pytest.mark.parametrize("leaf", LEAVES)
def test_native_getter_description_exposes_only_projected_schema(setup, run_cli, leaf):
    path, _, _, _ = leaf
    code, out, err = run_cli(["describe", "liquidity", *path, "get"])
    assert code == 0, (out, err)
    schema = parse(out)["data_schema"]
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    if path[0] == "operations":
        assert len(properties) == 15
        assert properties["taskId"]["x-observed-type"] == "str"
        assert "accountNo" not in properties
        assert properties["createTime"]["x-timezone"] == "unknown"
    elif path[0] == "network":
        assert len(properties) == 28
        assert properties["id"]["x-observed-type"] == "str"
        assert properties["version"]["x-observed-type"] == "unknown"
        assert "successRate" not in properties
    else:
        assert set(properties) == {"quotationDetail", "productDetail"}
        quotation_schema = properties["quotationDetail"]
        product_schema = properties["productDetail"]
        assert len(quotation_schema["properties"]) == 9
        assert len(product_schema["properties"]) == 8
        assert quotation_schema["properties"]["quotationId"]["x-observed-type"] == "str"
        assert quotation_schema["properties"]["quote"]["x-unit"] == "percent"
        assert product_schema["type"] == ["object", "null"]
        assert "quotationOrderId" not in properties
    assert setup.state.transports == []


@pytest.mark.parametrize("leaf", LEAVES)
def test_removed_detail_refresh_is_nonexecuting(setup, run_cli, leaf):
    path, flag, identity, _ = leaf
    code, out, _ = run_cli(
        ["refresh", "liquidity", *path, "detail", "get", "--" + flag, identity]
    )
    assert code != 0
    assert parse(out)["error"] is not None
    assert not setup.state.business_requests
    assert not setup.state.transports
