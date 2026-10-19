"""Installed B15 collection SLA List/Get with synthetic native responses."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
LEAF = "sla.configs"
SOURCE = ROOT / "leaf_packages/collection" / LEAF


def row(identity="1000000000000000001", **values):
    return {
        "slaConfigId": identity,
        "businessCategory": "BUSINESS",
        "legalEntityCode": "ENTITY",
        "creditorCurrency": "USD,EUR",
        "creditorRegion": "SG",
        "endToEndSla": 3600,
        "ipayInnerSla": 0,
        "holidayLimit": {"currencyCodes": ["USD", "EUR", "USD"], "regionCodes": []},
        "viewProcessInstanceRequired": False,
        "amount": Decimal("0.123456789012345678901"),
        "extension": {"zero": 0, "values": [None, False, "", "1.0000"]},
        **values,
    }


def detail(identity="1000000000000000001", **values):
    result = row(identity, **values)
    result.pop("viewProcessInstanceRequired")
    return {"status": 200, "body": {"success": True, "resultData": result}}


def page(rows, total=None, **echo):
    return {
        "status": 200,
        "body": {
            "success": True,
            "resultDataList": rows,
            "pageNo": 0,
            "pageSize": 1000,
            "totalCount": len(rows) if total is None else total,
            **echo,
        },
    }


@pytest.fixture(params=["directory"])
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
    browser = FakeBrowser(href="https://igfc.alipay.com/receivedPayment/sla/fundInSla")
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        result, output, error = run_cli(["collection", action, LEAF, *args])
        assert result == code, output + error
        return parse(output)

    try:
        source = tmp_path / "source"
        shutil.copytree(SOURCE, source)
        if request.param == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(source))
            source = archive_path
        result, output, error = run_cli(["plugins", "install", str(source)])
        assert result == 0, output + error
        if request.param == "directory":
            shutil.rmtree(source)
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_native_values_live_refresh_offline_and_static_help(installed):
    cli, browser, config = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.transports
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    rows = [row("2"), row("10")]
    browser.business_script.append(page(rows))
    live = cli("list", "--live", "--require-complete", "--limit", "0")
    assert live["data"] == sorted(rows, key=lambda item: int(item["slaConfigId"]))
    assert live["meta"]["complete"] is True
    assert not (config / "leaf-cache.sqlite3").exists()
    browser.business_script.append(page(rows))
    refreshed = cli("refresh", "--require-complete")
    calls = len(browser.business_requests)
    saved = cli("list", "--limit", "0")
    assert saved["data"] == live["data"]
    assert saved["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert len(browser.business_requests) == calls
    assert browser.business_requests == [{"pageNo": 0, "pageSize": 1000}] * 2
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert all(
        "https://iglobalfundcontrol.alipay.com/api/fundInSlaConfig/search.json" in e
        and 'method: "POST"' in e
        and "application/json" in e
        for e in expressions
    )


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (["--currency", "USD"], []),
        (["--currency", "USD,EUR"], ["1"]),
        (["--entity", "ENTITY"], ["1", "2", "3"]),
        (["--currency", "*"], ["3"]),
        (["--currency", "usd"], []),
        (["--currency", "USD,EUR", "--currency", "JPY", "--region", "HK"], ["2"]),
        (["--business-line", "None"], []),
    ],
)
def test_filters_are_exact_local_or_and_before_projection(installed, flags, expected):
    cli, browser, _ = installed
    rows = [
        row("1"),
        row("2", creditorCurrency="JPY", creditorRegion="HK"),
        row("3", creditorCurrency="*", businessCategory=None),
    ]
    browser.business_script.append(page(rows))
    cli("refresh", "--require-complete")
    result = cli("list", *flags, "--limit", "0", "--fields", "slaConfigId")
    assert result["data"] == [{"slaConfigId": value} for value in expected]
    assert browser.business_requests == [{"pageNo": 0, "pageSize": 1000}]


@pytest.mark.parametrize("flag", ["business-line", "entity", "currency", "region"])
def test_blank_local_filter_refuses_before_browser(installed, flag):
    cli, browser, _ = installed
    result = cli("list", "--live", "--" + flag, " ", code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "marker",
        "data",
        "null_rows",
        "bad_row",
        "id_missing",
        "id_number",
        "id_blank",
        "page",
        "size",
        "bool_total",
        "negative_total",
        "duplicate",
        "short",
        "capacity",
    ],
)
def test_rejected_refresh_preserves_saved_capture(installed, failure):
    cli, browser, _ = installed
    original = [row()]
    browser.business_script.append(page(original))
    before = cli("refresh", "--require-complete")
    candidate = page([row("OTHER")])
    data = candidate["body"]
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        candidate["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        candidate["body"]["success"] = 1
    elif failure == "data":
        candidate["body"] = []
    elif failure == "null_rows":
        data["resultDataList"] = None
    elif failure == "bad_row":
        data["resultDataList"] = [None]
    elif failure == "id_missing":
        data["resultDataList"] = [{}]
    elif failure == "id_number":
        data["resultDataList"] = [row(123)]
    elif failure == "id_blank":
        data["resultDataList"] = [row(" ")]
    elif failure == "page":
        data["pageNo"] = 1
    elif failure == "size":
        data["pageSize"] = 10
    elif failure == "bool_total":
        data["totalCount"] = True
    elif failure == "negative_total":
        data["totalCount"] = -1
    elif failure == "duplicate":
        candidate = page([row("X"), row("X")])
        expected = "INCOMPLETE_RESULT"
    elif failure == "short":
        data["totalCount"] = 2
        expected = "INCOMPLETE_RESULT"
    else:
        candidate = page([row(str(i)) for i in range(1000)], 1001)
        expected = "INCOMPLETE_RESULT"
    browser.business_script.append(candidate)
    failed = cli("refresh", "--require-complete", code=1)
    assert failed["error"]["code"] == expected
    assert failed["meta"]["published"] is False
    after = cli("list", "--limit", "0")
    assert after["data"] == original
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


@pytest.mark.parametrize("count", [0, 1000])
def test_native_empty_and_exact_capacity_without_total_pages(installed, count):
    cli, browser, _ = installed
    rows = [row(str(i)) for i in range(count)]
    browser.business_script.append(page(rows))
    result = cli("list", "--live", "--limit", "0", "--require-complete")
    assert len(result["data"]) == count
    assert result["meta"]["complete"] is True
    assert browser.business_requests == [{"pageNo": 0, "pageSize": 1000}]


def test_request_allowlist_refuses_business_filter_before_fetch(
    installed, run_cli, tmp_path
):
    cli, browser, _ = installed
    result, output, error = run_cli(["plugins", "uninstall", "collection.sla.configs"])
    assert result == 0, output + error
    source = tmp_path / "unverified-request"
    shutil.copytree(SOURCE, source)
    adapter = source / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            'return {"pageNo": 0, "pageSize": PAGE_SIZE}',
            'return {"pageNo": 0, "pageSize": PAGE_SIZE, "currency": "USD"}',
        )
    )
    result, output, error = run_cli(["plugins", "install", str(source)])
    assert result == 0, output + error
    rejected = cli("list", "--live", code=1)
    assert rejected["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_direct_detail_and_selected_window_preserve_independent_roots(
    installed, run_cli
):
    cli, browser, _ = installed
    rows = [row("1"), row("2"), row("3")]
    browser.business_script.append(page(rows))
    saved = cli("refresh", "--require-complete")
    browser.business_script.append(detail("2"))
    status, output, error = run_cli(["collection", "get", LEAF, "2"])
    assert status == 0, output + error
    direct = parse(output)
    assert direct["data"] == detail("2")["body"]["resultData"]
    assert "viewProcessInstanceRequired" not in direct["data"]
    assert browser.business_requests[-1] == {"slaConfigId": "2"}
    browser.business_script.extend([page(rows), detail("2")])
    combined = cli(
        "list",
        "--live",
        "--with-detail",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        "slaConfigId",
    )
    assert combined["data"] == [
        {"record": {"slaConfigId": "2"}, "detail": direct["data"]}
    ]
    assert browser.business_requests == [
        {"pageNo": 0, "pageSize": 1000},
        {"slaConfigId": "2"},
        {"pageNo": 0, "pageSize": 1000},
        {"slaConfigId": "2"},
    ]
    expressions = [
        e
        for t in browser.transports
        for e in t.expressions
        if "getDetailBySlaConfigId" in e
    ]
    assert expressions and all('method: "GET"' in e for e in expressions)
    before = len(browser.business_requests)
    after = cli("list", "--limit", "0")
    assert after["data"] == rows
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == before


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "marker",
        "root",
        "id",
        "missing_core",
        "holiday_missing",
        "holiday_array",
        "holiday_member",
    ],
)
def test_failed_get_and_composition_preserve_saved_list(installed, run_cli, failure):
    cli, browser, _ = installed
    rows = [row("1"), row("2")]
    browser.business_script.append(page(rows))
    saved = cli("refresh", "--require-complete")
    reply = detail("2")
    root = reply["body"]["resultData"]
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        reply = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        reply["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        reply["body"]["success"] = 1
    elif failure == "root":
        reply["body"]["resultData"] = None
    elif failure == "id":
        root["slaConfigId"] = "OTHER"
    elif failure == "missing_core":
        root.pop("ipayInnerSla")
    elif failure == "holiday_missing":
        root["holidayLimit"].pop("currencyCodes")
    elif failure == "holiday_array":
        root["holidayLimit"]["currencyCodes"] = None
    else:
        root["holidayLimit"]["currencyCodes"] = [False]
    browser.business_script.append(reply)
    status, output, error = run_cli(["collection", "get", LEAF, "2"])
    assert status == 1, output + error
    assert parse(output)["error"]["code"] == expected
    browser.business_script.extend([page(rows), detail("1"), reply])
    failed = cli("list", "--live", "--with-detail", "--limit", "0", code=1)
    assert failed["data"] is None
    assert failed["error"]["code"] == expected
    after = cli("list", "--limit", "0")
    assert after["data"] == rows
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_nullable_business_fields_preserve_presence_and_empty_list_exception(
    installed, run_cli
):
    cli, browser, _ = installed
    nullable = detail(holidayLimit=None, endToEndSla=None, ipayInnerSla=None)
    browser.business_script.append(nullable)
    status, output, error = run_cli(["collection", "get", LEAF, "1000000000000000001"])
    assert status == 0, output + error
    assert parse(output)["data"] == nullable["body"]["resultData"]
    omitted = page([])
    omitted["body"].pop("resultDataList")
    browser.business_script.append(omitted)
    assert cli("list", "--live", "--require-complete")["data"] == []


@pytest.mark.parametrize("identity", ["", " "])
def test_blank_detail_lookup_refuses_before_auth(installed, run_cli, identity):
    _, browser, _ = installed
    status, output, _ = run_cli(["collection", "get", LEAF, identity])
    assert status == 2
    assert parse(output)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


def test_native_string_identity_order_numeric_then_lexical_preserves_ids(installed):
    cli, browser, _ = installed
    identities = ["A2", "10", "2", "02", "002", "A10", "٢", "0", "00"]
    rows = [row(identity) for identity in identities]
    expected_ids = ["0", "00", "002", "02", "2", "10", "A10", "A2", "٢"]
    browser.business_script.append(page(rows))
    live = cli("list", "--live", "--limit", "0", "--require-complete")
    assert [item["slaConfigId"] for item in live["data"]] == expected_ids
    assert all(type(item["slaConfigId"]) is str for item in live["data"])
    browser.business_script.append(page(rows))
    cli("refresh", "--require-complete")
    saved = cli("list", "--limit", "0")
    assert saved["data"] == live["data"]
    window = cli("list", "--offset", "2", "--limit", "3", "--fields", "slaConfigId")
    assert window["data"] == [{"slaConfigId": value} for value in ["002", "02", "2"]]
