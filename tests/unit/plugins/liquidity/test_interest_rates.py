"""Native ISO interest-rate dates survive retained capture queries."""

from dataclasses import replace

import pytest

from dogopencli.cache import Cache
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import query
from dogopencli.plugins.liquidity import store as capture_store
from dogopencli.plugins.liquidity.leaves import INVESTMENT_INTEREST_RATES, list_leaf

AT = "2026-10-02T00:00:00+00:00"


def rates(day: str, count: int) -> list[dict]:
    return [
        {
            "currency": "USD",
            "rateName": f"BASE-{index:03d}",
            "ratePeriod": "1M",
            "effectiveDate": day,
            "rateValue": "0.01",
        }
        for index in range(count)
    ]


@pytest.fixture
def configured_store(tmp_path, monkeypatch):
    cache_path = tmp_path / "cache.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[cache]\npath = "{cache_path}"\n[sources.liquidity]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config_path))

    def reject_browser(*args, **kwargs):
        pytest.fail("offline interest-rate query opened the browser")

    monkeypatch.setattr(query, "inquiry_session", reject_browser)
    return Cache(cache_path)


@pytest.mark.parametrize("legacy_capture", [False, True])
def test_interest_rate_capture_reads_native_dates_in_compact_window(
    configured_store, run_cli, legacy_capture
):
    resolved = list_leaf(INVESTMENT_INTEREST_RATES.path).resolve(
        {"source": "market", "from_date": "20261001", "to_date": "20261002"}
    )
    rows = rates("2026-10-01", 137) + rates("2026-10-02", 2)
    # Previously published captures must become readable without recapture.
    published_spec = (
        replace(INVESTMENT_INTEREST_RATES, series_format=None)
        if legacy_capture
        else INVESTMENT_INTEREST_RATES
    )
    plan = capture_store.plan_capture_publish(
        configured_store,
        published_spec,
        resolved.scope_key,
        resolved.window,
        rows,
        len(rows),
        AT,
        AT,
    )
    capture_store.commit_plan(
        configured_store, INVESTMENT_INTEREST_RATES.name, plan, AT
    )
    for day, expected in [("20261001", rows[:137]), ("20261002", rows[137:])]:
        code, out, err = run_cli(
            [
                "liquidity",
                "investment",
                "interest-rates",
                "list",
                "--source",
                "market",
                "--from-date",
                day,
                "--to-date",
                day,
                "--all",
                "--require-complete",
            ]
        )
        assert code == 0, (out, err)
        envelope = parse(out)
        assert envelope["data"] == expected
        assert envelope["meta"]["matched_total"] == len(expected)
        assert envelope["meta"]["complete"] is True
        assert envelope["meta"]["requested_window"] == [day, day]


def test_interest_rate_retention_normalizes_native_day(configured_store):
    rows = rates("2026-09-30", 1) + rates("2026-10-01", 1)
    plan = capture_store.plan_capture_publish(
        configured_store,
        INVESTMENT_INTEREST_RATES,
        "market",
        ("20260930", "20261001"),
        rows,
        2,
        AT,
        AT,
        cap=1,
    )
    capture_store.commit_plan(
        configured_store, INVESTMENT_INTEREST_RATES.name, plan, AT
    )
    entry = plan.index.captures[0]
    assert plan.eviction.retained_from == "20261001"
    assert entry.window_from == "20261001"
    assert capture_store.read_capture(configured_store, entry) == rows[1:]


@pytest.mark.parametrize("day", ["2026-02-30", "2026-1-01", "20261001"])
def test_interest_rate_invalid_native_date_rejects_publication(configured_store, day):
    with pytest.raises(CliError, match="invalid series time effectiveDate"):
        capture_store.plan_capture_publish(
            configured_store,
            INVESTMENT_INTEREST_RATES,
            "market",
            ("20261001", "20261001"),
            rates(day, 1),
            1,
            AT,
            AT,
        )
    assert (
        capture_store.read_index(configured_store, INVESTMENT_INTEREST_RATES.name)
        is None
    )
