"""Forecast-point composite identities preserve meaningful empty/null native values."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "leaf_packages/liquidity/forecast.cashflows"
FLAGS = [
    "--account-alias",
    "ACCOUNT",
    "--currency",
    "USD",
    "--inst-id",
    "ENTITY",
    "--from-date",
    "20260308",
    "--to-date",
    "20260308",
]


def row(created=1, **extra):
    return {
        **dict(
            entity="ENTITY",
            bankId="BANK",
            bankAccountAliasName="ACCOUNT",
            bankAccountNo="",
            accountType="",
            currency="USD",
            bankAccountFlowDateSourceType="EXCHANGE_INSTRUCTION",
            fundDirection="Credit",
            expectValueDateTime="202603081000",
            extBizType="",
            subBizType="",
            originalBizNo="",
            gmtCreate=created,
            gmtModified=created,
            amountStr="123.4500",
            amount={"amount": Decimal("123.4500"), "cent": 12345, "currency": "USD"},
            timeZone="",
            unknown={"nested": [None, False]},
        ),
        **extra,
    }


def page(rows):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "bankAccountCashFlowVOList": rows,
                "actutalRecordNum": len(rows),
                "currentRecordNum": len(rows),
            },
        },
    }


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
            ["liquidity", action, "forecast.cashflows", *args]
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


def test_full_point_identity_and_null_created_refresh_offline(installed):
    cli, browser, config = installed
    cli("list", "--help")
    cli("describe")
    assert not browser.transports
    rows = [
        row(None),
        row(1),
        row(2),
        row(1, bankAccountFlowDateSourceType="SETTLE_INSTRUCTION"),
        row(1, fundDirection="Debit"),
    ]
    browser.business_script.append(page(rows))
    live = cli("list", "--live", *FLAGS, "--require-complete", "--limit", "0")
    assert live["data"] == rows and live["meta"]["complete"] is True
    assert not (config / "leaf-cache.sqlite3").exists()
    assert all("id" not in r for r in live["data"])
    assert (
        live["data"][0]["gmtCreate"] is None
        and live["data"][0]["amountStr"] == "123.4500"
    )
    q = browser.business_requests[0]
    assert set(q) == {"tntInstId", "cashFlowDataQueryVO"}
    assert parse(q["cashFlowDataQueryVO"]) == {
        "instId": "ENTITY",
        "aliasName": ["ACCOUNT"],
        "currency": ["USD"],
        "beginValueDay": "20260308",
        "endValueDay": "20260308",
        "minAmount": None,
        "maxAmount": None,
    }
    browser.business_script.append(page(rows))
    saved = cli("refresh", *FLAGS, "--require-complete")
    assert saved["meta"]["published"] is True
    count = len(browser.business_requests)
    browser.running = False
    offline = cli("list", "--require-complete", "--limit", "0")
    assert offline["data"] == rows and len(browser.business_requests) == count
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "count",
        "alias",
        "entity",
        "currency",
        "date",
        "timestamp",
        "business",
        "auth",
        "conflict",
    ],
)
def test_failed_point_acquisition_keeps_previous_snapshot(installed, failure):
    cli, browser, _ = installed
    browser.business_script.append(page([row(None)]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    candidate = page([row(2)])
    r = candidate["body"]["result"]
    expected = "INVALID_RESPONSE"
    if failure == "missing":
        del r["bankAccountCashFlowVOList"][0]["gmtCreate"]
    elif failure == "count":
        r["actutalRecordNum"] = 2
        expected = "INCOMPLETE_RESULT"
    elif failure in ("alias", "entity", "currency"):
        field = {
            "alias": "bankAccountAliasName",
            "entity": "entity",
            "currency": "currency",
        }[failure]
        r["bankAccountCashFlowVOList"][0][field] = "OTHER"
    elif failure == "date":
        r["bankAccountCashFlowVOList"][0]["expectValueDateTime"] = "202603091000"
    elif failure == "timestamp":
        r["bankAccountCashFlowVOList"][0]["gmtCreate"] = True
    elif failure == "business":
        r["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "conflict":
        candidate = page([row(2), row(2, amountStr="999")])
        expected = "INCOMPLETE_RESULT"
    browser.business_script.append(candidate)
    result = cli("refresh", *FLAGS, "--require-complete", code=1)
    assert result["error"]["code"] == expected and result["meta"]["published"] is False
    assert cli("list")["data"] == [row(None)]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "flags", [[], FLAGS[:-2], [*FLAGS[:-2], "--to-date", "20260230"]]
)
def test_required_ordered_scope_before_browser(installed, flags):
    cli, browser, _ = installed
    assert cli("list", "--live", *flags, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports
