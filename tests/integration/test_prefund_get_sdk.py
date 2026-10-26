"""Selected native prefund application only; no historical/drawdown acquisition."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.leaves.liquidity import test_operations_cli as b08

from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import CliError
from dogopencli.leaves.registry import Registry
from dogopencli.transport import QueryRequest, validate_request

pytest_plugins = ["integration.test_get_sdk"]
ROOT = Path(__file__).resolve().parents[2]
NAME = "operations.prefunds"


@pytest.fixture(params=["directory", "zip"])
def prefund_cli(detail_cli, tmp_path, request):
    cli, browser, config = detail_cli
    browser.href = LIQUIDITY_STARTUP_URL
    cli("domain", "enable", "liquidity")
    source = ROOT / "leaf_packages/liquidity" / NAME
    if request.param == "zip":
        archive = tmp_path / "prefund.zip"
        with ZipFile(archive, "w") as output:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    output.write(path, path.relative_to(source))
        source = archive
    cli("plugins", "install", str(source))
    return cli, browser, config


def native_root(identity="SELECTED"):
    return {
        "id": identity,
        "prefundingBizNo": "SAME-BUSINESS",
        "version": 0,
        "tntInstId": "GUAPW3SG",
        "amount": Decimal("0.123456789012345678901"),
        "allowUseAmount": "1.000000000000000001",
        "approverList": [{"native": [False, None, "", 0]}],
        "fileUrlList": [{"name": "synthetic", "url": "https://example.invalid/file"}],
        "success": False,
        "unknown": {"native": [None, "", False, 0, "1.0000"]},
    }


def response(root):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"success": True, "data": root, "count": 246},
        },
    }


def offline(cli):
    return cli("liquidity", "list", NAME, "--limit", "0")


def test_independent_selected_root_preserves_native_arrays_and_never_fans_out(
    prefund_cli,
):
    cli, browser, config = prefund_cli
    cli("liquidity", "get", NAME, "-h")
    cli("liquidity", "describe", NAME)
    assert not browser.business_requests
    storage = config / "duckdog.duckdb"
    previous = storage.read_bytes()
    root = native_root()
    browser.business_script.append(response(root))
    result = cli("liquidity", "get", NAME, "SELECTED")
    assert result["data"] == root
    assert type(result["data"]["amount"]) is Decimal
    assert result["meta"]["returned_count"] == 1
    assert result["meta"]["detail_scope"] == "native_root"
    assert result["meta"]["complete"] is True
    assert result["meta"]["dataset_complete"] is True
    assert result["meta"]["reported_total"] is None
    assert browser.business_requests == [
        {"tntInstId": "GUAPW3SG", "preFundingId": "SELECTED"}
    ]
    assert not {"historyApplications", "drawdownDetails"} & result["data"].keys()
    assert storage.read_bytes() == previous
    assert not (config / "leaf-cache.sqlite3").exists()
    expressions = [
        expression
        for transport in browser.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert len(expressions) == 1
    assert "/queryPreFundingOrderDetail.json" in expressions[0]
    assert 'method: "GET"' in expressions[0]


@pytest.mark.parametrize(
    "fault",
    [
        "outer_false",
        "inner_false",
        "outer_type",
        "inner_type",
        "inner_missing",
        "missing",
        "array",
        "empty",
        "id",
        "tenant",
        "auth",
    ],
)
def test_native_business_shape_identity_and_auth_failures_remain_failures(
    prefund_cli, fault
):
    cli, browser, config = prefund_cli
    root = native_root()
    candidate = response(root)
    expected = "INVALID_RESPONSE"
    if fault == "outer_false":
        candidate["body"]["resultFlag"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif fault == "inner_false":
        candidate["body"]["result"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif fault == "outer_type":
        candidate["body"]["resultFlag"] = 1
    elif fault == "inner_type":
        candidate["body"]["result"]["success"] = 1
    elif fault == "inner_missing":
        candidate["body"]["result"].pop("success")
    elif fault in {"missing", "array", "empty"}:
        candidate["body"]["result"]["data"] = {
            "missing": None,
            "array": [root],
            "empty": {},
        }[fault]
    elif fault == "id":
        root["id"] = "OTHER-APPLICATION"
    elif fault == "tenant":
        root["tntInstId"] = "OTHER"
    else:
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    browser.business_script.append(candidate)
    result = cli("liquidity", "get", NAME, "SELECTED", code=1)
    assert result["data"] is None
    assert result["error"]["code"] == expected
    assert len(browser.business_requests) == 1
    assert not (config / "leaf-cache.sqlite3").exists()


def test_composition_filters_then_windows_rows_without_version_or_business_lookup(
    prefund_cli,
):
    cli, browser, _ = prefund_cli
    rows = [b08.record("prefunds", index) for index in range(3)]
    rows[1]["currency"] = "EUR"
    for row in rows:
        row["prefundingBizNo"] = "SAME-BUSINESS"
    browser.business_script.append(b08.page("prefunds", rows))
    saved = cli("liquidity", "refresh", NAME, *b08.STATUS_FLAGS, "--require-complete")
    before = offline(cli)
    root = native_root("ID2")
    browser.business_script.extend([b08.page("prefunds", rows), response(root)])
    result = cli(
        "liquidity",
        "list",
        NAME,
        "--live",
        "--with-detail",
        *b08.STATUS_FLAGS,
        "--currency",
        "USD",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        "currency",
        "--require-complete",
    )
    assert result["data"] == [{"record": {"currency": "USD"}, "detail": root}]
    assert browser.business_requests[-1] == {
        "tntInstId": "GUAPW3SG",
        "preFundingId": "ID2",
    }
    assert len(browser.business_requests) == 3
    after = offline(cli)
    assert before["data"] == after["data"] == rows
    assert (
        before["meta"]["fetched_at"]
        == after["meta"]["fetched_at"]
        == saved["meta"]["fetched_at"]
    )


def test_failed_second_detail_has_no_successful_partial_array_or_cache_write(
    prefund_cli,
):
    cli, browser, _ = prefund_cli
    rows = [b08.record("prefunds", index) for index in range(2)]
    browser.business_script.append(b08.page("prefunds", rows))
    cli("liquidity", "refresh", NAME, *b08.STATUS_FLAGS, "--require-complete")
    before = offline(cli)
    browser.business_script.extend(
        [
            b08.page("prefunds", rows),
            response(native_root("ID0")),
            response(native_root("WRONG")),
        ]
    )
    failed = cli(
        "liquidity",
        "list",
        NAME,
        "--live",
        "--with-detail",
        *b08.STATUS_FLAGS,
        "--limit",
        "0",
        code=1,
    )
    assert failed["data"] is None
    assert failed["error"]["code"] == "INVALID_RESPONSE"
    assert len(browser.business_requests) == 4
    after = offline(cli)
    assert before["data"] == after["data"]
    assert before["meta"]["fetched_at"] == after["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "operation,flags",
    [
        ("get", ["SELECTED", "--with-detail"]),
        ("get", ["SELECTED", "--status", "APPROVED"]),
        ("list", ["--with-detail"]),
        ("refresh", ["--with-detail"]),
    ],
)
def test_unsupported_modes_and_get_list_context_reject_before_queries(
    prefund_cli, operation, flags
):
    cli, browser, _ = prefund_cli
    cli("liquidity", operation, NAME, *flags, code=2)
    assert not browser.business_requests


@pytest.mark.parametrize("change", ["path", "method", "extra", "tenant"])
def test_detail_transport_rejects_unqualified_endpoint_context_and_fields(
    prefund_cli, change
):
    _, browser, config = prefund_cli
    capability = (
        Registry(config / "config.toml")
        .scan()
        .get("liquidity", NAME)
        .adapter.detail_capability({})
    )
    contract = capability.contract
    request = QueryRequest(
        capability.name,
        contract.method,
        contract.host,
        contract.path,
        capability.request_body({}, "SELECTED"),
    )
    validate_request(request, contract)
    if change == "path":
        request = replace(request, path="/preFundingManage.json")
    elif change == "method":
        request = replace(request, method="POST")
    elif change == "extra":
        request = replace(
            request, body={**request.body, "prefundingBizNo": "SAME-BUSINESS"}
        )
    else:
        request = replace(request, body={**request.body, "tntInstId": "OTHER"})
    with pytest.raises(CliError) as failure:
        validate_request(request, contract)
    assert failure.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests
