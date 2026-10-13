"""Native ISO interest-rate dates survive retained capture queries."""

import pytest

from dogopencli.cache import Cache
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import query
from dogopencli.plugins.liquidity.leaves import INVESTMENT_INTEREST_RATES, list_leaf
from dogopencli.result_policy import AcquisitionEvidence
from dogopencli.temporary_query import publish_slot

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


def test_interest_rate_slot_filters_native_dates(configured_store, run_cli):
    resolved = list_leaf(INVESTMENT_INTEREST_RATES.path).resolve(
        {"source": "market", "from_date": "20261001", "to_date": "20261002"}
    )
    rows = rates("2026-10-01", 137) + rates("2026-10-02", 2)
    with configured_store.refresh_lock():
        publish_slot(
            configured_store,
            "liquidity.investment.interest-rates",
            rows,
            capability=resolved.spec.name,
            scope=resolved.request_values,
            variant=resolved.spec.endpoint,
            fetched_at=AT,
            evidence=AcquisitionEvidence.for_collection(
                complete=True, reported_total=139, collected_total=139
            ),
        )
    for day, expected in [("20261001", rows[:137]), ("20261002", rows[137:])]:
        code, out, err = run_cli(
            [
                "liquidity",
                "investment",
                "interest-rates",
                "list",
                "--from-date",
                day,
                "--to-date",
                day,
                "--limit",
                "0",
                "--require-complete",
            ]
        )
        assert code == 0, (out, err)
        assert parse(out)["data"] == expected
        assert parse(out)["meta"]["matched_total"] == len(expected)
