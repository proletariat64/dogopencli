"""Installed native product history preserves the accepted array boundary."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "leaf_packages/liquidity/investment.products.history"
FLAGS = ["--product-code", "PRODUCT"]


def row(identity="VERSION-2", **extra):
    return {
        "incrementProductId": identity,
        "incrementProductCode": "PRODUCT",
        "tntInstId": "GUAPW3SG",
        "version": "2",
        "incrementRateRules": [
            {"rate": Decimal("0.1234567890123456789"), "empty": None}
        ],
        "unknown": {"nested": [False, ""]},
        **extra,
    }


def page(rows):
    return {"status": 200, "body": {"success": True, "data": rows}}


@pytest.fixture(params=["directory", "zip"])
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
    browser = FakeBrowser(
        href="https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        result, output, error = run_cli(
            ["liquidity", action, "investment.products.history", *args]
        )
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


def test_native_history_refresh_and_request_free_replay(installed):
    cli, browser, config = installed
    cli("list", "--help")
    cli("describe")
    assert not browser.transports
    rows = [row(), row("VERSION-1", version="1", tntInstId="")]
    browser.business_script.append(page(rows))
    live = cli("list", "--live", *FLAGS, "--require-complete", "--limit", "0")
    assert live["data"] == rows
    assert live["meta"]["complete"] is True
    assert live["meta"]["acquisition"]["reported_total"] is None
    assert not (config / "leaf-cache.sqlite3").exists()
    assert browser.business_requests == [
        {"tntInstId": "GUAPW3SG", "incrementProductCode": "PRODUCT"}
    ]
    browser.business_script.append(page(rows))
    saved = cli("refresh", *FLAGS, "--require-complete")
    assert saved["meta"]["published"] is True
    count = len(browser.business_requests)
    browser.running = False
    offline = cli("list", "--require-complete", "--limit", "0")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == count
    other = cli("list", "--product-code", "OTHER")
    assert other["data"] == []
    assert other["meta"]["complete"] is False
    assert other["meta"]["dataset_complete"] is False
    assert other["meta"]["warnings"]
    assert (
        cli("list", "--product-code", "OTHER", "--require-complete", code=1)["error"][
            "code"
        ]
        == "INCOMPLETE_RESULT"
    )
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("flags", [[], ["--product-code", " "]])
def test_required_scope_before_browser(installed, flags):
    cli, browser, _ = installed
    result = cli("list", "--live", *flags, code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize(
    "failure",
    [
        "business",
        "marker",
        "shape",
        "row",
        "code",
        "identity",
        "tenant",
        "auth",
        "duplicate",
        "conflict",
    ],
)
def test_failed_history_preserves_previous_snapshot(installed, failure):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    candidate = page([row("NEW")])
    body = candidate["body"]
    expected = "INVALID_RESPONSE"
    if failure == "business":
        body["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        body["success"] = "true"
    elif failure == "shape":
        body["data"] = {"data": [row()]}
    elif failure == "row":
        body["data"] = [None]
    elif failure == "code":
        body["data"][0]["incrementProductCode"] = "OTHER"
    elif failure == "identity":
        body["data"][0]["incrementProductId"] = ""
    elif failure == "tenant":
        body["data"][0]["tntInstId"] = "OTHER"
    elif failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure in {"duplicate", "conflict"}:
        body["data"] = [
            row(),
            row() if failure == "duplicate" else row(version="CHANGED"),
        ]
        expected = "INCOMPLETE_RESULT"
    browser.business_script.append(candidate)
    result = cli("refresh", *FLAGS, "--require-complete", code=1)
    assert result["error"]["code"] == expected
    assert result["meta"]["published"] is False
    assert cli("list")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_empty_history_never_adds_current_and_preserves_capture(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    browser.business_script.append(page([]))
    live = cli("list", "--live", *FLAGS, "--require-complete")
    assert live["data"] == [] and live["meta"]["complete"] is True
    browser.business_script.append(page([]))
    assert cli("refresh", *FLAGS, "--require-complete")["meta"]["published"] is False
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == 3


def test_undeclared_request_field_rejected_before_fetch(installed, run_cli, tmp_path):
    cli, browser, _ = installed
    code, output, error = run_cli(
        ["plugins", "uninstall", "liquidity.investment.products.history"]
    )
    assert code == 0, output + error
    source = tmp_path / "badrequest"
    shutil.copytree(SOURCE, source)
    path = source / "adapter.py"
    text = path.read_text()
    assert "return context" in text
    path.write_text(
        text.replace("return context", 'return {**context, "mutation": "Y"}')
    )
    code, output, error = run_cli(["plugins", "install", str(source)])
    assert code == 0, output + error
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests
