"""Installed B10 account capability List through public CLI and synthetic CDP."""

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
LEAF = "network.account_capabilities"


def record(identity=0):
    return {
        "id": identity,
        "tntInstId": "GUAPW3SG",
        "aliasName": "ACCOUNT",
        "ruleId": 500,
        "amount": Decimal("0.123456789012345678901"),
        "status": "UNKNOWN_NATIVE_STATE",
        "zero": 0,
        "nullable": None,
        "unknown": {"nested": [False, "", 0, "1.0000", {"original": True}]},
    }


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
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
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        status, output, error = run_cli(["liquidity", action, LEAF, *args])
        assert status == code, output + error
        return parse(output)

    try:
        status, output, error = run_cli(["domain", "enable", "liquidity"])
        assert status == 0, output + error
        source = ROOT / "leaf_packages/liquidity" / LEAF
        if request.param == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(source))
            source = archive_path
        status, output, error = run_cli(["plugins", "install", str(source)])
        assert status == 0, output + error
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_live_refresh_offline_preserve_full_native_records_and_integer_ids(installed):
    cli, browser, _ = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.business_requests
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    rows = [record(0), record(-1), record(1)]
    browser.business_script.append(page(rows))
    live = cli("list", "--live", "--require-complete", "--limit", "0")
    assert live["data"] == rows
    assert all(type(row["id"]) is int for row in live["data"])
    assert live["meta"]["unique_count"] == 3
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(rows))
    saved = cli("refresh", "--require-complete", "--limit", "1")
    count = len(browser.business_requests)
    offline = cli("list", "--limit", "0")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert offline["meta"]["complete"] is True
    assert offline["meta"]["scope"] == ""
    assert len(browser.business_requests) == count
    assert (
        browser.business_requests
        == [{"tntInstId": "GUAPW3SG", "rowStart": 0, "pageSize": 10}] * 2
    )
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions
    assert all(
        "/serviceInfoQuery.json" in e
        and 'method: "POST"' in e
        and "application/json" in e
        for e in expressions
    )


def test_offset_paging_precedes_display_limit(installed):
    cli, browser, _ = installed
    rows = [record(i - 1) for i in range(11)]
    browser.business_script.extend([page(rows[:10], 11), page(rows[10:], 11)])
    result = cli("list", "--live", "--require-complete", "--limit", "1")
    assert result["data"] == rows[:1]
    assert result["meta"]["collected_total"] == 11
    assert browser.business_requests == [
        {"tntInstId": "GUAPW3SG", "rowStart": offset, "pageSize": 10}
        for offset in (0, 10)
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
def test_rejected_refresh_preserves_prior_rows_and_fetched_at(installed, failure):
    cli, browser, _ = installed
    rows = [record(0), record(-1)]
    browser.business_script.append(page(rows))
    saved = cli("refresh", "--require-complete")
    candidate = page(rows)
    expected = "INVALID_RESPONSE"
    code = 1
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
        candidate = page([{"aliasName": "ACCOUNT"}])
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
    result = cli("refresh", "--require-complete", code=code)
    assert result["meta"]["published"] is False
    if code:
        assert result["error"]["code"] == expected
    offline = cli("list", "--limit", "0")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "identity", [None, "", "0", True, False, Decimal("1.5"), [], {}]
)
def test_identity_requires_native_integer_without_coercion(installed, identity):
    cli, browser, _ = installed
    browser.business_script.append(page([record(identity)]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("failure", ["negative", "float", "string"])
def test_native_total_requires_nonnegative_integer(installed, failure):
    cli, browser, _ = installed
    value = {"negative": -1, "float": Decimal("1.5"), "string": "1"}[failure]
    browser.business_script.append(page([record()], value))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize(
    "change", ["path", "host", "method", "tenant", "extra", "width", "missing_tenant"]
)
def test_shared_transport_rejects_unqualified_request(installed, change):
    _, browser, config = installed
    adapter = Registry(config / "config.toml").scan().get("liquidity", LEAF).adapter
    capability = adapter.capability({})
    body = capability.page_body("", 0, 10)
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
    elif change == "host":
        request = replace(request, host="other.example")
    elif change == "method":
        request = replace(request, method="GET")
    elif change == "tenant":
        body["tntInstId"] = "OTHER"
    elif change == "extra":
        body["action"] = "edit"
    elif change == "width":
        body["pageSize"] = 100
    else:
        body.pop("tntInstId")
    with pytest.raises(CliError) as error:
        validate_request(request, capability.contract)
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


@pytest.mark.parametrize(
    "scope,offset,width",
    [
        ("OTHER", 0, 10),
        ("", True, 10),
        ("", -1, 10),
        ("", 1, 10),
        ("", 0, True),
        ("", 0, 100),
    ],
)
def test_capability_rejects_unverified_scope_and_paging(
    installed, scope, offset, width
):
    _, browser, config = installed
    adapter = Registry(config / "config.toml").scan().get("liquidity", LEAF).adapter
    with pytest.raises(CliError) as error:
        adapter.capability({}).page_body(scope, offset, width)
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_conflict_keeps_last_arrival_and_marks_incomplete(installed):
    cli, browser, _ = installed
    rows = [record(0), record(-1)]
    last = {**rows[0], "unknown": "CHANGED"}
    browser.business_script.append(page([rows[0], last, rows[1]], 3))
    result = cli("list", "--live", "--limit", "0")
    assert result["data"] == [last, rows[1]]
    assert result["meta"]["complete"] is False
    assert result["meta"]["duplicate_count"] == 1


@pytest.mark.parametrize(
    "failure", ["empty", "short", "duplicate", "conflict", "changed_total"]
)
def test_offset_incomplete_or_changed_total_preserves_previous_cache(
    installed, failure
):
    cli, browser, _ = installed
    original = [record()]
    browser.business_script.append(page(original))
    saved = cli("refresh", "--require-complete")
    rows = [record(i) for i in range(11)]
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
        [page(first, 11), page(last, 12 if failure == "changed_total" else 11)]
    )
    result = cli("refresh", "--require-complete", code=1)
    assert result["error"]["code"] == (
        "INVALID_RESPONSE" if failure == "changed_total" else "INCOMPLETE_RESULT"
    )
    offline = cli("list", "--limit", "0")
    assert offline["data"] == original
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_page_exceeding_requested_width_is_rejected(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([record(i) for i in range(11)]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize(
    "args",
    [
        ("get", "NATIVE_ID"),
        ("list", "--live", "--currency", "USD"),
        ("list", "--live", "--from-date", "2026-10-01"),
    ],
)
def test_invalid_integer_lookup_and_undeclared_filters_never_query(installed, args):
    cli, browser, _ = installed
    cli(*args, code=2)
    assert not browser.business_requests


@pytest.mark.parametrize("unqualified_marker", [False, 1])
def test_unknown_envelope_metadata_does_not_override_verified_outer_success(
    installed, unqualified_marker
):
    cli, browser, _ = installed
    rows = [record(0), record(-1)]
    candidate = page(rows)
    candidate["body"]["data"]["success"] = unqualified_marker
    browser.business_script.append(candidate)
    result = cli("list", "--live", "--require-complete", "--limit", "0")
    assert result["data"] == rows
    assert result["meta"]["complete"] is True
