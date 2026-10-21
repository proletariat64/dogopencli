"""Conservative channel candidate; production coverage remains unqualified."""

from copy import deepcopy
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

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "leaf_packages/payment/channel"
STARTUP = "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"


def row(identity=1, scope="EXTERNAL", **extra):
    return {
        "abilityId": identity,
        "payoutType": scope,
        "financialInstCode": "BANK",
        "debitInstCountryCode": "GB",
        "status": "ENABLE",
        "debitAccountName": "ACCOUNT",
        "debitAccountNo": "123",
        "clearingSystemName": "SWIFT",
        "debitCurrency": "USD",
        "creditCurrency": "USD",
        "configVersion": "",
        "unknown": {"values": [Decimal("1.00000000000000001"), None, "", False]},
        **extra,
    }


def page(records, number=1, total=None, **paging):
    count = len(records) if total is None else total
    return {
        "status": 200,
        "body": {
            "success": True,
            "status": True,
            "resultObj": {
                "success": True,
                "payoutAbilityVOList": records,
                "pageNum": number,
                "pageSize": 100,
                "totalCount": count,
                "totalPages": -(-count // 100),
                **paging,
            },
        },
    }


def scripted(browser, records):
    def handler(body, _):
        assert set(body) == {"payoutType", "pageNum", "pageSize"}
        assert body["pageSize"] == 100
        start = (body["pageNum"] - 1) * 100
        return page(records[start : start + 100], body["pageNum"], len(records))

    browser.business_handler = handler


@pytest.fixture
def installed(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for key in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(key, raising=False)
    browser = FakeBrowser(href=STARTUP)
    cdp.set_transport_factory(browser.transport)
    source = SOURCE
    if getattr(request, "param", "directory") == "zip":
        target = tmp_path / "candidate.zip"
        with ZipFile(target, "w") as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(source))
        source = target
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 0, output + error

    def cli(action, *flags, code=0):
        status, output, error = run_cli(["payment", action, "channel", *flags])
        assert status == code, output + error
        return parse(output)

    try:
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_native_records_multipage_local_filters_and_refresh_replay(installed):
    cli, browser, _ = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.transports
    native = [row(i) for i in range(101)] + [
        row(101, clearingSystemName="BOOK", creditCurrency="GBP")
    ]
    scripted(browser, native)
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    live = cli(
        "list",
        "--live",
        "--clearing-system-name",
        "BOOK",
        "--require-complete",
        "--limit",
        "0",
    )
    assert live["data"] == native[-1:]
    assert live["meta"]["reported_total"] == live["meta"]["collected_total"] == 102
    assert live["meta"]["matched_total"] == 1
    assert [body["pageNum"] for body in browser.business_requests] == [1, 2]
    assert all(
        set(body) == {"pageNum", "pageSize", "payoutType"}
        for body in browser.business_requests
    )
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    saved = cli("refresh", "--require-complete")
    count = len(browser.business_requests)
    offline = cli(
        "list", "--clearing-system-name", "BOOK", "--require-complete", "--limit", "0"
    )
    assert offline["data"] == live["data"]
    assert offline["meta"]["matched_total"] == 1
    assert offline["meta"]["reported_total"] == 102
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == count
    assert cli("list", "--clearing-system-name", "book")["data"] == []
    assert cli("list", "--debit-currency", "U*")["data"] == []
    assert cli("list", "--debit-currency", "USD,GBP")["data"] == []


@pytest.mark.parametrize("scope", ["EXTERNAL", "LIQUIDITY", "MANUAL", "SETTLEMENT"])
def test_four_native_payout_scopes(installed, scope):
    cli, browser, _ = installed
    scripted(browser, [row(scope=scope)])
    got = cli("list", "--live", "--payout-type", scope, "--require-complete")
    assert got["data"][0]["payoutType"] == scope
    assert browser.business_requests == [
        {"payoutType": scope, "pageNum": 1, "pageSize": 100}
    ]


@pytest.mark.parametrize("conflict", [False, True])
def test_duplicate_primary_keys_keep_coverage_incomplete_or_hard_fail(
    installed, conflict
):
    cli, browser, _ = installed
    scripted(browser, [row(999)])
    saved = cli("refresh", "--require-complete")
    original = [row(i) for i in range(100)]
    repeated = {**original[0], **({"status": "DISABLE"} if conflict else {})}
    native = [*original, repeated]
    scripted(browser, native)
    if conflict:
        rejected = cli("list", "--live", "--limit", "0", code=1)
        assert rejected["error"]["code"] == "INVALID_RESPONSE"
        assert rejected.get("data") in (None, [])
    else:
        got = cli("list", "--live", "--limit", "0")
        assert got["data"] == original
        assert got["meta"]["complete"] is False
        assert got["meta"]["reported_total"] == 101
        assert got["meta"]["collected_total"] == got["meta"]["matched_total"] == 100
        evidence = got["meta"]["acquisition"]
        assert evidence["arrivals"] == 101 and evidence["duplicate_count"] == 1
        assert "COUNT_MISMATCH" in evidence["reasons"]
        assert (
            cli("list", "--live", "--require-complete", code=1)["error"]["code"]
            == "INCOMPLETE_RESULT"
        )
    failed = cli("refresh", "--require-complete", code=1)
    assert failed["meta"]["published"] is False
    assert failed["error"]["code"] == (
        "INVALID_RESPONSE" if conflict else "INCOMPLETE_RESULT"
    )
    offline = cli("list")
    assert offline["data"] == [row(999)]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "failure",
    [
        "business",
        "inner_business",
        "auth",
        "marker",
        "inner_marker",
        "status",
        "root",
        "rows",
        "id",
        "bool_id",
        "scope",
        "page",
        "clamp",
        "total_pages",
        "total_changed",
    ],
)
def test_failures_and_page_echoes_preserve_previous_capture(installed, failure):
    cli, browser, _ = installed
    scripted(browser, [row()])
    saved = cli("refresh", "--require-complete")
    browser.business_handler = None
    reply = page([row(2)])
    result = reply["body"]["resultObj"]
    expected = "INVALID_RESPONSE"
    if failure == "business":
        reply["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "inner_business":
        result["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "auth":
        reply = {"status": 403, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "marker":
        reply["body"]["success"] = "true"
    elif failure == "inner_marker":
        result["success"] = "true"
    elif failure == "status":
        reply["body"]["status"] = 1
    elif failure == "root":
        reply["body"]["resultObj"] = []
    elif failure == "rows":
        result["payoutAbilityVOList"] = None
    elif failure == "id":
        del result["payoutAbilityVOList"][0]["abilityId"]
    elif failure == "bool_id":
        result["payoutAbilityVOList"][0]["abilityId"] = True
    elif failure == "scope":
        result["payoutAbilityVOList"][0]["payoutType"] = "MANUAL"
    elif failure == "page":
        result["pageNum"] = 2
    elif failure == "clamp":
        result["pageSize"] = 10
    elif failure == "total_pages":
        result["totalPages"] = 2
    else:
        browser.business_script.append(page([row(i) for i in range(100)], total=101))
        reply = page([row(100)], number=2, total=102)
    browser.business_script.append(reply)
    failed = cli("refresh", "--require-complete", code=1)
    assert failed["error"]["code"] == expected
    assert failed["meta"]["published"] is False
    assert cli("list")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "flag,field",
    [
        ("financial-inst-id", "financialInstCode"),
        ("debit-inst-country-code", "debitInstCountryCode"),
        ("status", "status"),
        ("debit-account-name", "debitAccountName"),
        ("debit-account-no", "debitAccountNo"),
        ("clearing-system-name", "clearingSystemName"),
        ("debit-currency", "debitCurrency"),
        ("credit-currency", "creditCurrency"),
    ],
)
def test_each_exact_local_filter_and_repeated_value_or(installed, flag, field):
    cli, browser, _ = installed
    alternative = "DISABLE" if flag == "status" else "OTHER"
    records = [row(1), row(2, **{field: alternative}), row(3, **{field: None})]
    scripted(browser, records)
    got = cli(
        "list",
        "--live",
        "--" + flag,
        records[0][field],
        "--" + flag,
        alternative,
        "--limit",
        "0",
        "--require-complete",
    )
    assert got["data"] == records[:2]
    assert got["meta"]["reported_total"] == 3 and got["meta"]["matched_total"] == 2
    assert set(browser.business_requests[0]) == {"payoutType", "pageNum", "pageSize"}


@pytest.mark.parametrize("change", ["endpoint", "method", "extra", "width", "scope"])
def test_native_request_default_deny(installed, change):
    _, _, config = installed
    adapter = Registry(config / "config.toml").scan().get("payment", "channel").adapter
    capability = adapter.query_capability("list", "channels", {})
    body = capability.page_body("EXTERNAL", 1, 100)
    contract = capability.contract
    request = QueryRequest(
        capability.name, contract.method, contract.host, contract.path, deepcopy(body)
    )
    validate_request(request, contract)
    if change == "endpoint":
        request = replace(request, path="/mutation.json")
    elif change == "method":
        request = replace(request, method="GET")
    elif change == "extra":
        request.body["action"] = "save"
    elif change == "width":
        request.body["pageSize"] = 10
    else:
        with pytest.raises(CliError) as failure:
            capability.page_body("ANY", 1, 100)
        assert failure.value.code == "REQUEST_NOT_ALLOWED"
        return
    with pytest.raises(CliError) as failure:
        validate_request(request, contract)
    assert failure.value.code == "REQUEST_NOT_ALLOWED"
