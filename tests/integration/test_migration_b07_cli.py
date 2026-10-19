"""B07 installed List packages through public CLI and synthetic native responses."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.leaves.registry import Registry
from dogopencli.transport import QueryRequest, validate_request

ROOT = Path(__file__).resolve().parents[2]
CASES = ("events", "anomalies", "sla")
WINDOW = ("--from-date", "20260925", "--to-date", "20260926")
MODE = {"events": "RISK_EVENT", "anomalies": "RISK_ALERT"}
SIZES = {"events": 10, "anomalies": 50, "sla": 5000}


def flags(case):
    return () if case == "sla" else WINDOW


def record(case, index=0):
    row = {
        "slaConfigId" if case == "sla" else "id": f"ID{index}",
        "tntInstId": "GUAPW3SG",
        "amount": Decimal("0.123456789012345678901"),
        "zero": 0,
        "unknown": {"list": [None, "", False, 0, "1.0000"]},
    }
    if case == "sla":
        row.update(version="001", slaRuleVOList=[{"unknown": {"levels": [0, "0"]}}])
    else:
        row.update(
            riskMode=MODE[case],
            gmtCreate="2026-09-01 12:00:00（GMT+08）",
            gmtModified="",
            firstAlertTime="",
            nextAlertTime="",
            closeRiskTime="",
            riskProcessingTime=0,
            alertNum=0,
            riskStatus="UNRECOGNIZED_NATIVE_CODE",
            treatmentLogs=[{"native": {"unknown": True}}],
        )
    return row


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


def expected_request(case, offset=0):
    body = {"rowStart": offset, "pageSize": SIZES[case]}
    if case != "sla":
        body.update(
            tntInstId="GUAPW3SG",
            riskMode=MODE[case],
            timeZone="GMT+08",
            startTime="2026-09-25",
            endTime="2026-09-26",
        )
    return body


@pytest.fixture(params=CASES)
def installed(request, run_cli, tmp_path, monkeypatch):
    case, kind = (
        request.param
        if isinstance(request.param, tuple)
        else (request.param, "directory")
    )
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for variable in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(variable, raising=False)
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)
    leaf = "risk." + case

    def cli(action, *args, code=0, scoped=True):
        status, output, error = run_cli(
            [
                "liquidity",
                action,
                leaf,
                *(
                    flags(case)
                    if scoped
                    and (action == "refresh" or (action == "list" and "--live" in args))
                    else ()
                ),
                *args,
            ]
        )
        assert status == code, output + error
        return parse(output)

    try:
        status, output, error = run_cli(["domain", "enable", "liquidity"])
        assert status == 0, output + error
        source = ROOT / "leaf_packages/liquidity" / leaf
        if kind == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(source))
            source = archive_path
        status, output, error = run_cli(["plugins", "install", str(source)])
        assert status == 0, output + error
        yield case, cli, browser, config
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize(
    "installed",
    [(case, kind) for case in CASES for kind in ("directory", "zip")],
    indirect=True,
)
def test_native_lifecycle_and_full_records(installed):
    case, cli, browser, _ = installed
    rows = [record(case, i) for i in range(3)]
    cli("list", "-h", scoped=False)
    cli("describe")
    assert not browser.business_requests
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(rows))
    live = cli("list", "--live", "--limit", "0", "--require-complete")
    assert live["data"] == rows
    assert live["meta"]["complete"] is True
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(rows))
    refreshed = cli("refresh", "--require-complete", "--limit", "1")
    count = len(browser.business_requests)
    offline = cli("list", "--limit", "0")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert len(browser.business_requests) == count
    assert browser.business_requests == [expected_request(case)] * 2
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    endpoint = (
        "/api/risk/sla/slaConfigPageQuery.json"
        if case == "sla"
        else "/api/risk/event/getAll.json"
    )
    assert expressions
    assert all(
        endpoint in e and 'method: "POST"' in e and "application/json" in e
        for e in expressions
    )


@pytest.mark.parametrize("installed", ["events", "anomalies"], indirect=True)
def test_offset_collection_precedes_display_limit(installed):
    case, cli, browser, _ = installed
    count = 95 if case == "anomalies" else 11
    width = SIZES[case]
    rows = [record(case, i) for i in range(count)]
    browser.business_script.extend(
        [page(rows[:width], count), page(rows[width:], count)]
    )
    result = cli("list", "--live", "--require-complete", "--limit", "1")
    assert result["data"] == rows[:1]
    assert result["meta"]["collected_total"] == count
    assert browser.business_requests == [
        expected_request(case),
        expected_request(case, width),
    ]


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "auth",
        "business",
        "outer_type",
        "shape",
        "rows",
        "missing_id",
        "tenant",
        "invalid_total",
        "missing_total",
        "duplicate",
        "conflict",
        "short",
    ],
)
def test_rejected_refresh_preserves_previous_records_and_timestamp(installed, failure):
    case, cli, browser, _ = installed
    rows = [record(case, i) for i in range(2)]
    browser.business_script.append(page(rows))
    saved = cli("refresh", "--require-complete")
    candidate = page(rows)
    code = 1
    expected = "INVALID_RESPONSE"
    if failure == "empty":
        candidate = page([])
        code = 0
    elif failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        candidate["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "outer_type":
        candidate["body"]["success"] = 1
    elif failure == "shape":
        candidate["body"]["data"] = []
    elif failure == "rows":
        candidate = page([None])
    elif failure == "missing_id":
        candidate = page([{"riskMode": MODE.get(case)}])
    elif failure == "tenant":
        candidate = page([{**rows[0], "tntInstId": "OTHER"}])
    elif failure == "invalid_total":
        candidate = page(rows, True)
    elif failure == "missing_total":
        candidate["body"]["data"].pop("totalCount")
    elif failure == "duplicate":
        candidate = page([rows[0], rows[0]])
        expected = "INCOMPLETE_RESULT"
    elif failure == "conflict":
        candidate = page([rows[0], {**rows[0], "unknown": "CHANGED"}])
        expected = "INCOMPLETE_RESULT"
    else:
        candidate = page(rows[:1], 2)
        expected = "INCOMPLETE_RESULT"
    browser.business_script.append(candidate)
    rejected = cli("refresh", "--require-complete", code=code)
    assert rejected["meta"]["published"] is False
    if code:
        assert rejected["error"]["code"] == expected
    offline = cli("list", "--limit", "0")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("identity", [None, "", " ", True, 1, [], {}])
def test_identity_requires_native_nonempty_string(installed, identity):
    case, cli, browser, _ = installed
    row = record(case)
    row["slaConfigId" if case == "sla" else "id"] = identity
    browser.business_script.append(page([row]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("installed", ["events", "anomalies"], indirect=True)
@pytest.mark.parametrize(
    "change",
    [
        "mode",
        "missing_time",
        "time_format",
        "time_type",
        "counter_bool",
        "counter_string",
        "optional_string",
    ],
)
def test_risk_native_scope_and_field_types(installed, change):
    case, cli, browser, _ = installed
    row = record(case)
    if change == "mode":
        row["riskMode"] = "UNREQUESTED_MODE"
    elif change == "missing_time":
        row.pop("gmtCreate")
    elif change == "time_format":
        row["gmtCreate"] = "2026-09-25T12:00:00+08:00"
    elif change == "time_type":
        row["gmtModified"] = None
    elif change == "counter_bool":
        row["alertNum"] = False
    elif change == "counter_string":
        row["riskProcessingTime"] = "0"
    else:
        row["riskStatus"] = 1
    browser.business_script.append(page([row]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("installed", ["sla"], indirect=True)
def test_sla_version_requires_native_string_when_present(installed):
    case, cli, browser, _ = installed
    browser.business_script.append(page([{**record(case), "version": 1}]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("installed", ["events", "anomalies"], indirect=True)
@pytest.mark.parametrize(
    "dates",
    [
        (),
        ("--from-date", "20260925"),
        ("--from-date", "2026-09-25", "--to-date", "20260926"),
        ("--from-date", "20260230", "--to-date", "20260301"),
        ("--from-date", "20260925", "--to-date", "20260927"),
        ("--from-date", "20260926", "--to-date", "20260925"),
        ("--from-date", "20260925", "--to-date", "20260925"),
    ],
)
def test_unqualified_dates_fail_before_business_contact(installed, dates):
    _, cli, browser, _ = installed
    result = cli("list", "--live", *dates, code=2, scoped=False)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


@pytest.mark.parametrize("change", ["path", "method", "extra", "width", "scope"])
def test_shared_transport_default_deny(installed, change):
    case, _, browser, config = installed
    adapter = (
        Registry(config / "config.toml").scan().get("liquidity", "risk." + case).adapter
    )
    parameters = (
        {} if case == "sla" else {"from_date": "20260925", "to_date": "20260926"}
    )
    capability = adapter.capability(parameters)
    body = capability.page_body(adapter.scope(parameters), 0, SIZES[case])
    request = QueryRequest(
        capability.name,
        capability.contract.method,
        capability.contract.host,
        capability.contract.path,
        body,
    )
    validate_request(request, capability.contract)
    if change == "path":
        request = replace(request, path="/mutation.json")
    elif change == "method":
        request = replace(request, method="GET")
    elif change == "extra":
        body["action"] = "edit"
    elif change == "width":
        body["pageSize"] = 100
    elif case == "sla":
        body["tntInstId"] = "GUAPW3SG"
    else:
        body["startTime"] = "2026-09-24"
    with pytest.raises(CliError) as error:
        validate_request(request, capability.contract)
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


@pytest.mark.parametrize(
    "scope,position,width",
    [
        ("OTHER", 0, None),
        (None, True, None),
        (None, -1, None),
        (None, 1, None),
        (None, 0, True),
        (None, 0, 100),
    ],
)
def test_capability_rejects_unverified_scope_and_paging(
    installed, scope, position, width
):
    case, _, browser, config = installed
    adapter = (
        Registry(config / "config.toml").scan().get("liquidity", "risk." + case).adapter
    )
    parameters = (
        {} if case == "sla" else {"from_date": "20260925", "to_date": "20260926"}
    )
    with pytest.raises(CliError) as error:
        adapter.capability(parameters).page_body(
            adapter.scope(parameters) if scope is None else scope,
            position,
            SIZES[case] if width is None else width,
        )
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_conflict_keeps_last_arrival_and_marks_incomplete(installed):
    case, cli, browser, _ = installed
    rows = [record(case, i) for i in range(2)]
    last = {**rows[0], "unknown": "CHANGED"}
    browser.business_script.append(page([rows[0], last, rows[1]], 3))
    result = cli("list", "--live", "--limit", "0")
    assert result["data"] == [last, rows[1]]
    assert result["meta"]["complete"] is False
    assert result["meta"]["duplicate_count"] == 1


@pytest.mark.parametrize("installed", ["events", "anomalies"], indirect=True)
@pytest.mark.parametrize(
    "failure", ["empty", "short", "duplicate", "conflict", "changed_total"]
)
def test_offset_incomplete_or_changed_pages_preserve_cache(installed, failure):
    case, cli, browser, _ = installed
    original = [record(case)]
    browser.business_script.append(page(original))
    saved = cli("refresh", "--require-complete")
    count = SIZES[case] + 1
    rows = [record(case, i) for i in range(count)]
    first, last = rows[: SIZES[case]], rows[SIZES[case] :]
    if failure == "empty":
        first = []
    elif failure == "short":
        first = first[:-1]
    elif failure == "duplicate":
        last = [first[0]]
    elif failure == "conflict":
        last = [{**first[0], "unknown": "CHANGED"}]
    browser.business_script.extend(
        [
            page(first, count),
            page(last, count + 1 if failure == "changed_total" else count),
        ]
    )
    rejected = cli("refresh", "--require-complete", code=1)
    assert rejected["error"]["code"] == (
        "INVALID_RESPONSE" if failure == "changed_total" else "INCOMPLETE_RESULT"
    )
    offline = cli("list", "--limit", "0")
    assert offline["data"] == original
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("installed", ["sla"], indirect=True)
def test_sla_single_capacity_never_falls_back_or_publishes(installed):
    case, cli, browser, _ = installed
    browser.business_script.append(page([record(case)], 5001))
    assert (
        cli("refresh", "--require-complete", code=1)["error"]["code"]
        == "INCOMPLETE_RESULT"
    )
    assert len(browser.business_requests) == 1
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize("installed", ["anomalies"], indirect=True)
@pytest.mark.parametrize("width", [10, 20, 100])
def test_anomalies_rejects_unqualified_width_without_fallback(installed, width):
    _, _, browser, config = installed
    adapter = (
        Registry(config / "config.toml")
        .scan()
        .get("liquidity", "risk.anomalies")
        .adapter
    )
    parameters = {"from_date": "20260925", "to_date": "20260926"}
    with pytest.raises(CliError) as error:
        adapter.capability(parameters).page_body(adapter.scope(parameters), 0, width)
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


@pytest.mark.parametrize("installed", ["anomalies"], indirect=True)
@pytest.mark.parametrize(
    "failure", ["duplicate", "short_first", "short_final", "changed_total"]
)
def test_anomalies_native_two_page_quality_failure_preserves_cache(installed, failure):
    case, cli, browser, _ = installed
    previous = [record(case)]
    browser.business_script.append(page(previous))
    saved = cli("refresh", "--require-complete")
    records = [record(case, i) for i in range(95)]
    first, final = records[:50], records[50:]
    if failure == "duplicate":
        final[-1] = first[0]
    elif failure == "short_first":
        first = first[:-1]
    elif failure == "short_final":
        final = final[:-1]
    browser.business_script.extend(
        [page(first, 95), page(final, 96 if failure == "changed_total" else 95)]
    )
    result = cli("refresh", "--require-complete", code=1)
    assert result["error"]["code"] == (
        "INVALID_RESPONSE" if failure == "changed_total" else "INCOMPLETE_RESULT"
    )
    assert result["meta"]["published"] is False
    assert all(
        "riskEventId" not in request and request["pageSize"] == 50
        for request in browser.business_requests
    )
    after = cli("list", "--limit", "0")
    assert after["data"] == previous
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
