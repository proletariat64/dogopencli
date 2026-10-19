"""Installed real leaves exercise accepted native shape and source relationships."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
LEAVES = ("rules.waterlevel", "investment.quotes", "investment.returns")
QUOTE_FLAGS = ("--from-date", "20260820", "--to-date", "20260820")
RETURN_FLAGS = (
    "--accrual-from-date",
    "20261015",
    "--accrual-to-date",
    "20261016",
    "--settlement-from-date",
    "20261015",
    "--settlement-to-date",
    "20261016",
)


@pytest.fixture
def installed(request, run_cli, tmp_path, monkeypatch):
    leaf, kind = (
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
        if kind == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        archive.write(path, path.relative_to(package))
            package = archive_path
        cli("plugins", "install", str(package))
        yield leaf, cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def reply(value):
    return {"status": 200, "body": value}


def quote_rows(count=2):
    return [
        {
            "quotationOrderId": str(index),
            "valueDate": "20260820",
            "quote": "0.00100%",
            "unknown": {"raw": [None, False, Decimal("0.123456789012345678901")]},
        }
        for index in range(count)
    ]


def quote_detail(identity="0"):
    return {
        "quotationDetail": {"quotationId": identity, "success": False},
        "operationLog": [{"native": [None, "", False]}],
        "unknown": Decimal("0.123456789012345678901"),
    }


def water_rows():
    return [
        {
            "bufferId": identity,
            "aliasName": "account",
            "version": version,
            "success": False,
            "unknown": [None, {"value": "1.0000"}],
        }
        for identity, version in (("history", "07"), (8, "08"))
    ]


def water_envelope(rows):
    return {"resultFlag": True, "result": {"dataValue": rows}}


def native_sources():
    accrual = [
        {
            "investmentNo": parent,
            "transactionDate": date,
            "amount": Decimal("0.123456789012345678901"),
            "unknown": [None, False, {"raw": "1.0000"}],
        }
        for parent, date in (("A", "20261015"), ("A", "20261016"), ("B", "20261015"))
    ]
    cash = [
        {
            "id": identity,
            "transactionId": parent,
            "settlementDate": "20261016",
            "amount": "0.00100",
            "success": "native-value",
        }
        for identity, parent in (("one", "A"), ("two", "A"), ("three", "C"))
    ]
    return accrual, cash


def source_envelope(rows, total=None):
    return reply(
        {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        }
    )


def query(cli, action, leaf, *flags, code=0):
    return cli("liquidity", action, leaf, *flags, code=code)


@pytest.mark.parametrize(
    "installed",
    [(leaf, kind) for leaf in LEAVES for kind in ("directory", "zip")],
    indirect=True,
)
def test_help_is_declaration_only(installed):
    leaf, cli, browser, _ = installed
    query(cli, "list", leaf, "--help")
    cli("liquidity", "describe", leaf)
    if leaf != "investment.returns":
        query(cli, "get", leaf, "--help")
    assert not browser.business_requests


@pytest.mark.parametrize(
    "installed",
    [("rules.waterlevel", kind) for kind in ("directory", "zip")],
    indirect=True,
)
def test_waterlevel_preserves_native_array_and_projects_each_member(installed):
    leaf, cli, browser, _ = installed
    rows = water_rows()
    browser.business_script.append(reply(water_envelope(rows)))
    result = query(cli, "get", leaf, "account")
    assert result["data"] == rows
    assert result["meta"]["returned_count"] == 2
    assert not {"complete", "reported_total", "acquisition"} & result["meta"].keys()
    assert browser.business_requests == [
        {"tntInstId": "GUAPW3SG", "aliasName": "account"}
    ]
    browser.business_script.append(reply(water_envelope(rows)))
    projected = query(cli, "get", leaf, "account", "--fields", "bufferId,version")
    assert projected["data"] == [
        {"bufferId": row["bufferId"], "version": row["version"]} for row in rows
    ]
    browser.business_script.append(reply(water_envelope([])))
    empty = query(cli, "get", leaf, "account")
    assert empty["data"] == [] and empty["meta"]["returned_count"] == 0


@pytest.mark.parametrize(
    "fault",
    [
        "null",
        "object",
        "member",
        "identity",
        "duplicate",
        "alias",
        "tenant",
        "business",
    ],
)
@pytest.mark.parametrize("installed", ["rules.waterlevel"], indirect=True)
def test_waterlevel_rejects_malformed_or_contradictory_array(installed, fault):
    leaf, cli, browser, _ = installed
    rows = water_rows()
    if fault == "null":
        rows = None
    elif fault == "object":
        rows = {}
    elif fault == "member":
        rows = [None]
    elif fault == "identity":
        rows[0]["bufferId"] = True
    elif fault == "duplicate":
        rows[1]["bufferId"] = rows[0]["bufferId"]
    elif fault == "alias":
        rows[1]["aliasName"] = "other"
    elif fault == "tenant":
        rows[0]["tntInstId"] = "OTHER"
    envelope = water_envelope(rows)
    if fault == "business":
        envelope["resultFlag"] = False
    browser.business_script.append(reply(envelope))
    result = query(cli, "get", leaf, "account", code=1)
    assert result["error"]["code"] == (
        "BUSINESS_QUERY_FAILED" if fault == "business" else "INVALID_RESPONSE"
    )


@pytest.mark.parametrize("installed", ["rules.waterlevel"], indirect=True)
def test_waterlevel_get_keeps_current_list_and_has_no_binding(installed):
    leaf, cli, browser, _ = installed
    current = [{"bufferId": "current", "aliasName": "account"}]
    browser.business_script.append(
        reply({"resultFlag": True, "result": {"dataValue": current, "count": 1}})
    )
    query(cli, "refresh", leaf, "--require-complete")
    saved = query(cli, "list", leaf, "--limit", "0")
    browser.business_script.append(reply(water_envelope(water_rows())))
    query(cli, "get", leaf, "account")
    after = query(cli, "list", leaf, "--limit", "0")
    assert (
        saved["data"] == after["data"]
        and saved["meta"]["fetched_at"] == after["meta"]["fetched_at"]
    )
    count = len(browser.business_requests)
    query(cli, "list", leaf, "--live", "--with-detail", code=2)
    assert len(browser.business_requests) == count


@pytest.mark.parametrize(
    "installed", ["rules.waterlevel", "investment.quotes"], indirect=True
)
@pytest.mark.parametrize("identity", ["", "   "])
def test_blank_lookup_is_rejected_before_transport(installed, identity):
    leaf, cli, browser, _ = installed
    result = query(cli, "get", leaf, identity, code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


@pytest.mark.parametrize(
    "installed",
    [("investment.quotes", kind) for kind in ("directory", "zip")],
    indirect=True,
)
def test_quotes_single_response_and_nested_get_keep_native_data(installed):
    leaf, cli, browser, _ = installed
    rows = quote_rows(5001)
    browser.business_script.append(reply({"success": True, "data": rows}))
    result = query(
        cli, "list", leaf, *QUOTE_FLAGS, "--live", "--require-complete", "--limit", "0"
    )
    assert result["data"] == rows
    acquisition = result["meta"]["acquisition"]
    assert acquisition["reported_total"] is None
    assert acquisition["coverage_basis"] == "qualified_single_response"
    assert len(browser.business_requests) == 1
    assert browser.business_requests[0] == {
        "dataType": "QUOTED",
        "startValueDate": "20260820",
        "endValueDate": "20260820",
        "timeZone": None,
        "rowStart": 0,
        "pageSize": 5000,
    }
    native = quote_detail()
    browser.business_script.append(
        reply({"baseResult": {"success": True, "data": native}})
    )
    detail = query(cli, "get", leaf, "0")
    assert detail["data"] == native and "quotationId" not in detail["data"]
    assert browser.business_requests[-1] == {"quotationOrderId": "0"}


@pytest.mark.parametrize("installed", ["investment.quotes"], indirect=True)
def test_quotes_refresh_offline_composition_is_selected_and_atomic(installed):
    leaf, cli, browser, _ = installed
    rows = quote_rows()
    browser.business_script.append(reply({"success": True, "data": rows}))
    query(cli, "refresh", leaf, *QUOTE_FLAGS, "--require-complete")
    saved = query(cli, "list", leaf, "--limit", "0")
    browser.business_script.extend(
        [
            reply({"success": True, "data": rows}),
            reply({"baseResult": {"success": True, "data": quote_detail("1")}}),
        ]
    )
    combined = query(
        cli,
        "list",
        leaf,
        *QUOTE_FLAGS,
        "--live",
        "--with-detail",
        "--offset",
        "1",
        "--limit",
        "1",
    )
    assert combined["data"] == [{"record": rows[1], "detail": quote_detail("1")}]
    assert browser.business_requests[-1] == {"quotationOrderId": "1"}
    browser.business_script.extend(
        [
            reply({"success": True, "data": rows}),
            reply({"baseResult": {"success": False}}),
        ]
    )
    failed = query(
        cli,
        "list",
        leaf,
        *QUOTE_FLAGS,
        "--live",
        "--with-detail",
        "--limit",
        "1",
        code=1,
    )
    assert failed["data"] is None
    browser.business_script.append(reply({"success": True, "data": []}))
    empty = query(cli, "refresh", leaf, *QUOTE_FLAGS, "--require-complete")
    assert not empty["data"]["published"]
    after = query(cli, "list", leaf, "--limit", "0")
    assert (
        after["data"] == rows
        and after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    )


@pytest.mark.parametrize(
    "fault", ["missing", "null", "wrong", "boolean", "array", "business"]
)
@pytest.mark.parametrize("installed", ["investment.quotes"], indirect=True)
def test_quotes_nested_identity_is_validated_before_projection(installed, fault):
    leaf, cli, browser, _ = installed
    native = quote_detail()
    if fault == "missing":
        native.pop("quotationDetail")
    elif fault == "null":
        native["quotationDetail"] = None
    elif fault == "wrong":
        native["quotationDetail"]["quotationId"] = "other"
    elif fault == "boolean":
        native["quotationDetail"]["quotationId"] = True
    elif fault == "array":
        native["quotationDetail"]["quotationId"] = []
    browser.business_script.append(
        reply({"baseResult": {"success": fault != "business", "data": native}})
    )
    result = query(cli, "get", leaf, "0", "--fields", "operationLog", code=1)
    assert result["data"] is None


@pytest.mark.parametrize("installed", ["investment.quotes"], indirect=True)
@pytest.mark.parametrize("fault", ["duplicate", "date", "tenant", "business", "schema"])
def test_quotes_strict_failure_preserves_saved_cache(installed, fault):
    leaf, cli, browser, _ = installed
    rows = quote_rows()
    browser.business_script.append(reply({"success": True, "data": rows}))
    query(cli, "refresh", leaf, *QUOTE_FLAGS, "--require-complete")
    saved = query(cli, "list", leaf, "--limit", "0")
    bad = deepcopy(rows)
    if fault == "duplicate":
        bad.append(deepcopy(bad[0]))
    elif fault == "date":
        bad[0]["valueDate"] = "20260821"
    elif fault == "tenant":
        bad[0]["tntInstId"] = "OTHER"
    elif fault == "schema":
        bad = None
    browser.business_script.append(reply({"success": fault != "business", "data": bad}))
    query(cli, "refresh", leaf, *QUOTE_FLAGS, "--require-complete", code=1)
    after = query(cli, "list", leaf, "--limit", "0")
    assert (
        after["data"] == rows
        and after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    )


@pytest.mark.parametrize(
    "installed",
    [("investment.returns", kind) for kind in ("directory", "zip")],
    indirect=True,
)
def test_returns_assembles_union_without_losing_native_children(installed):
    leaf, cli, browser, _ = installed
    accrual, cash = native_sources()
    browser.business_script.extend([source_envelope(accrual), source_envelope(cash)])
    query(cli, "refresh", leaf, *RETURN_FLAGS, "--require-complete")
    saved = query(cli, "list", leaf, "--limit", "0", "--require-complete")
    expected = [
        {"investmentNo": "A", "accrual": accrual[:2], "cash": cash[:2]},
        {"investmentNo": "B", "accrual": accrual[2:], "cash": []},
        {"investmentNo": "C", "accrual": [], "cash": cash[2:]},
    ]
    assert saved["data"] == expected
    evidence = saved["meta"]["acquisition"]
    assert (
        evidence["coverage_basis"] == "validated_sources"
        and evidence["reported_total"] is None
    )
    assert evidence["total_semantics"] == "assembled_roots"
    assert evidence["sources"]["accrual"]["acquisition"]["reported_total"] == 3
    assert evidence["sources"]["cash"]["acquisition"]["reported_total"] == 3
    assert browser.business_requests == [
        {
            "tntInstId": "GUAPW3SG",
            "timeZone": "GMT+08",
            "queryBeginTime": "20261015",
            "queryEndTime": "20261016",
            "transactionId": [],
            "rowStart": 0,
            "pageSize": 5000,
        },
        {
            "tntInstId": "GUAPW3SG",
            "timeZone": "GMT+08",
            "settlementDateBegin": "20261015",
            "settlementDateEnd": "20261016",
            "postingDateBegin": "",
            "postingDateEnd": "",
            "rowStart": 0,
            "pageSize": 5000,
        },
    ]
    count = len(browser.business_requests)
    assert query(cli, "list", leaf, "--limit", "0")["data"] == expected
    assert len(browser.business_requests) == count


@pytest.mark.parametrize("installed", ["investment.returns"], indirect=True)
def test_returns_accrual_filter_is_not_a_cash_filter(installed):
    leaf, cli, browser, _ = installed
    accrual, cash = native_sources()
    browser.business_script.extend([source_envelope(accrual), source_envelope(cash)])
    result = query(
        cli,
        "list",
        leaf,
        *RETURN_FLAGS,
        "--accrual-investment-no",
        "A",
        "--accrual-investment-no",
        "B",
        "--live",
        "--require-complete",
        "--limit",
        "0",
    )
    assert [row["investmentNo"] for row in result["data"]] == ["A", "B", "C"]
    assert browser.business_requests[0]["transactionId"] == ["A", "B"]
    assert "transactionId" not in browser.business_requests[1]


@pytest.mark.parametrize(
    "fault",
    ["business", "schema", "incomplete", "duplicate", "tenant", "date", "parent"],
)
@pytest.mark.parametrize("installed", ["investment.returns"], indirect=True)
def test_returns_failed_source_never_publishes_partial_parents(installed, fault):
    leaf, cli, browser, _ = installed
    accrual, cash = native_sources()
    browser.business_script.extend([source_envelope(accrual), source_envelope(cash)])
    query(cli, "refresh", leaf, *RETURN_FLAGS, "--require-complete")
    saved = query(cli, "list", leaf, "--limit", "0")
    bad = deepcopy(cash)
    if fault == "duplicate":
        bad.append(deepcopy(bad[0]))
    elif fault == "tenant":
        bad[0]["tntInstId"] = "OTHER"
    elif fault == "date":
        bad[0]["settlementDate"] = "20261017"
    elif fault == "parent":
        bad[0]["transactionId"] = None
    envelope = source_envelope(bad, total=len(bad) + (fault == "incomplete"))
    if fault == "business":
        envelope["body"]["success"] = False
    elif fault == "schema":
        envelope["body"]["data"]["data"] = None
    browser.business_script.extend([source_envelope(accrual), envelope])
    failed = query(cli, "refresh", leaf, *RETURN_FLAGS, code=1)
    assert failed["data"] is None and failed["meta"]["source"] == "cash"
    after = query(cli, "list", leaf, "--limit", "0")
    assert (
        after["data"] == saved["data"]
        and after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    )


@pytest.mark.parametrize("installed", ["investment.returns"], indirect=True)
def test_returns_complete_empty_does_not_replace_saved_roots(installed):
    leaf, cli, browser, _ = installed
    accrual, cash = native_sources()
    browser.business_script.extend([source_envelope(accrual), source_envelope(cash)])
    query(cli, "refresh", leaf, *RETURN_FLAGS, "--require-complete")
    saved = query(cli, "list", leaf, "--limit", "0")
    browser.business_script.extend([source_envelope([]), source_envelope([])])
    empty = query(cli, "refresh", leaf, *RETURN_FLAGS, "--require-complete")
    assert not empty["data"]["published"]
    after = query(cli, "list", leaf, "--limit", "0")
    assert (
        after["data"] == saved["data"]
        and after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    )


@pytest.mark.parametrize(
    "installed", ["investment.quotes", "investment.returns"], indirect=True
)
def test_dates_are_required_before_business_calls(installed):
    leaf, cli, browser, _ = installed
    query(cli, "list", leaf, "--live", code=2)
    assert not browser.business_requests
