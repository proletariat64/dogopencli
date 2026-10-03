"""Holdings query dates scope snapshots without filtering native row dates."""

from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.cache import Cache
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import spec
from dogopencli.plugins.liquidity import store as capture_store
from dogopencli.plugins.liquidity.leaves import INVESTMENT_HOLDINGS


@pytest.fixture
def source(tmp_path: Path, monkeypatch):
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


def mixed_rows():
    return [
        {"investmentNo": "H1", "valueDate": "20220815", "amount": "10.00"},
        {"investmentNo": "H2", "valueDate": "20260930", "amount": "20.00"},
        {"investmentNo": "H3", "valueDate": "20261001", "amount": "30.00"},
    ]


def query(day="20261001"):
    return ["liquidity", "investment", "holdings", "list", "--date", day, "--all"]


def refresh(day="20261001"):
    return ["refresh", "liquidity", "investment", "holdings", "--date", day]


def install(browser, rows):
    def answer(payload, index):
        assert payload["pageSize"] == 500
        assert payload["date"] in ("20261001", "20260930")
        return {
            "status": 200,
            "body": {"success": True, "data": {"data": rows, "totalCount": len(rows)}},
        }

    browser.business_handler = answer


def test_holdings_mixed_native_dates_survive_live_refresh_and_offline(source, run_cli):
    browser, cache = source
    rows = mixed_rows()
    install(browser, rows)
    code, out, err = run_cli([*query(), "--live", "--require-complete"])
    assert code == 0, err
    live = parse(out)
    assert live["data"] == rows
    assert live["meta"]["complete"] is True
    code, out, err = run_cli(refresh())
    assert code == 0, err
    published = parse(out)
    assert published["data"]["row_count"] == 3
    before = cache.read_bytes()

    def disconnected(*args, **kwargs):
        pytest.fail("offline holdings contacted CDP")

    cdp.set_transport_factory(disconnected)
    code, out, err = run_cli([*query(), "--require-complete"])
    assert code == 0, err
    offline = parse(out)
    assert offline["data"] == rows
    assert offline["meta"]["complete"] is True
    assert offline["meta"]["reported_total"] == 3
    assert offline["meta"]["snapshot_id"] == published["meta"]["snapshot_id"]
    assert 'date="20261001"' in offline["meta"]["scope"]
    assert offline["meta"]["requested_window"] is None
    assert cache.read_bytes() == before


def test_holdings_query_dates_have_independent_cache_scopes(source, run_cli):
    browser, _ = source
    first = mixed_rows()
    install(browser, first)
    code, _, err = run_cli(refresh())
    assert code == 0, err
    code, out, _ = run_cli(query("20260930"))
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    second = [{"investmentNo": "H4", "valueDate": "20220101", "amount": "40.00"}]
    install(browser, second)
    code, _, err = run_cli(refresh("20260930"))
    assert code == 0, err
    code, out, _ = run_cli(query())
    assert code == 0 and parse(out)["data"] == first
    code, out, _ = run_cli(query("20260930"))
    assert code == 0 and parse(out)["data"] == second


def test_holdings_retention_uses_capture_history_and_warns_for_trimmed_scope(
    source, run_cli, monkeypatch
):
    browser, cache = source
    rows = mixed_rows()
    install(browser, rows)
    monkeypatch.setattr(
        capture_store,
        "plan_capture_publish",
        partial(capture_store.plan_capture_publish, cap=2),
    )
    code, out, err = run_cli(refresh())
    assert code == 0, err
    assert parse(out)["data"]["row_count"] == 2
    assert "retention evicted" in err
    before = cache.read_bytes()
    code, out, err = run_cli(query())
    result = parse(out)
    assert code == 0
    assert result["data"] == rows[1:]
    assert result["meta"]["complete"] is False
    assert result["meta"]["reported_total"] == 3
    assert result["meta"]["collected_total"] == 2
    assert result["error"] is None
    assert "warning: INCOMPLETE_RESULT" in err
    code, out, _ = run_cli([*query(), "--require-complete"])
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert cache.read_bytes() == before


def test_holdings_does_not_reuse_legacy_cache_without_native_query_date(
    source, run_cli
):
    _, path = source
    cache = Cache(path)
    legacy = replace(
        INVESTMENT_HOLDINGS, profile=spec.PROFILE_DATED, series_field="valueDate"
    )
    at = "2026-10-03T00:00:00+00:00"
    plan = capture_store.plan_capture_publish(
        cache, legacy, "", ("20261001", "20261001"), mixed_rows(), 3, at, at
    )
    capture_store.commit_plan(cache, legacy.name, plan, at)
    before = path.read_bytes()
    code, out, _ = run_cli(query())
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert path.read_bytes() == before
