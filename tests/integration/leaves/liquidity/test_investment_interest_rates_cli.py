"""Native rate sources preserve their identities and source-specific counts."""

import shutil
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "leaf_packages/liquidity/investment.interest_rates"


def row(source="market", index=0, **extra):
    r = {
        "currency": "USD",
        "rateValue": "1.2345000",
        "ruleValue": "0.009900",
        "unknown": {
            "amount": Decimal("0.123456789012345678901"),
            "nested": [None, False],
        },
    }
    if source == "market":
        r.update(
            rateName="RATE" + str(index), ratePeriod="1D", effectiveDate="2026-03-08"
        )
    elif source == "bank":
        r.update(
            bankId="BANK" + str(index),
            productTerm="1D",
            productType="DEPOSIT",
            quoteDate="20260308",
        )
    else:
        r.update(
            ruleId="RULE" + str(index),
            rateCategory="CUSTOMER_TYPE"
            if source == "expectation-rule"
            else "FINANCIAL_INST_TYPE",
            ruleStatus="DEPRECATED",
            version="3",
        )
    return {**r, **extra}


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "data": rows,
                "totalCount": len(rows) if total is None else total,
                "rowStart": 0,
                "pageSize": 0,
            },
        },
    }


def flags(source):
    return ["--source", source] + (
        ["--from-date", "20260308", "--to-date", "2026-03-08"]
        if source in ("market", "bank")
        else []
    )


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
            ["liquidity", action, "investment.interest_rates", *args]
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


@pytest.mark.parametrize("source", ["market", "bank", "expectation-rule", "expection"])
def test_each_source_full_native_live_refresh_offline(installed, source):
    cli, browser, config = installed
    cli("list", "--help")
    cli("describe")
    assert not browser.transports
    rows = [row(source, i) for i in range(3)]
    total = 1 if source == "bank" else 3
    browser.business_script.append(page(rows, total))
    live = cli("list", "--live", *flags(source), "--require-complete", "--limit", "0")
    assert live["data"] == rows and live["meta"]["complete"] is True
    assert live["meta"]["reported_total"] == total
    if source == "bank":
        assert (
            live["meta"]["total_semantics"] == "quote_date_groups"
            and live["meta"]["collected_total"] == 3
        )
    assert not (config / "leaf-cache.sqlite3").exists()
    request = browser.business_requests[0]
    assert request["pageSize"] == 1000 and request["rowStart"] == 0
    if source == "bank":
        assert request["beginDate"] == "2026-03-08"
    if source == "market":
        assert request["beginDate"] == "20260308" and request["currency"] == []
    browser.business_script.append(page(rows, total))
    saved = cli("refresh", *flags(source), "--require-complete")
    assert saved["meta"]["published"] is True
    count = len(browser.business_requests)
    browser.running = False
    assert cli("list", "--limit", "0", "--require-complete")["data"] == rows
    assert len(browser.business_requests) == count
    assert cli("list", "--currency", "CNY")["data"] == []
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_bank_stride_is_groups_not_rate_rows(installed):
    cli, browser, _ = installed
    start = datetime(2020, 1, 1)
    rows = [
        row("bank", 0, quoteDate=(start + timedelta(days=i)).strftime("%Y%m%d"))
        for i in range(1001)
    ]
    browser.business_script.extend([page(rows[:1000], 1001), page(rows[1000:], 1001)])
    result = cli(
        "list",
        "--live",
        "--source",
        "bank",
        "--from-date",
        "20200101",
        "--to-date",
        "20231231",
        "--require-complete",
        "--limit",
        "0",
    )
    assert result["data"] == rows
    assert [r["rowStart"] for r in browser.business_requests] == [0, 1000]


@pytest.mark.parametrize(
    "failure",
    [
        "group_gap",
        "duplicate",
        "count_change",
        "business",
        "auth",
        "identity",
        "category",
        "scope",
    ],
)
def test_failures_keep_prior_capture(installed, failure):
    cli, browser, _ = installed
    browser.business_script.append(page([row("bank")], 1))
    saved = cli("refresh", *flags("bank"), "--require-complete")
    candidate = page([row("bank")], 1)
    expected = "INVALID_RESPONSE"
    if failure == "group_gap":
        candidate = page([row("bank")], 2)
        expected = "INCOMPLETE_RESULT"
    elif failure == "duplicate":
        candidate = page([row("bank"), row("bank")], 1)
    elif failure == "count_change":
        candidate = page([row("bank")], 0)
    elif failure == "business":
        candidate["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "identity":
        candidate["body"]["data"]["data"][0]["bankId"] = ""
    elif failure == "category":
        candidate = page([row("expection", rateCategory="CUSTOMER_TYPE")])
    elif failure == "scope":
        candidate["body"]["data"]["data"][0]["quoteDate"] = "20260309"
    browser.business_script.append(candidate)
    selected = "expection" if failure == "category" else "bank"
    result = cli("refresh", *flags(selected), "--require-complete", code=1)
    assert result["error"]["code"] == expected and result["meta"]["published"] is False
    assert cli("list")["data"] == [row("bank")]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "selection",
    [
        [],
        ["--source", "bank"],
        ["--source", "market", "--from-date", "20260230", "--to-date", "20260308"],
        ["--source", "expection", "--from-date", "20260308"],
    ],
)
def test_invalid_scope_before_browser(installed, selection):
    cli, browser, _ = installed
    assert (
        cli("list", "--live", *selection, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    )
    assert not browser.transports


def test_expection_get_is_native_independent_and_live_only(installed):
    cli, browser, config = installed
    record = row(
        "expection",
        financialInstFilesMap={"nested": [None, False]},
        operationLogDetailList=[{"version": "1"}],
    )
    browser.business_script.append(
        {"status": 200, "body": {"success": True, "data": record}}
    )
    result = cli("get", "RULE0", "--source", "expection")
    assert result["data"] == record
    assert browser.business_requests == [{"id": "RULE0", "_output_charset": "utf-8"}]
    assert not (config / "leaf-cache.sqlite3").exists()
    count = len(browser.business_requests)
    assert (
        cli("get", "RULE0", "--source", "market", code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert len(browser.business_requests) == count
    browser.business_script.append(
        {"status": 200, "body": {"success": True, "data": row("expection", 1)}}
    )
    assert (
        cli("get", "RULE0", "--source", "expection", code=1)["error"]["code"]
        == "INVALID_RESPONSE"
    )
