"""Installed account blacklist SDK acquisition, raw records and local filters."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
LEAF = "reference.blacklist.account"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
TENANT = "GUAPW3SG"


def row(alias="ACCOUNT", **values):
    return {
        "aliasName": alias,
        "instId": "ENTITY",
        "bankId": "BANK",
        "status": "VALID",
        "id": 0,
        "unknown": {
            "amount": Decimal("0.123456789012345678901"),
            "values": [None, False, "", 0],
        },
        **values,
    }


def page(rows, total=None, **extra):
    count = len(rows) if total is None else total
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": count,
            "result": {"success": True, "count": count, "data": rows},
            **extra,
        },
    }


def decoded_requests(browser):
    result = []
    for request in browser.business_requests:
        assert set(request) == {"tntInstId", "accountFilterConfigQuery"}
        assert request["tntInstId"] == TENANT
        assert isinstance(request["accountFilterConfigQuery"], str)
        result.append(parse(request["accountFilterConfigQuery"]))
    return result


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
def test_native_records_order_query_and_refresh_offline(installed):
    cli, browser, config = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.transports
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    rows = [
        row("Z", tntInstId=""),
        row("A"),
        row("M", tntInstId=TENANT, status="INVALID"),
    ]
    browser.business_script.append(page(rows))
    live = cli("list", "--live", "--limit", "0", "--require-complete")
    assert live["data"] == rows
    assert live["meta"]["reported_total"] == 3
    assert not (config / "leaf-cache.sqlite3").exists()
    browser.business_script.append(page(rows))
    saved = cli("refresh", "--require-complete")
    calls = len(browser.business_requests)
    offline = cli("list", "--limit", "0")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == calls
    assert (
        decoded_requests(browser)
        == [
            {
                "tntInstId": TENANT,
                "timezone": "GMT+08",
                "currentArea": "3",
                "rowStart": 0,
                "pageSize": 5000,
            }
        ]
        * 2
    )
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions and all(
        "/accountFilterConfigQuery.json" in e and 'method: "GET"' in e
        for e in expressions
    )


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (["--entity", "ENTITY"], ["Z", "A", "M"]),
        (["--bank-id", "BANK", "--bank-id", "OTHER", "--status", "INVALID"], ["A"]),
        (["--account-alias", "A"], ["A"]),
        (["--bank-id", "B"], []),
        (["--bank-id", "BANK,OTHER"], []),
        (["--bank-id", "*"], ["M"]),
        (["--entity", "entity"], []),
    ],
)
def test_exact_repeat_local_filters_preserve_source_order_and_scope(
    installed, flags, expected
):
    cli, browser, _ = installed
    rows = [row("Z"), row("A", bankId="OTHER", status="INVALID"), row("M", bankId="*")]
    browser.business_script.append(page(rows))
    cli("refresh", "--require-complete")
    filtered = cli("list", *flags, "--limit", "0", "--fields", "aliasName")
    assert filtered["data"] == [{"aliasName": alias} for alias in expected]
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize("flag", ["entity", "bank-id", "account-alias", "status"])
def test_blank_local_filter_rejects_before_auth(installed, flag):
    cli, browser, _ = installed
    assert (
        cli("list", "--live", "--" + flag, " ", code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert not browser.transports


def test_short_candidate_fallback_restarts_without_mixing_rows(installed):
    cli, browser, _ = installed
    browser.business_script.extend(
        [page([row("GHOST")], total=2), page([row("A"), row("B")])]
    )
    result = cli("refresh", "--require-complete")
    assert result["data"]["row_count"] == 2
    assert cli("list", "--limit", "0")["data"] == [row("A"), row("B")]
    assert [(r["rowStart"], r["pageSize"]) for r in decoded_requests(browser)] == [
        (0, 5000),
        (0, 1000),
    ]


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "outer_false",
        "outer_type",
        "inner_false",
        "inner_missing",
        "inner_type",
        "outer_count",
        "inner_count",
        "count_mismatch",
        "rows",
        "id",
        "tenant",
    ],
)
def test_hard_failure_preserves_saved_capture_without_fallback(installed, failure):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", "--require-complete")
    candidate = page([row("OTHER")])
    outer = candidate["body"]
    inner = outer["result"]
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "outer_false":
        outer["resultFlag"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "outer_type":
        outer["resultFlag"] = 1
    elif failure == "inner_false":
        inner["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "inner_missing":
        inner.pop("success")
    elif failure == "inner_type":
        inner["success"] = 1
    elif failure == "outer_count":
        outer["count"] = True
    elif failure == "inner_count":
        inner["count"] = "1"
    elif failure == "count_mismatch":
        outer["count"] = 2
    elif failure == "rows":
        inner["data"] = None
    elif failure == "id":
        inner["data"] = [row(123)]
    else:
        inner["data"] = [row(tntInstId="OTHER")]
    browser.business_script.append(candidate)
    failed = cli("refresh", "--require-complete", code=1)
    assert failed["error"]["code"] == expected
    assert failed["meta"]["published"] is False
    assert len(browser.business_requests) == 2
    cached = cli("list")
    assert cached["data"] == [row()]
    assert cached["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("conflict", [False, True])
def test_duplicate_or_conflicting_aliases_remain_incomplete(installed, conflict):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", "--require-complete")
    duplicate = [row("SAME"), row("SAME", bankId="OTHER") if conflict else row("SAME")]
    browser.business_script.extend([page(duplicate), page(duplicate)])
    assert (
        cli("refresh", "--require-complete", code=1)["error"]["code"]
        == "INCOMPLETE_RESULT"
    )
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_offset_stride_uses_qualified_width_and_no_extra_terminal_probe(installed):
    cli, browser, _ = installed
    rows = [{"aliasName": str(i)} for i in range(5001)]
    browser.business_script.extend(
        [page(rows[:5000], total=5001), page(rows[5000:], total=5001)]
    )
    result = cli("list", "--live", "--limit", "1", "--require-complete")
    assert result["data"] == rows[:1]
    assert result["meta"]["collected_total"] == 5001
    assert [(r["rowStart"], r["pageSize"]) for r in decoded_requests(browser)] == [
        (0, 5000),
        (5000, 5000),
    ]


def test_nested_closed_request_rejects_unverified_selector(
    installed, run_cli, tmp_path
):
    cli, browser, _ = installed
    status, output, error = run_cli(["plugins", "uninstall", "liquidity." + LEAF])
    assert status == 0, output + error
    source = tmp_path / "badrequest"
    shutil.copytree(SOURCE, source)
    adapter = source / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            '"rowStart": row_start,', '"unverified": True, "rowStart": row_start,'
        )
    )
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 0, output + error
    assert cli("list", "--live", code=1)["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_empty_native_array_is_valid_without_synthesizing_records(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([]))
    assert cli("list", "--live", "--require-complete")["data"] == []
