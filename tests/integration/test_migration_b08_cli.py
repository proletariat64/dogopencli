"""Installed B08 List packages through public CLI and synthetic native responses."""

import json
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
CASES = ("asset_trades", "forwards", "prefunds", "demands", "transfers", "swaps")
SIZES = {case: 5000 if case == "demands" else 10 for case in CASES}
IDS = {
    "asset_trades": "orderNo",
    "forwards": "orderNo",
    "prefunds": "id",
    "demands": "taskId",
    "transfers": "orderNo",
    "swaps": "dealId",
}
VOS = {
    "prefunds": "preFundingOrderQueryVO",
    "demands": "riskActionTaskQueryVO",
    "transfers": "transferOrderQueryRequestVO",
    "swaps": "swapOrderQueryVO",
}
ENDPOINTS = {
    "asset_trades": "/assetTransferOrderListQuery.json",
    "forwards": "/forwardOrderList.json",
    "prefunds": "/queryPreFundingOrderList.json",
    "demands": "/riskActionTaskQuery.json",
    "transfers": "/transferOrderQuery.json",
    "swaps": "/swapOrderQuery.json",
}
DAY_FLAGS = ("--from-date", "2026-09-30", "--to-date", "2026-09-30")
DEMAND_FLAGS = (
    "--execute-from",
    "2026-04-01T00:00:00",
    "--execute-to",
    "2026-04-02T00:00:00",
)
STATUS_FLAGS = ("--status", "APPROVED", "--status", "CLOSED")


def flags(case):
    if case == "forwards":
        return ()
    if case == "prefunds":
        return STATUS_FLAGS
    return DEMAND_FLAGS if case == "demands" else DAY_FLAGS


def parameters(case):
    if case == "forwards":
        return {}
    if case == "prefunds":
        return {"status": ["APPROVED", "CLOSED"]}
    if case == "demands":
        return {
            "execute_from": "2026-04-01T00:00:00",
            "execute_to": "2026-04-02T00:00:00",
        }
    return {"from_date": "2026-09-30", "to_date": "2026-09-30"}


def record(case, index=0):
    row = {
        IDS[case]: f"ID{index}",
        "tntInstId": "GUAPW3SG",
        "currency": "USD",
        "nativeDecimal": Decimal("0.123456789012345678901"),
        "zero": 0,
        "unknown": {"nested": [None, "", False, 0, "1.0000"]},
    }
    if case == "asset_trades":
        row.update(tradingDate="20260930")
    elif case == "prefunds":
        row.update(status="APPROVED", prefundingBizNo="BUSINESS", version=1)
    elif case == "demands":
        row.update(
            source="FUND_REQUIRE",
            sourceId="SOURCE",
            amount="0.123456789012345678901",
            executeTime="2026-04-01 00:00:00",
            status="UNRECOGNIZED_NATIVE",
        )
    elif case == "transfers":
        row.update(
            debitAmount="0.000000000000000001",
            creditAmount="",
            gmtReturnFinnet=None,
            gmtCreate="UNINTERPRETED_SOURCE_TIME",
            orderStatus="UNRECOGNIZED_NATIVE",
            receiptStatus="PENDING",
            executeResult="",
            transFerOrderLogVoList=[{"native": [0, None]}],
        )
    elif case == "swaps":
        row.update(
            tradeDate="20260930",
            nearLegValueDate="20261001",
            farLegValueDate="20261101",
            nearLegDebitAmount="1,234.000000000000000001",
            nearLegCreditAmount="0",
            farLegDebitAmount=None,
            farLegCreditAmount="",
            nearLegFxRate="1.0000",
            farLegFxRate="0",
            gmtCreate=0,
            nodeNum=0,
            needReview=False,
        )
    return row


def page(case, rows, total=None):
    count = len(rows) if total is None else total
    if case in ("asset_trades", "forwards"):
        document = {"success": True, "data": {"data": rows, "totalCount": count}}
    else:
        key = (
            "data"
            if case == "transfers"
            else "swapOrderVOList"
            if case == "swaps"
            else "dataValue"
        )
        document = {
            "resultFlag": True,
            "result": {"success": True, key: rows, "count": count},
        }
        if case == "transfers":
            document["count"] = count
    return {"status": 200, "body": document}


def node(case, document):
    return document["data" if case in ("asset_trades", "forwards") else "result"]


def expected_request(case, position=0):
    paging = {"rowStart": position, "pageSize": SIZES[case]}
    if case == "forwards":
        return {"tntInstId": "GUAPW3SG", **paging}
    if case == "asset_trades":
        return {
            "tntInstId": "GUAPW3SG",
            "timeZone": "GMT+08",
            "tradingDateBegin": "20260930",
            "tradingDateEnd": "20260930",
            **paging,
        }
    inner = {"tntInstId": "GUAPW3SG", **paging}
    if case == "prefunds":
        inner["statusList"] = ["APPROVED", "CLOSED"]
    elif case == "demands":
        inner.update(
            source=["FUND_REQUIRE"],
            startExecuteTime="2026-04-01 00:00:00",
            endExecuteTime="2026-04-02 00:00:00",
        )
    elif case == "transfers":
        inner.update(
            debitEntity=[],
            creditEntity=[],
            transactionStartDate="2026-09-30 00:00:00",
            transactionEndDate="2026-09-30 23:59:59",
            debitStartDate="",
            debitEndDate="",
            creditStartDate="",
            creditEndDate="",
        )
    else:
        inner.update(
            nearLegDebitEntity=[],
            nearLegCreditEntity=[],
            tradeStartDate="20260930",
            tradeEndDate="20260930",
            nearLegStartDate="",
            nearLegEndDate="",
            farLegStartDate="",
            farLegEndDate="",
        )
    outer = {"tntInstId": "GUAPW3SG", VOS[case]: inner}
    if case == "prefunds":
        outer["timeZone"] = "GMt+8"
    return outer


def decoded_request(case, body):
    result = dict(body)
    if case in VOS:
        result[VOS[case]] = json.loads(result[VOS[case]])
    return result


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
    leaf = "operations." + case

    def cli(action, *args, code=0, scoped=True):
        automatic = (
            flags(case)
            if scoped
            and (action == "refresh" or (action == "list" and "--live" in args))
            else ()
        )
        status, output, error = run_cli(["liquidity", action, leaf, *automatic, *args])
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
    browser.business_script.append(page(case, rows))
    live = cli("list", "--live", "--limit", "0", "--require-complete")
    assert live["data"] == rows
    assert live["meta"]["complete"] is True
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(case, rows))
    refreshed = cli("refresh", "--require-complete", "--limit", "1")
    count = len(browser.business_requests)
    offline = cli("list", "--limit", "0")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert len(browser.business_requests) == count
    assert [decoded_request(case, body) for body in browser.business_requests] == [
        expected_request(case)
    ] * 2
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    method = "GET" if case in ("prefunds", "demands") else "POST"
    assert expressions
    assert all(ENDPOINTS[case] in e and f'method: "{method}"' in e for e in expressions)
    if method == "GET":
        assert all("new URLSearchParams(payload).toString()" in e for e in expressions)
        assert all("Content-Type" not in e for e in expressions)
    else:
        encoding = (
            "application/x-www-form-urlencoded"
            if case in ("transfers", "swaps")
            else "application/json"
        )
        assert all(encoding in e for e in expressions)


@pytest.mark.parametrize(
    "installed", [case for case in CASES if case != "demands"], indirect=True
)
def test_offset_collection_precedes_display_limit(installed):
    case, cli, browser, _ = installed
    rows = [record(case, i) for i in range(11)]
    browser.business_script.extend(
        [page(case, rows[:10], 11), page(case, rows[10:], 11)]
    )
    result = cli("list", "--live", "--require-complete", "--limit", "1")
    assert result["data"] == rows[:1]
    assert result["meta"]["collected_total"] == 11
    assert [decoded_request(case, body) for body in browser.business_requests] == [
        expected_request(case),
        expected_request(case, 10),
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
def test_rejected_refresh_preserves_previous_capture(installed, failure):
    case, cli, browser, _ = installed
    rows = [record(case, i) for i in range(2)]
    browser.business_script.append(page(case, rows))
    saved = cli("refresh", "--require-complete")
    candidate = page(case, rows)
    code, expected = 1, "INVALID_RESPONSE"
    if failure == "empty":
        candidate, code = page(case, []), 0
    elif failure == "auth":
        candidate, expected = {"status": 401, "body": {}}, "AUTH_REQUIRED"
    elif failure == "business":
        candidate["body"][
            "success" if case in ("asset_trades", "forwards") else "resultFlag"
        ] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "outer_type":
        candidate["body"][
            "success" if case in ("asset_trades", "forwards") else "resultFlag"
        ] = 1
    elif failure == "shape":
        candidate["body"][
            "data" if case in ("asset_trades", "forwards") else "result"
        ] = []
    elif failure == "rows":
        candidate = page(case, [None])
    elif failure == "missing_id":
        row = record(case)
        row.pop(IDS[case])
        candidate = page(case, [row])
    elif failure == "tenant":
        candidate = page(case, [{**rows[0], "tntInstId": "OTHER"}])
    elif failure == "invalid_total":
        candidate = page(case, rows, True)
    elif failure == "missing_total":
        node(case, candidate["body"]).pop(
            "totalCount" if case in ("asset_trades", "forwards") else "count"
        )
        if case == "transfers":
            candidate["body"].pop("count")
    elif failure == "duplicate":
        candidate = page(case, [rows[0], rows[0]])
        expected = "INCOMPLETE_RESULT"
    elif failure == "conflict":
        candidate = page(case, [rows[0], {**rows[0], "unknown": "CHANGED"}])
        expected = "INCOMPLETE_RESULT"
    else:
        candidate, expected = page(case, rows[:1], 2), "INCOMPLETE_RESULT"
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
    row[IDS[case]] = identity
    browser.business_script.append(page(case, [row]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("change", ["path", "method", "extra", "width", "scope"])
def test_shared_transport_default_deny(installed, change):
    case, _, browser, config = installed
    adapter = (
        Registry(config / "config.toml")
        .scan()
        .get("liquidity", "operations." + case)
        .adapter
    )
    capability = adapter.capability(parameters(case))
    body = capability.page_body(adapter.scope(parameters(case)), 0, SIZES[case])
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
        request = replace(request, method="PUT")
    elif change == "extra":
        body["action"] = "edit"
    elif case in VOS:
        inner = json.loads(body[VOS[case]])
        inner["pageSize" if change == "width" else "tntInstId"] = (
            100 if change == "width" else "OTHER"
        )
        body[VOS[case]] = json.dumps(inner)
    else:
        body["pageSize" if change == "width" else "tntInstId"] = (
            100 if change == "width" else "OTHER"
        )
    with pytest.raises(CliError) as error:
        validate_request(request, capability.contract)
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


@pytest.mark.parametrize("installed", ["swaps"], indirect=True)
def test_unsupported_get_never_queries(installed):
    _, cli, browser, _ = installed
    cli("get", "NATIVE_ID", code=2)
    assert not browser.business_requests


def test_conflict_keeps_last_arrival_and_marks_incomplete(installed):
    case, cli, browser, _ = installed
    rows = [record(case, i) for i in range(2)]
    last = {**rows[0], "unknown": "CHANGED"}
    browser.business_script.append(page(case, [rows[0], last, rows[1]], 3))
    result = cli("list", "--live", "--limit", "0")
    assert result["data"] == [last, rows[1]]
    assert result["meta"]["complete"] is False
    assert result["meta"]["duplicate_count"] == 1


@pytest.mark.parametrize(
    "installed", [case for case in CASES if case != "demands"], indirect=True
)
@pytest.mark.parametrize(
    "failure", ["empty", "short", "duplicate", "conflict", "changed_total"]
)
def test_offset_incomplete_or_changed_pages_preserve_cache(installed, failure):
    case, cli, browser, _ = installed
    original = [record(case)]
    browser.business_script.append(page(case, original))
    saved = cli("refresh", "--require-complete")
    rows = [record(case, i) for i in range(11)]
    first, last = rows[:10], rows[10:]
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
            page(case, first, 11),
            page(case, last, 12 if failure == "changed_total" else 11),
        ]
    )
    rejected = cli("refresh", "--require-complete", code=1)
    assert rejected["error"]["code"] == (
        "INVALID_RESPONSE" if failure == "changed_total" else "INCOMPLETE_RESULT"
    )
    offline = cli("list", "--limit", "0")
    assert offline["data"] == original
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("installed", ["demands"], indirect=True)
def test_single_capacity_never_falls_back_or_publishes(installed):
    case, cli, browser, _ = installed
    browser.business_script.append(page(case, [record(case)], 5001))
    result = cli("refresh", "--require-complete", code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert len(browser.business_requests) == 1
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize("installed", ["prefunds"], indirect=True)
@pytest.mark.parametrize(
    "statuses,canonical",
    [
        (["CLOSED", "APPROVED"], ["APPROVED", "CLOSED"]),
        (["APPROVED", "CLOSED", "APPROVED"], ["APPROVED", "CLOSED"]),
        (
            ["CLOSED_SUBMITTED", "SUBMITTED", "REJECTED"],
            ["SUBMITTED", "REJECTED", "CLOSED_SUBMITTED"],
        ),
    ],
)
def test_prefund_status_views_and_full_scope_local_currency(
    installed, statuses, canonical
):
    case, cli, browser, _ = installed
    rows = [
        {**record(case, i), "status": canonical[0], "currency": currency}
        for i, currency in enumerate(("USD", "EUR", "JPY"))
    ]
    status_flags = tuple(value for status in statuses for value in ("--status", status))
    browser.business_script.append(page(case, rows))
    refreshed = cli(
        "refresh",
        *status_flags,
        "--currency",
        "USD",
        "--require-complete",
        scoped=False,
    )
    offline = cli("list", "--limit", "0")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert cli("list", "--currency", "USD", "--currency", "EUR")["data"] == rows[:2]
    assert cli("list", "--currency", "usd")["data"] == []
    request = decoded_request(case, browser.business_requests[0])
    assert request[VOS[case]]["statusList"] == canonical
    assert request[VOS[case]]["tntInstId"] == "GUAPW3SG"
    assert "currency" not in request and "currency" not in request[VOS[case]]
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize("installed", ["prefunds"], indirect=True)
@pytest.mark.parametrize(
    "statuses",
    [(), ("APPROVED",), ("CLOSED",), ("APPROVED", "SUBMITTED"), ("APPROVED_FINAL",)],
)
def test_prefund_unqualified_status_sets_rejected_before_contact(installed, statuses):
    _, cli, browser, _ = installed
    status_flags = tuple(value for status in statuses for value in ("--status", status))
    result = cli("list", "--live", *status_flags, code=2, scoped=False)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


@pytest.mark.parametrize(
    "installed", ["asset_trades", "transfers", "swaps"], indirect=True
)
@pytest.mark.parametrize(
    "date_flags",
    [
        (),
        ("--from-date", "2026-09-30"),
        ("--from-date", "20260930", "--to-date", "20260930"),
        ("--from-date", "2026-02-30", "--to-date", "2026-03-01"),
        ("--from-date", "2026-10-01", "--to-date", "2026-09-30"),
    ],
)
def test_required_iso_date_scopes_rejected_before_contact(installed, date_flags):
    _, cli, browser, _ = installed
    result = cli("list", "--live", *date_flags, code=2, scoped=False)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


@pytest.mark.parametrize("installed", ["demands"], indirect=True)
@pytest.mark.parametrize(
    "timestamp_flags",
    [
        (),
        ("--execute-from", "2026-04-01T00:00:00"),
        (
            "--execute-from",
            "2026-04-01 00:00:00",
            "--execute-to",
            "2026-04-02T00:00:00",
        ),
        (
            "--execute-from",
            "2026-04-01T00:00:00Z",
            "--execute-to",
            "2026-04-02T00:00:00Z",
        ),
        (
            "--execute-from",
            "2026-04-01T00:00:00+08:00",
            "--execute-to",
            "2026-04-02T00:00:00+08:00",
        ),
        (
            "--execute-from",
            "2026-02-30T00:00:00",
            "--execute-to",
            "2026-04-02T00:00:00",
        ),
        (
            "--execute-from",
            "2026-04-02T00:00:00",
            "--execute-to",
            "2026-04-01T00:00:00",
        ),
    ],
)
def test_demand_execution_scope_has_no_legacy_or_zone_aliases(
    installed, timestamp_flags
):
    _, cli, browser, _ = installed
    result = cli("list", "--live", *timestamp_flags, code=2, scoped=False)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


@pytest.mark.parametrize("installed", ["demands", "transfers", "swaps"], indirect=True)
@pytest.mark.parametrize("inner_success", [None, False, 1])
def test_required_inner_success_cannot_be_missing_false_or_nonboolean(
    installed, inner_success
):
    case, cli, browser, _ = installed
    candidate = page(case, [record(case)])
    if inner_success is None:
        candidate["body"]["result"].pop("success")
    else:
        candidate["body"]["result"]["success"] = inner_success
    browser.business_script.append(candidate)
    result = cli("list", "--live", code=1)
    assert result["error"]["code"] == (
        "BUSINESS_QUERY_FAILED" if inner_success is False else "INVALID_RESPONSE"
    )


@pytest.mark.parametrize("installed", ["transfers"], indirect=True)
def test_transfer_native_totals_must_agree(installed):
    case, cli, browser, _ = installed
    candidate = page(case, [record(case)], 1)
    candidate["body"]["count"] = 2
    browser.business_script.append(candidate)
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("installed", ["demands"], indirect=True)
@pytest.mark.parametrize(
    "change",
    [
        {"source": "DECISION"},
        {"source": ["FUND_REQUIRE"]},
        {"source": None},
        {"currency": ""},
        {"amount": ""},
        {"amount": "NaN"},
        {"amount": "Infinity"},
        {"amount": 1},
        {"amount": True},
        {"executeTime": "2026-04-01T00:00:00"},
        {"executeTime": "2026-03-31 23:59:59"},
        {"executeTime": "2026-04-02 00:00:01"},
        {"executeTime": "2026-04-01 99:00:00"},
        {"status": False},
    ],
)
def test_demand_native_scope_and_types(installed, change):
    case, cli, browser, _ = installed
    browser.business_script.append(page(case, [{**record(case), **change}]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("installed", ["demands"], indirect=True)
def test_demand_native_bounds_are_inclusive_and_source_id_is_separate(installed):
    case, cli, browser, _ = installed
    rows = [
        {**record(case, i), "sourceId": "ONE_SOURCE", "executeTime": time}
        for i, time in enumerate(("2026-04-01 00:00:00", "2026-04-02 00:00:00"))
    ]
    browser.business_script.append(page(case, rows))
    result = cli("list", "--live", "--require-complete", "--limit", "0")
    assert result["data"] == rows
    assert result["meta"]["unique_count"] == 2


@pytest.mark.parametrize("installed", ["transfers"], indirect=True)
@pytest.mark.parametrize(
    "change",
    [
        {"debitAmount": "NaN"},
        {"creditAmount": "Infinity"},
        {"debitAmount": 1},
        {"creditAmount": False},
        {"orderStatus": 0},
        {"gmtReturnFinnet": False},
        {"gmtReturnFinnet": "1"},
    ],
)
def test_transfer_native_types_and_amounts(installed, change):
    case, cli, browser, _ = installed
    browser.business_script.append(page(case, [{**record(case), **change}]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("installed", ["transfers"], indirect=True)
def test_transfer_native_null_blank_and_zero_amounts_are_distinct(installed):
    case, cli, browser, _ = installed
    rows = [
        {**record(case, i), "debitAmount": value, "creditAmount": value}
        for i, value in enumerate((None, "", "0", "-0.123456789012345678901"))
    ]
    browser.business_script.append(page(case, rows))
    assert cli("list", "--live", "--require-complete", "--limit", "0")["data"] == rows


@pytest.mark.parametrize("installed", ["swaps"], indirect=True)
@pytest.mark.parametrize(
    "change",
    [
        {"tradeDate": "20260929"},
        {"tradeDate": "20260931"},
        {"tradeDate": "2026-09-30"},
        {"nearLegValueDate": "20260230"},
        {"farLegValueDate": 20261101},
        {"nearLegDebitAmount": "NaN"},
        {"nearLegDebitAmount": "1,23.00"},
        {"farLegFxRate": "Infinity"},
        {"farLegCreditAmount": 1},
        {"gmtCreate": False},
        {"nodeNum": "1"},
        {"needReview": 1},
    ],
)
def test_swap_native_dates_amounts_and_types(installed, change):
    case, cli, browser, _ = installed
    browser.business_script.append(page(case, [{**record(case), **change}]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("installed", ["asset_trades"], indirect=True)
def test_asset_trading_date_remains_native_without_inferred_membership(installed):
    case, cli, browser, _ = installed
    rows = [
        {**record(case, i), "tradingDate": value, "gmtCreate": "OTHER_SOURCE_CLOCK"}
        for i, value in enumerate(("2026-09-30", "NATIVE_UNINTERPRETED", "20260929"))
    ]
    browser.business_script.append(page(case, rows))
    assert cli("list", "--live", "--require-complete", "--limit", "0")["data"] == rows


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
def test_capability_rejects_unqualified_scope_position_and_width(
    installed, scope, position, width
):
    case, _, browser, config = installed
    adapter = (
        Registry(config / "config.toml")
        .scan()
        .get("liquidity", "operations." + case)
        .adapter
    )
    values = parameters(case)
    with pytest.raises(CliError) as error:
        adapter.capability(values).page_body(
            adapter.scope(values) if scope is None else scope,
            position,
            SIZES[case] if width is None else width,
        )
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests
