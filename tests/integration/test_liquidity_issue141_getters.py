"""Native asset roots and physical quotation group versions at public CLI seam."""

from decimal import Decimal

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]


def asset(identity="SYN-ORDER"):
    return {
        "success": True,
        "data": {
            "orderNo": identity,
            "orderStatus": "UNKNOWN",
            "tradingDate": "20261007",
            "assetTransferAmount": "0.1234000000",
            "counterpartTransferAmount": Decimal("0.123456789012345678901"),
            "assetTransferCurrency": "USD",
            "actualValueDate": None,
            "timezone": "",
            "assetProductVo": {
                "assertProductCategory": "SYN-CATEGORY",
                "assertProductCode": "SYN-CODE",
                "assertProductName": "SYN-PRODUCT",
                "assertProductTenor": "O/N",
                "assertProductType": "SYN-TYPE",
            },
            "transFerOrderLogVoList": [
                {"orderNo": "OTHER-UNBOUND", "content": "PRIVATE-LOG"}
            ],
        },
    }


def asset_command(refresh=False, identity="SYN-ORDER"):
    path = ["liquidity", "operations", "asset-trades"]
    return [
        *(["refresh", *path, "detail"] if refresh else path),
        "get",
        "--order-no",
        identity,
    ]


def test_asset_form_root_product_and_disconnected_capture(setup, run_cli):
    native = asset()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, err = run_cli(asset_command(True))
    assert code == 0, (out, err)
    assert setup.state.business_requests == [{"orderNo": "SYN-ORDER"}]
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any(
        "https://iliquidity.alipay.com/assetTransferOrderDetailQuery.json" in e
        and 'method: "POST"' in e
        and "application/x-www-form-urlencoded" in e
        for e in expressions
    )
    setup.state.running = False
    code, out, err = run_cli(asset_command())
    assert code == 0, (out, err)
    data = parse(out)["data"]
    assert data == {
        key: value
        for key, value in native["data"].items()
        if key != "transFerOrderLogVoList"
    }
    assert "PRIVATE-LOG" not in out
    assert "0.123456789012345678901" in out
    assert "tntInstId" not in data


def group_row(identity="SYN-ROW-3", version=3):
    return {
        "id": identity,
        "quotationGroupId": "SYN-BUSINESS-GROUP",
        "version": version,
        "tntInstId": "GUAPW3SG",
        "quotationGroupName": "SYN-GROUP",
        "bankId": "SYN-BANK",
        "department": "SYN-DEPARTMENT",
        "status": "UNKNOWN",
        "processStatus": "UNKNOWN-PROCESS",
        "memo": "synthetic memo",
        "contactInfoList": [
            {
                "name": "Synthetic Person",
                "emailAddress": "synthetic@example.invalid",
                "memo": "",
            }
        ],
        "operationHistoryList": [],
        "fileDownloadUrl": "PRIVATE-ATTACHMENT",
        "fileKey": "PRIVATE-KEY",
        "reviewLink": "PRIVATE-ACTION",
    }


def group(identity="SYN-ROW-3", version=3):
    data = group_row(identity, version)
    data["operationHistoryList"] = [
        group_row("SYN-ROW-3", 3),
        group_row("SYN-ROW-1", 1),
    ]
    return {"success": True, "data": data}


def group_command(refresh=False, identity="SYN-ROW-3"):
    path = ["liquidity", "investment", "quote-groups"]
    return [
        *(["refresh", *path, "detail"] if refresh else path),
        "get",
        "--quotation-group-row-id",
        identity,
    ]


def test_group_physical_versions_independent_and_history_curated(setup, run_cli):
    for identity, version in (("SYN-ROW-3", 3), ("SYN-ROW-1", 1)):
        native = group(identity, version)
        setup.state.business_handler = lambda payload, index, native=native: {
            "status": 200,
            "body": native,
        }
        code, out, err = run_cli(group_command(True, identity))
        assert code == 0, (out, err)
        assert setup.state.business_requests[-1] == {"quotationGroupId": identity}
        assert parse(out)["meta"]["source_version"] == version
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any(
        "https://iliquidity.alipay.com/queryQuotationDetail.json" in e
        and 'method: "POST"' in e
        and "application/x-www-form-urlencoded" in e
        for e in expressions
    )
    setup.state.running = False
    for identity, version in (("SYN-ROW-3", 3), ("SYN-ROW-1", 1)):
        code, out, err = run_cli(group_command(False, identity))
        assert code == 0, (out, err)
        result = parse(out)
        assert result["data"]["id"] == identity
        assert result["data"]["version"] == version
        assert result["meta"]["source_version"] == version
        assert result["data"]["quotationGroupId"] == "SYN-BUSINESS-GROUP"
        assert [row["id"] for row in result["data"]["operationHistoryList"]] == [
            "SYN-ROW-3",
            "SYN-ROW-1",
        ]
        assert result["data"]["contactInfoList"] == group_row()["contactInfoList"]
        assert "PRIVATE" not in out


