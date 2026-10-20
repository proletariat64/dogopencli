"""B19 custom three-source directory through installation and the public CLI."""

import json
from copy import deepcopy
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
LEAF = "cash.accounts"


@pytest.fixture
def installed(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for name in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(name, raising=False)
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    try:
        cli("domain", "enable", "liquidity")
        package = ROOT / "leaf_packages/liquidity" / LEAF
        if getattr(request, "param", "directory") == "zip":
            target = tmp_path / "candidate.zip"
            with ZipFile(target, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(package))
            package = target
        cli("plugins", "install", str(package))
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def account(alias, currency="USD", **fields):
    return {
        "aliasName": alias,
        "currency": currency,
        "bankId": "BANK",
        "instId": "ENTITY",
        **fields,
    }


def response(rows, *, source="baseline", total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": len(rows) if total is None else total,
            "result": {
                "success": True,
                "bankAccountPropertyVOList" if source == "cash" else "data": rows,
            },
        },
    }


def scripted(
    browser,
    cash,
    baseline,
    details=None,
    *,
    refusal=None,
    failure=None,
    failures=None,
    baseline_total=None,
):
    details = details or {
        row["aliasName"]: {
            **row,
            "nested": {
                "unknown": [None, "", False, 0, Decimal("1.234567890123456789")]
            },
        }
        for row in baseline
    }

    def handler(body, _):
        if "bankAccountQueryVO" in body:
            vo = json.loads(body["bankAccountQueryVO"])
            assert set(body) == {"tntInstId", "wallet", "bankAccountQueryVO"}
            assert body["wallet"] is False
            assert body["tntInstId"] == vo["tntInstId"] == "GUAPW3SG"
            assert set(vo) == {"tntInstId", "rowStart", "pageSize"}
            rows = [
                row
                for row in cash[vo["rowStart"] : vo["rowStart"] + vo["pageSize"]]
                if row is not None
            ]
            return response(rows, source="cash", total=999999)
        if "bankAccountBaseLineQuery" in body:
            vo = json.loads(body["bankAccountBaseLineQuery"])
            assert set(body) == {"tntInstId", "bankAccountBaseLineQuery"}
            assert body["tntInstId"] == vo["tntInstId"] == "GUAPW3SG"
            assert set(vo) == {"tntInstId", "rowStart", "pageSize"}
            assert vo["pageSize"] == 1000
            rows = baseline[vo["rowStart"] : vo["rowStart"] + vo["pageSize"]]
            return response(
                rows, total=len(baseline) if baseline_total is None else baseline_total
            )
        assert set(body) == {"tntInstId", "aliasName"}
        assert body["tntInstId"] == "GUAPW3SG"
        if failures and body["aliasName"] in failures:
            return failures[body["aliasName"]]
        if failure:
            return failure
        if body["aliasName"] == refusal:
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "result": {
                        "success": False,
                        "errorCode": "099",
                        "message": "PRIVATE",
                    },
                },
            }
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "result": {"success": True, "data": details[body["aliasName"]]},
            },
        }

    browser.business_handler = handler
    return details


def coverage(result):
    return next(
        item
        for item in result["meta"]["acquisition"]["attempts"]
        if item.get("kind") == "unified_cash_accounts"
    )


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_three_native_sources_live_refresh_offline_and_local_filters(installed):
    cli, browser, _ = installed
    cash = [
        account(
            "A",
            status="CASH",
            accountType="cash",
            gmtModified="cash-time",
            operator="cash-op",
            cashOnly={"a": [False, None]},
        ),
        account("B", "EUR"),
    ]
    baseline = [
        account(
            "A",
            status="NORMAL",
            accountType="baseline",
            gmtModified="baseline-time",
            operator="baseline-op",
        ),
        account("B", "EUR"),
    ]
    details = scripted(browser, cash, baseline)
    assert cli("liquidity", "list", LEAF, code=1)["error"]["code"] == "CACHE_MISS"
    assert browser.business_requests == []
    live = cli(
        "liquidity", "list", LEAF, "--live", "--limit", "0", "--require-complete"
    )
    assert live["meta"]["complete"] is True
    assert live["meta"]["reported_total"] is None
    assert live["meta"]["collected_total"] == 2
    row = live["data"][0]
    assert row["status"] == "NORMAL" and row["accountType"] == "baseline"
    assert row["gmtModified"] == "cash-time" and row["operator"] == "cash-op"
    assert row["source_metadata"]["raw"] == {
        "cash": cash[0],
        "baseline": baseline[0],
        "detail": details["A"],
    }
    assert row["nested"] == details["A"]["nested"]
    assert row["source_metadata"]["conflicts"]["status"]["cash"] == "CASH"
    assert row["source_metadata"]["provenance"]["status"] == "baseline"
    assert all(record["detail_state"] == "succeeded" for record in live["data"])
    evidence = coverage(live)
    assert evidence["sources"]["cash"]["reported_total"] is None
    assert evidence["sources"]["baseline"]["reported_total"] == 2
    assert evidence["detail_coverage"] == {
        "complete": True,
        "required": 2,
        "attempted": 2,
        "succeeded": 2,
        "refused": 0,
        "failed": 0,
    }
    assert cli("liquidity", "list", LEAF, code=1)["error"]["code"] == "CACHE_MISS"
    refreshed = cli(
        "liquidity",
        "refresh",
        LEAF,
        "--currency",
        "EUR",
        "--require-complete",
        "--limit",
        "0",
    )
    count = len(browser.business_requests)
    offline = cli("liquidity", "list", LEAF, "--limit", "0")
    assert len(browser.business_requests) == count
    assert offline["data"] == live["data"]
    assert coverage(offline) == coverage(refreshed)
    assert offline["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert (
        cli("liquidity", "list", LEAF, "--currency", "EUR")["data"] == live["data"][1:]
    )
    assert (
        cli("liquidity", "list", LEAF, "--account-alias", "A")["data"]
        == live["data"][:1]
    )
    assert cli("liquidity", "list", LEAF, "--status", "CASH")["data"] == []
    assert cli("liquidity", "get", LEAF, "A", code=2)["error"]


def test_dependent_detail_covers_full_baseline_before_window_and_filter(installed):
    cli, browser, _ = installed
    rows = [account(str(i)) for i in range(1001)]
    scripted(browser, rows, rows)
    result = cli(
        "liquidity",
        "list",
        LEAF,
        "--live",
        "--limit",
        "1",
        "--account-alias",
        "1000",
        "--require-complete",
    )
    assert result["data"][0]["aliasName"] == "1000"
    assert result["meta"]["collected_total"] == 1001
    assert [
        body["aliasName"] for body in browser.business_requests if "aliasName" in body
    ] == [str(i) for i in range(1001)]
    assert [
        json.loads(body["bankAccountBaseLineQuery"])["rowStart"]
        for body in browser.business_requests
        if "bankAccountBaseLineQuery" in body
    ] == [0, 1000]


def test_cash_hole_evidence_is_owned_by_sdk_and_retained_offline(installed):
    cli, browser, _ = installed
    rows = [account("A"), account("B")]
    scripted(browser, [rows[0], None, rows[1]], rows)
    cli("liquidity", "refresh", LEAF, "--require-complete")
    offline = cli("liquidity", "list", LEAF, "--limit", "0", "--require-complete")
    assert [row["aliasName"] for row in offline["data"]] == ["A", "B"]
    cash = coverage(offline)["sources"]["cash"]
    assert cash["reported_total"] is None
    assert cash["coverage_basis"] == "qualified_short_page"
    assert cash["attempts"][-1]["hole_count"] == 1
    assert "PAGINATION_HOLES_BYPASSED" in offline["meta"]["acquisition"]["reasons"]


def test_cash_only_rows_preserve_missing_detail_and_baseline_classification(installed):
    cli, browser, _ = installed
    rows = [account("A"), account("B", status="CASH", accountType="cash")]
    scripted(browser, rows, rows[:1])
    result = cli("liquidity", "list", LEAF, "--live", "--limit", "0")
    cash_only = result["data"][1]
    assert cash_only["detail_state"] == "missing"
    assert cash_only["source_metadata"]["raw"] == {"cash": rows[1]}
    assert "status" not in cash_only and "accountType" not in cash_only
    assert coverage(result)["list_coverage"]["cash_only"] == 1
    assert result["meta"]["complete"] is False


def test_conflicts_preserve_legacy_owner_comparison_and_all_raw_values(installed):
    cli, browser, _ = installed
    cash = [account("A", x="cash", y="same")]
    baseline = [account("A", x="baseline", y="same")]
    details = {"A": account("A", x="baseline", y="detail")}
    scripted(browser, cash, baseline, details)
    result = cli("liquidity", "list", LEAF, "--live", "--require-complete")
    row = result["data"][0]
    assert row["x"] == "baseline" and row["y"] == "same"
    assert row["source_metadata"]["conflicts"] == {
        "x": {"cash": "cash", "baseline": "baseline"},
        "y": {"baseline": "same", "detail": "detail"},
    }
    assert row["source_metadata"]["raw"]["detail"] == details["A"]


@pytest.mark.parametrize("failure", ["refusal", "mismatch", "baseline_short"])
def test_incomplete_live_strict_and_refresh_preserve_complete_cache(installed, failure):
    cli, browser, _ = installed
    rows = [account("A"), account("B")]
    scripted(browser, rows, rows)
    cli("liquidity", "refresh", LEAF, "--require-complete", "--limit", "0")
    saved = cli("liquidity", "list", LEAF, "--limit", "0")
    if failure == "refusal":
        scripted(browser, rows, rows, refusal="B")
    elif failure == "mismatch":
        scripted(browser, rows[:1], rows)
    else:
        scripted(browser, rows, rows, baseline_total=3)
    live = cli("liquidity", "list", LEAF, "--live", "--limit", "0")
    assert live["meta"]["complete"] is False
    if failure == "refusal":
        assert live["data"][1]["detail_state"] == "refused"
        assert live["data"][1]["source_metadata"]["detail_error"] == {
            "code": "BUSINESS_QUERY_FAILED",
            "message": "backend refused account detail",
            "native_code": "099",
        }
        assert "PRIVATE" not in str(live)
    if failure == "mismatch":
        assert coverage(live)["list_coverage"]["baseline_only"] == 1
    assert (
        cli("liquidity", "list", LEAF, "--live", "--require-complete", code=1)["error"][
            "code"
        ]
        == "INCOMPLETE_RESULT"
    )
    rejected = cli("liquidity", "refresh", LEAF, code=1)
    assert rejected["meta"]["published"] is False
    offline = cli("liquidity", "list", LEAF, "--limit", "0")
    assert offline["data"] == saved["data"]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def failed_detail(native_code="999"):
    return {
        "status": 200,
        "body": {
            "resultFlag": False,
            "result": {
                "success": False,
                "data": None,
                "errorCode": native_code,
                "errorMessage": "PRIVATE backend explanation",
                "errorContext": {"private": "PRIVATE"},
            },
        },
    }


@pytest.mark.parametrize("native_code", ["999", 999])
@pytest.mark.parametrize("with_refusal", [False, True])
def test_failed_detail_continues_all_accounts_and_preserves_complete_cache(
    installed, native_code, with_refusal
):
    cli, browser, _ = installed
    aliases = [
        "SYNTHETIC-FIRST",
        "SYNTHETIC-FAILED",
        "SYNTHETIC-REFUSAL",
        "SYNTHETIC-LAST",
    ]
    rows = [account(alias) for alias in aliases]
    scripted(browser, rows, rows)
    cli("liquidity", "refresh", LEAF, "--require-complete")
    saved = cli("liquidity", "list", LEAF, "--limit", "0")
    scripted(
        browser,
        rows,
        rows,
        failures={aliases[1]: failed_detail(native_code)},
        refusal=aliases[2] if with_refusal else None,
    )
    start = len(browser.business_requests)
    live = cli("liquidity", "list", LEAF, "--live", "--limit", "0")
    assert [
        body["aliasName"]
        for body in browser.business_requests[start:]
        if "aliasName" in body
    ] == aliases
    assert [row["detail_state"] for row in live["data"]] == [
        "succeeded",
        "failed",
        "refused" if with_refusal else "succeeded",
        "succeeded",
    ]
    assert live["error"] is None and live["meta"]["complete"] is False
    assert live["meta"]["dataset_complete"] is False
    assert live["meta"]["warnings"][0]["code"] == "INCOMPLETE_RESULT"
    assert "DETAIL_COVERAGE_INCOMPLETE" in live["meta"]["acquisition"]["reasons"]
    failed = live["data"][1]["source_metadata"]
    assert failed["raw"] == {"cash": rows[1], "baseline": rows[1]}
    assert failed["presence"]["detail"] is False
    assert failed["detail_error"] == {
        "code": "BUSINESS_QUERY_FAILED",
        "message": "backend failed account detail",
        "native_code": native_code,
    }
    assert "PRIVATE" not in str(live)
    expected_coverage = {
        "complete": False,
        "required": 4,
        "attempted": 4,
        "succeeded": 2 if with_refusal else 3,
        "refused": int(with_refusal),
        "failed": 1,
    }
    assert coverage(live)["detail_coverage"] == expected_coverage
    trace = next(
        item
        for item in live["meta"]["acquisition"]["attempts"]
        if item.get("kind") == "custom_query"
    )["queries"]["detail"]
    assert trace["calls"] == 4 and trace["requests"] == 4
    assert trace["succeeded"] == expected_coverage["succeeded"]
    assert trace["failed"] == 1
    assert trace.get("refused", 0) == int(with_refusal)
    for operation, flags in (
        ("list", ("--live", "--require-complete")),
        ("refresh", ()),
    ):
        start = len(browser.business_requests)
        rejected = cli("liquidity", operation, LEAF, *flags, code=1)
        assert rejected["error"]["code"] == "INCOMPLETE_RESULT"
        assert [
            body["aliasName"]
            for body in browser.business_requests[start:]
            if "aliasName" in body
        ] == aliases
        if operation == "refresh":
            assert rejected["meta"]["published"] is False
    offline = cli("liquidity", "list", LEAF, "--limit", "0")
    assert offline["data"] == saved["data"]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "change",
    [
        "other_code",
        "bool_code",
        "decimal_code",
        "missing_code",
        "top_level_code",
        "missing_data",
        "nonnull_data",
        "missing_success",
        "string_success",
        "missing_result",
        "array_result",
        "string_outer",
        "auth",
    ],
)
def test_unqualified_outer_failure_shape_remains_hard_and_stops_details(
    installed, change
):
    cli, browser, _ = installed
    rows = [account("SYNTHETIC-REJECTED"), account("SYNTHETIC-UNREACHED")]
    failure = failed_detail()
    document = failure["body"]
    node = document["result"]
    expected = "BUSINESS_QUERY_FAILED"
    if change == "other_code":
        node["errorCode"] = "998"
    elif change == "bool_code":
        node["errorCode"] = True
    elif change == "decimal_code":
        node["errorCode"] = Decimal("999.0")
    elif change == "missing_code":
        del node["errorCode"]
    elif change == "top_level_code":
        document["errorCode"] = node.pop("errorCode")
    elif change == "missing_data":
        del node["data"]
    elif change == "nonnull_data":
        node["data"] = {}
    elif change == "missing_success":
        del node["success"]
    elif change == "string_success":
        node["success"] = "false"
    elif change == "missing_result":
        del document["result"]
    elif change == "array_result":
        document["result"] = []
    elif change == "string_outer":
        document["resultFlag"] = "false"
        expected = "INVALID_RESPONSE"
    else:
        failure["status"] = 403
        expected = "AUTH_REQUIRED"
    scripted(browser, rows, rows, failure=failure)
    result = cli("liquidity", "list", LEAF, "--live", code=1)
    assert result["error"]["code"] == expected
    assert result.get("data") in (None, [])
    assert "PRIVATE" not in str(result)
    assert [
        body["aliasName"] for body in browser.business_requests if "aliasName" in body
    ] == [rows[0]["aliasName"]]


@pytest.mark.parametrize("field", ["aliasName", "currency", "bankId", "instId"])
def test_detail_identity_disagreement_fails_operation(installed, field):
    cli, browser, _ = installed
    rows = [account("A")]
    scripted(browser, rows, rows, {"A": {**rows[0], field: "OTHER"}})
    result = cli("liquidity", "list", LEAF, "--live", code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result.get("data") in (None, [])


@pytest.mark.parametrize(
    "failure,code",
    [
        ({"status": 403, "body": {}}, "AUTH_REQUIRED"),
        (
            {
                "status": 200,
                "body": {"resultFlag": False, "result": {"success": False}},
            },
            "BUSINESS_QUERY_FAILED",
        ),
        (
            {
                "status": 200,
                "body": {"resultFlag": True, "result": {"success": "false"}},
            },
            "INVALID_RESPONSE",
        ),
        (
            {
                "status": 200,
                "body": {"resultFlag": True, "result": {"success": True, "data": []}},
            },
            "INVALID_RESPONSE",
        ),
    ],
)
def test_non_refusal_detail_failures_abort_and_preserve_cache(installed, failure, code):
    cli, browser, _ = installed
    rows = [account("A")]
    scripted(browser, rows, rows)
    cli("liquidity", "refresh", LEAF, "--require-complete")
    saved = cli("liquidity", "list", LEAF)
    scripted(browser, rows, rows, failure=failure)
    assert cli("liquidity", "refresh", LEAF, code=1)["error"]["code"] == code
    offline = cli("liquidity", "list", LEAF)
    assert offline["data"] == saved["data"]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_ambiguous_baseline_alias_aborts_before_detail(installed):
    cli, browser, _ = installed
    rows = [account("A"), account("A", "EUR")]
    scripted(browser, rows, rows)
    result = cli("liquidity", "list", LEAF, "--live", code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert not any("aliasName" in body for body in browser.business_requests)


@pytest.mark.parametrize("source", ["cash", "baseline", "detail"])
@pytest.mark.parametrize("change", ["endpoint", "method", "tenant", "extra", "scope"])
def test_custom_inquiries_keep_default_deny_transport(installed, source, change):
    _, _, config = installed
    adapter = Registry(config / "config.toml").scan().get("liquidity", LEAF).adapter
    capability = adapter.query_capability("list", source, {})
    body = (
        capability.request_body({}, "A")
        if source == "detail"
        else capability.page_body("", 0, 1000)
    )
    contract = capability.contract
    request = QueryRequest(
        capability.name, contract.method, contract.host, contract.path, deepcopy(body)
    )
    validate_request(request, contract)
    body = request.body
    if change == "endpoint":
        request = replace(request, path="/mutation.json")
    elif change == "method":
        request = replace(request, method="POST")
    elif change == "tenant":
        body["tntInstId"] = "OTHER"
    elif change == "extra":
        body["action"] = "edit"
    elif source == "detail":
        body["pageSize"] = 1000
    elif source == "cash":
        body["wallet"] = True
    else:
        vo = json.loads(body["bankAccountBaseLineQuery"])
        vo["tntInstId"] = "OTHER"
        body["bankAccountBaseLineQuery"] = json.dumps(vo)
    with pytest.raises(CliError) as error:
        validate_request(request, contract)
    assert error.value.code == "REQUEST_NOT_ALLOWED"
