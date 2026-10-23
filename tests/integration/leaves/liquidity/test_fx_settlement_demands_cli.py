"""Installed FX settlement demands through the public CLI and fake CDP."""

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAF = "operations.fx_settlement_demands"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
FLAGS = ["--from-date", "2026-10-23", "--to-date", "2026-10-23"]
VO = "queryFxSettlementReportRequest"


def row(index=1, **values):
    return {
        "id": index,
        "tntInstId": "GUAPW3SG",
        "instId": "ENTITY",
        "currency": "USD",
        "amount": "-0.123456789012345678901",
        "value": 0,
        "direction": "NATIVE_DIRECTION",
        "bizType": "NATIVE_BUSINESS",
        "subBizType": "NATIVE_SUB_BUSINESS",
        "counterParty": "COUNTERPARTY",
        "aliasName": "ACCOUNT",
        "transNo": "SHARED_REFERENCE",
        "memo": "",
        "valueDate": "20261023",
        "extParamsMap": None,
        "unknown": {"nested": [None, "", False, 0, Decimal("0.000000000000000001")]},
        **values,
    }


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "results": rows,
                "count": len(rows) if total is None else total,
            },
        },
    }


@pytest.fixture
def installed(run_cli, tmp_path, monkeypatch):
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

    def cli(action, *args, code=0):
        status, output, error = run_cli(["liquidity", action, LEAF, *args])
        assert status == code, output + error
        return parse(output)

    try:
        source = tmp_path / "source"
        shutil.copytree(SOURCE, source)
        status, output, error = run_cli(["plugins", "install", str(source)])
        assert status == 0, output + error
        shutil.rmtree(source)
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def test_native_records_live_refresh_and_offline_preserve_complete_source(installed):
    cli, browser, _ = installed
    rows = [row(2), row(1)]
    cli("list", "--help")
    cli("describe")
    assert not browser.transports
    browser.business_script.append(page(rows))
    live = cli("list", "--live", *FLAGS, "--limit", "0", "--require-complete")
    assert live["data"] == rows
    assert live["meta"]["complete"] is True
    assert live["meta"]["scope"] == {
        "tntInstId": "GUAPW3SG",
        "valueDateStart": "2026-10-23",
        "valueDateEnd": "2026-10-23",
    }
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(rows))
    saved = cli("refresh", *FLAGS, "--require-complete", "--limit", "1")
    before = len(browser.transports)
    browser.running = False
    offline = cli("list", "--limit", "0", "--require-complete")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.transports) == before
    assert len(browser.business_requests) == 2
    for body in browser.business_requests:
        assert set(body) == {"tntInstId", VO}
        assert body["tntInstId"] == "GUAPW3SG"
        assert json.loads(body[VO]) == {
            "valueDateStart": "2026-10-23",
            "valueDateEnd": "2026-10-23",
            "offset": 0,
            "size": 5000,
            "page": 1,
        }
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions and all(
        "/queryFxSettlementReportList.json" in e and 'method: "GET"' in e
        for e in expressions
    )


