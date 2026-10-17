"""Installed banks inquiry: public CLI with controlled CDP, never production."""

import json
import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/dogopencli/leaf_packages/liquidity/reference.banks"
ROWS = [
    {
        "bankId": "a",
        "cityCode": "SG",
        "bankName": "Synthetic A",
        "extra": None,
        "amount": Decimal("0.1234567890123456789"),
        "zero": 0,
        "empty": "",
    },
    {"bankId": "b", "cityCode": "US", "bankName": "Synthetic B"},
    {"bankId": "c", "cityCode": "sg", "bankName": "Synthetic C"},
]


def page(rows, *, total=None, success=True):
    return {
        "status": 200,
        "body": {
            "resultFlag": success,
            "result": {"bankVoList": rows},
            "count": len(rows) if total is None else total,
        },
    }


@pytest.fixture(params=["directory", "zip"])
def banks(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    browser = FakeBrowser(
        href="https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    try:
        cli("domain", "enable", "liquidity")
        source = SOURCE
        if request.param == "zip":
            source = tmp_path / "banks.zip"
            with ZipFile(source, "w") as archive:
                for path in SOURCE.iterdir():
                    if path.is_file():
                        archive.write(path, path.name)
        cli("plugins", "install", str(source))
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def test_installed_banks_types_country_and_lifecycle(banks):
    cli, browser, _ = banks
    cli("liquidity", "list", "reference.banks", "-h")
    described = cli("liquidity", "describe", "reference.banks")
    assert "cityCode" in json.dumps(described)
    assert not browser.business_requests
    browser.business_script.append(page(ROWS))
    live = cli(
        "liquidity",
        "list",
        "reference.banks",
        "--live",
        "--limit",
        "0",
        "--country",
        "SG",
        "--country",
        "US",
        "--country",
        "SG",
    )
    assert live["data"] == ROWS[:2]
    assert live["meta"]["complete"] is True
    assert (
        cli("liquidity", "list", "reference.banks", code=1)["error"]["code"]
        == "CACHE_MISS"
    )
    browser.business_script.append(page(ROWS))
    refreshed = cli("liquidity", "refresh", "reference.banks", "--limit", "1")
    assert refreshed["data"]["row_count"] == 3
    before = len(browser.business_requests)
    assert cli("liquidity", "list", "reference.banks", "--limit", "0")["data"] == ROWS
    assert (
        cli("liquidity", "list", "reference.banks", "--limit", "0", "--country", "SG")[
            "data"
        ]
        == ROWS[:1]
    )
    assert (
        cli(
            "liquidity",
            "list",
            "reference.banks",
            "--limit",
            "0",
            "--country",
            "SG",
            "--country",
            "US",
        )["data"]
        == live["data"]
    )
    assert len(browser.business_requests) == before
    for request in browser.business_requests:
        assert set(request) == {"tntInstId", "paraBankVO"}
        assert request["tntInstId"] == "GUAPW3SG"
        assert json.loads(request["paraBankVO"]) == {
            "tntInstId": "GUAPW3SG",
            "rowStart": 0,
            "pageSize": 5000,
        }
    cli("plugins", "uninstall", "liquidity.reference.banks")
    assert (
        cli("plugins", "uninstall", "liquidity.reference.banks")["data"]["removed"]
        is False
    )


def test_banks_collects_every_offset_before_display_limit(banks):
    cli, browser, _ = banks
    first = [{"bankId": str(i), "cityCode": "SG"} for i in range(5000)]
    browser.business_script.extend(
        [page(first, total=5001), page([ROWS[0]], total=5001)]
    )
    result = cli("liquidity", "list", "reference.banks", "--live", "--limit", "1")
    assert result["data"] == first[:1]
    assert result["meta"]["complete"] is True
    assert len(browser.business_requests) == 2
    offsets = [
        json.loads(request["paraBankVO"])["rowStart"]
        for request in browser.business_requests
    ]
    assert offsets == [0, 5000]


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "business",
        "nested-business",
        "shape",
        "missing-container",
        "identity",
        "invalid-total",
        "boolean-total",
        "changed-total",
        "early-empty",
        "oversize",
        "strict",
        "auth",
        "transport",
    ],
)
def test_banks_failed_refresh_preserves_native_snapshot(banks, failure):
    cli, browser, _ = banks
    browser.business_script.append(page(ROWS))
    cli("liquidity", "refresh", "reference.banks")
    before = cli("liquidity", "list", "reference.banks", "--limit", "0")
    expected = "INVALID_RESPONSE"
    flags = []
    responses = []
    if failure == "empty":
        response, expected = page([]), None
    elif failure == "business":
        response, expected = page([], success=False), "BUSINESS_QUERY_FAILED"
    elif failure == "nested-business":
        response, expected = page([]), "BUSINESS_QUERY_FAILED"
        response["body"]["result"]["success"] = False
    elif failure == "shape":
        response = page(["invalid"])
    elif failure == "missing-container":
        response = page([])
        del response["body"]["result"]["bankVoList"]
    elif failure == "identity":
        response = page([{"cityCode": "SG"}])
    elif failure == "invalid-total":
        response = page(ROWS, total="3")
    elif failure == "boolean-total":
        response = page(ROWS, total=True)
    elif failure in {"changed-total", "early-empty"}:
        responses.append(page([ROWS[0]], total=5001))
        response = page([], total=5002 if failure == "changed-total" else 5001)
    elif failure == "oversize":
        response = page([{"bankId": str(i)} for i in range(5001)])
    elif failure == "strict":
        response, expected = page([ROWS[0], ROWS[0]]), "INCOMPLETE_RESULT"
        flags = ["--require-complete"]
    elif failure == "auth":
        response, expected = {"status": 401, "body": {}}, "AUTH_REQUIRED"
    else:
        response, expected = {"error": "fetch failed"}, "TIMEOUT"
        browser.business_handler = lambda *_: response
    browser.business_script.extend([*responses, response])
    result = cli(
        "liquidity", "refresh", "reference.banks", *flags, code=1 if expected else 0
    )
    if expected:
        assert result["error"]["code"] == expected
    else:
        assert result["meta"]["published"] is False
    browser.business_handler = None
    after = cli("liquidity", "list", "reference.banks", "--limit", "0")
    assert after["data"] == before["data"] == ROWS
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


def test_banks_duplicate_identity_is_truthfully_incomplete(banks):
    cli, browser, _ = banks
    browser.business_script.append(page([ROWS[0], ROWS[0]]))
    result = cli("liquidity", "list", "reference.banks", "--live", "--limit", "0")
    assert result["data"] == ROWS[:1]
    assert result["meta"]["complete"] is False


def test_banks_conflicting_identity_rejects_response(banks):
    cli, browser, _ = banks
    browser.business_script.append(page([ROWS[0], {"bankId": "a", "cityCode": "US"}]))
    result = cli("liquidity", "list", "reference.banks", "--live", code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"


def test_banks_filtered_refresh_retains_full_native_scope(banks):
    cli, browser, _ = banks
    browser.business_script.append(page(ROWS))
    refreshed = cli("liquidity", "refresh", "reference.banks", "--country", "SG")
    assert refreshed["data"]["row_count"] == 3
    requests = len(browser.business_requests)
    all_rows = cli("liquidity", "list", "reference.banks", "--limit", "0")
    expanded = cli(
        "liquidity", "list", "reference.banks", "--limit", "0", "--country", "US"
    )
    assert all_rows["data"] == ROWS
    assert expanded["data"] == [ROWS[1]]
    assert all_rows["meta"]["complete"] is expanded["meta"]["complete"] is True
    assert len(browser.business_requests) == requests


def test_banks_request_boundary_rejects_unverified_native_country(banks, tmp_path):
    cli, browser, _ = banks
    cli("plugins", "uninstall", "liquidity.reference.banks")
    source = tmp_path / "unverified-request"
    shutil.copytree(SOURCE, source)
    adapter = source / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            '"tntInstId": TENANT,', '"unverifiedCountry": "SG", "tntInstId": TENANT,', 1
        )
    )
    cli("plugins", "install", str(source))
    result = cli("liquidity", "list", "reference.banks", "--live", code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests
