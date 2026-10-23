"""Installed T3 inquiry contracts, native values and saved coverage."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
LEAF = "forecast.account_t3"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
FLAGS = [
    "--account-alias",
    "ACCOUNT",
    "--from-date",
    "20261019",
    "--to-date",
    "20261020",
]


def row(index=0, **values):
    return {
        "aliasName": "ACCOUNT",
        "currency": "USD",
        "entity": "ENTITY",
        "bankId": "BANK",
        "forecastDate": "20261019",
        "expectValueDate": "20261025",
        "fundActionType": "ACTION",
        "dateFlag": str(index),
        "amount": "123.4500",
        "timeZone": None,
        "unknown": {
            "precise": Decimal("0.123456789012345678901"),
            "array": [None, False, 1],
        },
        **values,
    }


def page(rows, total=None, **echo):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "data": rows,
                "totalCount": len(rows) if total is None else total,
                **echo,
            },
        },
    }


@pytest.fixture(params=["directory"])
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
        result, output, error = run_cli(["liquidity", action, LEAF, *args])
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


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_full_native_arrival_order_detached_install_and_saved_scope(installed):
    cli, browser, config = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.transports
    rows = [row(8), row(2, forecastDate="20261020")]
    browser.business_script.append(page(rows, pageSize=1000, rowStart=0))
    assert (
        cli("list", "--live", *FLAGS, "--limit", "0", "--require-complete")["data"]
        == rows
    )
    assert not (config / "leaf-cache.sqlite3").exists()
    browser.business_script.append(page(rows))
    saved = cli("refresh", *FLAGS, "--require-complete")
    assert cli("list", "--limit", "0")["data"] == rows
    assert cli("list", *FLAGS, "--require-complete")["data"] == rows
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert (
        browser.business_requests
        == [
            {
                "aliasName": "ACCOUNT",
                "startDate": "20261019",
                "endDate": "20261020",
                "rowStart": 0,
                "pageSize": 1000,
            }
        ]
        * 2
    )
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions and all(
        "/t3ForecastDemandList.json" in e
        and 'method: "POST"' in e
        and "application/json" in e
        for e in expressions
    )


@pytest.mark.parametrize(
    "flags",
    [
        [],
        ["--account-alias", "ANY", "--from-date", "20261019", "--to-date", "20261020"],
        ["--account-alias", "A,B", "--from-date", "20261019", "--to-date", "20261020"],
        ["--account-alias", "A", "--from-date", "20260230", "--to-date", "20261020"],
        ["--account-alias", "A", "--from-date", "20261021", "--to-date", "20261020"],
        [
            "--account-alias",
            "A",
            "--from-date",
            "２０２６１０１９",
            "--to-date",
            "20261020",
        ],
    ],
)
def test_invalid_scope_before_browser(installed, flags):
    cli, browser, _ = installed
    assert cli("list", "--live", *flags, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


def test_offline_alias_and_forecast_date_filter_coverage(installed):
    cli, browser, config = installed
    rows = [row(), row(1, forecastDate="20261020")]
    browser.business_script.append(page(rows))
    saved = cli("refresh", *FLAGS, "--require-complete")
    files = [config / "leaf-cache.sqlite3", config / "leaf-cache.sqlite3-wal"]
    before = {p: p.read_bytes() for p in files if p.exists()}
    assert cli("list", "--from-date", "20261020")["data"] == rows[1:]
    assert cli("list", "--to-date", "20261019")["data"] == rows[:1]
    assert cli("list", "--account-alias", "OTHER")["data"] == []
    assert (
        cli("list", "--from-date", "20261020", "--require-complete", code=1)["error"][
            "code"
        ]
        == "INCOMPLETE_RESULT"
    )
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert {p: p.read_bytes() for p in before} == before
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "marker",
        "root",
        "rows",
        "total",
        "identity",
        "date",
        "alias_scope",
        "date_scope",
        "size",
        "offset",
    ],
)
def test_failure_preserves_saved_snapshot(installed, failure):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    candidate = page([row(1)])
    data = candidate["body"]["data"]
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        candidate["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        candidate["body"]["success"] = 1
    elif failure == "root":
        candidate["body"]["data"] = []
    elif failure == "rows":
        data["data"] = None
    elif failure == "total":
        data["totalCount"] = True
    elif failure == "identity":
        data["data"][0]["dateFlag"] = True
    elif failure == "date":
        data["data"][0]["forecastDate"] = "20260230"
    elif failure == "alias_scope":
        data["data"][0]["aliasName"] = "OTHER"
    elif failure == "date_scope":
        data["data"][0]["forecastDate"] = "20261021"
    elif failure == "size":
        data["pageSize"] = 100
    else:
        data["rowStart"] = 1
    browser.business_script.append(candidate)
    result = cli("refresh", *FLAGS, "--require-complete", code=1)
    assert result["error"]["code"] == expected
    assert result["meta"]["published"] is False
    assert cli("list")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("mode", ["duplicate", "conflict", "gap", "changed_total"])
def test_completeness_never_replaces_saved_capture(installed, mode):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    if mode in ("duplicate", "conflict"):
        browser.business_script.append(
            page([row(1), row(1, amount="99") if mode == "conflict" else row(1)])
        )
    elif mode == "gap":
        browser.business_script.append(page([row(1)], total=2))
    else:
        browser.business_script.extend(
            [
                page([row(i) for i in range(1000)], total=1001),
                page([row(1000)], total=1002),
            ]
        )
    assert cli("refresh", *FLAGS, "--require-complete", code=1)["error"]["code"] == (
        "INVALID_RESPONSE" if mode == "changed_total" else "INCOMPLETE_RESULT"
    )
    assert cli("list")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_offset_stride_no_terminal_probe_and_display_window(installed):
    cli, browser, _ = installed
    rows = [row(i) for i in range(1001)]
    browser.business_script.extend(
        [page(rows[:1000], total=1001), page(rows[1000:], total=1001)]
    )
    result = cli(
        "list",
        "--live",
        *FLAGS,
        "--offset",
        "1000",
        "--limit",
        "1",
        "--require-complete",
    )
    assert result["data"] == rows[1000:]
    assert [v["rowStart"] for v in browser.business_requests] == [0, 1000]
    assert all(v["pageSize"] == 1000 for v in browser.business_requests)


def test_closed_transport_rejects_extra_context(installed, run_cli, tmp_path):
    cli, browser, _ = installed
    status, output, error = run_cli(["plugins", "uninstall", "liquidity." + LEAF])
    assert status == 0, output + error
    source = tmp_path / "badrequest"
    shutil.copytree(SOURCE, source)
    adapter = source / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            'return {**values, "rowStart": row_start, "pageSize": PAGE_SIZE}',
            'return {**values, "rowStart": row_start, '
            '"pageSize": PAGE_SIZE, "entity": "ENTITY"}',
        )
    )
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 0, output + error
    assert (
        cli("list", "--live", *FLAGS, code=1)["error"]["code"] == "REQUEST_NOT_ALLOWED"
    )
    assert not browser.business_requests


def test_successful_empty_native_scope(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([]))
    assert cli("list", "--live", *FLAGS, "--require-complete")["data"] == []