LEAVES = ((asset_command, asset), (group_command, group))


@pytest.mark.parametrize("leaf", LEAVES)
def test_offline_miss_live_no_write_no_fallback_and_hard_failure_preservation(
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
    prior = setup.cache_path.read_bytes()
    code, out, err = run_cli([*invoke(), "--live", "--require-complete"])
    assert code == 0, (out, err)
    assert parse(out)["meta"]["source"] == "live"
    assert setup.cache_path.read_bytes() == prior
    assert parse(out)["meta"]["scope_tenant"] == "GUAPW3SG"
    if invoke is asset_command:
        assert parse(out)["meta"]["native_context_echo"] == {"tntInstId": "absent"}
    else:
        assert parse(out)["meta"]["native_context_echo"] == {"tntInstId": "present"}
    setup.state.business_handler = lambda payload, index: {"status": 401, "body": {}}
    for args in (invoke(True), [*invoke(), "--live"]):
        code, out, _ = run_cli(args)
        assert code == 1 and parse(out)["error"]["code"] == "AUTH_REQUIRED"
        assert setup.cache_path.read_bytes() == prior
    setup.state.running = False
    code, out, _ = run_cli([*invoke(), "--live"])
    assert code == 1 and parse(out)["error"]["code"] == "BROWSER_UNAVAILABLE"
    assert parse(out)["data"] is None
    assert setup.cache_path.read_bytes() == prior
    assert run_cli(invoke())[0] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("orderNo", "OTHER"),
        ("orderNo", 7),
        ("orderNo", ""),
        ("orderNo", None),
        ("assetProductVo", []),
        ("assetProductVo", ""),
        ("tntInstId", "OTHER"),
    ],
)
def test_asset_identity_and_product_failures_preserve_prior(
    setup, run_cli, field, value
):
    native = asset()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(asset_command(True))[0] == 0
    prior = setup.cache_path.read_bytes()
    native["data"][field] = value
    code, out, _ = run_cli(asset_command(True))
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == prior


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "OTHER"),
        ("id", 7),
        ("id", ""),
        ("quotationGroupId", ""),
        ("quotationGroupId", 7),
        ("tntInstId", "OTHER"),
        ("tntInstId", None),
        ("version", "3"),
        ("version", True),
        ("version", None),
        ("contactInfoList", {}),
        ("contactInfoList", [None]),
        ("operationHistoryList", {}),
        ("operationHistoryList", [None]),
    ],
)
def test_group_root_structure_identity_and_scope_failures_preserve_cache(
    setup, run_cli, field, value
):
    native = group()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(group_command(True))[0] == 0
    prior = setup.cache_path.read_bytes()
    native["data"][field] = value
    code, out, _ = run_cli(group_command(True))
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == prior


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "SYN-ROW-1"),
        ("id", None),
        ("quotationGroupId", "OTHER-BUSINESS"),
        ("tntInstId", "OTHER"),
        ("version", 1.5),
        ("contactInfoList", ""),
        ("operationHistoryList", [{"id": "RECURSIVE"}]),
        ("operationHistoryList", {}),
    ],
)
def test_group_history_identity_composition_and_recursion_failures(
    setup, run_cli, field, value
):
    native = group()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(group_command(True))[0] == 0
    prior = setup.cache_path.read_bytes()
    native["data"]["operationHistoryList"][0][field] = value
    code, out, _ = run_cli(group_command(True))
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == prior


@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize(
    "mutation",
    [
        "false",
        "missing-success",
        "numeric-success",
        "null-data",
        "list-data",
        "missing-id",
    ],
)
def test_business_and_malformed_success_never_become_not_found(
    setup, run_cli, leaf, mutation
):
    invoke, factory = leaf
    native = factory()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(invoke(True))[0] == 0
    prior = setup.cache_path.read_bytes()
    if mutation == "false":
        native["success"] = False
    elif mutation == "missing-success":
        del native["success"]
    elif mutation == "numeric-success":
        native["success"] = 1
    elif mutation == "null-data":
        native["data"] = None
    elif mutation == "list-data":
        native["data"] = []
    else:
        del native["data"]["orderNo" if invoke is asset_command else "id"]
    code, out, _ = run_cli(invoke(True))
    assert code == 1
    assert parse(out)["error"]["code"] == (
        "BUSINESS_QUERY_FAILED"
        if mutation in ("false", "missing-success", "numeric-success")
        else "INVALID_RESPONSE"
    )
    assert setup.cache_path.read_bytes() == prior


@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize(
    "extra",
    [
        ["--id", "x"],
        ["--version", "1"],
        ["--all"],
        ["--limit", "1"],
        ["--offset", "0"],
        ["--method", "GET"],
        ["--endpoint", "/x"],
        ["--quotation-group-id", "BUSINESS"],
    ],
)
def test_unsupported_parameters_rejected_before_browser(setup, run_cli, leaf, extra):
    invoke, _ = leaf
    code, out, _ = run_cli([*invoke(), *extra])
    assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize("identity", ["", "   "])
def test_blank_request_identity_rejected_before_browser(setup, run_cli, leaf, identity):
    invoke, _ = leaf
    for refresh in (True, False):
        code, out, _ = run_cli(invoke(refresh, identity))
        assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


@pytest.mark.parametrize(
    "leaf,path",
    [
        (LEAVES[0], ("operations", "asset-trades")),
        (LEAVES[1], ("investment", "quote-groups")),
    ],
)
def test_getter_help_describe_and_output_policies(setup, run_cli, leaf, path):
    invoke, factory = leaf
    for prefix in ("help", "describe"):
        code, out, err = run_cli([prefix, "liquidity", *path, "get"])
        assert code == 0, (out, err)
    code, out, _ = run_cli(["describe", "liquidity", *path, "get"])
    schema = parse(out)["data_schema"]
    assert schema["properties"]
    assert schema["additionalProperties"] is False
    if invoke is group_command:
        assert "Physical" in schema["properties"]["id"]["description"]
    else:
        assert set(schema["properties"]["assetProductVo"]["properties"]) == set(
            asset()["data"]["assetProductVo"]
        )
        assert "transFerOrderLogVoList" not in schema["properties"]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(),
    }
    assert run_cli(invoke(True))[0] == 0
    field = "orderNo" if invoke is asset_command else "id"
    code, out, err = run_cli(
        [*invoke(), "--require-fresh", "--require-complete", "--fields", field]
    )
    assert code == 0, (out, err)
    assert list(parse(out)["data"]) == [field]
    assert run_cli([*invoke(), "--format", "table"])[0] == 0


def test_complete_native_contacts_survive_root_history_and_offline(setup, run_cli):
    native = group()
    native["data"]["contactInfoList"][0]["futureNativeChannel"] = {
        "code": "SYN-CHANNEL",
        "enabled": None,
    }
    native["data"]["operationHistoryList"][0]["contactInfoList"][0][
        "futureNativeChannel"
    ] = "SYN-HISTORY-CHANNEL"
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    assert run_cli(group_command(True))[0] == 0
    setup.state.running = False
    code, out, err = run_cli(group_command())
    assert code == 0, (out, err)
    data = parse(out)["data"]
    assert data["contactInfoList"] == native["data"]["contactInfoList"]
    assert (
        data["operationHistoryList"][0]["contactInfoList"]
        == native["data"]["operationHistoryList"][0]["contactInfoList"]
    )
    code, out, _ = run_cli(
        ["describe", "liquidity", "investment", "quote-groups", "get"]
    )
    assert code == 0
    contacts = parse(out)["data_schema"]["properties"]["contactInfoList"]["items"]
    assert contacts["additionalProperties"] is True


