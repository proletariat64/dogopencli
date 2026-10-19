"""Installed B12 strategy Get preserves its independent native settings root."""

import json
import runpy
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "leaf_packages/liquidity/investment.strategies"
LEAF = "investment.strategies"
CODE = "SYNTHETIC_RULE"
NATIVE = {
    "strategyRuleCode": CODE,
    "subStrategyRuleList": ["TenorStrategyRule", "TenorStrategyRule"],
    "productStrategyRuleVoList": [{"product": None, "amount": "0.0000"}],
    "tenorStrategyRuleVoList": [{"productTermList": ["3M", "5NT"]}],
    "currencyStrategyRuleVoList": [],
    "unknown": {"rate": Decimal("0.123456789012345678901"), "items": [False, None]},
}


@pytest.fixture(params=["directory", "zip"])
def installed(request, run_cli, tmp_path, monkeypatch, capsys):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    source = tmp_path / "source"
    shutil.copytree(SOURCE, source)
    if request.param == "zip":
        helper = runpy.run_path(str(ROOT / "tools/leaf-dev/leaf.py"))["main"]
        delivery = tmp_path / "delivery"
        monkeypatch.setattr(
            "sys.argv", ["leaf.py", "pack", str(source), "--output", str(delivery)]
        )
        assert helper() == 0
        assert json.loads(capsys.readouterr().out)["state"] == "packed"
        source = delivery / "liquidity.investment.strategies.zip"

    def cli(*args, code=0):
        result, output, error = run_cli(list(args))
        assert result == code, output + error
        return parse(output)

    browser = FakeBrowser(
        href="https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    )
    cdp.set_transport_factory(browser.transport)
    try:
        cli("plugins", "install", str(source))
        if request.param == "directory":
            shutil.rmtree(source)
        assert not browser.business_requests
        yield cli, browser, config, tmp_path
    finally:
        cdp.set_transport_factory(None)


def test_get_only_static_help_and_native_complete_root(installed):
    cli, browser, config, _ = installed
    cli("liquidity", "get", LEAF, "-h")
    description = cli("liquidity", "describe", LEAF)
    assert description
    assert not browser.business_requests
    assert not browser.transports
    browser.business_script.append(
        {"status": 200, "body": {"success": True, "data": NATIVE}}
    )
    result = cli("liquidity", "get", LEAF, CODE)
    assert result["data"] == NATIVE
    assert result["meta"]["query"] == {"identity": CODE, "parameters": {}}
    assert result["meta"]["detail_scope"] == "native_root"
    assert browser.business_requests == [{"strategyRuleCode": CODE}]
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert any("/queryIncrementStrategyRuleDetail.json" in e for e in expressions)
    assert any('method: "POST"' in e for e in expressions)
    assert any("application/x-www-form-urlencoded" in e for e in expressions)
    assert not (config / "leaf-cache.sqlite3").exists()
    assert not (config / "duckdog.duckdb").exists()
    rejected = cli("liquidity", "list", LEAF, "--live", code=2)
    assert rejected["error"]["code"] == "INVALID_ARGUMENT"
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize("identity", ["", " "])
def test_blank_lookup_fails_before_authentication(installed, identity):
    cli, browser, _, _ = installed
    before = len(browser.transports)
    result = cli("liquidity", "get", LEAF, identity, code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert len(browser.transports) == before
    assert not browser.business_requests


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"status": 401, "body": {}}, "AUTH_REQUIRED"),
        ({"status": 200, "body": {"success": False}}, "BUSINESS_QUERY_FAILED"),
        ({"status": 200, "body": {"data": NATIVE}}, "INVALID_RESPONSE"),
        ({"status": 200, "body": {"success": 1, "data": NATIVE}}, "INVALID_RESPONSE"),
        ({"status": 200, "body": {"success": True}}, "INVALID_RESPONSE"),
        ({"status": 200, "body": {"success": True, "data": None}}, "INVALID_RESPONSE"),
        ({"status": 200, "body": {"success": True, "data": []}}, "INVALID_RESPONSE"),
        ({"status": 200, "body": {"success": True, "data": {}}}, "INVALID_RESPONSE"),
        (
            {
                "status": 200,
                "body": {"success": True, "data": {"strategyRuleCode": "OTHER"}},
            },
            "INVALID_RESPONSE",
        ),
        (
            {
                "status": 200,
                "body": {"success": True, "data": {"strategyRuleCode": True}},
            },
            "INVALID_RESPONSE",
        ),
        (
            {
                "status": 200,
                "body": {"success": True, "data": {"strategyRuleCode": " "}},
            },
            "INVALID_RESPONSE",
        ),
    ],
)
def test_get_failures_preserve_error_classification(installed, response, expected):
    cli, browser, config, _ = installed
    browser.business_script.append(response)
    result = cli("liquidity", "get", LEAF, CODE, code=1)
    assert result["data"] is None
    assert result["error"]["code"] == expected
    assert not (config / "leaf-cache.sqlite3").exists()
    assert not (config / "duckdog.duckdb").exists()


def test_request_allowlist_rejects_injected_tenant(installed):
    cli, browser, _, tmp_path = installed
    cli("plugins", "uninstall", "liquidity." + LEAF)
    source = tmp_path / "unverified-request"
    shutil.copytree(SOURCE, source)
    adapter = source / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            'return {"strategyRuleCode": identity}',
            'return {"strategyRuleCode": identity, "tntInstId": "GUAPW3SG"}',
        )
    )
    cli("plugins", "install", str(source))
    result = cli("liquidity", "get", LEAF, CODE, code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests
