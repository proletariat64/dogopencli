"""Holdings query dates scope snapshots without filtering native row dates."""

from dataclasses import replace
from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.cache import Cache
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import spec
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


def query(day=None):
    return [
        "liquidity",
        "investment",
        "holdings",
        "list",
        *(["--date", day] if day else []),
        "--limit",
        "0",
    ]


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
    code, out, err = run_cli([*query("20261001"), "--live", "--require-complete"])
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
    assert offline["meta"]["scope"]["date"] == "20261001"
    assert offline["meta"]["requested_window"] is None
    assert cache.read_bytes() == before


def test_holdings_query_dates_have_independent_cache_scopes(source, run_cli):
    browser, _ = source
    first = mixed_rows()
    install(browser, first)
    code, _, err = run_cli(refresh())
    assert code == 0, err
    code, out, _ = run_cli(query("20260930"))
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    second = [{"investmentNo": "H4", "valueDate": "20220101", "amount": "40.00"}]
    install(browser, second)
    code, _, err = run_cli(refresh("20260930"))
    assert code == 0, err
    code, out, _ = run_cli(query())
    assert code == 0 and parse(out)["data"] == second
    code, out, _ = run_cli(query())
    assert code == 0 and parse(out)["data"] == second


def test_holdings_does_not_reuse_legacy_cache_without_native_query_date(
    source, run_cli
):
    _, path = source
    cache = Cache(path)
    legacy = replace(
        INVESTMENT_HOLDINGS, profile=spec.PROFILE_DATED, series_field="valueDate"
    )
    at = "2026-10-03T00:00:00+00:00"
    from dogopencli.cache import SnapshotMeta
    from dogopencli.jsonutil import canonical

    meta = SnapshotMeta(
        namespace="legacy-liquidity",
        capability=legacy.name,
        scope="{}",
        source_kind="cdp",
        snapshot_id="old",
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at=at,
        loaded_at=at,
        source_observed_from=None,
        source_observed_to=None,
        row_count=1,
    )
    cache.publish(meta, [(1, canonical(mixed_rows()[0]))])
    before = path.read_bytes()
    code, out, _ = run_cli(query())
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert path.read_bytes() != before
