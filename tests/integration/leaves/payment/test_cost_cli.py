"""Installed payment cost uses one complete source for live and offline filters."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.leaves.registry import Registry
from dogopencli.transport import QueryRequest, validate_request

ROOT = Path(__file__).resolve().parents[4]
COST_TYPE = "FUND_OUT_CHANNEL_TRANS_FEE"


@pytest.fixture(params=["directory", "zip"])
def installed(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for name in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(name, raising=False)
    browser = FakeBrowser(
        href="https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(operation, *args, code=0):
        status, output, error = run_cli(["payment", operation, "cost", *args])
        assert status == code, output + error
        return parse(output)

    try:
        status, output, error = run_cli(["domain", "enable", "payment"])
        assert status == 0, output + error
        package = ROOT / "leaf_packages/payment/cost"
        if request.param == "zip":
            target = tmp_path / "candidate.zip"
            with ZipFile(target, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        archive.write(path, path.relative_to(package))
            package = target
        status, output, error = run_cli(["plugins", "install", str(package)])
        assert status == 0, output + error
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def row(identity="003", **fields):
    return {
        "itemId": identity,
        "itemType": COST_TYPE,
        "legalEntity": "ENTITY",
        "financialInst": "BANK",
        "bankAccountAliasName": "ALIAS",
        "transCurrencyCode": "CNY",
        "chargeBearer": "DEBT",
        "clearingNetworkName": "NETWORK",
        "isFvt": "N",
        "status": "ACTIVATED",
        "costRateConfigList": [
            {
                "rate": Decimal("0.123456789012345678901"),
                "unknown": [None, False, "1.0000", 0],
            }
        ],
        "unknown": {"retained": True},
        **fields,
    }


def reply(rows, *, total=None, page=0, size=5000):
    return {
        "status": 200,
        "body": {
            "success": True,
            "resultDataList": rows,
            "pageNo": page,
            "pageSize": size,
            "totalCount": len(rows) if total is None else total,
        },
    }


def test_live_refresh_offline_preserve_specifications_and_exact_network(installed):
    cli, browser, config = installed
    cli("list", "--help")
    assert not browser.business_requests
    rows = [
        row(),
        row("001", isFvt="Y"),
        row("002", costCurrencyCode="USD"),
        row("004", clearingNetworkName="NETWORKFX"),
    ]
    browser.business_script.append(reply(rows))
    live = cli(
        "list",
        "--live",
        "--clearing-network-name",
        "NETWORK",
        "--require-complete",
        "--limit",
        "0",
    )
    expected = sorted(rows[:3], key=lambda item: item["itemId"])
    assert live["data"] == expected
    assert live["meta"]["reported_total"] == 4
    assert live["meta"]["matched_total"] == 3
    assert browser.business_requests == [
        {"costTypeCode": COST_TYPE, "pageNo": 0, "pageSize": 5000}
    ]
    assert not (config / "leaf-cache.sqlite3").exists()
    browser.business_script.append(reply(rows))
    assert cli("refresh")["meta"]["published"] is True
    before = len(browser.business_requests)
    offline = cli("list", "--clearing-network-name", "NETWORK", "--limit", "0")
    assert offline["data"] == live["data"]
    assert offline["meta"]["reported_total"] == 4
    assert offline["meta"]["matched_total"] == 3
    assert len(browser.business_requests) == before
    for spelling in ("network", "NET", "NETWORK*"):
        assert cli("list", "--clearing-network-name", spelling)["data"] == []


@pytest.mark.parametrize(
    "flag,field",
    [
        ("--legal-entity-code", "legalEntity"),
        ("--financial-inst-code", "financialInst"),
        ("--account-alias", "bankAccountAliasName"),
        ("--trans-currency-code", "transCurrencyCode"),
        ("--charge-bearer", "chargeBearer"),
        ("--clearing-network-name", "clearingNetworkName"),
    ],
)
def test_all_original_filters_are_local_exact_or_with_cross_field_and(
    installed, flag, field
):
    cli, browser, _ = installed
    rows = [
        row("001", **{field: "Exact,*"}),
        row("002", **{field: "Other"}),
        row("003", **{field: "Exact"}),
        row("004", **{field: None}),
    ]
    browser.business_script.append(reply(rows))
    live = cli("list", "--live", flag, "Exact,*", flag, "Other", "--limit", "0")
    assert live["data"] == rows[:2]
    assert set(browser.business_requests[-1]) == {"costTypeCode", "pageNo", "pageSize"}
    browser.business_script.append(reply(rows))
    cli("refresh")
    assert (
        cli("list", flag, "Exact,*", flag, "Other", "--limit", "0")["data"] == rows[:2]
    )
    other_flag = "--charge-bearer" if flag != "--charge-bearer" else "--account-alias"
    assert cli("list", flag, "Exact,*", other_flag, "absent")["data"] == []


@pytest.mark.parametrize(
    "failure,error",
    [
        ("gap", "INCOMPLETE_RESULT"),
        ("duplicate", "INCOMPLETE_RESULT"),
        ("conflict", "INCOMPLETE_RESULT"),
        ("identity", "INVALID_RESPONSE"),
        ("scope", "INVALID_RESPONSE"),
        ("echo", "INVALID_RESPONSE"),
        ("size", "INVALID_RESPONSE"),
        ("success", "INVALID_RESPONSE"),
        ("business", "BUSINESS_QUERY_FAILED"),
        ("auth", "AUTH_REQUIRED"),
        ("empty", None),
    ],
)
def test_failure_or_empty_refresh_keeps_prior_capture(installed, failure, error):
    cli, browser, config = installed
    browser.business_script.append(reply([row()]))
    cli("refresh")
    database = config / "leaf-cache.sqlite3"
    original = database.read_bytes()
    response = reply([row()])
    body = response["body"]
    if failure == "gap":
        body["totalCount"] = 2
    elif failure in {"duplicate", "conflict"}:
        body["resultDataList"].append(
            row(status="OFFLINE") if failure == "conflict" else row()
        )
        body["totalCount"] = 2
    elif failure == "identity":
        body["resultDataList"][0]["itemId"] = ""
    elif failure == "scope":
        body["resultDataList"][0]["itemType"] = "FUND_IN_CHANNEL_TRANS_FEE"
    elif failure == "echo":
        body["pageNo"] = 1
    elif failure == "size":
        body["pageSize"] = True
    elif failure == "success":
        body["success"] = "true"
    elif failure == "business":
        body["success"] = False
        body["errorContext"] = "PRIVATE"
    elif failure == "auth":
        response["status"] = 401
    else:
        response = reply([])
    browser.business_script.append(response)
    result = cli("refresh", code=1 if error else 0)
    assert result["meta"]["published"] is False
    if error:
        assert result["error"]["code"] == error
        assert "PRIVATE" not in str(result)
    assert database.read_bytes() == original
    assert cli("list", "--limit", "0")["data"] == [row()]


def test_native_paging_preserves_source_coverage_before_filtering(installed):
    cli, browser, _ = installed
    rows = [row(f"{index:05}", clearingNetworkName="OTHER") for index in range(5001)]
    rows[-1]["clearingNetworkName"] = "NETWORK"
    browser.business_script.extend(
        [reply(rows[:5000], total=5001), reply(rows[5000:], total=5001, page=1)]
    )
    result = cli(
        "list",
        "--live",
        "--clearing-network-name",
        "NETWORK",
        "--require-complete",
        "--limit",
        "0",
    )
    assert result["data"] == rows[-1:]
    assert result["meta"]["reported_total"] == 5001
    assert result["meta"]["matched_total"] == 1
    assert browser.business_requests == [
        {"costTypeCode": COST_TYPE, "pageNo": number, "pageSize": 5000}
        for number in (0, 1)
    ]


def test_request_contract_excludes_native_filters_and_other_cost_types(installed):
    _, browser, config = installed
    leaf = Registry(config / "config.toml").scan().get("payment", "cost")
    capability = leaf.adapter.capability({})
    body = capability.page_body(COST_TYPE, 0, 5000)
    request = QueryRequest(
        capability.name,
        "POST",
        capability.contract.host,
        capability.contract.path,
        body,
    )
    validate_request(request, capability.contract)
    for invalid in (
        {**body, "clearingNetworkName": "NETWORK"},
        {**body, "costTypeCode": "FUND_IN_CHANNEL_TRANS_FEE"},
        {**body, "pageSize": 10000},
        {**body, "execute": True},
    ):
        with pytest.raises(CliError):
            validate_request(replace(request, body=invalid), capability.contract)
    with pytest.raises(CliError):
        capability.page_body(COST_TYPE, True, 5000)
    assert not browser.business_requests
