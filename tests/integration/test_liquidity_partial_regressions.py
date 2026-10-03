"""Partial holdings and single-response duplicate coverage stay explicit."""

import json
import sqlite3
from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.cache import Cache
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import store as capture_store
from dogopencli.plugins.liquidity.capability import LiquidityListCapability
from dogopencli.plugins.liquidity.collect import collect_liquidity_scope
from dogopencli.plugins.liquidity.leaves import INVESTMENT_PRODUCTS, list_leaf
from dogopencli.transport import OriginMetadata, TransportResponse


@pytest.mark.parametrize("require_complete", [False, True])
@pytest.mark.parametrize(
    "corruption",
    [
        "conflicting_identity",
        "identical_identity",
        "missing_identity",
        "seqid_gap",
        "capture_json",
        "index_json",
    ],
)
def test_corrupt_capture_is_rejected_before_display_or_identity_merge(
    holdings_source, run_cli, corruption, require_complete
):
    _, path = holdings_source
    leaf = list_leaf(("risk", "metrics"))
    resolved = leaf.resolve({"metric": "CONCENTRATION_RATE"})
    rows = [{"id": 1, "value": "1"}, {"id": 2, "value": "2"}]
    cache = Cache(path)
    at = "2026-10-03T00:00:00+00:00"
    plan = capture_store.plan_capture_publish(
        cache, resolved.spec, resolved.scope_key, resolved.window, rows, None, at, at
    )
    capture_store.commit_plan(cache, resolved.spec.name, plan, at)
    capture_ns = plan.capture_meta.namespace
    with sqlite3.connect(path) as connection:
        if corruption == "seqid_gap":
            connection.execute(
                "UPDATE records SET seqid = 3 WHERE namespace = ? AND seqid = 2",
                (capture_ns,),
            )
        elif corruption in ("capture_json", "index_json"):
            corrupted_ns = (
                capture_ns
                if corruption == "capture_json"
                else capture_store.index_namespace(resolved.spec.name)
            )
            connection.execute(
                "UPDATE records SET body = ? WHERE namespace = ? AND seqid = 2",
                ("{", corrupted_ns),
            )
        else:
            record = dict(rows[1])
            if corruption == "missing_identity":
                del record["id"]
            else:
                record["id"] = 1
                if corruption == "identical_identity":
                    record = rows[0]
            connection.execute(
                "UPDATE records SET body = ? WHERE namespace = ? AND seqid = 2",
                (json.dumps(record), capture_ns),
            )
    before = path.read_bytes()

    def disconnected(*args, **kwargs):
        pytest.fail("offline corrupt capture query contacted CDP")

    cdp.set_transport_factory(disconnected)
    query = [
        "liquidity",
        "risk",
        "metrics",
        "list",
        "--metric",
        "CONCENTRATION_RATE",
        "--limit",
        "1",
        "--fields",
        "value",
    ]
    if require_complete:
        query.append("--require-complete")
    code, out, _ = run_cli(query)
    result = parse(out)
    assert code == 1
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert path.read_bytes() == before


