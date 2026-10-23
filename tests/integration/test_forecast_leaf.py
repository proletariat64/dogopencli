"""Installed forecast inquiry through real CLI and controlled CDP."""

import json
import shutil
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

SOURCE = Path(__file__).resolve().parents[2] / "leaf_packages/liquidity/rules.forecast"
ROWS = [
    {
        "ruleId": f"rule-{i}",
        "instId": "Z21",
        "unknown": None,
        "zero": 0,
        "empty": "",
        "enabled": False,
        "amount": Decimal("0.1234567890123456789"),
        "timestamp": "2026-10-17T11:00:00+08:00",
    }
    for i in range(1001)
]


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "dataValue": rows,
                "count": len(rows) if total is None else total,
            },
        },
    }


@pytest.fixture(params=["directory", "zip"])
def forecast(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        actual, out, err = run_cli(list(args))
        assert actual == code, out + err
        return parse(out)

    try:
        source = SOURCE
        if request.param == "zip":
            source = tmp_path / "forecast.zip"
            with zipfile.ZipFile(source, "w") as archive:
                for item in SOURCE.iterdir():
                    if item.is_file():
                        archive.write(item, item.name)
        cli("plugins", "install", str(source))
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def queue_full(browser):
    browser.business_script.extend([page(ROWS[:1000], 1001), page(ROWS[1000:], 1001)])


def test_forecast_native_scope_pages_and_snapshot(forecast):
    cli, browser, _ = forecast
    cli("liquidity", "list", "rules.forecast", "-h")
    cli("liquidity", "describe", "rules.forecast")
    assert browser.business_requests == []
    queue_full(browser)
    live = cli("liquidity", "list", "rules.forecast", "--live", "--limit", "0")
    assert live["data"] == ROWS
    assert live["meta"]["complete"] is True
    assert len(browser.business_requests) == 2
    for offset, request in zip((0, 1000), browser.business_requests, strict=True):
        assert request == {
            "tntInstId": "GUAPW3SG",
            "bankCashForecastRuleQueryVO": json.dumps(
                {
                    "tntInstId": "GUAPW3SG",
                    "instId": ["Z21"],
                    "rowStart": offset,
                    "pageSize": 1000,
                }
            ),
        }
    assert (
        cli("liquidity", "list", "rules.forecast", code=1)["error"]["code"]
        == "CACHE_MISS"
    )
    queue_full(browser)
    refreshed = cli("liquidity", "refresh", "rules.forecast", "--limit", "1")
    assert refreshed["data"]["row_count"] == 1001
    before = len(browser.business_requests)
    assert cli("liquidity", "list", "rules.forecast", "--limit", "0")["data"] == ROWS
    assert len(browser.business_requests) == before
    cli("plugins", "uninstall", "liquidity.rules.forecast")


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "business",
        "nested-business",
        "flag",
        "json",
        "shape",
        "identity",
        "auth",
        "transport",
        "total",
        "early-empty",
        "over-page",
        "conflict",
        "duplicate",
    ],
)
def test_forecast_refresh_failure_preserves_cache(forecast, failure):
    cli, browser, _ = forecast
    queue_full(browser)
    cli("liquidity", "refresh", "rules.forecast")
    old = cli("liquidity", "list", "rules.forecast", "--limit", "0")
    expected, flags = "INVALID_RESPONSE", []
    if failure == "empty":
        responses, expected = [page([])], None
    elif failure == "business":
        responses, expected = (
            [{"status": 200, "body": {"resultFlag": False}}],
            "BUSINESS_QUERY_FAILED",
        )
    elif failure == "nested-business":
        response = page([])
        response["body"]["result"]["success"] = False
        responses, expected = [response], "BUSINESS_QUERY_FAILED"
    elif failure == "flag":
        responses = [{"status": 200, "body": {"resultFlag": "true"}}]
    elif failure == "json":
        responses = [{"status": 200, "body": "not-json"}]
    elif failure == "shape":
        responses = [
            {
                "status": 200,
                "body": {"resultFlag": True, "result": {"dataValue": {}, "count": 1}},
            }
        ]
    elif failure == "identity":
        responses = [page([{"ruleId": ""}])]
    elif failure == "auth":
        responses, expected = [{"status": 401, "body": {}}], "AUTH_REQUIRED"
    elif failure == "transport":
        responses, expected = (
            [{"status": 0, "body": {}, "error": "fetch failed"}] * 4,
            "TIMEOUT",
        )
    elif failure == "total":
        responses = [page(ROWS[:1000], 1001), page(ROWS[1000:], 1002)]
    elif failure == "early-empty":
        responses = [page(ROWS[:1000], 1001), page([], 1001)]
        expected = "INCOMPLETE_RESULT"
    elif failure == "over-page":
        responses = [page(ROWS, 1001)]
    elif failure == "conflict":
        responses = [page([ROWS[0], {**ROWS[0], "empty": "changed"}], 2)]
        expected = "INCOMPLETE_RESULT"
    else:
        responses, expected, flags = (
            [page([ROWS[0], ROWS[0]], 2)],
            "INCOMPLETE_RESULT",
            ["--require-complete"],
        )
    browser.business_script.extend(responses)
    result = cli(
        "liquidity", "refresh", "rules.forecast", *flags, code=1 if expected else 0
    )
    if expected:
        assert result["error"]["code"] == expected
    else:
        assert result["meta"]["published"] is False
    after = cli("liquidity", "list", "rules.forecast", "--limit", "0")
    assert after["data"] == old["data"] == ROWS
    assert after["meta"]["fetched_at"] == old["meta"]["fetched_at"]