def test_asset_list_cannot_satisfy_detail_and_generations_are_independent(
    setup, run_cli
):
    root = ["liquidity", "operations", "asset-trades"]
    bounds = ["--from-date", "2026-10-07", "--to-date", "2026-10-07"]
    row = {
        "orderNo": "SYN-ORDER",
        "tradingDate": "20261007",
        "assetTransferAmount": "777.000",
    }
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"data": [row], "totalCount": 1}},
    }
    code, out, err = run_cli(["refresh", *root, *bounds])
    assert code == 0, (out, err)
    code, out, err = run_cli([*root, "list", *bounds, "--all"])
    assert code == 0, (out, err)
    parent = parse(out)
    requests = len(setup.state.business_requests)
    code, out, _ = run_cli(asset_command())
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert len(setup.state.business_requests) == requests
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": asset(),
    }
    assert run_cli(asset_command(True))[0] == 0
    after = parse(run_cli([*root, "list", *bounds, "--all"])[1])
    assert after["data"] == parent["data"]
    assert after["meta"]["snapshot_id"] == parent["meta"]["snapshot_id"]
    detail = parse(run_cli(asset_command())[1])
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"data": [], "totalCount": 0}},
    }
    assert run_cli(["refresh", *root, *bounds])[0] == 0
    setup.state.running = False
    assert parse(run_cli([*root, "list", *bounds, "--all"])[1])["data"] == []
    after = parse(run_cli(asset_command())[1])
    assert after["data"] == detail["data"]
    assert after["meta"]["detail_fetched_at"] == detail["meta"]["detail_fetched_at"]


@pytest.mark.parametrize(
    "leaf,path",
    [
        (LEAVES[0], ("operations", "asset-trades", "get")),
        (LEAVES[1], ("investment", "quote-groups", "get")),
    ],
)
def test_schema_isolation_and_cross_object_cache_miss(
    setup, run_cli, leaf, path, monkeypatch
):
    from dataclasses import replace

    from dogopencli.plugins.liquidity.leaves import DETAIL_LEAVES, DetailLeaf

    invoke, factory = leaf
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": factory(),
    }
    assert run_cli(invoke(True))[0] == 0
    prior = setup.cache_path.read_bytes()
    requests = len(setup.state.business_requests)
    setup.state.running = False
    code, out, _ = run_cli(invoke(False, "SYN-OTHER"))
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    original = DETAIL_LEAVES[path]
    monkeypatch.setitem(
        DETAIL_LEAVES,
        path,
        DetailLeaf(replace(original.spec, schema_version="synthetic-next")),
    )
    code, out, _ = run_cli(invoke())
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.cache_path.read_bytes() == prior
    assert len(setup.state.business_requests) == requests


@pytest.mark.parametrize("value", [None, "absent"])
def test_optional_product_and_contact_history_absence_null_preserved(
    setup, run_cli, value
):
    for invoke, native, fields in (
        (asset_command, asset(), ("assetProductVo",)),
        (group_command, group(), ("contactInfoList", "operationHistoryList")),
    ):
        for field in fields:
            if value == "absent":
                del native["data"][field]
            else:
                native["data"][field] = None
        setup.state.business_handler = lambda payload, index, native=native: {
            "status": 200,
            "body": native,
        }
        code, out, err = run_cli([*invoke(), "--live"])
        assert code == 0, (out, err)
        data = parse(out)["data"]
        for field in fields:
            assert (field in data) == (value is None)
            if value is None:
                assert data[field] is None


def test_quote_group_list_remains_unsupported_and_metadata_keeps_physical_binding(
    setup, run_cli
):
    code, out, _ = run_cli(["liquidity", "investment", "quote-groups", "list"])
    assert code == 1 and parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": group("SYN-ROW-1", 1),
    }
    code, out, err = run_cli([*group_command(False, "SYN-ROW-1"), "--live"])
    assert code == 0, (out, err)
    assert parse(out)["meta"]["request_scope"] == {"quotationGroupId": "SYN-ROW-1"}
    assert parse(out)["data"]["quotationGroupId"] == "SYN-BUSINESS-GROUP"


def test_selected_physical_history_row_cannot_echo_different_version(setup, run_cli):
    native = group()
    native["data"]["operationHistoryList"][0]["version"] = 9
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": native,
    }
    code, out, _ = run_cli([*group_command(), "--live"])
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
