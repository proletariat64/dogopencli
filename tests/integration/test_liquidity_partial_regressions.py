"""Partial holdings and single-response duplicate coverage stay explicit."""

import json
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


def test_holdings_partial_warns_without_replacing_complete_cache(
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
    assert code == 1
    assert result["data"] == [{"investmentNo": "H0"}]
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["meta"]["complete"] is False
    assert result["meta"]["reported_total"] == 3
    assert result["meta"]["collected_total"] == 2
    assert result["meta"]["matched_total"] == 2
    assert result["meta"]["returned_count"] == 1
    assert result["meta"]["warnings"][0]["code"] == "INCOMPLETE_RESULT"
    assert "warning: INCOMPLETE_RESULT" in err
    assert cache.read_bytes() == before

    code, out, err = run_cli([*query, "--live", "--all", "--format", "table"])
    assert code == 1
    assert "warning: INCOMPLETE_RESULT" in err
    assert "H0" in out and "H1" in out

    code, out, _ = run_cli([*query, "--live", "--all", "--require-complete"])
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"

    code, out, err = run_cli(refresh)
    result = parse(out)
    assert code == 1
    assert result["data"] == records
    assert result["meta"]["published"] is False
    assert result["meta"]["complete"] is False
    assert result["meta"]["reported_total"] == 3
    assert result["meta"]["collected_total"] == 2
    assert "warning: INCOMPLETE_RESULT" in err
    assert cache.read_bytes() == before
    assert all(body["pageSize"] == 500 for body in requests)

    def disconnected(*args, **kwargs):
        pytest.fail("offline holdings query contacted CDP")

    cdp.set_transport_factory(disconnected)
    code, out, _ = run_cli([*query, "--all", "--require-complete"])
    assert code == 0
    assert parse(out)["data"] == original
    assert parse(out)["meta"]["complete"] is True
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
    assert code == (0 if cap == 2 else 1)
    if cap == 1:
        assert result["error"]["code"] == "INCOMPLETE_RESULT"
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
