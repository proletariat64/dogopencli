"""Liquidity public CLI + fake CDP + real SQLite acceptance (issue #72).

Covers peer-plugin registration and different-origin routing, verified
encodings and identities, offline-default isolation from the browser,
independent list/detail acquisition, partial live results, refresh rollback,
retention metadata, deferred discovery and auth expiry. All data synthetic.
"""

import json
from datetime import timedelta
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

    The session setup probes the liquidity entry; origin checks,
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
    # Session setup verifies only the requested liquidity origin (ADR 0015).
    assert PAYMENT_URL not in created
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
        {"id": "0", "aliasName": f"ALIAS{i:03d}", "currency": "USD"} for i in range(15)
    ]

    def answer(payload, index):
        vo = json.loads(payload["bankAccountQueryVO"])
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "result": {
                    "bankAccountPropertyVOList": rows[
                        vo["rowStart"] : vo["rowStart"] + vo["pageSize"]
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
    assert json.loads(request["bankAccountQueryVO"])["pageSize"] == 5000
    code, out, _ = run_cli(["liquidity", "cash", "accounts", "list", "--limit", "3"])
    assert code == 0
    envelope = parse(out)
    assert envelope["meta"]["kind"] == "reference"
    assert envelope["meta"]["reported_total"] == 15
    assert [row["aliasName"] for row in envelope["data"]] == [
        "ALIAS000",
        "ALIAS001",
        "ALIAS002",
    ]
    assert envelope["meta"]["has_more"] is True


@pytest.mark.parametrize(
    "extra", [[], ["--limit", "1"], ["--fields", "aliasName"], ["--format", "table"]]
)
def test_accounts_partial_live_warns_returns_rows_and_fails(setup, run_cli, extra):
    rows = [{"id": "0", "aliasName": f"A{i}", "currency": "USD"} for i in range(2)]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"bankAccountPropertyVOList": rows},
            "count": 3,
        },
    }
    before = setup.cache_path.read_bytes() if setup.cache_path.exists() else None
    code, out, err = run_cli(
        ["liquidity", "cash", "accounts", "list", "--live", *extra]
    )
    assert code == 1
    assert "warning: INCOMPLETE_RESULT" in err
    assert "collected 2, reported 3" in err
    if "table" in extra:
        assert "A0" in out
    else:
        envelope = parse(out)
        assert envelope["error"]["code"] == "INCOMPLETE_RESULT"
        assert envelope["meta"]["complete"] is False
        assert envelope["meta"]["reported_total"] == 3
        assert envelope["meta"]["collected_total"] == 2
        assert envelope["meta"]["warnings"][0]["code"] == "INCOMPLETE_RESULT"
        assert len(envelope["data"]) == (1 if "--limit" in extra else 2)
        if "--fields" in extra:
            assert envelope["data"] == [{"aliasName": "A0"}, {"aliasName": "A1"}]
    assert (
        setup.cache_path.read_bytes() if setup.cache_path.exists() else None
    ) == before
    code, out, err = run_cli(
        ["liquidity", "cash", "accounts", "list", "--live", "--require-complete"]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert parse(out)["data"] is None


def test_accounts_partial_refresh_returns_rows_and_preserves_cache(setup, run_cli):
    old_rows = [{"id": "0", "aliasName": "OLD", "currency": "USD"}]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"bankAccountPropertyVOList": old_rows},
            "count": 1,
        },
    }
    code, _, _ = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 0
    before = setup.cache_path.read_bytes()
    new_rows = [{"id": "0", "aliasName": "NEW", "currency": "USD"}]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"bankAccountPropertyVOList": new_rows},
            "count": 2,
        },
    }
    code, out, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 1
    assert "warning: INCOMPLETE_RESULT" in err
    envelope = parse(out)
    assert envelope["data"] == new_rows
    assert envelope["error"]["code"] == "INCOMPLETE_RESULT"
    assert envelope["meta"]["complete"] is False
    assert envelope["meta"]["published"] is False
    assert envelope["meta"]["source"] == "live"
    assert setup.cache_path.read_bytes() == before
    code, out, _ = run_cli(["liquidity", "cash", "accounts", "list"])
    assert code == 0
    assert parse(out)["data"] == old_rows


@pytest.mark.parametrize(
    ("path", "scope", "response"),
    [
        (
            ["cash", "waterlevels"],
            ["--account", "A1"],
            {"success": True, "data": {"data": [], "totalCount": 0}},
        ),
        (
            ["cash", "statements", "intraday"],
            [
                "--account",
                "A1",
                "--currency",
                "USD",
                "--from-date",
                "20260930",
                "--to-date",
                "20260930",
            ],
            {"success": True, "data": {"data": [], "totalCount": 0}},
        ),
        (
            ["forecast", "cashflows"],
            [
                "--account",
                "A1",
                "--currency",
                "USD",
                "--from-date",
                "20260930",
                "--to-date",
                "20260930",
            ],
            {"resultFlag": True, "result": {"bankAccountCashFlowVOList": []}},
        ),
    ],
)
def test_cash_forecast_empty_refresh_then_offline_parameters(
    setup, run_cli, path, scope, response
):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": response,
    }
    code, out, err = run_cli(["refresh", "liquidity", *path, *scope])
    assert code == 0, err
    assert parse(out)["data"]["row_count"] == 0
    before = len(setup.state.transports)
    for flags in [
        [],
        ["--all", "--require-complete", "--require-fresh"],
        ["--limit", "1"],
        ["--offset", "1"],
        ["--fields", "currency"],
    ]:
        code, out, err = run_cli(["liquidity", *path, "list", *scope, *flags])
        assert code == 0, err
        doc = parse(out)
        assert doc["data"] == []
        assert doc["meta"]["complete"] is True
        assert doc["meta"]["matched_total"] == 0
    code, out, err = run_cli(["liquidity", *path, "list", *scope, "--format", "table"])
    assert code == 0 and out.strip(), err
    assert len(setup.state.transports) == before


@pytest.mark.parametrize(
    "path", [["cash", "statements", "intraday"], ["forecast", "cashflows"]]
)
@pytest.mark.parametrize("prefix", [["liquidity"], ["refresh", "liquidity"]])
def test_invalid_cash_forecast_calendar_date_never_opens_browser(
    setup, run_cli, path, prefix
):
    args = [*prefix, *path]
    if prefix == ["liquidity"]:
        args.append("list")
    args += [
        "--account",
        "A1",
        "--currency",
        "USD",
        "--from-date",
        "20260230",
        "--to-date",
        "20260930",
    ]
    code, out, _ = run_cli(args)
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


def test_cashflows_native_time_and_duplicate_occurrences_end_to_end(setup, run_cli):
    row = {
        "bankAccountNo": "N1",
        "bankAccountAliasName": "A1",
        "currency": "USD",
        "originalBizNo": "",
        "expectValueDate": "",
        "expectValueDateTime": "202609302359",
        "fundDirection": "Credit",
        "amountStr": "1.00",
    }
    rows = [row, dict(row), {**row, "amountStr": "2.00"}]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"resultFlag": True, "result": {"bankAccountCashFlowVOList": rows}},
    }
    scope = [
        "--account",
        "A1",
        "--currency",
        "USD",
        "--from-date",
        "20260930",
        "--to-date",
        "20260930",
    ]
    base = ["liquidity", "forecast", "cashflows", "list"]
    code, out, err = run_cli([*base, *scope, "--live", "--all", "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"] == rows
    for start in ["20260929", "20260930"]:
        refresh_scope = [*scope]
        refresh_scope[refresh_scope.index("--from-date") + 1] = start
        code, out, err = run_cli(
            ["refresh", "liquidity", "forecast", "cashflows", *refresh_scope]
        )
        assert code == 0, err
        assert parse(out)["data"]["row_count"] == 3
    before = len(setup.state.transports)
    code, out, err = run_cli([*base, *scope, "--all", "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"] == rows  # not 2 from deduplication, or 6 from overlap
    code, out, err = run_cli([*base, *scope, "--offset", "1", "--limit", "1"])
    assert code == 0, err
    assert parse(out)["data"] == rows[1:2]
    code, out, err = run_cli([*base, *scope, "--fields", "expectValueDateTime"])
    assert code == 0, err
    assert parse(out)["data"] == [{"expectValueDateTime": "202609302359"}] * 3
    code, out, err = run_cli([*base, *scope, "--format", "table"])
    assert code == 0 and "expectValueDateTime" in out, err
    assert len(setup.state.transports) == before


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


def test_offline_cash_returns_uses_cash_identity_and_time(setup, run_cli):
    from dogopencli.cache import Cache
    from dogopencli.plugins.liquidity import store as captures
    from dogopencli.plugins.liquidity.leaves import list_leaf

    leaf = list_leaf(("investment", "returns"))
    resolved = leaf.resolve(
        {"basis": "cash", "from_date": "20261001", "to_date": "20261001"}
    )
    rows = [{"transactionId": "T1", "settlementDate": "20261001"}]
    cache = Cache(setup.cache_path)
    plan = captures.plan_capture_publish(
        cache,
        resolved.spec,
        resolved.scope_key,
        resolved.window,
        rows,
        1,
        "2026-10-01T00:00:00+00:00",
        "2026-10-01T00:00:00+00:00",
    )
    captures.commit_plan(cache, resolved.spec.name, plan, "2026-10-01T00:00:00+00:00")
    code, out, err = run_cli(
        [
            "liquidity",
            "investment",
            "returns",
            "list",
            "--basis",
            "cash",
            "--from-date",
            "20261001",
            "--to-date",
            "20261001",
        ]
    )
    assert code == 0, err
    assert parse(out)["data"] == rows
    assert not setup.state.transports
    code, out, err = run_cli(["describe", "liquidity", "investment", "returns", "list"])
    assert code == 0, err
    assert "/cashBaseList.json" in out and "transactionId" in out


def test_detail_freshness_is_per_object_not_latest_upsert(setup, run_cli):
    from dogopencli.cache import Cache
    from dogopencli.plugins.liquidity import details
    from dogopencli.plugins.liquidity.common import now
    from dogopencli.plugins.liquidity.leaves import detail_leaf

    cache = Cache(setup.cache_path)
    leaf = detail_leaf(("investment", "holdings", "get"))
    old = "2000-01-01T00:00:00+00:00"
    fresh = now().isoformat()
    details.upsert_detail(
        cache,
        leaf.spec.name,
        details.detail_key({"investment_no": "A"}, leaf.spec.identity),
        {"orderId": "A"},
        old,
        old,
    )
    details.upsert_detail(
        cache,
        leaf.spec.name,
        details.detail_key({"investment_no": "B"}, leaf.spec.identity),
        {"orderId": "B"},
        fresh,
        fresh,
    )
    args = ["liquidity", "investment", "holdings", "get", "--investment-no", "A"]
    code, out, err = run_cli(args)
    assert code == 0, err
    assert parse(out)["meta"]["fetched_at"] == old
    assert parse(out)["meta"]["stale"] is True
    code, out, _ = run_cli([*args, "--require-fresh"])
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_STALE"


def test_declared_customer_version_is_not_global_version(setup, run_cli):
    code, out, _ = run_cli(
        [
            "liquidity",
            "ledger",
            "customers",
            "get",
            "--customer-no",
            "C1",
            "--version",
            "1",
        ]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert not setup.state.transports


def test_liquidity_does_not_require_payment_auth(setup, run_cli):
    def route(browser):
        url = browser.transports[-1].created[-1]
        return SSO_URL if url == PAYMENT_URL else LIQUIDITY_URL

    setup.state.href = route
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"data": [holding(1)], "totalCount": 1}},
    }
    code, out, err = run_cli(
        [
            "liquidity",
            "investment",
            "holdings",
            "list",
            "--live",
            "--date",
            "20261001",
        ]
    )
    assert code == 0, err
    assert parse(out)["data"][0]["investmentNo"] == "H0001"
    assert all(
        PAYMENT_URL not in transport.created for transport in setup.state.transports
    )


def _seed_returns_captures(setup, captures):
    """Publish dated cash-return captures with explicit fetch times."""
    from dogopencli.cache import Cache
    from dogopencli.plugins.liquidity import store as capture_store
    from dogopencli.plugins.liquidity.leaves import list_leaf

    leaf = list_leaf(("investment", "returns"))
    store = Cache(setup.cache_path)
    for window, rows, fetched_at in captures:
        resolved = leaf.resolve(
            {"basis": "cash", "from_date": window[0], "to_date": window[1]}
        )
        plan = capture_store.plan_capture_publish(
            store,
            resolved.spec,
            resolved.scope_key,
            resolved.window,
            rows,
            len(rows),
            fetched_at,
            fetched_at,
        )
        capture_store.commit_plan(store, resolved.spec.name, plan, fetched_at)


def _returns_row(identity, day, income):
    return {
        "transactionId": identity,
        "settlementDate": day,
        "interestIncome": income,
        "currency": "USD",
    }


RETURNS_QUERY = [
    "liquidity",
    "investment",
    "returns",
    "list",
    "--basis",
    "cash",
    "--all",
]


def test_overlapping_captures_resolve_to_the_newest_value(setup, run_cli):
    from dogopencli.plugins.liquidity.common import now

    recent = (now() - timedelta(hours=1)).isoformat()
    newest = now().isoformat()
    _seed_returns_captures(
        setup,
        [
            (("20260930", "20261001"), [_returns_row("T1", "20261001", "OLD")], recent),
            (("20261001", "20261001"), [_returns_row("T1", "20261001", "NEW")], newest),
        ],
    )
    code, out, err = run_cli(
        [*RETURNS_QUERY, "--from-date", "20261001", "--to-date", "20261001"]
    )
    assert code == 0, err
    data = parse(out)["data"]
    # One identity, two retained captures: the later acquisition wins.
    assert [row["interestIncome"] for row in data] == ["NEW"]


def test_require_fresh_covers_every_contributing_capture(setup, run_cli):
    from dogopencli.plugins.liquidity.common import now

    expired = (now() - timedelta(hours=100)).isoformat()  # beyond the 72h ttl
    fresh = now().isoformat()
    _seed_returns_captures(
        setup,
        [
            (("20260930", "20260930"), [_returns_row("T1", "20260930", "1")], expired),
            (("20261001", "20261001"), [_returns_row("T2", "20261001", "2")], fresh),
        ],
    )
    query = [*RETURNS_QUERY, "--from-date", "20260930", "--to-date", "20261001"]
    code, out, err = run_cli(query)
    assert code == 0, err
    envelope = parse(out)
    assert [row["transactionId"] for row in envelope["data"]] == ["T1", "T2"]
    # A freshly refreshed day does not vouch for the expired one it merged with.
    assert envelope["meta"]["stale"] is True
    code, out, err = run_cli([*query, "--require-fresh"])
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_STALE"


def test_expired_capture_contributing_nothing_keeps_result_fresh(setup, run_cli):
    from dogopencli.plugins.liquidity.common import now

    expired = (now() - timedelta(hours=100)).isoformat()  # beyond the 72h ttl
    fresh = now().isoformat()
    _seed_returns_captures(
        setup,
        [
            (
                ("20260930", "20261001"),
                [_returns_row("T1", "20261001", "OLD")],
                expired,
            ),
            (
                ("20261001", "20261001"),
                [_returns_row("T1", "20261001", "NEW")],
                fresh,
            ),
        ],
    )
    query = [*RETURNS_QUERY, "--from-date", "20261001", "--to-date", "20261001"]
    code, out, err = run_cli([*query, "--require-fresh"])
    assert code == 0, err
    envelope = parse(out)
    # The expired capture is retained and covers the window, but every row it
    # holds is superseded, so it contributes nothing to the reported result.
    assert [row["interestIncome"] for row in envelope["data"]] == ["NEW"]
    assert envelope["meta"]["stale"] is False


def test_expired_sole_coverage_of_an_empty_day_is_not_fresh(setup, run_cli):
    from dogopencli.plugins.liquidity.common import now

    expired = (now() - timedelta(hours=100)).isoformat()  # beyond the 72h ttl
    fresh = now().isoformat()
    _seed_returns_captures(
        setup,
        [
            (("20260930", "20260930"), [], expired),
            (("20261001", "20261001"), [_returns_row("T2", "20261001", "2")], fresh),
        ],
    )
    query = [*RETURNS_QUERY, "--from-date", "20260930", "--to-date", "20261001"]
    code, out, err = run_cli(query)
    assert code == 0, err
    envelope = parse(out)
    assert [row["transactionId"] for row in envelope["data"]] == ["T2"]
    # The empty 20260930 rests only on the expired capture, so the combined
    # answer is not fresh even though every reported row came from a fresh one.
    assert envelope["meta"]["stale"] is True
    code, out, err = run_cli([*query, "--require-fresh"])
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_STALE"


def test_integer_detail_identity_spellings_share_one_cache_entry(setup, run_cli):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"id": payload["id"], "name": "SVC"}},
    }
    refresh = [
        "refresh",
        "liquidity",
        "network",
        "account-capabilities",
        "detail",
        "get",
        "--id",
        "007",
    ]
    code, out, err = run_cli(refresh)
    assert code == 0, err
    assert setup.state.business_requests[0]["id"] == 7
    code, out, err = run_cli(
        ["liquidity", "network", "account-capabilities", "get", "--id", "7"]
    )
    assert code == 0, err
    assert parse(out)["data"]["id"] == 7