@pytest.fixture
def holdings_source(tmp_path: Path, monkeypatch):
    cache = tmp_path / "cache.sqlite3"
    config = tmp_path / "config.toml"
    config.write_text(
        f'[cache]\npath = "{cache}"\n'
        f'[auth]\nprofile = "{tmp_path / "profile"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
        '[sources.liquidity]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    browser = FakeBrowser(
        href="https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    )
    cdp.set_transport_factory(browser.transport)
    yield browser, cache
    cdp.set_transport_factory(None)


def test_holdings_partial_publishes_and_warns_on_every_offline_read(
    holdings_source, run_cli
):
    browser, cache = holdings_source
    scope = ["--date", "20261001"]
    query = ["liquidity", "investment", "holdings", "list", *scope]
    refresh = ["refresh", "liquidity", "investment", "holdings", *scope]
    original = [
        {"investmentNo": f"H{i}", "valueDate": "20261001", "amount": "10.00"}
        for i in range(2)
    ]
    records = original
    total = 2
    requests = []

    def answer(payload, index):
        requests.append(payload)
        return {
            "status": 200,
            "body": {"success": True, "data": {"data": records, "totalCount": total}},
        }

    browser.business_handler = answer
    code, out, err = run_cli(refresh)
    assert code == 0, err
    assert parse(out)["data"]["published"] is True
    before = cache.read_bytes()
    total = 3
    records = [dict(row, amount="20.00") for row in original]

    code, out, err = run_cli(
        [*query, "--live", "--limit", "1", "--fields", "investmentNo"]
    )
    result = parse(out)
    assert code == 0
    assert result["data"] == [{"investmentNo": "H0"}]
    assert result["error"] is None
    assert result["meta"]["complete"] is False
    assert result["meta"]["reported_total"] == 3
    assert result["meta"]["collected_total"] == 2
    assert result["meta"]["matched_total"] == 2
    assert result["meta"]["returned_count"] == 1
    assert result["meta"]["warnings"][0]["code"] == "INCOMPLETE_RESULT"
    assert "warning: INCOMPLETE_RESULT" in err
    assert cache.read_bytes() == before

    code, out, err = run_cli([*query, "--live", "--all", "--format", "table"])
    assert code == 0
    assert "warning: INCOMPLETE_RESULT" in err
    assert "H0" in out and "H1" in out

    code, out, _ = run_cli([*query, "--live", "--all", "--require-complete"])
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"

    code, out, err = run_cli(refresh)
    result = parse(out)
    assert code == 0
    assert result["data"]["published"] is True
    assert result["data"]["row_count"] == 2
    assert result["meta"]["published"] is True
    assert result["meta"]["complete"] is False
    assert result["meta"]["reported_total"] == 3
    assert result["meta"]["collected_total"] == 2
    assert "warning: INCOMPLETE_RESULT" in err
    assert cache.read_bytes() != before
    before = cache.read_bytes()
    assert all(body["pageSize"] == 500 for body in requests)

    def disconnected(*args, **kwargs):
        pytest.fail("offline holdings query contacted CDP")

    cdp.set_transport_factory(disconnected)
    for _ in range(2):
        code, out, err = run_cli([*query, "--all"])
        assert code == 0
        assert parse(out)["data"] == records
        assert parse(out)["meta"]["complete"] is False
        assert parse(out)["error"] is None
        assert "warning: INCOMPLETE_RESULT" in err
    code, out, _ = run_cli([*query, "--all", "--require-complete"])
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert cache.read_bytes() == before


@pytest.mark.parametrize("total", [1, 2])
def test_single_response_duplicate_arrivals_never_prove_complete(total):
    row = {"incrementProductId": "P1", "currency": "USD"}
    origin = OriginMetadata("cdp", False, None, None, None, None, None)
    calls = []

    class Transport:
        def execute(self, request, *, timeout=None):
            calls.append(request)
            return TransportResponse(
                200,
                json.dumps(
                    {"success": True, "data": {"data": [row, row], "totalCount": total}}
                ).encode(),
                origin,
            )

    result = collect_liquidity_scope(
        LiquidityListCapability(INVESTMENT_PRODUCTS), Transport(), ""
    )
    assert result.records == [row]
    assert result.total_count == total
    assert result.complete is False
    assert len(calls) == 1


@pytest.mark.parametrize("cap", [1, 2])
def test_history_retention_preserves_truthful_scope_completeness(
    holdings_source, run_cli, cap
):
    _, path = holdings_source

    def disconnected(*args, **kwargs):
        pytest.fail("offline history query contacted CDP")

    cdp.set_transport_factory(disconnected)
    query = ["liquidity", "investment", "transactions", "list", "--all"]
    code, out, _ = run_cli(query)
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"

    leaf = list_leaf(("investment", "transactions"))
    resolved = leaf.resolve({})
    variant = resolved.spec
    rows = [{"orderId": "T1"}, {"orderId": "T2"}]
    cache = Cache(path)
    at = "2026-10-03T00:00:00+00:00"
    plan = capture_store.plan_capture_publish(
        cache, variant, resolved.scope_key, resolved.window, rows, 2, at, at, cap=cap
    )
    capture_store.commit_plan(cache, variant.name, plan, at)
    index = capture_store.read_index(cache, variant.name)
    selected, covered = capture_store.select_captures(
        index, variant, resolved.scope_key, resolved.window
    )
    assert covered is (cap == 2)
    assert selected[0].row_count == cap
    assert selected[0].reported_total == 2
    before = path.read_bytes()

    code, out, err = run_cli(query)
    result = parse(out)
    assert result["data"] == rows[-cap:]
    assert result["meta"]["complete"] is (cap == 2)
    assert result["meta"]["reported_total"] == 2
    assert result["meta"]["returned_count"] == cap
    assert result["meta"]["retained_coverage"][0]["row_count"] == cap
    assert code == 0
    if cap == 1:
        assert result["error"] is None
        assert result["meta"]["collected_total"] == 1
        assert result["meta"]["warnings"][0]["code"] == "INCOMPLETE_RESULT"
        assert "warning: INCOMPLETE_RESULT" in err
    else:
        assert result["error"] is None

    code, out, _ = run_cli([*query, "--require-complete"])
    strict = parse(out)
    if cap == 1:
        assert code == 1
        assert strict["data"] is None
        assert strict["error"]["code"] == "INCOMPLETE_RESULT"
    else:
        assert code == 0
        assert strict["meta"]["complete"] is True
    assert path.read_bytes() == before


def test_strict_refresh_rejects_retention_before_commit(
    holdings_source, run_cli, monkeypatch
):
    from functools import partial

    browser, path = holdings_source
    rows = [{"orderId": "H1"}, {"orderId": "H2"}]
    browser.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"data": rows, "totalCount": 2}},
    }
    refresh = ["refresh", "liquidity", "investment", "transactions"]
    assert run_cli(refresh)[0] == 0
    before = path.read_bytes()
    monkeypatch.setattr(
        capture_store,
        "plan_capture_publish",
        partial(capture_store.plan_capture_publish, cap=1),
    )
    code, out, _ = run_cli([*refresh, "--require-complete"])
    result = parse(out)
    assert code == 1
    assert result["data"] is None
    assert result["meta"]["published"] is False
    assert "RETENTION_GAP" in result["meta"]["acquisition"]["reasons"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("same_timestamp", [False, True])
def test_latest_dated_request_replaces_rows_and_quality_without_old_hole_fill(
    holdings_source,
    run_cli,
    same_timestamp,
):
    from dogopencli.plugins.liquidity.common import now
    from dogopencli.result_policy import AcquisitionEvidence

    _, path = holdings_source
    leaf = list_leaf(("investment", "returns"))
    cache = Cache(path)
    fetched = now().isoformat()
    index = 0

    def publish(start, end, rows, total):
        nonlocal index
        resolved = leaf.resolve(
            {"basis": "accrual", "from_date": start, "to_date": end}
        )
        stamp = fetched if same_timestamp else f"2026-10-03T00:00:0{index}+00:00"
        index += 1
        evidence = AcquisitionEvidence.for_collection(
            complete=len(rows) == total,
            reported_total=total,
            collected_total=len(rows),
        )
        plan = capture_store.plan_capture_publish(
            cache,
            resolved.spec,
            resolved.scope_key,
            resolved.window,
            rows,
            total,
            stamp,
            stamp,
            acquisition=evidence,
        )
        capture_store.commit_plan(cache, resolved.spec.name, plan, stamp)

    def row(identity, day, amount):
        return {
            "investmentNo": identity,
            "transactionDate": day,
            "interestIncome": amount,
        }

    query = [
        "liquidity",
        "investment",
        "returns",
        "list",
        "--basis",
        "accrual",
        "--from-date",
        "20261001",
        "--to-date",
        "20261002",
        "--all",
    ]
    publish(
        "20261001",
        "20261002",
        [
            row("A", "20261001", "old"),
            row("B", "20261001", "old"),
            row("C", "20261002", "old"),
        ],
        3,
    )
    publish("20261001", "20261001", [row("A", "20261001", "partial")], 2)

    def disconnected(*args, **kwargs):
        pytest.fail("offline dated query contacted CDP")

    cdp.set_transport_factory(disconnected)
    code, out, err = run_cli(query)
    result = parse(out)
    assert code == 0
    assert result["data"] == [
        row("A", "20261001", "partial"),
        row("C", "20261002", "old"),
    ]
    assert result["meta"]["complete"] is False
    assert result["meta"]["reported_total"] is None
    assert result["meta"]["missing_count"] is None
    assert result["meta"]["coverage_ratio"] is None
    assert "COUNT_SHORTFALL" in result["meta"]["acquisition"]["reasons"]
    assert "INCOMPLETE_RESULT" in err
    assert run_cli([*query, "--require-complete"])[0] == 1
    publish(
        "20261001",
        "20261001",
        [row("A", "20261001", "new"), row("B", "20261001", "new")],
        2,
    )
    code, out, _ = run_cli([*query, "--require-complete"])
    assert code == 0
    assert parse(out)["data"] == [
        row("A", "20261001", "new"),
        row("B", "20261001", "new"),
        row("C", "20261002", "old"),
    ]
    publish("20261001", "20261001", [row("A", "20261001", "final")], 1)
    code, out, _ = run_cli([*query, "--require-complete"])
    assert code == 0
    assert parse(out)["data"] == [
        row("A", "20261001", "final"),
        row("C", "20261002", "old"),
    ]


@pytest.mark.parametrize(
    "rows", [[], [{"incrementProductId": "P1", "currency": "USD"}]]
)
def test_first_single_partial_refresh_publishes_usable_cache_and_strict_keeps_it(
    holdings_source,
    run_cli,
    rows,
):
    browser, path = holdings_source
    browser.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"data": rows, "totalCount": 2}},
    }
    refresh = ["refresh", "liquidity", "investment", "products"]
    query = ["liquidity", "investment", "products", "list", "--all"]
    code, out, err = run_cli(refresh)
    result = parse(out)
    assert code == 0
    assert result["data"]["published"] is True
    assert result["data"]["row_count"] == len(rows)
    assert result["meta"]["published"] is True
    assert result["meta"]["complete"] is False
    assert result["meta"]["missing_count"] == 2 - len(rows)
    assert result["error"] is None
    assert "INCOMPLETE_RESULT" in err
    before = path.read_bytes()
    code, out, _ = run_cli([*refresh, "--require-complete"])
    result = parse(out)
    assert code == 1
    assert result["data"] is None
    assert result["meta"]["published"] is False
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert path.read_bytes() == before

    def disconnected(*args, **kwargs):
        pytest.fail("offline partial query contacted CDP")

    cdp.set_transport_factory(disconnected)
    code, out, err = run_cli(query)
    result = parse(out)
    assert code == 0
    assert result["data"] == rows
    assert result["meta"]["complete"] is False
    assert result["meta"]["collected_total"] == len(rows)
    assert result["error"] is None
    assert "INCOMPLETE_RESULT" in err
    assert path.read_bytes() == before
