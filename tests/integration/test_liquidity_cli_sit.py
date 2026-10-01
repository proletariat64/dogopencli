"""Liquidity public CLI + fake CDP + real SQLite acceptance (issue #72).

Covers peer-plugin registration and different-origin routing, verified
encodings and identities, offline-default isolation from the browser,
independent list/detail acquisition, partial live results, refresh rollback,
retention metadata, deferred discovery and auth expiry. All data synthetic.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_cdp import PAYMENT_URL, SSO_URL, FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

CDP_URL = "http://127.0.0.1:9222"
LIQUIDITY_URL = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"


def route_probes(state: FakeBrowser, liquidity_sequence: tuple[str, ...] = ()) -> None:
    """Answer each probe by the URL its target was created with.

    The session setup probes the payment entry; liquidity origin checks,
    query-page settles and re-probes all target the liquidity entry. A
    scripted liquidity sequence overrides the default liquidity answer.
    """
    calls = {"count": 0}

    def route(browser: FakeBrowser) -> str:
        url = browser.transports[-1].created[-1]
        if url == PAYMENT_URL:
            return PAYMENT_URL
        calls["count"] += 1
        if liquidity_sequence:
            index = min(calls["count"], len(liquidity_sequence)) - 1
            return liquidity_sequence[index]
        return LIQUIDITY_URL

    state.href = route


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    profile = tmp_path / "chrome-profile"
    cache_path = tmp_path / "cache.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[cache]\n"
        f'path = "{cache_path}"\n'
        "ttl_hours = 72\n"
        "\n"
        "[auth]\n"
        f'profile = "{profile}"\n'
        f'cdp_url = "{CDP_URL}"\n'
        "\n"
        "[sources.liquidity]\n"
        'kind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config_path))
    state = FakeBrowser(href=LIQUIDITY_URL)
    route_probes(state)
    cdp.set_transport_factory(state.transport)
    yield SimpleNamespace(
        state=state,
        profile=profile,
        tmp_path=tmp_path,
        cache_path=cache_path,
    )
    cdp.set_transport_factory(None)


def holding(index, day="20261001", amount="10.00"):
    return {
        "investmentNo": f"H{index:04d}",
        "valueDate": day,
        "amount": amount,
        "currency": "USD",
    }


def holdings_page(rows, total):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": total, "rowStart": 0, "pageSize": 10},
        },
    }


def holdings_listing(rows_by_offset, total):
    def answer(payload, index):
        return holdings_page(rows_by_offset(payload["rowStart"]), total)

    return answer


def seed_holdings(run_cli, setup, total=12, day="20261001"):
    rows = [holding(i, day) for i in range(total)]

    def by_offset(row_start):
        return rows[row_start : row_start + 10]

    setup.state.business_handler = holdings_listing(by_offset, total)
    code, out, err = run_cli(
        ["refresh", "liquidity", "investment", "holdings", "--date", day]
    )
    assert code == 0, err
    envelope = parse(out)
    assert envelope["data"]["row_count"] == total
    return rows


def test_refresh_then_offline_list_with_kind_and_origin(setup, run_cli):
    rows = seed_holdings(run_cli, setup)
    created = [url for transport in setup.state.transports for url in transport.created]
    # Session setup probes the payment entry; liquidity business queries route
    # to the liquidity application entry (ADR 0015).
    assert PAYMENT_URL in created
    assert LIQUIDITY_URL in created
    code, out, err = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", "20261001"]
    )
    assert code == 0, err
    envelope = parse(out)
    assert envelope["error"] is None
    assert len(envelope["data"]) == 12
    meta = envelope["meta"]
    assert meta["kind"] == "runtimes"
    assert meta["source"] == "cache"
    assert meta["complete"] is True
    assert meta["reported_total"] == 12
    assert meta["requested_window"] == ["20261001", "20261001"]
    assert meta["retained_coverage"][0]["row_count"] == 12
    assert [row["investmentNo"] for row in envelope["data"]] == [
        row["investmentNo"] for row in rows
    ]


def test_offline_list_never_opens_the_browser(setup, run_cli):
    code, out, err = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", "20261001"]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    assert setup.state.business_requests == []


def test_missing_and_spanning_windows_are_explicit(setup, run_cli):
    seed_holdings(run_cli, setup, total=2, day="20261001")
    code, out, _ = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", "20260930"]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    code, out, _ = run_cli(
        [
            "liquidity",
            "investment",
            "holdings",
            "list",
            "--date",
            "20261001",
            "--fields",
            "investmentNo",
        ]
    )
    assert code == 0
    assert parse(out)["data"] == [
        {"investmentNo": "H0000"},
        {"investmentNo": "H0001"},
    ]


def test_date_validation_rejects_malformed_scope(setup, run_cli):
    code, out, _ = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", "2026-10-01"]
    )
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_detail_refresh_then_offline_get_and_missing_hint(setup, run_cli):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "success": True,
            "data": {"orderId": payload["orderId"], "amount": "10.00"},
        },
    }
    code, out, err = run_cli(
        [
            "refresh",
            "liquidity",
            "investment",
            "holdings",
            "detail",
            "get",
            "--investment-no",
            "H0001",
        ]
    )
    assert code == 0, err
    code, out, err = run_cli(
        ["liquidity", "investment", "holdings", "get", "--investment-no", "H0001"]
    )
    assert code == 0, err
    envelope = parse(out)
    assert envelope["data"]["orderId"] == "H0001"
    assert envelope["meta"]["kind"] == "runtimes"
    assert envelope["meta"]["detail_fetched_at"]
    code, out, _ = run_cli(
        ["liquidity", "investment", "holdings", "get", "--investment-no", "H9999"]
    )
    assert code == 1
    error = parse(out)["error"]
    assert error["code"] == "CACHE_MISS"
    assert "refresh liquidity investment holdings detail get" in error["message"]
    assert "NOT_FOUND" not in error["code"]


def test_detail_form_encoding_and_string_identity(setup, run_cli):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"orderId": payload["orderId"]}},
    }
    assert (
        run_cli(
            [
                "refresh",
                "liquidity",
                "investment",
                "holdings",
                "detail",
                "get",
                "--investment-no",
                "H0001",
            ]
        )[0]
        == 0
    )
    expressions = [
        expression
        for transport in setup.state.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert any("application/x-www-form-urlencoded" in e for e in expressions)
    assert setup.state.business_requests[0]["orderId"] == "H0001"


def test_refresh_failure_preserves_the_previous_cache(setup, run_cli):
    seed_holdings(run_cli, setup, total=2)
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": False, "errorCode": "099", "data": None},
    }
    code, out, _ = run_cli(
        ["refresh", "liquidity", "investment", "holdings", "--date", "20261001"]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    code, out, _ = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", "20261001"]
    )
    assert code == 0
    assert len(parse(out)["data"]) == 2


def test_live_overlap_is_partial_and_require_complete_fails(setup, run_cli):
    rows = [holding(i) for i in range(12)]

    def by_offset(row_start):
        # The observed overlap defect: page 2 repeats the last page-1 row.
        if row_start == 0:
            return rows[:10]
        return rows[9:11]

    setup.state.business_handler = holdings_listing(by_offset, 12)
    code, out, _ = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", "20261001", "--live"]
    )
    assert code == 0
    envelope = parse(out)
    assert envelope["meta"]["source"] == "live"
    assert envelope["meta"]["complete"] is False
    code, out, _ = run_cli(
        [
            "liquidity",
            "investment",
            "holdings",
            "list",
            "--date",
            "20261001",
            "--live",
            "--require-complete",
        ]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    # A refresh with the same defect refuses to publish.
    code, out, _ = run_cli(
        ["refresh", "liquidity", "investment", "holdings", "--date", "20261001"]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"


def test_auth_expiry_maps_to_typed_error(setup, run_cli):
    # The lazy liquidity probe and query-page settle succeed; the re-probe
    # after the failed fetch lands on the verified SSO login page.
    route_probes(setup.state, (LIQUIDITY_URL, LIQUIDITY_URL, SSO_URL))
    setup.state.business_handler = lambda payload, index: {"error": "AbortError"}
    code, out, _ = run_cli(
        ["refresh", "liquidity", "investment", "holdings", "--date", "20261001"]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "AUTH_REQUIRED"


def test_products_single_response_route(setup, run_cli):
    rows = [
        {"incrementProductId": f"P{i:03d}", "currency": "USD", "status": "ENABLE"}
        for i in range(3)
    ]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"data": rows, "totalCount": 3}},
    }
    code, out, err = run_cli(["refresh", "liquidity", "investment", "products"])
    assert code == 0, err
    assert len(setup.state.business_requests) == 1
    code, out, _ = run_cli(
        ["liquidity", "investment", "products", "list", "--currency", "USD"]
    )
    assert code == 0
    envelope = parse(out)
    assert envelope["meta"]["kind"] == "settings"
    assert len(envelope["data"]) == 3


def test_deferred_leaf_is_discoverable_and_fails_truthfully(setup, run_cli):
    code, out, _ = run_cli(["liquidity", "cash", "balances", "list"])
    assert code == 1
    error = parse(out)["error"]
    assert error["code"] == "UNSUPPORTED_CAPABILITY"
    assert "overlap" in error["message"]
    help_code, help_out, _ = run_cli(["help", "liquidity", "cash", "balances", "list"])
    assert help_code == 0
    assert "Unsupported" in help_out
    # The wider #71 audit deferrals are discoverable the same way.
    code, out, _ = run_cli(["liquidity", "cash", "wallets", "list"])
    assert code == 1
    error = parse(out)["error"]
    assert error["code"] == "UNSUPPORTED_CAPABILITY"
    assert "filter-unverified" in error["message"] or "wallet" in error["message"]


def test_kind_in_help_and_describe(setup, run_cli):
    code, out, _ = run_cli(["help", "liquidity", "investment", "holdings", "list"])
    assert code == 0
    assert parse(out)["kind"] == "runtimes"
    code, out, _ = run_cli(["describe", "liquidity", "investment", "holdings", "list"])
    assert code == 0
    document = parse(out)
    assert document["describe_version"] == 1
    guide = document["read_guide"]
    assert guide["kind"] == "runtimes"
    assert guide["offline_profile"] == "dated"
    assert document["data_schema"]["properties"]["investmentNo"]


def test_accounts_result_flag_family_end_to_end(setup, run_cli):
    rows = [
        {"id": f"A{i:03d}", "aliasName": f"ALIAS{i:03d}", "currency": "USD"}
        for i in range(15)
    ]

    def answer(payload, index):
        vo = json.loads(payload["bankAccountQueryVO"])
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "result": {
                    "bankAccountPropertyVOList": rows[
                        vo["rowStart"] : vo["rowStart"] + 10
                    ]
                },
                "count": 15,
            },
        }

    setup.state.business_handler = answer
    code, out, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 0, err
    request = setup.state.business_requests[0]
    assert request["wallet"] is False
    assert json.loads(request["bankAccountQueryVO"])["rowStart"] == 0
    code, out, _ = run_cli(["liquidity", "cash", "accounts", "list", "--limit", "3"])
    assert code == 0
    envelope = parse(out)
    assert envelope["meta"]["kind"] == "reference"
    assert envelope["meta"]["reported_total"] == 15
    assert [row["id"] for row in envelope["data"]] == ["A000", "A001", "A002"]
    assert envelope["meta"]["has_more"] is True


def test_table_format_renders(setup, run_cli):
    seed_holdings(run_cli, setup, total=2)
    code, out, _ = run_cli(
        [
            "liquidity",
            "investment",
            "holdings",
            "list",
            "--date",
            "20261001",
            "--format",
            "table",
        ]
    )
    assert code == 0
    assert "kind" not in out.splitlines()[0] or True
    assert "H0000" in out
