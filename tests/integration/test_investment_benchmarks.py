"""Installed benchmark inquiry contract exercised through the public CLI."""

import runpy
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "leaf_packages/liquidity/investment.benchmarks"
ROW = {
    "id": 0,
    "value": Decimal("0.123456789012345678901"),
    "currency": "USD",
    "effectiveDate": "2026-10-17T00:00:00+08:00",
    "extra": {"null": None, "empty": "", "zero": 0},
}


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


@pytest.fixture(params=["directory", "zip"])
def benchmark(request, run_cli, tmp_path, monkeypatch, capsys):
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
    try:

        def cli(*args, code=0):
            result, output, error = run_cli(list(args))
            assert result == code, output + error
            return parse(output)

        source = SOURCE
        if request.param == "zip":
            helper = runpy.run_path(
                str(ROOT / ".agents/skills/plugin-helper/scripts/plugin_helper.py")
            )["main"]
            source = tmp_path / "benchmarks.zip"
            monkeypatch.setattr(
                "sys.argv",
                ["plugin_helper.py", "pack", str(SOURCE), "--output", str(source)],
            )
            assert helper() == 0
            capsys.readouterr()
        cli("domain", "enable", "liquidity")
        cli("plugins", "install", str(source))
        assert browser.business_requests == []
        yield cli, browser
    finally:
        cdp.set_transport_factory(None)


def test_benchmark_native_request_and_cache(benchmark):
    cli, browser = benchmark
    cli("liquidity", "list", "investment.benchmarks", "-h")
    description = cli("liquidity", "describe", "investment.benchmarks")
    assert "valueDateStart" in str(description)
    browser.business_script.append(page([ROW]))
    live = cli("liquidity", "list", "investment.benchmarks", "--live", "--limit", "0")
    assert live["data"] == [ROW]
    assert live["meta"]["complete"] is True
    assert browser.business_requests == [
        {
            "tntInstId": "GUAPW3SG",
            "timeZone": "GMT+08",
            "valueDateStart": "",
            "valueDateEnd": "",
            "rowStart": 0,
            "pageSize": 5000,
        }
    ]
    assert (
        cli("liquidity", "list", "investment.benchmarks", code=1)["error"]["code"]
        == "CACHE_MISS"
    )
    browser.business_script.append(page([ROW]))
    assert (
        cli("liquidity", "refresh", "investment.benchmarks")["meta"]["published"]
        is True
    )
    requests = len(browser.business_requests)
    assert cli("liquidity", "list", "investment.benchmarks", "--limit", "0")[
        "data"
    ] == [ROW]
    assert len(browser.business_requests) == requests
    cli("plugins", "uninstall", "liquidity.investment.benchmarks")
    assert (
        cli("plugins", "uninstall", "liquidity.investment.benchmarks")["data"][
            "removed"
        ]
        is False
    )


@pytest.mark.parametrize("bad_id", [None, "", "   ", True, {}, []])
def test_benchmark_rejects_missing_native_identity(benchmark, bad_id):
    cli, browser = benchmark
    browser.business_script.append(page([{**ROW, "id": bad_id}]))
    result = cli("liquidity", "list", "investment.benchmarks", "--live", code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"


def test_benchmark_offset_pages_and_display_limit(benchmark):
    cli, browser = benchmark
    rows = [{"id": number, "value": "0.0000"} for number in range(5001)]
    browser.business_script.extend([page(rows[:5000], 5001), page(rows[5000:], 5001)])
    live = cli("liquidity", "list", "investment.benchmarks", "--live", "--limit", "1")
    assert live["data"] == rows[:1]
    assert live["meta"]["collected_total"] == 5001
    assert live["meta"]["complete"] is True
    assert [request["rowStart"] for request in browser.business_requests] == [0, 5000]
    assert all(
        request["pageSize"] == 5000
        and request["valueDateStart"] == request["valueDateEnd"] == ""
        for request in browser.business_requests
    )


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "business",
        "shape",
        "total-type",
        "total-bool",
        "total-negative",
        "changed-total",
        "early-empty",
        "overfull",
        "duplicate",
        "conflict",
        "auth",
        "transport",
    ],
)
def test_benchmark_failed_refresh_preserves_snapshot(benchmark, failure, monkeypatch):
    cli, browser = benchmark
    browser.business_script.append(page([ROW]))
    cli("liquidity", "refresh", "investment.benchmarks")
    before = cli("liquidity", "list", "investment.benchmarks", "--limit", "0")
    expected, flags = "INVALID_RESPONSE", []
    if failure == "empty":
        responses, expected = [page([])], None
    elif failure == "business":
        responses, expected = (
            [{"status": 200, "body": {"success": False, "errorCode": "099"}}],
            "BUSINESS_QUERY_FAILED",
        )
    elif failure == "shape":
        responses = [
            {
                "status": 200,
                "body": {"success": True, "data": {"data": {}, "totalCount": 1}},
            }
        ]
    elif failure.startswith("total-"):
        total = {"total-type": "1", "total-bool": True, "total-negative": -1}[failure]
        responses = [page([ROW], total)]
    elif failure == "changed-total":
        responses = [page([ROW], 5001), page([{"id": 1}], 5002)]
    elif failure == "early-empty":
        responses = [page([], 5001)]
    elif failure == "overfull":
        responses = [page([{"id": n} for n in range(5001)], 5001)]
    elif failure == "duplicate":
        responses, expected, flags = (
            [page([ROW, ROW], 2)],
            "INCOMPLETE_RESULT",
            ["--require-complete"],
        )
    elif failure == "conflict":
        responses = [page([ROW, {**ROW, "value": "different"}], 2)]
    elif failure == "auth":
        responses, expected = [{"status": 401, "body": {}}], "AUTH_REQUIRED"
    else:
        monkeypatch.setattr("dogopencli.collect._sleep", lambda _: None)
        responses, expected = [{"status": 503, "body": {}}] * 3, "BUSINESS_QUERY_FAILED"
    browser.business_script.extend(responses)
    result = cli(
        "liquidity",
        "refresh",
        "investment.benchmarks",
        *flags,
        code=1 if expected else 0,
    )
    if expected:
        assert result["error"]["code"] == expected
    else:
        assert result["meta"]["published"] is False
    after = cli("liquidity", "list", "investment.benchmarks", "--limit", "0")
    assert after["data"] == before["data"] == [ROW]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


@pytest.mark.parametrize("mutation", ["extra", "date"])
def test_benchmark_unverified_request_is_blocked(benchmark, tmp_path, mutation):
    cli, browser = benchmark
    cli("plugins", "uninstall", "liquidity.investment.benchmarks")
    source = tmp_path / "mutated-source"
    shutil.copytree(SOURCE, source)
    path = source / "adapter.py"
    code = path.read_text()
    if mutation == "extra":
        code = code.replace(
            '"rowStart": row_start,', '"unverified": True, "rowStart": row_start,'
        )
    else:
        code = code.replace('"valueDateStart": "",', '"valueDateStart": "2026-10-17",')
    path.write_text(code)
    cli("plugins", "install", str(source))
    result = cli("liquidity", "list", "investment.benchmarks", "--live", code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert browser.business_requests == []
