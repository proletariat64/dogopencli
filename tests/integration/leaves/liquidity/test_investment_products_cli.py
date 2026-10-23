"""Installed product List and dependent detail/history Get composition."""

import json
import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAF = "investment.products"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
LIST_BODY = {"tntInstId": "GUAPW3SG", "rowStart": 0, "pageSize": 5000}


def row(identity="PHYSICAL-1", **values):
    return {
        "incrementProductId": identity,
        "incrementProductCode": "BUSINESS-CODE",
        "currency": "USD",
        "bankId": "BANK",
        "status": "Invalid",
        "version": 2,
        "incrementRateRules": [
            {
                "amount": Decimal("0.123456789012345678901"),
                "values": [None, False, "", 0],
            }
        ],
        "incrementAccounts": [],
        "incrementInterestRule": {"rate": "0.00000"},
        "unknown": {"items": [3, 1]},
        "optional": None,
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


def detail(identity="PHYSICAL-1", **values):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": row(
                identity,
                detailOnly={
                    "children": [None, {"value": Decimal("999.1234567890123456789")}]
                },
                **values,
            ),
        },
    }


def history(rows=()):
    return {"status": 200, "body": {"success": True, "data": list(rows)}}


def cache_bytes(config):
    return {
        p.name: p.read_bytes()
        for p in (config / "leaf-cache.sqlite3", config / "leaf-cache.sqlite3-wal")
        if p.exists()
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
def test_list_full_native_order_local_scope_and_detached_install(installed):
    cli, browser, config = installed
    cli("list", "-h")
    cli("get", "-h")
    cli("describe")
    assert not browser.transports
    rows = [row("Z"), row("A", version=1)]
    browser.business_script.append(page(rows, rowStart=0, pageSize=5000))
    live = cli("list", "--live", "--limit", "0", "--require-complete")
    assert live["data"] == rows
    assert not (config / "leaf-cache.sqlite3").exists()
    browser.business_script.append(page(rows))
    saved = cli("refresh", "--require-complete")
    assert cli("list", "--limit", "0", "--require-complete")["data"] == rows
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert browser.business_requests == [LIST_BODY] * 2
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions and all(
        "/incrementProductsPage.json" in e
        and 'method: "POST"' in e
        and "application/json" in e
        for e in expressions
    )


@pytest.mark.parametrize(
    ("flag", "field", "value"),
    [
        ("currency", "currency", "USD"),
        ("bank", "bankId", "BANK"),
        ("status", "status", "Invalid"),
    ],
)
def test_filters_are_exact_local_or_and_offline_with_no_source_change(
    installed, flag, field, value
):
    cli, browser, config = installed
    rows = [
        row("1"),
        row("2", **{field: value + "-OTHER"}),
        row("3", **{field: value.lower()}),
    ]
    browser.business_script.append(page(rows))
    cli("refresh", "--require-complete")
    cli("list", "--limit", "0")
    before = cache_bytes(config)
    assert cli("list", "--" + flag, value, "--require-complete")["data"] == rows[:1]
    assert (
        cli(
            "list",
            "--" + flag,
            value,
            "--" + flag,
            value + "-OTHER",
            "--require-complete",
        )["data"]
        == rows[:2]
    )
    assert cache_bytes(config) == before
    assert browser.business_requests == [LIST_BODY]
    browser.business_script.append(page(rows))
    assert (
        cli("list", "--live", "--" + flag, value, "--require-complete")["data"]
        == rows[:1]
    )
    assert browser.business_requests[-1] == LIST_BODY


def test_combined_and_and_filtered_refresh_keeps_whole_native_source(installed):
    cli, browser, _ = installed
    rows = [
        row("1"),
        row("2", currency="EUR"),
        row("3", bankId="OTHER"),
        row("4", status="Valid"),
    ]
    browser.business_script.append(page(rows))
    cli(
        "refresh",
        "--currency",
        "USD",
        "--bank",
        "BANK",
        "--status",
        "Invalid",
        "--require-complete",
    )
    assert cli("list", "--limit", "0")["data"] == rows
    assert (
        cli(
            "list",
            "--currency",
            "USD",
            "--bank",
            "BANK",
            "--status",
            "Invalid",
            "--require-complete",
        )["data"]
        == rows[:1]
    )
    assert browser.business_requests == [LIST_BODY]


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "marker",
        "root",
        "rows",
        "total",
        "id_missing",
        "id_bool",
        "tenant",
        "size",
        "offset",
        "gap",
        "duplicate",
        "conflict",
    ],
)
def test_failed_list_never_replaces_saved_capture(installed, failure):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", "--require-complete")
    reply = page([row("NEW")])
    body = reply["body"]
    data = body["data"]
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        reply = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        body["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        body["success"] = 1
    elif failure == "root":
        body["data"] = []
    elif failure == "rows":
        data["data"] = None
    elif failure == "total":
        data["totalCount"] = True
    elif failure == "id_missing":
        data["data"][0].pop("incrementProductId")
    elif failure == "id_bool":
        data["data"][0]["incrementProductId"] = True
    elif failure == "tenant":
        data["data"][0]["tntInstId"] = "OTHER"
    elif failure == "size":
        data["pageSize"] = 10
    elif failure == "offset":
        data["rowStart"] = 5000
    elif failure == "gap":
        data["totalCount"] = 2
        expected = "INCOMPLETE_RESULT"
    else:
        data["data"] = [
            row("DUP"),
            row("DUP", version=3) if failure == "conflict" else row("DUP"),
        ]
        data["totalCount"] = 2
        expected = "INCOMPLETE_RESULT"
    browser.business_script.append(reply)
    failed = cli("refresh", "--require-complete", code=1)
    assert failed["error"]["code"] == expected
    assert failed["meta"]["published"] is False
    assert cli("list")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == 2


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_get_before_list_full_root_form_and_no_cache(installed):
    cli, browser, config = installed
    versions = [row("OLDER-2", version=2), row("OLDER-1", version=1)]
    browser.business_script.extend([detail(), history(versions)])
    got = cli("get", "PHYSICAL-1")
    assert got["data"] == {"detail": detail()["body"]["data"], "history": versions}
    assert browser.business_requests == [
        {"tntInstId": "GUAPW3SG", "incrementProductId": "PHYSICAL-1"},
        {"tntInstId": "GUAPW3SG", "incrementProductCode": "BUSINESS-CODE"},
    ]
    coverage = got["meta"]["query_evidence"]["coverage"]
    history_coverage = coverage["attempts"][0]["components"]["history"]
    assert history_coverage["reported_total"] is None
    assert history_coverage["coverage_basis"] == "qualified_single_response"
    assert history_coverage["collected_total"] == 2
    assert got["meta"]["query_evidence"]["request_count"] == 2
    assert not (config / "leaf-cache.sqlite3").exists()
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert len(expressions) == 2
    assert "/incrementProductDetail.json" in expressions[0]
    assert "/incrementProductHistoryQuery.json" in expressions[1]
    assert all(
        'method: "POST"' in e and "application/x-www-form-urlencoded" in e
        for e in expressions
    )


def test_selected_filter_window_detail_projection_and_saved_bytes(installed):
    cli, browser, config = installed
    rows = [row("1"), row("2", currency="EUR"), row("3"), row("4")]
    browser.business_script.append(page(rows))
    saved = cli("refresh", "--require-complete")
    before = cache_bytes(config)
    versions = [row("OLD-3", version=1)]
    browser.business_script.extend(
        [page(rows), detail("3", version=99), history(versions)]
    )
    result = cli(
        "list",
        "--live",
        "--with-detail",
        "--currency",
        "USD",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        "incrementProductId",
        "--require-complete",
    )
    assert result["data"] == [
        {
            "record": {"incrementProductId": "3"},
            "detail": {
                "detail": detail("3", version=99)["body"]["data"],
                "history": versions,
            },
        }
    ]
    assert browser.business_requests == [
        LIST_BODY,
        LIST_BODY,
        {"tntInstId": "GUAPW3SG", "incrementProductId": "3"},
        {"tntInstId": "GUAPW3SG", "incrementProductCode": "BUSINESS-CODE"},
    ]
    assert cache_bytes(config) == before
    assert cli("list", "--limit", "0")["data"] == rows
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    browser.business_script.append(page(rows))
    assert cli("list", "--live", "--with-detail", "--offset", "99")["data"] == []
    assert len(browser.business_requests) == 5


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "marker",
        "null",
        "empty",
        "array",
        "missing_id",
        "boolean_id",
        "wrong_id",
        "tenant",
    ],
)
def test_detail_failure_and_second_composed_failure_are_atomic(installed, failure):
    cli, browser, config = installed
    rows = [row("1"), row("2")]
    browser.business_script.append(page(rows))
    saved = cli("refresh", "--require-complete")
    before = cache_bytes(config)
    reply = detail("2")
    body = reply["body"]
    root = body["data"]
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        reply = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        body["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        body["success"] = "true"
    elif failure == "null":
        body["data"] = None
    elif failure == "empty":
        body["data"] = {}
    elif failure == "array":
        body["data"] = []
    elif failure == "missing_id":
        root.pop("incrementProductId")
    elif failure == "boolean_id":
        root["incrementProductId"] = True
    elif failure == "tenant":
        root["tntInstId"] = "OTHER"
    else:
        root["incrementProductId"] = "OTHER"
    browser.business_script.append(reply)
    assert cli("get", "2", code=1)["error"]["code"] == expected
    browser.business_script.extend([page(rows), detail("1"), history(), reply])
    failed = cli("list", "--live", "--with-detail", "--limit", "0", code=1)
    assert failed["data"] is None
    assert failed["error"]["code"] == expected
    assert browser.business_requests[-4:] == [
        LIST_BODY,
        {"tntInstId": "GUAPW3SG", "incrementProductId": "1"},
        {"tntInstId": "GUAPW3SG", "incrementProductCode": "BUSINESS-CODE"},
        {"tntInstId": "GUAPW3SG", "incrementProductId": "2"},
    ]
    assert cache_bytes(config) == before
    assert cli("list", "--limit", "0")["data"] == rows
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("identity", ["", " "])
def test_blank_get_rejected_before_auth(installed, identity):
    cli, browser, _ = installed
    assert cli("get", identity, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize("flag", ["currency", "bank", "status"])
def test_blank_local_filter_rejected_before_auth(installed, flag):
    cli, browser, _ = installed
    assert (
        cli("list", "--live", "--" + flag, " ", code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert not browser.transports


def test_closed_transport_rejects_request_filter_injection(
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
            'return {"tntInstId": TENANT, "rowStart": 0, "pageSize": PAGE_SIZE}',
            'return {"tntInstId": TENANT, "rowStart": 0, '
            '"pageSize": PAGE_SIZE, "currency": "USD"}',
        )
    )
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 0, output + error
    assert cli("list", "--live", code=1)["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_empty_native_list_is_preserved_without_detail_queries(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([]))
    assert cli("list", "--live", "--with-detail", "--require-complete")["data"] == []
    assert browser.business_requests == [LIST_BODY]


def test_single_native_total_at_width_boundary_without_extra_query(installed):
    cli, browser, _ = installed
    rows = [row(str(i)) for i in range(5000)]
    browser.business_script.append(page(rows))
    result = cli("list", "--live", "--limit", "1", "--require-complete")
    assert result["data"] == rows[:1]
    assert result["meta"]["unique_count"] == 5000
    assert browser.business_requests == [LIST_BODY]
    browser.business_script.append(page(rows, total=5001))
    assert (
        cli("list", "--live", "--require-complete", code=1)["error"]["code"]
        == "INCOMPLETE_RESULT"
    )
    assert browser.business_requests == [LIST_BODY] * 2


def test_empty_refresh_preserves_nonempty_saved_list(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", "--require-complete")
    browser.business_script.append(page([]))
    empty = cli("refresh", "--require-complete")
    assert empty["meta"]["published"] is False
    assert cli("list")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("tenant", [None, "", "GUAPW3SG"])
def test_optional_native_tenant_retains_null_blank_and_correct_values(
    installed, tenant
):
    cli, browser, _ = installed
    native = row(tntInstId=tenant)
    browser.business_script.append(page([native]))
    assert cli("list", "--live", "--require-complete")["data"] == [native]
    browser.business_script.extend([detail(tntInstId=tenant), history()])
    assert cli("get", "PHYSICAL-1")["data"] == {
        "detail": detail(tntInstId=tenant)["body"]["data"],
        "history": [],
    }


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_history_uses_detail_code_and_preserves_independent_same_id_values(installed):
    cli, browser, _ = installed
    native = detail(incrementProductCode="DETAIL-CODE", version=9)
    versions = [row(incrementProductCode="DETAIL-CODE", version=1, unknown=None)]
    browser.business_script.extend([native, history(versions)])
    got = cli("get", "PHYSICAL-1")
    assert got["data"] == {"detail": native["body"]["data"], "history": versions}
    assert browser.business_requests[-1] == {
        "tntInstId": "GUAPW3SG",
        "incrementProductCode": "DETAIL-CODE",
    }


def test_empty_history_is_successful_and_projection_does_not_skip_acquisition(
    installed,
):
    cli, browser, _ = installed
    browser.business_script.extend([detail(), history()])
    got = cli("get", "PHYSICAL-1", "--fields", "history")
    assert got["data"] == {"history": []}
    assert len(browser.business_requests) == 2
    assert got["meta"]["query_evidence"]["coverage"]["scope_complete"] is True


@pytest.mark.parametrize("code", [None, "", " ", True, 1, [], {}])
def test_missing_detail_product_code_fails_without_history_request(installed, code):
    cli, browser, _ = installed
    browser.business_script.append(detail(incrementProductCode=code))
    got = cli("get", "PHYSICAL-1", code=1)
    assert got["data"] is None
    assert got["error"]["code"] == "INVALID_RESPONSE"
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "marker",
        "null",
        "object",
        "member",
        "missing_id",
        "blank_id",
        "boolean_id",
        "tenant",
        "code",
        "duplicate",
        "conflict",
    ],
)
def test_history_failure_is_atomic_and_preserves_saved_list(installed, failure):
    cli, browser, config = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", "--require-complete")
    before = cache_bytes(config)
    reply = history([row("OLDER")])
    body = reply["body"]
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        reply = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        body["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        body["success"] = 1
    elif failure == "null":
        body["data"] = None
    elif failure == "object":
        body["data"] = {}
    elif failure == "member":
        body["data"] = [None]
    elif failure == "missing_id":
        body["data"][0].pop("incrementProductId")
    elif failure == "blank_id":
        body["data"][0]["incrementProductId"] = " "
    elif failure == "boolean_id":
        body["data"][0]["incrementProductId"] = True
    elif failure == "tenant":
        body["data"][0]["tntInstId"] = "OTHER"
    elif failure == "code":
        body["data"][0]["incrementProductCode"] = "OTHER"
    else:
        body["data"] = [
            row("DUP"),
            row("DUP", version=3 if failure == "conflict" else 2),
        ]
    browser.business_script.extend([detail(), reply])
    got = cli("get", "PHYSICAL-1", code=1)
    assert got["data"] is None
    assert got["error"]["code"] == expected
    assert got["meta"]["query_evidence"]["queries"]["detail"]["succeeded"] == 1
    assert cache_bytes(config) == before
    assert cli("list")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_second_composed_history_failure_discards_the_entire_window(installed):
    cli, browser, config = installed
    rows = [row("1"), row("2")]
    browser.business_script.append(page(rows))
    cli("refresh", "--require-complete")
    before = cache_bytes(config)
    browser.business_script.extend(
        [
            page(rows),
            detail("1"),
            history(),
            detail("2"),
            {"status": 200, "body": {"success": False}},
        ]
    )
    got = cli("list", "--live", "--with-detail", "--limit", "0", code=1)
    assert got["data"] is None
    assert got["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert cache_bytes(config) == before


def test_retired_history_leaf_is_not_discovered(installed, run_cli):
    _, _, _ = installed
    status, output, _ = run_cli(
        ["liquidity", "list", "investment.products.history", "--help"]
    )
    assert status == 2
    assert parse(output)["error"]["code"] == "INVALID_ARGUMENT"


def test_composed_get_shares_request_budget_across_selected_rows(
    installed, run_cli, tmp_path
):
    cli, browser, _ = installed
    source = tmp_path / "bounded-products"
    shutil.copytree(SOURCE, source)
    manifest_file = source / "leaf.json"
    manifest = json.loads(manifest_file.read_text())
    manifest["operations"]["get"]["max_requests"] = 3
    manifest_file.write_text(json.dumps(manifest))
    status, output, error = run_cli(["plugins", "uninstall", "liquidity." + LEAF])
    assert status == 0, output + error
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 0, output + error
    browser.business_script.extend(
        [
            page([row("1"), row("2")]),
            detail("1"),
            history(),
            detail("2"),
            history(),
        ]
    )
    got = cli("list", "--live", "--with-detail", "--limit", "0", code=1)
    assert got["data"] is None
    assert got["error"]["code"] == "TIMEOUT"
    assert got["meta"]["query_evidence"]["request_count"] == 3
    assert len(browser.business_requests) == 4  # List plus three Get inquiries.


def test_history_request_extra_field_is_rejected_before_transport(
    installed, run_cli, tmp_path
):
    cli, browser, _ = installed
    source = tmp_path / "unapproved-history-request"
    shutil.copytree(SOURCE, source)
    adapter_file = source / "adapter.py"
    adapter_file.write_text(
        adapter_file.read_text().replace(
            "return context", 'return {**context, "extra": "unapproved"}'
        )
    )
    status, output, error = run_cli(["plugins", "uninstall", "liquidity." + LEAF])
    assert status == 0, output + error
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 0, output + error
    browser.business_script.append(detail())
    got = cli("get", "PHYSICAL-1", code=1)
    assert got["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize("tenant", [None, "", " ", "GUAPW3SG"])
def test_history_retains_native_optional_tenant_values(installed, tenant):
    cli, browser, _ = installed
    versions = [row("OLD", tntInstId=tenant)]
    browser.business_script.extend([detail(), history(versions)])
    assert cli("get", "PHYSICAL-1")["data"]["history"] == versions
