"""Installed SDK inquiries; all business responses are fabricated."""

import shutil
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAF = "operations.rule_status"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
VO = "transferRuleRecordQueryRequesVO"
FLAGS = (
    "--trigger-from",
    "2026-01-01T00:00:00Z",
    "--trigger-to",
    "2026-01-01T00:00:00Z",
)
EPOCH = 1767225600000


def row(identity=1, **values):
    return {
        "id": identity,
        "tntInstId": "GUAPW3SG",
        "ruleId": "RULE",
        "executeStatus": "UNKNOWN",
        "createdOrder": "N",
        "bizNo": "",
        "orderStatus": "",
        "expectTriggerTime": EPOCH,
        "realTriggerTime": None,
        "gmtCreate": EPOCH,
        "gmtModified": EPOCH + 123,
        "debitAmount": 123456789,
        "operator": "excluded",
        "creditAliasName": "excluded",
        **values,
    }


def projected(native):
    return {
        k: v
        for k, v in native.items()
        if k not in {"tntInstId", "debitAmount", "operator", "creditAliasName"}
    }


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "data": rows,
                "count": len(rows) if total is None else total,
            },
        },
    }


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
def test_summary_projection_native_order_exact_string_vo_and_utc_offsets(installed):
    cli, browser, config = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.transports
    rows = [
        row(9007199254740993, expectTriggerTime=EPOCH + 999),
        row(2, expectTriggerTime=EPOCH + 500),
        row(3),
    ]
    browser.business_script.append(page(rows))
    flags = (
        "--trigger-from",
        "2026-01-01T08:00:00+08:00",
        "--trigger-to",
        "2025-12-31T19:00:00-05:00",
    )
    got = cli("list", *flags, "--live", "--limit", "0", "--require-complete")
    assert got["data"] == [projected(r) for r in rows]
    assert not (config / "leaf-cache.sqlite3").exists()
    body = browser.business_requests[0]
    assert (
        set(body) == {"tntInstId", VO}
        and body["tntInstId"] == "GUAPW3SG"
        and isinstance(body[VO], str)
    )
    assert parse(body[VO]) == {
        "tntInstId": "GUAPW3SG",
        "queryDetailed": "false",
        "executeStatusList": [],
        "createdOrderList": [],
        "orderStatusList": [],
        "rowStart": 0,
        "pageSize": 5000,
        "triggerStartTime": "2026-01-01 00:00:00",
        "triggerEndTime": "2026-01-01 00:00:00",
    }
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert all(
        "/queryTransferRulePreRunRecords.json" in e and 'method: "GET"' in e
        for e in expressions
    )


@pytest.mark.parametrize(
    "bad",
    [
        "2026-01-01T00:00:00",
        "2026-01-01 00:00:00",
        "2026-01-01T00:00:00-00:00",
        "2026-01-01T00:00:00.001Z",
        "2026-01-01T00:00:60Z",
        "2026-02-30T00:00:00Z",
        "2026-01-01T00:00:01Z",
    ],
)
def test_invalid_or_reversed_scope_before_browser(installed, bad):
    cli, browser, _ = installed
    assert (
        cli("list", "--trigger-from", bad, "--trigger-to", FLAGS[3], "--live", code=2)[
            "error"
        ]["code"]
        == "INVALID_ARGUMENT"
    )
    assert not browser.transports


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "inner_business",
        "marker",
        "inner_marker",
        "root",
        "rows",
        "total",
        "id",
        "boolid",
        "tenant",
        "ruleId",
        "status",
        "reference",
        "missing_real",
        "real_bool",
        "negative_epoch",
        "before",
        "after",
        "duplicate",
        "gap",
        "overflow",
    ],
)
def test_invalid_or_incomplete_summary_preserves_prior_cache(installed, failure):
    cli, browser, config = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    before = cache_bytes(config)
    reply = page([row(2)])
    doc, expected = reply["body"], "INVALID_RESPONSE"
    result = doc["result"]
    if failure == "auth":
        reply = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        doc["resultFlag"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "inner_business":
        result["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        doc["resultFlag"] = 1
    elif failure == "inner_marker":
        result["success"] = "true"
    elif failure == "root":
        doc["result"] = []
    elif failure == "rows":
        result["data"] = None
    elif failure == "total":
        result["count"] = True
    elif failure == "id":
        result["data"][0]["id"] = 0
    elif failure == "boolid":
        result["data"][0]["id"] = True
    elif failure == "tenant":
        result["data"][0]["tntInstId"] = "OTHER"
    elif failure == "ruleId":
        result["data"][0]["ruleId"] = False
    elif failure == "status":
        result["data"][0]["executeStatus"] = " "
    elif failure == "reference":
        result["data"][0]["bizNo"] = None
    elif failure == "missing_real":
        result["data"][0].pop("realTriggerTime")
    elif failure == "real_bool":
        result["data"][0]["realTriggerTime"] = True
    elif failure == "negative_epoch":
        result["data"][0]["gmtCreate"] = -1
    elif failure == "before":
        result["data"][0]["expectTriggerTime"] = EPOCH - 1
    elif failure == "after":
        result["data"][0]["expectTriggerTime"] = EPOCH + 1000
    elif failure == "duplicate":
        result["data"] = [row(2), row(2)]
        result["count"] = 2
        expected = "INCOMPLETE_RESULT"
    elif failure == "gap":
        result["count"] = 2
        expected = "INCOMPLETE_RESULT"
    else:
        result["count"] = 5001
        expected = "INCOMPLETE_RESULT"
    browser.business_script.append(reply)
    failed = cli("refresh", *FLAGS, "--require-complete", code=1)
    assert failed["error"]["code"] == expected and failed["meta"]["published"] is False
    assert cache_bytes(config) == before
    assert cli("list")["data"] == [projected(row())]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == 2


def test_fixed_width_boundary_no_unstable_offset_loop_and_empty_retention(installed):
    cli, browser, _ = installed
    rows = [row(i + 1) for i in range(5000)]
    browser.business_script.append(page(rows))
    got = cli("list", *FLAGS, "--live", "--limit", "1", "--require-complete")
    assert got["data"] == [projected(rows[0])] and got["meta"]["unique_count"] == 5000
    assert len(browser.business_requests) == 1
    browser.business_script.append(page([row()]))
    cli("refresh", *FLAGS, "--require-complete")
    before = len(browser.business_requests)
    assert cli("list", "--require-complete")["data"] == [projected(row())]
    assert len(browser.business_requests) == before
    browser.business_script.append(page([]))
    assert cli("refresh", *FLAGS, "--require-complete")["meta"]["published"] is False
    assert cli("list")["data"] == [projected(row())]
    assert (
        cli("list", *FLAGS, "--require-complete", code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )


def test_get_and_with_detail_unsupported_before_queries(installed):
    cli, browser, _ = installed
    assert (
        cli("list", *FLAGS, "--live", "--with-detail", code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert not browser.transports


def test_missing_required_bounds_before_browser(installed):
    cli, browser, _ = installed
    assert cli("list", "--live", code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports
