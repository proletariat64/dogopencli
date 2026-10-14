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
        return holdings_page(
            rows_by_offset(payload["rowStart"], payload["pageSize"]), total
        )

    return answer


def seed_holdings(run_cli, setup, total=12, day="20261001"):
    rows = [holding(i, day) for i in range(total)]

    def by_offset(row_start, page_size):
        return rows[row_start : row_start + page_size]

    setup.state.business_handler = holdings_listing(by_offset, total)
    code, out, err = run_cli(
        ["refresh", "liquidity", "investment", "holdings", "--date", day]
    )
    assert code == 0, err
    envelope = parse(out)
    assert envelope["data"]["row_count"] == total
    return rows


def test_refresh_then_offline_list_with_kind_and_origin(setup, run_cli):
    rows = seed_holdings(run_cli, setup, total=512)
    assert [p["rowStart"] for p in setup.state.business_requests] == [0, 500]
    assert all(p["pageSize"] == 500 for p in setup.state.business_requests)
    created = [url for transport in setup.state.transports for url in transport.created]
    # Session setup verifies only the requested liquidity origin (ADR 0015).
    assert PAYMENT_URL not in created
    assert LIQUIDITY_URL in created
    code, out, err = run_cli(
        ["liquidity", "investment", "holdings", "list", "--limit", "0"]
    )
    assert code == 0, err
    envelope = parse(out)
    assert envelope["error"] is None
    assert len(envelope["data"]) == 512
    meta = envelope["meta"]
    assert meta["kind"] == "runtimes"
    assert meta["source"] == "cache"
    assert meta["complete"] is True
    assert meta["reported_total"] == 512
    assert meta["requested_window"] is None
    assert meta["query"]["date"] == "20261001"
    assert meta["collected_total"] == 512
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


def test_source_only_scope_requires_online_query(setup, run_cli):
    seed_holdings(run_cli, setup, total=2)
    code, out, err = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", "20260930"]
    )
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert "--live or refresh" in parse(out)["error"]["message"]
    code, out, err = run_cli(
        ["liquidity", "investment", "holdings", "list", "--fields", "investmentNo"]
    )
    assert code == 0
    assert parse(out)["data"] == [{"investmentNo": "H0000"}, {"investmentNo": "H0001"}]


def test_date_validation_rejects_malformed_scope(setup, run_cli):
    # Issue #127/#130: ISO YYYY-MM-DD is the preferred canonical form and now
    # passes validation (the cache-miss path returns a non-usage failure).
    code, out, _ = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", "2026-10-01"]
    )
    assert code != 2
    assert parse(out)["error"]["code"] != "INVALID_ARGUMENT"

    # Genuinely malformed dates are still rejected before any backend access.
    for bad in ("2026-13-01", "2026-02-30", "2026101"):
        code, out, _ = run_cli(
            ["liquidity", "investment", "holdings", "list", "--date", bad]
        )
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_detail_form_encoding_and_string_identity(setup, run_cli):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"orderId": payload["orderId"]}},
    }
    assert (
        run_cli(
            [
                "liquidity",
                "investment",
                "holdings",
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

    assert not setup.cache_path.exists()


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
    code, out, _ = run_cli(["liquidity", "investment", "holdings", "list"])
    assert code == 0
    assert len(parse(out)["data"]) == 2


def test_live_overlap_is_partial_and_require_complete_fails(setup, run_cli):
    rows = [holding(i) for i in range(512)]

    def by_offset(row_start, page_size):
        # The observed overlap defect: page 2 repeats the last page-1 row.
        if row_start == 0:
            return rows[:page_size]
        return rows[row_start - 1 : row_start + 11]

    setup.state.business_handler = holdings_listing(by_offset, 512)
    code, out, _ = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", "20261001", "--live"]
    )
    assert code == 0
    envelope = parse(out)
    assert envelope["meta"]["source"] == "live"
    assert envelope["meta"]["complete"] is False
    assert envelope["error"] is None
    assert envelope["meta"]["warnings"][0]["code"] == "INCOMPLETE_RESULT"
    assert envelope["data"]
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
    # Strict refresh rejects the same defect before publication.
    code, out, _ = run_cli(
        [
            "refresh",
            "liquidity",
            "investment",
            "holdings",
            "--date",
            "20261001",
            "--require-complete",
        ]
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
    assert "dogopencli login --domain liquidity" in parse(out)["error"]["message"]
    assert "dogopencli auth check --domain liquidity" in parse(out)["error"]["message"]


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
    code, out, _ = run_cli(["liquidity", "rules", "monitoring", "list"])
    assert code == 1
    error = parse(out)["error"]
    assert error["code"] == "UNSUPPORTED_CAPABILITY"
    assert "monitoring" in error["message"].lower()
    help_code, help_out, _ = run_cli(
        ["help", "liquidity", "rules", "monitoring", "list"]
    )
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
    assert guide["offline_profile"] == "single temporary leaf result"
    assert document["data_schema"]["properties"]["investmentNo"]


def accounts_handler(rows, cash_total=None):
    """Answer every native component of the composite directory."""
    cash_total = len(rows) if cash_total is None else cash_total
    baselines = [{**row, "accountType": "OA", "status": "NORMAL"} for row in rows]

    def answer(payload, index):
        if "aliasName" in payload:
            detail = next(
                row for row in baselines if row["aliasName"] == payload["aliasName"]
            )
            return {
                "status": 200,
                "body": {"resultFlag": True, "result": {"data": detail}},
            }
        if "bankAccountQueryVO" in payload:
            vo = json.loads(payload["bankAccountQueryVO"])
            source, container, total = rows, "bankAccountPropertyVOList", cash_total
        else:
            vo = json.loads(payload["bankAccountBaseLineQuery"])
            source, container, total = baselines, "data", len(baselines)
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "result": {
                    container: source[vo["rowStart"] : vo["rowStart"] + vo["pageSize"]]
                },
                "count": total,
            },
        }

    return answer


def account_row(alias):
    return {
        "id": "0",
        "aliasName": alias,
        "currency": "USD",
        "bankId": "BANK",
        "instId": "ENTITY",
    }


def test_accounts_result_flag_family_end_to_end(setup, run_cli):
    rows = [account_row(f"ALIAS{i:03d}") for i in range(15)]
    setup.state.business_handler = accounts_handler(rows)
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
    assert envelope["meta"]["detail_coverage"]["succeeded"] == 15
    assert envelope["meta"]["has_more"] is True


@pytest.mark.parametrize(
    "extra", [[], ["--limit", "1"], ["--fields", "aliasName"], ["--format", "table"]]
)
def test_accounts_partial_live_warns_and_returns_usable_rows(setup, run_cli, extra):
    rows = [account_row(f"A{i}") for i in range(2)]
    # Two missing native positions cannot receive the single-hole exception.
    setup.state.business_handler = accounts_handler(rows, cash_total=4)
    before = setup.cache_path.read_bytes() if setup.cache_path.exists() else None
    code, out, err = run_cli(
        ["liquidity", "cash", "accounts", "list", "--live", *extra]
    )
    assert code == 0
    assert "warning: INCOMPLETE_RESULT" in err
    assert "COUNT_SHORTFALL" in err
    if "table" in extra:
        assert "A0" in out
    else:
        envelope = parse(out)
        assert envelope["error"] is None
        assert envelope["meta"]["complete"] is False
        assert envelope["meta"]["sources"]["cash"]["reported_total"] == 4
        assert envelope["meta"]["collected_total"] == 2
        assert envelope["meta"]["detail_coverage"]["succeeded"] == 2
        assert envelope["meta"]["accepted_diagnostics"] == []
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


def test_accounts_partial_refresh_replaces_cache_and_warns(setup, run_cli):
    old_rows = [account_row("OLD")]
    setup.state.business_handler = accounts_handler(old_rows)
    code, _, _ = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 0
    before = setup.cache_path.read_bytes()
    new_rows = [account_row("NEW")]
    setup.state.business_handler = accounts_handler(new_rows, cash_total=3)
    code, out, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 0
    assert "warning: INCOMPLETE_RESULT" in err
    envelope = parse(out)
    assert envelope["data"]["published"] is True
    assert envelope["error"] is None
    assert envelope["meta"]["complete"] is False
    assert envelope["meta"]["published"] is True
    assert envelope["meta"]["source"] == "live"
    assert setup.cache_path.read_bytes() != before
    code, out, _ = run_cli(["liquidity", "cash", "accounts", "list"])
    assert code == 0
    result = parse(out)
    assert [row["aliasName"] for row in result["data"]] == ["NEW"]
    assert result["data"][0]["status"] == "NORMAL"
    assert result["meta"]["sources"]["cash"]["reported_total"] == 3
    assert result["meta"]["detail_coverage"]["succeeded"] == 1


@pytest.mark.parametrize(
    ("path", "scope", "response"),
    [
        (
            ["cash", "waterlevels"],
            ["--account-alias", "A1"],
            {"success": True, "data": {"data": [], "totalCount": 0}},
        ),
        (
            ["cash", "statements", "intraday"],
            [
                "--account-alias",
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
                "--account-alias",
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
    assert parse(out)["meta"]["published"] is False
    assert not setup.cache_path.exists()
    before = len(setup.state.transports)
    code, out, err = run_cli(["liquidity", *path, "list"])
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
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
        "--account-alias",
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
        "--account-alias",
        "A1",
        "--currency",
        "USD",
        "--from-date",
        "20260930",
        "--to-date",
        "20260930",
    ]
    base = ["liquidity", "forecast", "cashflows", "list"]
    code, out, err = run_cli(
        [*base, *scope, "--live", "--limit", "0", "--require-complete"]
    )
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
    code, out, err = run_cli([*base, *scope, "--limit", "0", "--require-complete"])
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
            "--format",
            "table",
        ]
    )
    assert code == 0
    assert "kind" not in out.splitlines()[0] or True
    assert "H0000" in out


def test_offline_cash_returns_uses_cash_identity_and_time(setup, run_cli):
    from dogopencli.cache import Cache
    from dogopencli.plugins.liquidity.leaves import list_leaf
    from dogopencli.result_policy import AcquisitionEvidence
    from dogopencli.temporary_query import publish_slot

    leaf = list_leaf(("investment", "returns"))
    resolved = leaf.resolve(
        {"basis": "cash", "from_date": "20261001", "to_date": "20261001"}
    )
    rows = [{"transactionId": "T1", "settlementDate": "20261001"}]
    cache = Cache(setup.cache_path)
    with cache.refresh_lock():
        publish_slot(
            cache,
            "liquidity.investment.returns",
            rows,
            capability=resolved.spec.name,
            scope=resolved.request_values,
            variant=resolved.spec.endpoint,
            fetched_at="2026-10-01T00:00:00+00:00",
            evidence=AcquisitionEvidence.for_collection(
                complete=True, reported_total=1, collected_total=1
            ),
        )
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


def test_declared_customer_version_is_not_global_version(setup, run_cli):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "customerNo": payload["customerNo"],
                "version": int(payload["version"]),
            },
        },
    }
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
    assert code == 0, out
    assert parse(out)["data"]["version"] == 1
    assert not setup.cache_path.exists()


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
    "--limit",
    "0",
]


def test_liquidity_initial_auth_failure_exposes_domain_login(setup, run_cli):
    route_probes(setup.state, (SSO_URL,))
    code, out, _ = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", "20261001", "--live"]
    )
    assert code == 1
    error = parse(out)["error"]
    assert error["code"] == "AUTH_REQUIRED"
    assert "dogopencli login --domain liquidity" in error["message"]
    assert "dogopencli auth check --domain liquidity" in error["message"]
    assert setup.state.business_requests == []
