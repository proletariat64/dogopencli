"""Installed account-outflow inquiry through the public CLI and fake CDP."""

import shutil
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.registry import Registry
from dogopencli.transport import QueryRequest, validate_request

ROOT = Path(__file__).resolve().parents[4]
LEAF = "risk.account_outflow"
VO = "accountflowMonitorQueryRequest"
FLAGS = (
    "--warning-from",
    "2026-10-23T08:00:00+08:00",
    "--warning-to",
    "2026-10-24T23:59:59.999+08:00",
)


def row(index=0, **values):
    return {
        "monitorNo": f"MONITOR-{index}",
        "aliasName": "ACCOUNT",
        "instId": "ENTITY",
        "bankId": "BANK",
        "currencyPairs": "NATIVE-CURRENCY-CONTEXT",
        "currentBal": "1,234.000000000000000001",
        "currentAvlIOD": None,
        "expAvlIOD": "",
        "expDaytimeOutflow": 0,
        "expDayendOutflow": "0",
        "expDaytimeBalResource": "-0.000000000000000001",
        "daytimeBuffer": Decimal("0.123456789012345678901"),
        "totalIOD": {"amount": "0", "currency": "USD"},
        "warningTime": "2026-10-23 08:00:00",
        "warningLocalTime": "2026-10-23 01:00:00",
        "timezone": "Europe/London",
        "updateTime": "UNINTERPRETED_NATIVE_UPDATE_TIME",
        "unknown": {"nested": [None, "", False, 0, "1.0000"]},
        **values,
    }


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "dataValue": rows,
                "count": len(rows) if total is None else total,
            },
        },
    }


@pytest.fixture(params=["directory"])
def installed(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for key in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(key, raising=False)
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        status, output, error = run_cli(["liquidity", action, LEAF, *args])
        assert status == code, output + error
        return parse(output)

    try:
        source = tmp_path / "source"
        shutil.copytree(ROOT / "leaf_packages/liquidity" / LEAF, source)
        candidate = source
        if request.param == "zip":
            candidate = tmp_path / "candidate.zip"
            with ZipFile(candidate, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(source))
        status, output, error = run_cli(["plugins", "install", str(candidate)])
        assert status == 0, output + error
        shutil.rmtree(source)
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def test_native_outflow_scope_values_and_inquiry_only_request(installed):
    cli, browser, _ = installed
    records = [row(9), row(2)]
    browser.business_script.append(page(records))
    result = cli("list", "--live", *FLAGS, "--limit", "0", "--require-complete")
    assert result["data"] == records
    assert result["meta"]["complete"] is True
    assert parse(browser.business_requests[0][VO]) == {
        "tntInstId": "GUAPW3SG",
        "warningReason": "EXPECTED_BAL_NOT_ENOUGH",
        "warningTimeStart": "2026-10-23T00:00:00.000Z",
        "warningTimeEnd": "2026-10-24T15:59:59.999Z",
        "rowStart": 0,
        "pageSize": 1000,
    }
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions and all(
        "/queryAccountflowMonitor.json" in e and 'method: "GET"' in e
        for e in expressions
    )


@pytest.mark.parametrize(
    "warning_time",
    [
        None,
        "",
        "2026-10-23T08:00:00",
        "2026-02-30 08:00:00",
        "2026-10-23 07:59:59",
        "2026-10-25 00:00:00",
    ],
)
def test_native_warning_time_contradictions_fail(installed, warning_time):
    cli, browser, _ = installed
    browser.business_script.append(page([row(warningTime=warning_time)]))
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize(
    "bounds",
    [
        (),
        ("--warning-from", "2026-10-23T00:00:00Z"),
        (
            "--warning-from",
            "2026-10-23T00:00:00",
            "--warning-to",
            "2026-10-24T00:00:00",
        ),
        (
            "--warning-from",
            "2026-10-23 00:00:00Z",
            "--warning-to",
            "2026-10-24T00:00:00Z",
        ),
        (
            "--warning-from",
            "2026-02-30T00:00:00Z",
            "--warning-to",
            "2026-10-24T00:00:00Z",
        ),
        (
            "--warning-from",
            "2026-10-23T00:00:00.000001Z",
            "--warning-to",
            "2026-10-24T00:00:00Z",
        ),
        (
            "--warning-from",
            "2026-10-25T00:00:00Z",
            "--warning-to",
            "2026-10-24T00:00:00Z",
        ),
    ],
)
def test_invalid_warning_bounds_fail_before_browser(installed, bounds):
    cli, browser, _ = installed
    assert cli("list", "--live", *bounds, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


def test_exact_entity_and_bank_arrays_define_native_scope(installed):
    cli, browser, _ = installed
    records = [row(instId="ENTITY-B", bankId="BANK-B")]
    browser.business_script.append(page(records))
    result = cli(
        "refresh",
        *FLAGS,
        "--entity",
        "ENTITY-B",
        "--entity",
        "ENTITY-A",
        "--entity",
        "ENTITY-B",
        "--bank-id",
        "BANK-B",
        "--require-complete",
    )
    assert result["meta"]["published"] is True
    inner = parse(browser.business_requests[0][VO])
    assert inner["entitys"] == ["ENTITY-A", "ENTITY-B"]
    assert inner["bankIds"] == ["BANK-B"]
    browser.running = False
    assert cli("list", "--require-complete")["data"] == records


@pytest.mark.parametrize(
    "values",
    [
        {"instId": "OTHER"},
        {"bankId": "OTHER"},
        {"tntInstId": "OTHER"},
        {"warningReason": "OTHER"},
    ],
)
def test_native_selector_or_fixed_scope_contradiction_fails(installed, values):
    cli, browser, _ = installed
    browser.business_script.append(page([row(**values)]))
    result = cli(
        "list", "--live", *FLAGS, "--entity", "ENTITY", "--bank-id", "BANK", code=1
    )
    assert result["error"]["code"] == "INVALID_RESPONSE"


def test_zero_native_count_with_rows_is_explicit_contradiction(installed):
    cli, browser, _ = installed
    records = [row()]
    browser.business_script.append(page(records, 0))
    result = cli("list", "--live", *FLAGS, "--limit", "0", code=1)
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result["error"]["message"] == "unique records exceed reported total"


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_help_describe_live_and_saved_replay_keep_their_boundaries(installed):
    cli, browser, _ = installed
    cli("list", "--help")
    cli("describe")
    assert not browser.transports
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    records = [row(9), row(2)]
    browser.business_script.append(page(records))
    assert cli("list", "--live", *FLAGS, "--limit", "0")["data"] == records
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(records))
    saved = cli("refresh", *FLAGS, "--require-complete")
    n = len(browser.transports)
    browser.running = False
    offline = cli("list", "--limit", "0", "--require-complete")
    assert offline["data"] == records
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.transports) == n
    assert (
        cli("list", *FLAGS, "--entity", "OTHER", code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert len(browser.transports) == n


def test_complete_native_acquisition_precedes_display_window(installed):
    cli, browser, _ = installed
    records = [row(i) for i in range(1001)]
    browser.business_script.extend(
        [page(records[:1000], 1001), page(records[1000:], 1001)]
    )
    result = cli("list", "--live", *FLAGS, "--limit", "1", "--require-complete")
    assert result["data"] == records[:1]
    assert result["meta"]["collected_total"] == 1001
    assert [parse(body[VO])["rowStart"] for body in browser.business_requests] == [
        0,
        1000,
    ]


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "short",
        "duplicate",
        "conflict",
        "zero_count",
        "auth",
        "business",
        "inner_business",
        "outer_marker",
        "inner_marker",
        "missing_inner",
        "shape",
        "rows",
        "missing_identity",
        "blank_identity",
        "total_type",
        "missing_total",
        "malformed_json",
        "warning_scope",
    ],
)
def test_rejected_or_empty_refresh_preserves_prior_capture(installed, failure):
    cli, browser, _ = installed
    records = [row(7)]
    browser.business_script.append(page(records))
    saved = cli("refresh", *FLAGS, "--require-complete")
    candidate = page([row(8)])
    code, expected = 1, "INVALID_RESPONSE"
    if failure == "empty":
        candidate, code = page([]), 0
    elif failure == "short":
        candidate, expected = page([row(8)], 2), "INCOMPLETE_RESULT"
    elif failure == "duplicate":
        candidate, expected = page([row(8), row(8)], 2), "INCOMPLETE_RESULT"
    elif failure == "conflict":
        candidate, expected = (
            page([row(8), row(8, currentBal="OTHER")], 2),
            "INCOMPLETE_RESULT",
        )
    elif failure == "zero_count":
        candidate = page([row(8)], 0)
    elif failure == "auth":
        candidate, expected = {"status": 401, "body": {}}, "AUTH_REQUIRED"
    elif failure == "business":
        candidate["body"]["resultFlag"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "inner_business":
        candidate["body"]["result"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "outer_marker":
        candidate["body"]["resultFlag"] = 1
    elif failure == "inner_marker":
        candidate["body"]["result"]["success"] = 1
    elif failure == "missing_inner":
        candidate["body"]["result"].pop("success")
    elif failure == "shape":
        candidate["body"]["result"] = []
    elif failure == "rows":
        candidate = page([None])
    elif failure == "missing_identity":
        candidate["body"]["result"]["dataValue"][0].pop("monitorNo")
    elif failure == "blank_identity":
        candidate = page([row(monitorNo=" ")])
    elif failure == "total_type":
        candidate = page([row(8)], True)
    elif failure == "missing_total":
        candidate["body"]["result"].pop("count")
    elif failure == "malformed_json":
        candidate = {"status": 200, "body": "not JSON"}
    elif failure == "warning_scope":
        candidate = page([row(8, warningTime="2026-10-01 00:00:00")])
    browser.business_script.append(candidate)
    rejected = cli("refresh", *FLAGS, "--require-complete", code=code)
    assert rejected["meta"]["published"] is False
    if code:
        assert rejected["error"]["code"] == expected
    offline = cli("list", "--limit", "0")
    assert offline["data"] == records
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("kind", ["short", "duplicate", "conflict"])
def test_valid_incomplete_arrivals_remain_visible_without_strict_mode(installed, kind):
    cli, browser, _ = installed
    records = [row()]
    expected = records
    if kind == "duplicate":
        records = [row(), row()]
    elif kind == "conflict":
        records = [row(), row(currentBal="NATIVE_CHANGED")]
        expected = records[-1:]
    browser.business_script.append(page(records, 2))
    result = cli("list", "--live", *FLAGS, "--limit", "0")
    assert result["data"] == expected
    assert result["meta"]["complete"] is False


def test_transient_retries_repeat_only_same_qualified_inquiry(installed):
    cli, browser, _ = installed
    browser.business_script.extend(
        [
            {"status": 503, "body": {}},
            {"status": 502, "body": {}},
            page([row()]),
        ]
    )
    assert cli("list", "--live", *FLAGS, "--require-complete")["data"] == [row()]
    assert len(browser.business_requests) == 3
    assert (
        browser.business_requests[0]
        == browser.business_requests[1]
        == browser.business_requests[2]
    )


@pytest.mark.parametrize("identity", [None, "", True, 1, [], {}])
def test_identity_is_native_nonblank_string(installed, identity):
    cli, browser, _ = installed
    browser.business_script.append(page([row(monitorNo=identity)]))
    assert cli("list", "--live", *FLAGS, code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize(
    "options",
    [
        ("--alias-name", "ACCOUNT"),
        ("--currency", "USD"),
        ("--entity", " "),
        ("--bank-id", ""),
        ("--page-size", "10"),
        ("--with-detail",),
    ],
)
def test_unqualified_selectors_width_and_composition_fail_before_browser(
    installed, options
):
    cli, browser, _ = installed
    assert (
        cli("list", "--live", *FLAGS, *options, code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert not browser.transports


@pytest.mark.parametrize(
    "change",
    [
        "method",
        "path",
        "top_extra",
        "inner_extra",
        "reason",
        "tenant",
        "width",
        "bounds",
        "selector",
    ],
)
def test_restricted_transport_rejects_changed_inquiry_contract(installed, change):
    _, browser, config = installed
    parameters = {
        "warning_from": "2026-10-23T00:00:00Z",
        "warning_to": "2026-10-24T15:59:59.999Z",
        "entity": ["ENTITY"],
    }
    adapter = Registry(config / "config.toml").scan().get("liquidity", LEAF).adapter
    capability = adapter.capability(parameters)
    body = capability.page_body(adapter.scope(parameters), 0, 1000)
    request = QueryRequest(
        capability.name,
        "GET",
        "iliquidity.alipay.com",
        "/queryAccountflowMonitor.json",
        body,
    )
    validate_request(request, capability.contract)
    if change == "method":
        request = replace(request, method="POST")
    elif change == "path":
        request = replace(request, path="/mutation.json")
    elif change == "top_extra":
        body["action"] = "edit"
    else:
        inner = parse(body[VO])
        field, value = {
            "inner_extra": ("action", "edit"),
            "reason": ("warningReason", "OTHER"),
            "tenant": ("tntInstId", "OTHER"),
            "width": ("pageSize", 10),
            "bounds": ("warningTimeStart", "2026-10-01T00:00:00Z"),
            "selector": ("entitys", ["OTHER"]),
        }[change]
        inner[field] = value
        body[VO] = canonical(inner)
    with pytest.raises(CliError) as caught:
        validate_request(request, capability.contract)
    assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests
