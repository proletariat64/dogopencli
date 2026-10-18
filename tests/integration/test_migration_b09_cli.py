"""Installed TARGET_RFQ SDK List through public CLI with synthetic native input."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import duckdb
import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.leaves.registry import Registry
from dogopencli.transport import QueryRequest, validate_request

ROOT = Path(__file__).resolve().parents[2]
LEAF = "investment.rfqs"
PARAMETERS = {"from_date": "2026-01-01", "to_date": "2026-10-05"}
FLAGS = ("--from-date", "2026-01-01", "--to-date", "2026-10-05")
EXPECTED = {
    "rowStart": 0,
    "pageSize": 5000,
    "inquiryType": "TARGET_RFQ",
    "inquiryStartDate": "20260101",
    "inquiryEndDate": "20261005",
}


def record(index=0):
    return {
        "inquirySubTaskId": f"SYNTHETIC-{index}",
        "inquiryTaskId": "ONE_PARENT",
        "inquiryType": "TARGET_RFQ",
        "quotedNum": None,
        "inquiryNum": "UNINTERPRETED_NATIVE_COUNT",
        "winNum": -1,
        "inquiryStartTime": None,
        "inquiryEndTime": "UNINTERPRETED_NATIVE_TIME",
        "modifyTime": 0,
        "inquiryStatus": "FUTURE_NATIVE_STATUS",
        "nativeDecimal": Decimal("0.123456789012345678901"),
        "unknown": {"nested": [None, "", False, 0, "1.0000"]},
    }


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "data": rows,
                "totalCount": len(rows) if total is None else total,
            },
        },
    }


@pytest.fixture
def installed(request, run_cli, tmp_path, monkeypatch):
    kind = getattr(request, "param", "directory")
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for variable in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(variable, raising=False)
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0, scoped=True):
        automatic = (
            FLAGS
            if scoped
            and (action == "refresh" or (action == "list" and "--live" in args))
            else ()
        )
        status, output, error = run_cli(["liquidity", action, LEAF, *automatic, *args])
        assert status == code, output + error
        return parse(output)

    try:
        status, output, error = run_cli(["domain", "enable", "liquidity"])
        assert status == 0, output + error
        source = ROOT / "leaf_packages/liquidity" / LEAF
        if kind == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(source))
            source = archive_path
        status, output, error = run_cli(["plugins", "install", str(source)])
        assert status == 0, output + error
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_native_lifecycle_preserves_full_subtasks_and_empty_binding(installed):
    cli, browser, config = installed
    rows = [record(i) for i in range(3)]
    cli("list", "-h", scoped=False)
    cli("describe")
    assert not browser.business_requests
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(rows))
    live = cli("list", "--live", "--limit", "0", "--require-complete")
    assert live["data"] == rows
    assert live["meta"]["complete"] is True
    assert live["meta"]["unique_count"] == 3
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(rows))
    refreshed = cli("refresh", "--require-complete", "--limit", "1")
    count = len(browser.business_requests)

    def denied(*args, **kwargs):
        raise AssertionError("offline activated the browser")

    cdp.set_transport_factory(denied)
    offline = cli("list", "--limit", "0", "--require-complete")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert (
        offline["meta"]["scope"] == refreshed["meta"]["scope"] == live["meta"]["scope"]
    )
    assert len(browser.business_requests) == count
    assert browser.business_requests == [EXPECTED] * 2
    assert all("tntInstId" not in body for body in browser.business_requests)
    expressions = [
        expression
        for transport in browser.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert expressions
    assert all(
        "/rfq/subInquiryTask/querySubInquiryTask.json" in expression
        and 'method: "POST"' in expression
        and "application/json" in expression
        for expression in expressions
    )
    with duckdb.connect(str(config / "duckdog.duckdb"), read_only=True) as database:
        assert (
            database.execute(
                "SELECT count(*) FROM liquidity_investment_rfqs"
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "auth",
        "business",
        "outer_type",
        "shape",
        "rows",
        "missing_id",
        "wrong_type",
        "tenant",
        "invalid_total",
        "missing_total",
        "negative_total",
        "capacity",
        "duplicate",
        "conflict",
        "short",
    ],
)
def test_rejected_refresh_preserves_previous_capture(installed, failure):
    cli, browser, _ = installed
    rows = [record(i) for i in range(2)]
    browser.business_script.append(page(rows))
    saved = cli("refresh", "--require-complete")
    candidate = page(rows)
    code, expected = 1, "INVALID_RESPONSE"
    if failure == "empty":
        candidate, code = page([]), 0
    elif failure == "auth":
        candidate, expected = {"status": 401, "body": {}}, "AUTH_REQUIRED"
    elif failure == "business":
        candidate["body"].update(success=False, buserviceErrorCode="099")
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "outer_type":
        candidate["body"]["success"] = 1
    elif failure == "shape":
        candidate["body"]["data"] = []
    elif failure == "rows":
        candidate = page([None])
    elif failure == "missing_id":
        row = record()
        row.pop("inquirySubTaskId")
        candidate = page([row])
    elif failure == "wrong_type":
        candidate = page([{**record(), "inquiryType": "FULL_RANGE_RFQ"}])
    elif failure == "tenant":
        candidate = page([{**record(), "tntInstId": "OTHER"}])
    elif failure == "invalid_total":
        candidate = page(rows, True)
    elif failure == "missing_total":
        candidate["body"]["data"].pop("totalCount")
    elif failure == "negative_total":
        candidate = page(rows, -1)
    elif failure == "capacity":
        candidate = page(rows, 5001)
    elif failure == "duplicate":
        candidate = page([rows[0], rows[0]])
        expected = "INCOMPLETE_RESULT"
    elif failure == "conflict":
        candidate = page([rows[0], {**rows[0], "unknown": "CHANGED"}])
        expected = "INCOMPLETE_RESULT"
    else:
        candidate, expected = page(rows[:1], 2), "INCOMPLETE_RESULT"
    before = len(browser.business_requests)
    browser.business_script.append(candidate)
    rejected = cli("refresh", "--require-complete", code=code)
    assert rejected["meta"]["published"] is False
    if code:
        assert rejected["error"]["code"] == expected
    assert len(browser.business_requests) == before + 1
    offline = cli("list", "--limit", "0")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("identity", [None, "", " ", True, 1, [], {}])
def test_identity_requires_native_nonempty_string(installed, identity):
    cli, browser, _ = installed
    browser.business_script.append(page([{**record(), "inquirySubTaskId": identity}]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("inquiry_type", [None, "FULL_RANGE_RFQ", "", [], True])
def test_response_source_type_cannot_change(installed, inquiry_type):
    cli, browser, _ = installed
    browser.business_script.append(page([{**record(), "inquiryType": inquiry_type}]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize(
    "date_flags",
    [
        (),
        ("--from-date", "2026-01-01"),
        ("--from-date", "20260101", "--to-date", "20261005"),
        ("--from-date", "2026-1-01", "--to-date", "2026-10-05"),
        ("--from-date", "2026-02-30", "--to-date", "2026-10-05"),
        ("--from-date", "2026-10-06", "--to-date", "2026-10-05"),
    ],
)
def test_required_iso_bounds_rejected_before_browser(installed, date_flags):
    cli, browser, _ = installed
    result = cli("list", "--live", *date_flags, scoped=False, code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


@pytest.mark.parametrize(
    "option", ["--inquiry-type", "--product-type", "--status", "--inquiry-task-id"]
)
def test_unqualified_native_filters_are_unregistered(installed, option):
    cli, browser, _ = installed
    cli("list", "--live", option, "UNQUALIFIED", code=2)
    assert not browser.business_requests


@pytest.mark.parametrize(
    "change", ["path", "method", "tenant", "type", "width", "position", "date"]
)
def test_shared_transport_default_deny(installed, change):
    _, browser, config = installed
    adapter = Registry(config / "config.toml").scan().get("liquidity", LEAF).adapter
    capability = adapter.capability(PARAMETERS)
    body = capability.page_body(adapter.scope(PARAMETERS), 0, 5000)
    request = QueryRequest(
        capability.name,
        capability.contract.method,
        capability.contract.host,
        capability.contract.path,
        body,
    )
    validate_request(request, capability.contract)
    if change == "path":
        request = replace(request, path="/mutation.json")
    elif change == "method":
        request = replace(request, method="PUT")
    elif change == "tenant":
        body["tntInstId"] = "GUAPW3SG"
    elif change == "type":
        body["inquiryType"] = "FULL_RANGE_RFQ"
    elif change == "width":
        body["pageSize"] = 1000
    elif change == "position":
        body["rowStart"] = 5000
    else:
        body["inquiryStartDate"] = "20260102"
    with pytest.raises(CliError) as error:
        validate_request(request, capability.contract)
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


@pytest.mark.parametrize(
    "scope,position,width",
    [
        ("OTHER", 0, 5000),
        (None, True, 5000),
        (None, -1, 5000),
        (None, 1, 5000),
        (None, 0, True),
        (None, 0, 1000),
    ],
)
def test_capability_has_no_offset_or_width_fallback(installed, scope, position, width):
    _, browser, config = installed
    adapter = Registry(config / "config.toml").scan().get("liquidity", LEAF).adapter
    with pytest.raises(CliError) as error:
        adapter.capability(PARAMETERS).page_body(
            adapter.scope(PARAMETERS) if scope is None else scope, position, width
        )
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_get_is_unregistered_and_never_queries(installed):
    cli, browser, _ = installed
    cli("get", "SYNTHETIC", code=2)
    assert not browser.business_requests


def test_conflict_keeps_last_arrival_without_claiming_completeness(installed):
    cli, browser, _ = installed
    first, other = record(), record(1)
    last = {**first, "unknown": "CHANGED"}
    browser.business_script.append(page([first, last, other], 3))
    result = cli("list", "--live", "--limit", "0")
    assert result["data"] == [last, other]
    assert result["meta"]["complete"] is False
    assert result["meta"]["duplicate_count"] == 1


def test_single_acquisition_precedes_display_limit(installed):
    cli, browser, _ = installed
    rows = [record(i) for i in range(3)]
    browser.business_script.append(page(rows))
    result = cli("list", "--live", "--limit", "1", "--require-complete")
    assert result["data"] == rows[:1]
    assert result["meta"]["collected_total"] == 3
    assert browser.business_requests == [EXPECTED]


def test_equal_date_bounds_do_not_infer_native_timestamp_membership(installed):
    cli, browser, _ = installed
    rows = [
        {**record(i), "inquiryStartTime": value, "inquiryEndTime": value}
        for i, value in enumerate((None, "", "1900-01-01", 0, -1))
    ]
    browser.business_script.append(page(rows))
    result = cli(
        "list",
        "--live",
        "--require-complete",
        "--limit",
        "0",
        "--from-date",
        "2026-10-05",
        "--to-date",
        "2026-10-05",
        scoped=False,
    )
    assert result["data"] == rows
    assert browser.business_requests == [{**EXPECTED, "inquiryStartDate": "20261005"}]
