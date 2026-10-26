"""Installed native Get roots and same-value selected-window bindings."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.leaves.liquidity import test_investment_rfqs_cli as b09
from integration.leaves.liquidity import test_network_account_capabilities_cli as b10
from integration.leaves.liquidity import test_operations_cli as b08

from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import CliError
from dogopencli.leaves.registry import Registry
from dogopencli.transport import QueryRequest, validate_request

pytest_plugins = ["integration.test_get_sdk"]
ROOT = Path(__file__).resolve().parents[4]
CASES = (
    "operations.asset_trades",
    "operations.forwards",
    "operations.demands",
    "operations.transfers",
    "investment.rfqs",
    "investment.quote_groups",
    "ledger.customers",
    "network.account_capabilities",
)
COMBINED = tuple(
    name
    for name in CASES
    if name not in {"investment.quote_groups", "ledger.customers"}
)
IDENTITY = {
    "operations.asset_trades": "orderNo",
    "operations.forwards": "orderNo",
    "operations.demands": "taskId",
    "operations.transfers": "orderNo",
    "investment.rfqs": "inquiryTaskId",
    "investment.quote_groups": "id",
    "ledger.customers": "customerNo",
    "network.account_capabilities": "id",
}
WIRE = {
    **IDENTITY,
    "operations.forwards": "forwardId",
    "investment.quote_groups": "quotationGroupId",
}
PATH = {
    "operations.asset_trades": "/assetTransferOrderDetailQuery.json",
    "operations.forwards": "/forwardOrderDetail.json",
    "operations.demands": "/riskActionTaskQueryDetail.json",
    "operations.transfers": "/transferOrderQueryDetail.json",
    "investment.rfqs": "/rfq/subInquiryTask/queryInquiryTaskDetail.json",
    "investment.quote_groups": "/queryQuotationDetail.json",
    "ledger.customers": "/bookCustomer/detail.json",
    "network.account_capabilities": "/serviceInfoDetail.json",
}


def detail(name, identity="SELECTED"):
    value = {
        IDENTITY[name]: int(identity)
        if name == "network.account_capabilities"
        else identity,
        "amount": Decimal("0.123456789012345678901"),
        "unknown": {"native": [None, "", False, 0, "1.0000", {"raw": True}]},
        "success": False,
        "tntInstId": "GUAPW3SG",
    }
    if name == "investment.rfqs":
        value.update(
            inquiryType="TARGET_RFQ",
            inquiryOrderListVOList=[{"inquiryId": "INSTITUTION", "unknown": []}],
        )
    elif name == "investment.quote_groups":
        value.update(
            quotationGroupId="BUSINESS-GROUP",
            version=1,
            contactInfoList=[{"emailAddress": "synthetic@example.invalid"}],
            operationHistoryList=[
                {"id": "NEWER-ROW", "quotationGroupId": "BUSINESS-GROUP", "version": 2}
            ],
        )
    elif name == "operations.demands":
        value.update(source="FUND_REQUIRE", sourceId="OTHER-REFERENCE")
    elif name == "operations.asset_trades":
        value.update(
            assetProductVo={"assertProductCode": "RAW"},
            transFerOrderLogVoList=[{"id": 5, "unknown": []}],
        )
    return value


def envelope(name, value, success=True):
    if name == "operations.demands":
        return {
            "resultFlag": success,
            "result": {
                "success": success,
                "riskActionVO": value,
                "bestActionDecisionReportVOList": [{"separate": True}],
            },
        }
    if name == "operations.transfers":
        return {"baseResult": {"success": success, "data": value}}
    return {"success": success, "data": value}


def flags(name):
    return ("--customer-version", "1") if name == "ledger.customers" else ()


def lookup(name):
    return "0" if name == "network.account_capabilities" else "SELECTED"


def install(cli, name, tmp_path, kind="directory"):
    cli("domain", "enable", "liquidity")
    source = ROOT / "leaf_packages/liquidity" / name
    if kind == "zip":
        target = tmp_path / (name + ".zip")
        with ZipFile(target, "w") as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.write(path, path.relative_to(source))
        source = target
    cli("plugins", "install", str(source))


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize("kind", ["directory", "zip"])
def test_independent_get_preserves_whole_native_root_and_never_publishes(
    detail_cli, tmp_path, name, kind
):
    cli, browser, config = detail_cli
    browser.href = LIQUIDITY_STARTUP_URL
    install(cli, name, tmp_path, kind)
    storage = config / "duckdog.duckdb"
    prior_storage = storage.read_bytes() if storage.exists() else None
    cli("liquidity", "get", name, "-h")
    cli("liquidity", "describe", name)
    assert not browser.business_requests
    value = detail(name, lookup(name))
    browser.business_script.append({"status": 200, "body": envelope(name, value)})
    result = cli("liquidity", "get", name, lookup(name), *flags(name))
    assert result["data"] == value
    assert type(result["data"]["amount"]) is Decimal
    assert result["meta"]["detail_scope"] == "native_root"
    assert result["meta"]["complete"] is True
    assert result["meta"]["dataset_complete"] is True
    assert result["meta"]["publication"]["status"] == "not_requested"
    expected = {
        WIRE[name]: int(lookup(name))
        if name == "network.account_capabilities"
        else lookup(name)
    }
    if name in {"operations.demands", "ledger.customers"}:
        expected["tntInstId"] = "GUAPW3SG"
    if name == "ledger.customers":
        expected["version"] = "1"
    assert browser.business_requests == [expected]
    assert not (config / "leaf-cache.sqlite3").exists()
    assert (storage.read_bytes() if storage.exists() else None) == prior_storage
    if name in {"ledger.customers", "investment.quote_groups"}:
        assert prior_storage is None
    expressions = [
        expression
        for transport in browser.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert any(PATH[name] in expression for expression in expressions)
    if name in {
        "operations.asset_trades",
        "operations.forwards",
        "operations.transfers",
        "investment.quote_groups",
    }:
        assert any(
            "application/x-www-form-urlencoded" in expression
            for expression in expressions
        )
    if name in {"ledger.customers", "investment.quote_groups"}:
        operations = cli("liquidity", "describe", name)["data"]["operations"]
        assert "list" not in operations


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize(
    "fault",
    [
        "business",
        "marker_type",
        "missing_root",
        "array_root",
        "missing_identity",
        "wrong_identity",
        "tenant",
    ],
)
def test_native_failures_withhold_detail_data(detail_cli, tmp_path, name, fault):
    cli, browser, _ = detail_cli
    browser.href = LIQUIDITY_STARTUP_URL
    browser.href = LIQUIDITY_STARTUP_URL
    install(cli, name, tmp_path)
    value = detail(name, lookup(name))
    success = False if fault == "business" else 1 if fault == "marker_type" else True
    if fault == "missing_root":
        value = None
    elif fault == "array_root":
        value = [value]
    elif fault == "missing_identity":
        value.pop(IDENTITY[name])
    elif fault == "wrong_identity":
        value[IDENTITY[name]] = (
            99 if name == "network.account_capabilities" else "OTHER"
        )
    elif fault == "tenant":
        value["tntInstId"] = "OTHER"
    browser.business_script.append(
        {"status": 200, "body": envelope(name, value, success)}
    )
    result = cli("liquidity", "get", name, lookup(name), *flags(name), code=1)
    assert result["data"] is None
    assert result["error"]["code"] == (
        "BUSINESS_QUERY_FAILED" if fault == "business" else "INVALID_RESPONSE"
    )
    assert len(browser.business_requests) == 1


def list_source(name):
    if name.startswith("operations."):
        case = name.split(".")[1]
        rows = [b08.record(case, index) for index in range(3)]
        return rows, b08.page(case, rows), b08.flags(case)
    if name == "investment.rfqs":
        rows = [b09.record(index) for index in range(3)]
        return rows, b09.page(rows), b09.FLAGS
    rows = [b10.record(index) for index in range(3)]
    return rows, b10.page(rows), ()


@pytest.mark.parametrize("name", COMBINED)
def test_composition_binds_only_selected_native_row_and_preserves_saved_list(
    detail_cli, tmp_path, name
):
    cli, browser, config = detail_cli
    browser.href = LIQUIDITY_STARTUP_URL
    install(cli, name, tmp_path)
    rows, native_list, list_flags = list_source(name)
    browser.business_script.append(native_list)
    saved = cli("liquidity", "refresh", name, *list_flags, "--require-complete")
    before = cli("liquidity", "list", name, "--limit", "0")
    source = "inquirySubTaskId" if name == "investment.rfqs" else IDENTITY[name]
    selected = str(rows[1][source])
    value = detail(name, selected)
    browser.business_script.extend(
        [native_list, {"status": 200, "body": envelope(name, value)}]
    )
    result = cli(
        "liquidity",
        "list",
        name,
        "--live",
        "--with-detail",
        *list_flags,
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        source,
        "--require-complete",
    )
    assert result["data"] == [{"record": {source: rows[1][source]}, "detail": value}]
    expected = {
        WIRE[name]: int(selected)
        if name == "network.account_capabilities"
        else selected
    }
    if name == "operations.demands":
        expected["tntInstId"] = "GUAPW3SG"
    assert browser.business_requests[-1] == expected
    assert len(browser.business_requests) == 3
    if name == "investment.rfqs":
        assert (
            browser.business_requests[-1]["inquiryTaskId"] != rows[1]["inquiryTaskId"]
        )
    after = cli("liquidity", "list", name, "--limit", "0")
    assert before["data"] == after["data"] == rows
    assert (
        before["meta"]["fetched_at"]
        == after["meta"]["fetched_at"]
        == saved["meta"]["fetched_at"]
    )
    assert (config / "leaf-cache.sqlite3").exists()


@pytest.mark.parametrize("name", CASES)
def test_detail_contract_rejects_mutation_path_and_extra_request_fields(
    detail_cli, tmp_path, name
):
    cli, _, config = detail_cli
    install(cli, name, tmp_path)
    leaf = Registry(config / "config.toml").scan().get("liquidity", name)
    capability = leaf.adapter.detail_capability({"customer_version": "1"})
    body = capability.request_body({"customer_version": "1"}, lookup(name))
    contract = capability.contract
    validate_request(
        QueryRequest(
            capability.name, contract.method, contract.host, contract.path, body
        ),
        contract,
    )
    invalid = QueryRequest(
        capability.name,
        contract.method,
        contract.host,
        contract.path,
        {**body, "action": "delete"},
    )
    with pytest.raises(CliError) as rejected:
        validate_request(invalid, contract)
    assert rejected.value.code == "REQUEST_NOT_ALLOWED"
    with pytest.raises(CliError):
        validate_request(replace(invalid, body=body, path="/mutate.json"), contract)


def test_customer_version_required_and_contradictory_echo_fails(detail_cli, tmp_path):
    cli, browser, _ = detail_cli
    browser.href = LIQUIDITY_STARTUP_URL
    install(cli, "ledger.customers", tmp_path)
    cli("liquidity", "get", "ledger.customers", "CUSTOMER", code=2)
    assert not browser.business_requests
    value = detail("ledger.customers", "CUSTOMER")
    value["version"] = 2
    browser.business_script.append(
        {"status": 200, "body": envelope("ledger.customers", value)}
    )
    result = cli(
        "liquidity",
        "get",
        "ledger.customers",
        "CUSTOMER",
        "--customer-version",
        "1",
        code=1,
    )
    assert result["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize(
    "name,key,wrong",
    [
        ("operations.demands", "source", "REAL_TIME_RULE"),
        ("investment.rfqs", "inquiryType", "FULL_RANGE_RFQ"),
        ("investment.rfqs", "inquiryOrderListVOList", None),
        ("investment.quote_groups", "version", True),
        ("network.account_capabilities", "id", "-1"),
    ],
)
def test_native_scope_and_identity_types_are_not_coerced(
    detail_cli, tmp_path, name, key, wrong
):
    cli, browser, _ = detail_cli
    browser.href = LIQUIDITY_STARTUP_URL
    install(cli, name, tmp_path)
    value = detail(name, lookup(name))
    value[key] = wrong
    browser.business_script.append({"status": 200, "body": envelope(name, value)})
    result = cli("liquidity", "get", name, lookup(name), *flags(name), code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"


def test_negative_integer_lookup_uses_option_separator(detail_cli, tmp_path):
    cli, browser, _ = detail_cli
    browser.href = LIQUIDITY_STARTUP_URL
    install(cli, "network.account_capabilities", tmp_path)
    value = detail("network.account_capabilities", "-1")
    browser.business_script.append(
        {"status": 200, "body": envelope("network.account_capabilities", value)}
    )
    result = cli("liquidity", "get", "network.account_capabilities", "--", "-1")
    assert result["data"]["id"] == -1
    assert browser.business_requests == [{"id": -1}]