@pytest.mark.parametrize(
    "flags",
    [
        [],
        ["--from-date", "2026-10-23"],
        ["--from-date", "20261023", "--to-date", "2026-10-23"],
        ["--from-date", "2026-02-30", "--to-date", "2026-10-23"],
        ["--from-date", "2026-10-24", "--to-date", "2026-10-23"],
        ["--from-date", "2026-09-21", "--to-date", "2026-10-23"],
        ["--from-date", "２０２６-10-23", "--to-date", "2026-10-23"],
    ],
)
def test_invalid_dates_fail_before_browser(installed, flags):
    cli, browser, _ = installed
    assert cli("list", "--live", *flags, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


def test_date_difference_of_31_days_remains_allowed(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    result = cli(
        "list", "--live", "--from-date", "2026-09-22", "--to-date", "2026-10-23"
    )
    assert result["data"] == [row()]
    assert parse(browser.business_requests[0][VO])["valueDateStart"] == "2026-09-22"


@pytest.mark.parametrize(
    "change",
    [
        {"id": -1},
        {"id": True},
        {"id": "1"},
        {"id": None},
        {"tntInstId": "OTHER"},
        {"valueDate": "2026-10-23"},
        {"valueDate": "20260230"},
        {"valueDate": "20261024"},
    ],
)
def test_native_identity_and_scope_contradictions_fail(installed, change):
    cli, browser, _ = installed
    browser.business_script.append(page([row(**change)]))
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result["data"] is None


def test_local_literal_selectors_filter_after_acquisition_and_keep_full_cache(
    installed,
):
    cli, browser, _ = installed
    rows = [
        row(
            1,
            instId="甲*",
            currency="USD",
            aliasName="A,B",
            counterParty="NATIVE*",
            subBizType="ONE",
        ),
        row(
            2,
            instId="甲*",
            currency="EUR",
            aliasName="A,B",
            counterParty="NATIVE*",
            subBizType="TWO",
        ),
        row(
            3,
            instId="甲*",
            currency="JPY",
            aliasName="A,B",
            counterParty="NATIVE*",
            subBizType="ONE",
        ),
        row(
            4,
            instId="OTHER",
            currency="USD",
            aliasName="A,B",
            counterParty="NATIVE*",
            subBizType="ONE",
        ),
    ]
    browser.business_script.append(page(rows))
    selected = cli(
        "list",
        "--live",
        *FLAGS,
        "--inst-id",
        "甲*",
        "--currency",
        "USD",
        "--currency",
        "EUR",
        "--account-alias",
        "A,B",
        "--counterparty",
        "NATIVE*",
        "--sub-biz-type",
        "ONE",
        "--sub-biz-type",
        "TWO",
        "--limit",
        "0",
        "--require-complete",
    )
    assert selected["data"] == rows[:2]
    assert selected["meta"]["collected_total"] == 4
    browser.business_script.append(page(rows))
    cli("refresh", *FLAGS, "--currency", "EUR", "--require-complete")
    before = len(browser.business_requests)
    assert cli("list", "--limit", "0")["data"] == rows
    assert cli("list", "--currency", "EUR")["data"] == rows[1:2]
    assert cli("list", "--account-alias", "A")["data"] == []
    assert len(browser.business_requests) == before
    assert set(parse(browser.business_requests[0][VO])) == {
        "valueDateStart",
        "valueDateEnd",
        "offset",
        "size",
        "page",
    }


@pytest.mark.parametrize(
    "flag",
    ["--inst-id", "--currency", "--account-alias", "--counterparty", "--sub-biz-type"],
)
def test_blank_local_selector_fails_before_browser(installed, flag):
    cli, browser, _ = installed
    assert (
        cli("list", "--live", *FLAGS, flag, "  ", code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert not browser.transports


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "auth",
        "business",
        "inner",
        "marker",
        "inner_marker",
        "root",
        "rows",
        "row",
        "count",
        "missing_count",
        "count_zero",
        "duplicate",
        "conflict",
        "short",
    ],
)
def test_failed_incomplete_or_empty_refresh_preserves_saved_capture(installed, failure):
    cli, browser, _ = installed
    original = [row(1), row(2)]
    browser.business_script.append(page(original))
    saved = cli("refresh", *FLAGS, "--require-complete")
    candidate = page([row(3)])
    expected, code = "INVALID_RESPONSE", 1
    if failure == "empty":
        candidate, code = page([]), 0
    elif failure == "auth":
        candidate, expected = {"status": 401, "body": {}}, "AUTH_REQUIRED"
    elif failure == "business":
        candidate["body"]["resultFlag"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "inner":
        candidate["body"]["result"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        candidate["body"]["resultFlag"] = 1
    elif failure == "inner_marker":
        candidate["body"]["result"]["success"] = "true"
    elif failure == "root":
        candidate["body"]["result"] = []
    elif failure == "rows":
        candidate["body"]["result"]["results"] = {}
    elif failure == "row":
        candidate["body"]["result"]["results"] = [None]
    elif failure == "count":
        candidate["body"]["result"]["count"] = True
    elif failure == "missing_count":
        candidate["body"]["result"].pop("count")
    elif failure == "count_zero":
        candidate["body"]["result"]["count"] = 0
    elif failure in ("duplicate", "conflict"):
        candidate = page(
            [row(3), row(3, memo="CHANGED") if failure == "conflict" else row(3)]
        )
        expected = "INCOMPLETE_RESULT"
    elif failure == "short":
        candidate = page([row(3)], 2)
        expected = "INCOMPLETE_RESULT"
    browser.business_script.append(candidate)
    result = cli("refresh", *FLAGS, "--require-complete", code=code)
    assert result["meta"]["published"] is False
    if code:
        assert result["error"]["code"] == expected
    offline = cli("list", "--limit", "0")
    assert offline["data"] == original
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_valid_incomplete_live_is_visible_but_not_published(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row()], 2))
    result = cli("list", "--live", *FLAGS, "--limit", "0")
    assert result["data"] == [row()]
    assert result["meta"]["complete"] is False
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"


def test_unqualified_second_page_exhausts_budget_and_preserves_capture(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    before = len(browser.business_requests)
    browser.business_script.append(page([row(i) for i in range(1, 5001)], 5001))
    rejected = cli("refresh", *FLAGS, "--require-complete", code=1)
    assert rejected["error"]["code"] == "TIMEOUT"
    assert len(browser.business_requests) == before + 1
    assert cli("list")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "bad_field", ['"mutation": "Y"', '"size": 10', '"offset": 5000', '"page": 2']
)
def test_nested_request_contract_rejects_unqualified_changes(
    installed, run_cli, tmp_path, bad_field
):
    cli, browser, _ = installed
    status, output, error = run_cli(["plugins", "uninstall", "liquidity." + LEAF])
    assert status == 0, output + error
    source = tmp_path / "changed-request"
    shutil.copytree(SOURCE, source)
    adapter = source / "adapter.py"
    text = adapter.read_text()
    assert '"page": 1})' in text
    adapter.write_text(text.replace('"page": 1})', '"page": 1, ' + bad_field + "})"))
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 0, output + error
    assert (
        cli("list", "--live", *FLAGS, code=1)["error"]["code"] == "REQUEST_NOT_ALLOWED"
    )
    assert not browser.business_requests


def test_transient_retry_remains_bounded_and_preserves_cache_on_failure(installed):
    cli, browser, _ = installed
    browser.business_script.extend(
        [{"status": 429, "body": {}, "retry_after": "0"}, page([row()])]
    )
    saved = cli("refresh", *FLAGS, "--require-complete")
    assert len(browser.business_requests) == 2
    before = len(browser.business_requests)
    browser.business_script.extend(
        [{"status": 429, "body": {}, "retry_after": "0"}] * 5
    )
    result = cli("refresh", *FLAGS, "--require-complete", code=1)
    assert result["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert 1 <= len(browser.business_requests) - before <= 3
    assert cli("list")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_changed_source_scope_offline_is_rejected_without_browser(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    cli("refresh", *FLAGS, "--require-complete")
    browser.running = False
    before = len(browser.transports)
    result = cli(
        "list",
        "--from-date",
        "2026-10-22",
        "--to-date",
        "2026-10-23",
        "--require-complete",
        code=2,
    )
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert len(browser.transports) == before
