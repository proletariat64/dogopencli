"""Installed native forecast results: scopes, closed transport and publication."""

import json
import shutil
from collections import deque
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAF = "forecast.results"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
FLAGS = ["--from-date", "2026-03-08", "--to-date", "20260308"]
VO = "bankCashForecastRecordQueryVo"
CURVE_VO = "bankCashForecastRecordCashFlowVo"


def row(index=0, **values):
    return {
        "id": str(index),
        "bankAccountAliasName": "ACCOUNT",
        "valueDate": "20260308",
        "recordCreateTime": "123456",
        "forecastBalance": "1,234.5000",
        "minimumBalance": None,
        "openBalance": "0.00",
        "currency": "USD",
        "cashFlowTransIn": Decimal("0.123456789012345678901"),
        "cashFlowTransOut": 0,
        "forecastBatchNo": 1,
        "gmtCreate": 123,
        "gmtModified": None,
        "lastestFlag": 0,
        "tntInstId": "GUAPW3SG",
        "unknown": {
            "nested": [None, False, {"amount": Decimal("999.123456789012345678901")}]
        },
        **values,
    }


def page(rows, total=None):
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


def curve(**values):
    return {
        "allDate": ["12:00", "12:00"],
        "expectBalance": ["1,234.500000000000001", "0"],
        "expectInflow": ["0", "0.000000000000000001"],
        "expectOutFlow": ["-1.0", "0"],
        "unknown": {"native": [None, "", 0]},
        **values,
    }


def curve_response(value=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"success": True, "alias": curve() if value is None else value},
        },
    }


def composed(rows):
    return [{**record, "cashflow_curve": curve()} for record in rows]


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
    browser.curve_script = deque()

    def respond(payload, index):
        if CURVE_VO in payload:
            return (
                browser.curve_script.popleft()
                if browser.curve_script
                else curve_response()
            )
        return browser.business_script.popleft()

    browser.business_handler = respond

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


def test_each_forecast_has_its_own_native_curve_before_display_window(installed):
    cli, browser, _ = installed
    rows = [row(1), row(2, openBalance=0)]
    first = curve()
    empty = {
        field: []
        for field in ("allDate", "expectBalance", "expectInflow", "expectOutFlow")
    }
    browser.business_script.append(page(rows))
    browser.curve_script.extend([curve_response(first), curve_response(empty)])
    result = cli(
        "list", "--live", *FLAGS, "--offset", "1", "--limit", "1", "--require-complete"
    )
    assert result["data"] == [{**rows[1], "cashflow_curve": empty}]
    assert [parse(request[CURVE_VO]) for request in browser.business_requests[1:]] == [
        {
            "tntInstId": "GUAPW3SG",
            "forecastRecordId": "1",
            "baseBalance": "0.00",
            "currency": "USD",
            "valueDate": "20260308",
        },
        {
            "tntInstId": "GUAPW3SG",
            "forecastRecordId": "2",
            "baseBalance": 0,
            "currency": "USD",
            "valueDate": "20260308",
        },
    ]


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_full_native_detached_install_scope_and_saved_replay(installed):
    cli, browser, config = installed
    cli("list", "--help")
    cli("describe")
    assert not browser.transports
    rows = [row(9), row(2, bankAccountAliasName="第二,A*", recordCreateTime="134500")]
    browser.business_script.append(page(rows))
    assert cli("list", "--live", *FLAGS, "--limit", "0", "--require-complete")[
        "data"
    ] == composed(rows)
    assert not (config / "leaf-cache.sqlite3").exists()
    browser.business_script.append(page(rows))
    saved = cli("refresh", *FLAGS, "--require-complete")
    browser.running = False
    n = len(browser.transports)
    assert cli("list", "--limit", "0", "--require-complete")["data"] == composed(rows)
    assert cli("list", *FLAGS, "--limit", "0", "--require-complete")[
        "data"
    ] == composed(rows)
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.transports) == n
    for request in (request for request in browser.business_requests if VO in request):
        assert set(request) == {"tntInstId", VO} and request["tntInstId"] == "GUAPW3SG"
        inner = parse(request[VO])
        assert inner == {
            "tntInstId": "GUAPW3SG",
            "expectInflowStart": None,
            "expectInflowEnd": None,
            "expectOutflowStart": None,
            "expectOutflowEnd": None,
            "expectMinBalance": None,
            "expectMaxBalance": None,
            "valueStartDay": "20260308",
            "valueEndDay": "20260308",
            "recordStartTime": "000000",
            "recordEndTime": "235959",
            "rowStart": 0,
            "pageSize": 5000,
        }
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions and all(
        any(
            path in e
            for path in (
                "/bankCashForecastRecordQuery.json",
                "/bankCashForecastRecordCashFlowQuery.json",
            )
        )
        and 'method: "GET"' in e
        for e in expressions
    )


