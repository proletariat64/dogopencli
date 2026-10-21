"""Installed request-bound accuracy preserves legacy scope and atomicity."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "leaf_packages/liquidity/forecast.accuracy"
FLAGS = ["--account-alias", "ACCOUNT", "--record-date", "2026-03-08"]
BASE_VO = "bankCashForecastRecordQueryVo"
METRIC_VO = "bankAccountDetailCashFlowQueryVO"


def row(index=0, **overrides):
    return {
        "id": str(index),
        "bankAccountAliasName": "ACCOUNT",
        "currency": "USD",
        "valueDate": "20260309",
        "baseValueDate": "20260308",
        "recordCreateTime": "123456",
        "forecastBalance": "0.00",
        "cashFlowTransIn": Decimal("0.123456789012345678901"),
        "cashFlowTransOut": "",
        "forecastTaskId": "TASK",
        "forecastBatchNo": 1,
        "forecastRuleId": None,
        "accountNo": "NUMBER",
        "instId": "ENTITY",
        "bankId": "BANK",
        "tntInstId": "GUAPW3SG",
        "unknown": {"nested": True},
        **overrides,
    }


def base(rows, total=None):
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


def metric(**values):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "bankAccountDetailDayVO": {
                    "cashFlowAccuracy": "1",
                    "realizedBalance": "0.00",
                    "flowAccuracy": "",
                    "unknown": "excluded legacy field",
                    **values,
                },
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
            ["liquidity", action, "forecast.accuracy", *args]
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


def test_bound_native_projection_refresh_and_request_free_replay(installed):
    cli, browser, config = installed
    cli("list", "--help")
    cli("describe")
    assert not browser.transports
    native = [row(9), row(2, forecastBalance="1.234567890123456789")]
    browser.business_script.extend(
        [base(native), metric(), metric(realizedBalance=None)]
    )
    live = cli("list", "--live", *FLAGS, "--limit", "0", "--require-complete")
    rows = live["data"]
    assert [r["id"] for r in rows] == ["9", "2"]
    assert rows[0]["forecastBalance"] == "0.00"
    assert rows[0]["cashFlowTransIn"] == native[0]["cashFlowTransIn"]
    assert rows[0]["accuracy"]["flowAccuracy"] == ""
    assert rows[1]["accuracy"]["realizedBalance"] is None
    assert rows[0]["accuracy"]["inflowAccuracy"] is None
    assert "unknown" not in rows[0] and "accountNo" not in rows[0]
    assert "unknown" not in rows[0]["accuracy"]
    assert not (config / "leaf-cache.sqlite3").exists()
    first = parse(browser.business_requests[0][BASE_VO])
    assert first == {
        "tntInstId": "GUAPW3SG",
        "recordStartTime": "000000",
        "recordEndTime": "235959",
        "rowStart": 0,
        "pageSize": 5000,
        "aliasName": ["ACCOUNT"],
        "valueStartDay": "20260308",
        "valueEndDay": "20260308",
    }
    for request, original in zip(browser.business_requests[1:], native, strict=True):
        assert set(request) == {"tntInstId", METRIC_VO}
        context = parse(request[METRIC_VO])
        assert context == {
            "forecastRecordId": original["id"],
            "aliasName": "ACCOUNT",
            "accountNo": "NUMBER",
            "instId": "ENTITY",
            "bankId": "BANK",
            "currency": "USD",
            "valueDate": "20260309",
            "forecastBalance": "0"
            if original["id"] == "9"
            else original["forecastBalance"],
        }
    browser.business_script.extend(
        [base(native), metric(), metric(realizedBalance=None)]
    )
    saved = cli("refresh", *FLAGS, "--require-complete")
    assert saved["meta"]["published"] is True
    count = len(browser.business_requests)
    browser.running = False
    offline = cli("list", "--require-complete", "--limit", "0")
    assert offline["data"] == rows
    assert len(browser.business_requests) == count
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert offline["meta"]["acquisition"]["attempts"][0]["metric_succeeded"] == 2


@pytest.mark.parametrize(
    "flags",
    [
        [],
        FLAGS[:2],
        [*FLAGS[:2], "--record-date", "2026-02-30"],
        ["--account-alias", " ", *FLAGS[2:]],
    ],
)
def test_invalid_scope_before_browser(installed, flags):
    cli, browser, _ = installed
    assert cli("list", "--live", *flags, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate",
        "count",
        "limit",
        "identity",
        "binding",
        "alias",
        "tenant",
        "balance",
        "total_type",
        "base_business",
        "metric_business",
        "metric_shape",
        "auth",
    ],
)
def test_atomic_failure_preserves_prior_capture(installed, failure):
    cli, browser, _ = installed
    browser.business_script.extend([base([row()]), metric()])
    saved = cli("refresh", *FLAGS, "--require-complete")
    candidate = base([row(1), row(2)])
    data = candidate["body"]["result"]
    expected = "INVALID_RESPONSE"
    if failure == "duplicate":
        data["dataValue"] = [row(1), row(1)]
        expected = "INCOMPLETE_RESULT"
    elif failure == "count":
        data["count"] = 3
        expected = "INCOMPLETE_RESULT"
    elif failure == "limit":
        candidate = base([row(i) for i in range(101)])
        expected = "INCOMPLETE_RESULT"
    elif failure == "identity":
        data["dataValue"][1]["id"] = 2
    elif failure == "binding":
        data["dataValue"][1]["bankId"] = ""
    elif failure == "alias":
        data["dataValue"][1]["bankAccountAliasName"] = "OTHER"
    elif failure == "tenant":
        data["dataValue"][1]["tntInstId"] = "OTHER"
    elif failure == "balance":
        data["dataValue"][1]["forecastBalance"] = None
    elif failure == "total_type":
        data["count"] = True
    elif failure == "base_business":
        data["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    metric_fail = metric()
    if failure == "metric_business":
        metric_fail["body"]["result"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "metric_shape":
        metric_fail["body"]["result"]["bankAccountDetailDayVO"] = []
    elif failure == "auth":
        metric_fail = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    browser.business_script.extend([candidate, metric(), metric_fail])
    before = len(browser.business_requests)
    result = cli("refresh", *FLAGS, "--require-complete", code=1)
    assert result["error"]["code"] == expected
    assert result["meta"]["published"] is False
    assert len(browser.business_requests) - before == (
        3 if failure in {"metric_business", "metric_shape", "auth"} else 1
    )
    assert cli("list")["data"][0]["id"] == "0"
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_empty_metric_is_preserved_as_unknown_projected_values(installed):
    cli, browser, _ = installed
    response = metric()
    response["body"]["result"]["bankAccountDetailDayVO"] = {}
    browser.business_script.extend([base([row()]), response])
    result = cli("list", "--live", *FLAGS, "--require-complete")
    assert all(v is None for v in result["data"][0]["accuracy"].values())


def test_empty_refresh_keeps_prior_nonempty_result(installed):
    cli, browser, _ = installed
    browser.business_script.extend([base([row()]), metric()])
    saved = cli("refresh", *FLAGS, "--require-complete")
    browser.business_script.append(base([]))
    assert cli("refresh", *FLAGS, "--require-complete")["meta"]["published"] is False
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_undeclared_metric_payload_rejected_before_fetch(installed, run_cli, tmp_path):
    cli, browser, _ = installed
    code, output, error = run_cli(
        ["plugins", "uninstall", "liquidity.forecast.accuracy"]
    )
    assert code == 0, output + error
    source = tmp_path / "badrequest"
    shutil.copytree(SOURCE, source)
    path = source / "adapter.py"
    text = path.read_text()
    assert "inner = dict(parameters)" in text
    path.write_text(
        text.replace(
            "inner = dict(parameters)", 'inner = {**parameters, "mutation": "Y"}'
        )
    )
    code, output, error = run_cli(["plugins", "install", str(source)])
    assert code == 0, output + error
    browser.business_script.append(base([row()]))
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert len(browser.business_requests) == 1
