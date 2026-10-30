"""Native cash pool reports through independently installed packages."""

from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAVES = [("cash.physical_pool_reports", "Physical_Cash_Pool")]


@pytest.fixture(
    params=[
        (leaf, pool, source) for leaf, pool in LEAVES for source in ("directory", "zip")
    ]
)
def installed(request, run_cli, tmp_path, monkeypatch):
    leaf, pool, source = request.param
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
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    try:
        cli("domain", "enable", "liquidity")
        package = ROOT / "leaf_packages/liquidity" / leaf
        if source == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        archive.write(path, path.relative_to(package))
            package = archive_path
        cli("plugins", "install", str(package))
        yield cli, browser, leaf, pool
    finally:
        cdp.set_transport_factory(None)


def native(rows, total=None, amount="123.0000000000000001"):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "data": rows,
                "totalCount": len(rows) if total is None else total,
                "totalAmount": amount,
            },
        },
    }


def flags(start="2026-10-17", end="2026-10-23"):
    return ["--from-date", start, "--to-date", end, "--timezone", "GMT+08"]


def test_each_independent_leaf_queries_its_fixed_native_pool_scope(installed):
    cli, browser, leaf, pool = installed
    rows = [
        {
            "id": "native-1",
            "cashPoolType": "",
            "valueDate": "20261023",
            "amount": "9007199254740993.0000000001",
            "closingBalance": "-0.00000000001",
            "currency": "USD",
            "direction": "IN",
            "unknown": [None, False, {"same": [1, 1]}],
        }
    ]
    browser.business_script.append(native(rows))
    result = cli(
        "liquidity",
        "list",
        leaf,
        *flags(),
        "--live",
        "--limit",
        "0",
        "--require-complete",
    )
    assert result["data"] == rows
    assert browser.business_requests == [
        {
            "tntInstId": "GUAPW3SG",
            "cashPoolType": pool,
            "valueDateStart": "20261017",
            "valueDateEnd": "20261023",
            "timezone": "GMT+08",
            "rowStart": 0,
            "pageSize": 1000,
        }
    ]
    assert result["meta"]["scope"]["cashPoolType"] == pool
    assert result["meta"]["acquisition"]["native_metadata"] == [
        {
            "position": 0,
            "page_size": 1000,
            "metadata": {"totalAmount": "123.0000000000000001"},
        }
    ]


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-02-29", "2026-03-01"),
        ("20260101", "2026-01-02"),
        ("2026-10-24", "2026-10-23"),
        ("2026-01-31", "2026-02-28"),
        ("2028-01-31", "2028-02-29"),
        ("2026-10-01", "2026-11-01"),
    ],
)
def test_invalid_or_calendar_month_dates_do_not_query(installed, start, end):
    cli, browser, leaf, _ = installed
    cli("liquidity", "list", leaf, *flags(start, end), "--live", code=2)
    assert not browser.business_requests


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-01-31", "2026-02-27"),
        ("2028-01-31", "2028-02-28"),
        ("2026-02-28", "2026-03-27"),
        ("2026-10-23", "2026-10-23"),
    ],
)
def test_valid_calendar_month_range_sends_exact_source_dates(installed, start, end):
    cli, browser, leaf, _ = installed
    browser.business_script.append(native([]))
    cli("liquidity", "list", leaf, *flags(start, end), "--live")
    assert browser.business_requests[0]["valueDateStart"] == start.replace("-", "")
    assert browser.business_requests[0]["valueDateEnd"] == end.replace("-", "")


@pytest.mark.parametrize(
    "extra",
    [
        ["--pool-type", "Notional_Cash_Pool"],
        ["--execute"],
        ["--tnt-inst-id", "OTHER"],
        ["--timezone", "Asia/Singapore"],
        ["--to-date", "9999-99-99"],
    ],
)
def test_unverified_arguments_do_not_query(installed, extra):
    cli, browser, leaf, _ = installed
    cli("liquidity", "list", leaf, *flags(), *extra, "--live", code=2)
    assert not browser.business_requests


def test_native_pages_and_metadata_rebuild_together_on_width_fallback(installed):
    cli, browser, leaf, pool = installed
    rows = [
        {
            "id": f"record-{i}",
            "cashPoolType": pool,
            "valueDate": "20261023",
            "amount": str(i),
        }
        for i in range(101)
    ]
    browser.business_script.extend(
        [
            native(rows[:100], 101, "rejected-candidate"),
            native(rows[:100], 101, "native-total"),
            native(rows[100:], 101, "native-total"),
        ]
    )
    result = cli(
        "liquidity",
        "list",
        leaf,
        *flags(),
        "--live",
        "--require-complete",
        "--limit",
        "0",
    )
    assert result["data"] == rows
    assert [(x["rowStart"], x["pageSize"]) for x in browser.business_requests] == [
        (0, 1000),
        (0, 100),
        (100, 100),
    ]
    assert result["meta"]["acquisition"]["native_metadata"] == [
        {"position": 0, "page_size": 100, "metadata": {"totalAmount": "native-total"}},
        {
            "position": 100,
            "page_size": 100,
            "metadata": {"totalAmount": "native-total"},
        },
    ]


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "business",
        "auth",
        "success",
        "rows",
        "total",
        "id",
        "pool",
        "date",
        "duplicate",
        "conflict",
        "gap",
        "changing_total",
    ],
)
def test_failed_refresh_preserves_previous_native_capture_and_metadata(
    installed, failure
):
    cli, browser, leaf, pool = installed
    rows = [
        {
            "id": "saved",
            "cashPoolType": "",
            "valueDate": "20261023",
            "amount": "1.00000000000001",
        }
    ]
    browser.business_script.append(native(rows, amount="9007199254740993.0000000001"))
    refreshed = cli("liquidity", "refresh", leaf, *flags(), "--require-complete")
    before = cli("liquidity", "list", leaf, "--limit", "0")
    assert before["data"] == rows
    assert (
        before["meta"]["source_acquisition"]["native_metadata"]
        == refreshed["meta"]["acquisition"]["native_metadata"]
    )
    bad = {**rows[0]}
    response = native([bad], amount="should-not-publish")
    if failure == "empty":
        response = native([])
    elif failure == "business":
        response["body"]["success"] = False
    elif failure == "auth":
        response["status"] = 401
    elif failure == "success":
        response["body"]["success"] = "true"
    elif failure == "rows":
        response["body"]["data"]["data"] = None
    elif failure == "total":
        response["body"]["data"]["totalCount"] = True
    elif failure == "id":
        bad["id"] = ""
    elif failure == "pool":
        bad["cashPoolType"] = "Notional_Cash_Pool"
    elif failure == "date":
        bad["valueDate"] = "20261024"
    elif failure == "duplicate":
        response = native([bad, bad], 2)
    elif failure == "conflict":
        response = native([bad, {**bad, "amount": "2.00"}], 2)
    elif failure == "gap":
        response = native([bad], 2)
    if failure == "changing_total":
        first = [{**bad, "id": f"first-{i}"} for i in range(1000)]
        browser.business_script.extend([native(first, 1001), native([bad], 1002)])
    else:
        browser.business_script.extend([response, response])
    failed = cli(
        "liquidity",
        "refresh",
        leaf,
        *flags(),
        "--require-complete",
        code=0 if failure == "empty" else 1,
    )
    assert failed["meta"]["published"] is False
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"] == rows
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]
    assert after["meta"]["source_acquisition"] == before["meta"]["source_acquisition"]


def test_live_date_scope_preserves_saved_capture_and_metadata(installed):
    cli, browser, leaf, pool = installed
    saved = [{"id": "same-native-id", "cashPoolType": "", "valueDate": "20261023"}]
    different = [{"id": "same-native-id", "cashPoolType": "", "valueDate": "20261020"}]
    browser.business_script.append(native(saved, amount="original-total"))
    cli("liquidity", "refresh", leaf, *flags(), "--require-complete")
    before = cli("liquidity", "list", leaf, "--limit", "0")
    browser.business_script.append(native(different, amount="live-total"))
    live = cli(
        "liquidity",
        "list",
        leaf,
        *flags("2026-10-20", "2026-10-20"),
        "--live",
        "--limit",
        "0",
    )
    assert live["data"] == different
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"] == saved
    assert after["meta"]["scope"]["cashPoolType"] == pool
    assert after["meta"]["source_acquisition"] == before["meta"]["source_acquisition"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]
