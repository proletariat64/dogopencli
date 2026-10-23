"""Installed SDK inquiries; all business responses are fabricated."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAF = "operations.decisions"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
FLAGS = (
    "--start-from",
    "2026-10-15T00:00:00",
    "--start-to",
    "2026-10-15T23:59:59",
    "--created-from",
    "2026-10-15T00:00:00",
    "--created-to",
    "2026-10-15T23:59:59",
)
LIST_BODY = {
    "tntInstId": "GUAPW3SG",
    "startTime": "2026-10-15 00:00:00",
    "endTime": "2026-10-15 23:59:59",
    "createStartTime": "2026-10-15 00:00:00",
    "createEndTime": "2026-10-15 23:59:59",
    "rowStart": 0,
    "pageSize": 1000,
}


def row(identity=1, **values):
    return {
        "id": identity,
        "tntInstId": "GUAPW3SG",
        "executionTimeStart": "2026-10-15 00:00:00",
        "gmtCreate": "2026-10-15 23:59:59",
        "decisionAmount": "999999999.123456789012345678901",
        "reportId": "REPORT",
        "groupId": "GROUP",
        "orderNo": "ORDER",
        "version": 2,
        "status": "UNKNOWN",
        "operator": "excluded",
        "creditAliasName": "excluded",
        "unknownNested": {
            "precise": Decimal("0.1234567890123456789"),
            "items": [None, False, 3, 1],
        },
        **values,
    }


def projected(native):
    return {
        k: v
        for k, v in native.items()
        if k not in {"operator", "creditAliasName", "unknownNested"}
    }


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


def detail(identity=1, **values):
    return {"status": 200, "body": {"success": True, "data": row(identity, **values)}}


def cache_bytes(config):
    return {
        p.name: (p.exists(), p.read_bytes() if p.exists() else None)
        for p in (config / "leaf-cache.sqlite3", config / "leaf-cache.sqlite3-wal")
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
def test_projection_order_request_scope_and_detached_zip(installed):
    cli, browser, config = installed
    cli("list", "-h")
    cli("get", "-h")
    cli("describe")
    assert not browser.transports
    native = [row(9007199254740993), row(2)]
    browser.business_script.append(page(native))
    got = cli("list", *FLAGS, "--live", "--limit", "0", "--require-complete")
    assert got["data"] == [projected(r) for r in native]
    assert browser.business_requests == [LIST_BODY]
    assert not (config / "leaf-cache.sqlite3").exists()
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert all(
        "/api/ai/decision/report/getAllNew.json" in e
        and 'method: "POST"' in e
        and "application/json" in e
        for e in expressions
    )


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_independent_get_full_root_typed_echo_and_no_list_cache(installed):
    cli, browser, config = installed
    native = detail(9007199254740993)
    browser.business_script.append(native)
    got = cli("get", "9007199254740993")
    assert got["data"] == native["body"]["data"]
    assert browser.business_requests == [{"id": 9007199254740993}]
    assert not (config / "leaf-cache.sqlite3").exists()


def test_composed_window_projection_and_atomic_failure_preserve_saved_bytes(installed):
    cli, browser, config = installed
    native = [row(3), row(1), row(2)]
    browser.business_script.append(page(native))
    saved = cli("refresh", *FLAGS, "--require-complete")
    expected = [projected(r) for r in native]
    assert cli("list", "--limit", "0")["data"] == expected
    before = cache_bytes(config)
    browser.business_script.extend([page(native), detail(1)])
    got = cli(
        "list",
        *FLAGS,
        "--live",
        "--with-detail",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        "id",
        "--require-complete",
    )
    assert got["data"] == [{"record": {"id": 1}, "detail": detail(1)["body"]["data"]}]
    assert browser.business_requests[-2:] == [LIST_BODY, {"id": 1}]
    assert cache_bytes(config) == before
    browser.business_script.extend([page(native), detail(3), detail(999)])
    failed = cli("list", *FLAGS, "--live", "--with-detail", "--limit", "2", code=1)
    assert failed["data"] is None and failed["error"]["code"] == "INVALID_RESPONSE"
    assert cache_bytes(config) == before
    assert cli("list", "--limit", "0")["data"] == expected
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    browser.business_script.append(page(native))
    assert (
        cli("list", *FLAGS, "--live", "--with-detail", "--offset", "99")["data"] == []
    )
    assert browser.business_requests[-1] == LIST_BODY


def test_offset_stride_native_totals_without_terminal_probe(installed):
    cli, browser, _ = installed
    native = [row(i) for i in range(1001)]
    browser.business_script.extend(
        [page(native[:1000], 1001), page(native[1000:], 1001)]
    )
    got = cli("list", *FLAGS, "--live", "--limit", "0", "--require-complete")
    assert got["data"] == [projected(r) for r in native]
    assert browser.business_requests == [LIST_BODY, {**LIST_BODY, "rowStart": 1000}]


@pytest.mark.parametrize(
    "field,value",
    [("startTime", "2026-10-15 23:59:59"), ("createStartTime", "2026-10-15 23:59:59")],
)
def test_both_time_dimensions_are_independent(installed, field, value):
    cli, browser, _ = installed
    flags = list(FLAGS)
    flags[1 if field == "startTime" else 5] = value.replace(" ", "T")
    native = row(executionTimeStart="2026-10-15 23:59:59")
    browser.business_script.append(page([native]))
    assert cli("list", *flags, "--live", "--require-complete")["data"] == [
        projected(native)
    ]
    assert browser.business_requests == [{**LIST_BODY, field: value}]


@pytest.mark.parametrize(
    "bad",
    [
        "2026-10-15T00:00:00Z",
        "2026-10-15T00:00:00+08:00",
        "2026-10-15 00:00:00",
        "2026-02-30T00:00:00",
        "2026-10-15T00:00:00.1",
        "2026-10-16T00:00:00",
    ],
)
def test_invalid_scope_rejected_before_browser(installed, bad):
    cli, browser, _ = installed
    flags = list(FLAGS)
    flags[1] = bad
    assert cli("list", *flags, "--live", code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize("identity", ["", " ", "²", "１２", "1.0", "-1"])
def test_invalid_get_lookup_never_queries_business(installed, identity):
    cli, browser, _ = installed
    assert cli("get", identity, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests
    if not identity.strip():
        assert not browser.transports


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "marker",
        "root",
        "rows",
        "total",
        "id",
        "boolid",
        "tenant",
        "start",
        "created",
        "amount",
        "integer",
        "gap",
        "duplicate",
    ],
)
def test_failed_list_preserves_previous_saved_query(installed, failure):
    cli, browser, config = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    before = cache_bytes(config)
    reply = page([row(2)])
    doc, expected = reply["body"], "INVALID_RESPONSE"
    if failure == "auth":
        reply = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        doc["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        doc["success"] = 1
    elif failure == "root":
        doc["data"] = []
    elif failure == "rows":
        doc["data"]["data"] = None
    elif failure == "total":
        doc["data"]["totalCount"] = True
    elif failure == "id":
        doc["data"]["data"][0]["id"] = "2"
    elif failure == "boolid":
        doc["data"]["data"][0]["id"] = True
    elif failure == "tenant":
        doc["data"]["data"][0]["tntInstId"] = "OTHER"
    elif failure == "start":
        doc["data"]["data"][0]["executionTimeStart"] = "2026-10-14 23:59:59"
    elif failure == "created":
        doc["data"]["data"][0]["gmtCreate"] = "2026-10-16 00:00:00"
    elif failure == "amount":
        doc["data"]["data"][0]["decisionAmount"] = "NaN"
    elif failure == "integer":
        doc["data"]["data"][0]["version"] = True
    elif failure == "gap":
        doc["data"]["totalCount"] = 2
        expected = "INCOMPLETE_RESULT"
    else:
        doc["data"]["data"] = [row(2), row(2)]
        doc["data"]["totalCount"] = 2
        expected = "INCOMPLETE_RESULT"
    browser.business_script.append(reply)
    rejected = cli("refresh", *FLAGS, "--require-complete", code=1)
    assert (
        rejected["error"]["code"] == expected and rejected["meta"]["published"] is False
    )
    assert cache_bytes(config) == before
    assert cli("list")["data"] == [projected(row())]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "failure",
    ["auth", "business", "marker", "null", "array", "empty", "wrong", "bool", "string"],
)
def test_get_failures_are_not_not_found_or_partial_success(installed, failure):
    cli, browser, config = installed
    reply = detail()
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        reply = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        reply["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        reply["body"]["success"] = "true"
    elif failure in {"null", "array", "empty"}:
        reply["body"]["data"] = {"null": None, "array": [], "empty": {}}[failure]
    else:
        reply["body"]["data"]["id"] = {"wrong": 2, "bool": True, "string": "1"}[failure]
    browser.business_script.append(reply)
    assert cli("get", "1", code=1)["error"]["code"] == expected
    assert not (config / "leaf-cache.sqlite3").exists()


def test_empty_success_and_changed_offline_scope_follow_standard_host(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    cli("refresh", *FLAGS, "--require-complete")
    browser.business_script.append(page([]))
    assert cli("refresh", *FLAGS, "--require-complete")["meta"]["published"] is False
    assert cli("list")["data"] == [projected(row())]
    before = len(browser.business_requests)
    assert (
        cli("list", *FLAGS, "--require-complete", code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert len(browser.business_requests) == before
    browser.business_script.append(page([]))
    assert (
        cli("list", *FLAGS, "--live", "--with-detail", "--require-complete")["data"]
        == []
    )


def test_missing_required_ranges_before_browser(installed):
    cli, browser, _ = installed
    assert cli("list", "--live", code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize("failure", ["drift", "short_nonfinal"])
def test_paging_failure_rejects_strict_output(installed, failure):
    cli, browser, _ = installed
    native = [row(i) for i in range(1001)]
    if failure == "drift":
        browser.business_script.extend(
            [page(native[:1000], 1001), page(native[1000:], 1002)]
        )
    else:
        browser.business_script.extend(
            [page(native[:999], 1001), page(native[1000:], 1001)]
        )
    result = cli("list", *FLAGS, "--live", "--require-complete", code=1)
    assert result["data"] is None
    assert result["error"]["code"] in {"INVALID_RESPONSE", "INCOMPLETE_RESULT"}
