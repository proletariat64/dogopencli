"""Installed forecast inquiry through real CLI and controlled CDP."""

import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "src/dogopencli/leaf_packages/liquidity/rules.forecast"
)
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
    for i in range(11)
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
    browser.business_script.extend([page(ROWS[:10], 11), page(ROWS[10:], 11)])


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
    for offset, request in zip((0, 10), browser.business_requests, strict=True):
        assert request == {
            "tntInstId": "GUAPW3SG",
            "bankCashForecastRuleQueryVO": json.dumps(
                {
                    "tntInstId": "GUAPW3SG",
                    "instId": ["Z21"],
                    "rowStart": offset,
                    "pageSize": 10,
                }
            ),
        }
    assert (
        cli("liquidity", "list", "rules.forecast", code=1)["error"]["code"]
        == "CACHE_MISS"
    )
    queue_full(browser)
    refreshed = cli("liquidity", "refresh", "rules.forecast", "--limit", "1")
    assert refreshed["data"]["row_count"] == 11
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
        responses = [page(ROWS[:10], 11), page(ROWS[10:], 12)]
    elif failure == "early-empty":
        responses = [page(ROWS[:10], 11), page([], 11)]
    elif failure == "over-page":
        responses = [page(ROWS, 11)]
    elif failure == "conflict":
        responses = [page([ROWS[0], {**ROWS[0], "empty": "changed"}], 2)]
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