def test_forecast_rejects_unqualified_scope_and_get(forecast):
    cli, browser, _ = forecast
    for args in (
        ("list", "rules.forecast", "--inst-id", "OTHER", "--live"),
        ("get", "rules.forecast", "--id", "one"),
    ):
        cli("liquidity", *args, code=2)
    assert browser.business_requests == []


def test_forecast_duplicate_evidence_remains_incomplete(forecast):
    cli, browser, _ = forecast
    browser.business_script.append(page([ROWS[0], ROWS[0]], 2))
    result = cli("liquidity", "list", "rules.forecast", "--live", "--limit", "0")
    assert result["data"] == [ROWS[0]]
    assert result["meta"]["complete"] is False


@pytest.mark.parametrize("mutation", ["extra", "tenant", "scope", "width"])
def test_forecast_nested_request_boundary(forecast, tmp_path, mutation):
    cli, browser, _ = forecast
    cli("plugins", "uninstall", "liquidity.rules.forecast")
    source = tmp_path / "nested-request"
    shutil.copytree(SOURCE, source)
    path = source / "adapter.py"
    old, new = {
        "extra": (
            '"rowStart": row_start,',
            '"unverified": True, "rowStart": row_start,',
        ),
        "tenant": ('"tntInstId": TENANT,', '"tntInstId": "OTHER",'),
        "scope": ('"instId": ["Z21"],', '"instId": ["OTHER"],'),
        "width": ('"pageSize": PAGE_SIZE,', '"pageSize": 5000,'),
    }[mutation]
    code = path.read_text()
    if mutation == "tenant":
        code = code.replace(old, new, 2).replace(new, old, 1)
    else:
        code = code.replace(old, new)
    path.write_text(code)
    cli("plugins", "install", str(source))
    result = cli("liquidity", "list", "rules.forecast", "--live", code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_sdk_cross_page_conflict_keeps_last_arrival_and_prior_cache(forecast):
    cli, browser = forecast[:2]
    first = [{"ruleId": str(i), "value": "original"} for i in range(1000)]
    original = dict(first[0])
    changed = {**original, "value": "changed"}
    browser.business_script.append(page([original]))
    cli("liquidity", "refresh", "rules.forecast")
    before = cli("liquidity", "list", "rules.forecast", "--limit", "0")

    def queue_conflict():
        browser.business_script.extend([page(first, 1001), page([changed], 1001)])

    queue_conflict()
    result = cli("liquidity", "list", "rules.forecast", "--live", "--limit", "0")
    assert result["data"] == [changed, *first[1:]]
    assert result["meta"]["complete"] is False
    assert result["meta"]["duplicate_count"] == 1
    attempt = result["meta"]["acquisition"]["attempts"][0]
    assert attempt["conflict_count"] == 1
    assert attempt["pages"] == 2
    assert "LAST_ARRIVAL_WINS" in attempt["reasons"]
    assert [
        json.loads(request["bankCashForecastRuleQueryVO"])["rowStart"]
        for request in browser.business_requests[-2:]
    ] == [0, 1000]
    queue_conflict()
    refused = cli("liquidity", "refresh", "rules.forecast", code=1)
    assert refused["error"]["code"] == "INCOMPLETE_RESULT"
    after = cli("liquidity", "list", "rules.forecast", "--limit", "0")
    assert after["data"] == before["data"] == [original]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]