@pytest.mark.parametrize(
    "flags",
    [
        [],
        ["--from-date", "20260308"],
        ["--from-date", "20260230", "--to-date", "20260308"],
        ["--from-date", "20260309", "--to-date", "20260308"],
        ["--from-date", "２０２６０３０８", "--to-date", "20260308"],
        [*FLAGS, "--record-from-time", "240000"],
        [*FLAGS, "--record-from-time", "13:00:00", "--record-to-time", "12:00:00"],
        [*FLAGS, "--record-to-time", "1234"],
        [*FLAGS, "--account-alias", "   "],
    ],
)
def test_invalid_scope_rejected_before_browser(installed, flags):
    cli, browser, _ = installed
    assert cli("list", "--live", *flags, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


def test_native_alias_or_and_clock_time_with_literal_aliases(installed):
    cli, browser, _ = installed
    rows = [row(0, bankAccountAliasName="A,B"), row(1, bankAccountAliasName="甲*")]
    browser.business_script.append(page(rows))
    assert cli(
        "list",
        "--live",
        *FLAGS,
        "--account-alias",
        "A,B",
        "--account-alias",
        "甲*",
        "--record-from-time",
        "12:34:56",
        "--record-to-time",
        "123456",
        "--limit",
        "0",
    )["data"] == composed(rows)
    inner = parse(browser.business_requests[0][VO])
    assert inner["aliasName"] == ["A,B", "甲*"]
    assert inner["recordStartTime"] == inner["recordEndTime"] == "123456"


def test_filtered_refresh_bare_offline_retains_time_and_native_query(installed):
    cli, browser, config = installed
    selection = [
        *FLAGS,
        "--account-alias",
        "ACCOUNT",
        "--record-from-time",
        "12:34:56",
        "--record-to-time",
        "123456",
    ]
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *selection, "--require-complete")
    paths = [config / "leaf-cache.sqlite3", config / "leaf-cache.sqlite3-wal"]
    before = {p: p.read_bytes() for p in paths if p.exists()}
    browser.running = False
    n = len(browser.transports)
    bare = cli("list", "--limit", "0", "--require-complete")
    assert bare["data"] == composed([row()])
    assert bare["meta"]["scope"] == saved["meta"]["scope"]
    assert cli("list", *selection, "--require-complete")["data"] == composed([row()])
    assert cli("list", "--account-alias", "OTHER")["data"] == []
    result = cli("list", "--record-from-time", "12:00:00", "--require-complete", code=1)
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert (
        cli("list", "--from-date", "20260221", "--require-complete", code=1)["error"][
            "code"
        ]
        == "INCOMPLETE_RESULT"
    )
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert {p: p.read_bytes() for p in before} == before
    assert len(browser.transports) == n


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "inner_failure",
        "marker",
        "inner_marker",
        "root",
        "rows",
        "total",
        "identity",
        "date",
        "clock",
        "alias_scope",
        "time_scope",
        "date_scope",
        "tenant",
        "amount",
        "integer",
    ],
)
def test_native_failures_preserve_saved_snapshot(installed, failure):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    selection = [
        *FLAGS,
        "--account-alias",
        "ACCOUNT",
        "--record-from-time",
        "120000",
        "--record-to-time",
        "130000",
    ]
    saved = cli("refresh", *selection, "--require-complete")
    candidate = page([row(1)])
    data = candidate["body"]["result"]
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        candidate["body"]["resultFlag"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "inner_failure":
        data["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        candidate["body"]["resultFlag"] = 1
    elif failure == "inner_marker":
        data["success"] = "true"
    elif failure == "root":
        candidate["body"]["result"] = []
    elif failure == "rows":
        data["dataValue"] = {}
    elif failure == "total":
        data["count"] = True
    elif failure == "identity":
        data["dataValue"][0]["id"] = 123
    elif failure == "date":
        data["dataValue"][0]["valueDate"] = "20260230"
    elif failure == "clock":
        data["dataValue"][0]["recordCreateTime"] = "246000"
    elif failure == "alias_scope":
        data["dataValue"][0]["bankAccountAliasName"] = "OTHER"
    elif failure == "time_scope":
        data["dataValue"][0]["recordCreateTime"] = "140000"
    elif failure == "date_scope":
        data["dataValue"][0]["valueDate"] = "20260309"
    elif failure == "tenant":
        data["dataValue"][0]["tntInstId"] = "OTHER"
    elif failure == "amount":
        data["dataValue"][0]["forecastBalance"] = "not money"
    elif failure == "integer":
        data["dataValue"][0]["gmtCreate"] = True
    browser.business_script.append(candidate)
    result = cli("refresh", *selection, "--require-complete", code=1)
    assert result["error"]["code"] == expected
    assert result["meta"]["published"] is False
    assert cli("list")["data"] == composed([row()])
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("mode", ["duplicate", "conflict", "gap", "changed_total"])
def test_incomplete_native_scope_never_replaces_cache(installed, mode):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    if mode in ("duplicate", "conflict"):
        browser.business_script.append(
            page(
                [row(1), row(1, forecastBalance="99") if mode == "conflict" else row(1)]
            )
        )
    elif mode == "gap":
        browser.business_script.append(page([row(1)], total=2))
    else:
        browser.business_script.extend(
            [
                page([row(i) for i in range(5000)], total=5001),
                page([row(5000)], total=5002),
            ]
        )
    assert cli("refresh", *FLAGS, "--require-complete", code=1)["error"]["code"] == (
        "INVALID_RESPONSE" if mode == "changed_total" else "INCOMPLETE_RESULT"
    )
    assert cli("list")["data"] == composed([row()])
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_offset_stride_and_window_no_terminal_probe(installed):
    cli, browser, _ = installed
    rows = [row(i) for i in range(5001)]
    browser.business_script.extend(
        [page(rows[:5000], total=5001), page(rows[5000:], total=5001)]
    )
    assert cli(
        "list",
        "--live",
        *FLAGS,
        "--offset",
        "5000",
        "--limit",
        "1",
        "--require-complete",
    )["data"] == composed(rows[5000:])
    assert [parse(v[VO])["rowStart"] for v in browser.business_requests if VO in v] == [
        0,
        5000,
    ]
    assert len([v for v in browser.business_requests if CURVE_VO in v]) == 5001


def test_empty_refresh_retains_nonempty_cache(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    browser.business_script.append(page([]))
    result = cli("refresh", *FLAGS, "--require-complete")
    assert result["meta"]["published"] is False
    assert cli("list")["data"] == composed([row()])
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("extra", ['"mutation": "Y"', '"timeZone": "GMT+08"'])
def test_closed_nested_transport_before_business_fetch(
    installed, run_cli, tmp_path, extra
):
    cli, browser, _ = installed
    code, out, err = run_cli(["plugins", "uninstall", "liquidity." + LEAF])
    assert code == 0, out + err
    source = tmp_path / "badrequest"
    shutil.copytree(SOURCE, source)
    path = source / "adapter.py"
    original = path.read_text()
    assert "VO: canonical(inner)" in original
    path.write_text(
        original.replace(
            "VO: canonical(inner)", "VO: canonical({**inner, " + extra + "})"
        )
    )
    code, out, err = run_cli(["plugins", "install", str(source)])
    assert code == 0, out + err
    assert (
        cli("list", "--live", *FLAGS, code=1)["error"]["code"] == "REQUEST_NOT_ALLOWED"
    )
    assert not browser.business_requests


@pytest.mark.parametrize(
    "change",
    [
        {"openBalance": None},
        {"openBalance": ""},
        {"currency": ""},
        {"cashflow_curve": None},
    ],
)
def test_unqualified_parent_binding_fails_before_any_curve_io(installed, change):
    cli, browser, _ = installed
    browser.business_script.append(page([row(1), row(2, **change)]))
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize(
    "bad_curve",
    [
        {"allDate": [], "expectBalance": [], "expectInflow": []},
        curve(expectBalance=["0"]),
        curve(expectInflow=[None, "0"]),
        curve(allDate=[1200, "12:00"]),
        curve(currency="EUR"),
        curve(tntInstId="OTHER"),
        curve(forecastRecordId="OTHER"),
        curve(baseBalance=0),
        [],
    ],
)
def test_malformed_or_contradictory_curve_is_hard_failure(installed, bad_curve):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    browser.curve_script.append(curve_response(bad_curve))
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result["data"] is None
    trace = result["meta"]["query_evidence"]
    assert trace["queries"]["base"]["succeeded"] == 1
    assert trace["queries"]["curve"]["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("failure", ["auth", "business", "inner", "marker", "network"])
def test_later_curve_failure_keeps_prior_capture_and_source_evidence(
    installed, failure
):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    browser.business_script.append(page([row(1), row(2)]))
    candidate = curve_response()
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        candidate["body"]["resultFlag"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "inner":
        candidate["body"]["result"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        candidate["body"]["result"]["success"] = 1
    else:
        candidate = {"error": "TypeError: Failed to fetch"}
        expected = "TIMEOUT"
    browser.curve_script.extend([curve_response(), *([candidate] * 5)])
    result = cli("refresh", *FLAGS, code=1)
    assert result["error"]["code"] == expected
    assert result["data"] is None
    assert result["meta"]["published"] is False
    trace = result["meta"]["query_evidence"]
    assert trace["queries"]["base"]["succeeded"] == 1
    assert trace["queries"]["curve"]["succeeded"] == 1
    assert cli("list")["data"] == composed([row()])
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_curve_coverage_witnesses_survive_saved_replay(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    browser.running = False
    replay = cli("list", "--require-complete")
    assert replay["meta"]["acquisition"] == saved["meta"]["acquisition"]
    attempts = replay["meta"]["acquisition"]["attempts"]
    witness = next(
        value
        for value in attempts
        if value.get("composition") == "native-request-binding"
    )
    assert (
        witness["curve_required"]
        == witness["curve_attempted"]
        == witness["curve_succeeded"]
        == 1
    )
    assert witness["curve_reported_total"] is None
    assert witness["bindings"] == [
        {
            "request": {
                "tntInstId": "GUAPW3SG",
                "forecastRecordId": "0",
                "baseBalance": "0.00",
                "currency": "USD",
                "valueDate": "20260308",
            },
            "reported_total": None,
            "points": 2,
            "coverage": "validated-request-scoped-native-series",
        }
    ]


def test_shared_curve_budget_counts_base_and_retries(installed, run_cli, tmp_path):
    cli, browser, _ = installed
    code, output, error = run_cli(["plugins", "uninstall", "liquidity." + LEAF])
    assert code == 0, output + error
    source = tmp_path / "bounded"
    shutil.copytree(SOURCE, source)
    manifest_path = source / "leaf.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["operations"]["list"]["max_requests"] = 3
    manifest_path.write_text(json.dumps(manifest))
    code, output, error = run_cli(["plugins", "install", str(source)])
    assert code == 0, output + error
    browser.business_script.append(page([row(1), row(2)]))
    browser.curve_script.extend([{"status": 429, "body": {}, "retry_after": "0"}] * 3)
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "TIMEOUT"
    trace = result["meta"]["query_evidence"]
    assert trace["request_count"] == 3
    assert trace["queries"]["base"]["requests"] == 1
    assert trace["queries"]["curve"]["requests"] == 2
    assert len(browser.business_requests) == 3


def test_curve_deadline_covers_all_children(installed, monkeypatch):
    from dogopencli import collect as collection

    cli, browser, _ = installed
    clock = [100.0]
    monkeypatch.setattr(collection, "_monotonic", lambda: clock[0])
    original = browser.business_handler

    def respond(payload, index):
        result = original(payload, index)
        if CURVE_VO in payload:
            clock[0] += 1801.0
        return result

    browser.business_handler = respond
    browser.business_script.append(page([row(1), row(2)]))
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "TIMEOUT"
    assert len(browser.business_requests) == 2
    assert result["data"] is None


def test_base_only_capture_cannot_replay_as_composed_contract(
    installed, run_cli, tmp_path
):
    cli, browser, _ = installed
    code, output, error = run_cli(["plugins", "uninstall", "liquidity." + LEAF])
    assert code == 0, output + error
    source = tmp_path / "base-only"
    shutil.copytree(SOURCE, source)
    manifest_path = source / "leaf.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["fields"] = [
        field for field in manifest["fields"] if field["name"] != "cashflow_curve"
    ]
    manifest_path.write_text(json.dumps(manifest))
    adapter_path = source / "adapter.py"
    text = adapter_path.read_text()
    assert 'records.append({**row, "cashflow_curve": curve})' in text
    adapter_path.write_text(
        text.replace(
            'records.append({**row, "cashflow_curve": curve})',
            "records.append(dict(row))",
        )
    )
    code, output, error = run_cli(["plugins", "install", str(source)])
    assert code == 0, output + error
    browser.business_script.append(page([row()]))
    cli("refresh", *FLAGS, "--require-complete")
    assert cli("list")["data"] == [row()]
    code, output, error = run_cli(["plugins", "uninstall", "liquidity." + LEAF])
    assert code == 0, output + error
    code, output, error = run_cli(["plugins", "install", str(SOURCE)])
    assert code == 0, output + error
    before = len(browser.business_requests)
    result = cli("list", "--require-complete", code=1)
    assert result["error"]["code"] == "CACHE_MISS"
    assert len(browser.business_requests) == before
    browser.business_script.append(page([row()]))
    cli("refresh", *FLAGS, "--require-complete")
    assert cli("list", "--require-complete")["data"] == composed([row()])


@pytest.mark.parametrize("length", [1, 3, 49, 51])
def test_native_curve_has_no_fixed_length_or_cadence(installed, length):
    cli, browser, _ = installed
    native = curve(
        allDate=["native-clock"] * length,
        expectBalance=["0.000000000000000000001"] * length,
        expectInflow=["1,234.50000"] * length,
        expectOutFlow=["-0"] * length,
    )
    browser.business_script.append(page([row()]))
    browser.curve_script.append(curve_response(native))
    result = cli("list", "--live", *FLAGS, "--require-complete")
    assert result["data"] == [{**row(), "cashflow_curve": native}]


def test_curve_failure_keeps_exact_parent_request_binding(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row(7)]))
    browser.curve_script.append(
        {
            "status": 200,
            "body": {"resultFlag": False},
        }
    )
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["meta"]["curve_binding"] == {
        "tntInstId": "GUAPW3SG",
        "forecastRecordId": "7",
        "baseBalance": "0.00",
        "currency": "USD",
        "valueDate": "20260308",
    }
