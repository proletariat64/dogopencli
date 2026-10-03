"""Ledger capture windows normalize the native ISO value date."""

from dataclasses import replace

import pytest

from dogopencli.cache import Cache
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import query, store
from dogopencli.plugins.liquidity.leaves import LEDGER_BALANCES, list_leaf

AT = "2026-10-02T00:00:00+00:00"


def balance(day):
    return {
        "accountNo": "synthetic-account",
        "currency": "USD",
        "valueDate": day,
        "accountingDate": "2026-10-01",
    }


@pytest.mark.parametrize("legacy", [False, True])
def test_ledger_capture_filters_native_value_date(
    tmp_path, monkeypatch, run_cli, legacy
):
    cache = Cache(tmp_path / "cache.sqlite3")
    config = tmp_path / "config.toml"
    config.write_text(
        f'[cache]\npath = "{tmp_path / "cache.sqlite3"}"\n'
        '[sources.liquidity]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))

    def disconnected(*args, **kwargs):
        pytest.fail("offline ledger capture query contacted the browser")

    monkeypatch.setattr(query, "inquiry_session", disconnected)
    resolved = list_leaf(LEDGER_BALANCES.path).resolve(
        {
            "book_type": "OUTER",
            "timezone": "+08:00",
            "from_date": "20261001",
            "to_date": "20261002",
        }
    )
    rows = [balance("2026-10-01"), balance("2026-10-02")]
    old = replace(LEDGER_BALANCES, series_format=None) if legacy else LEDGER_BALANCES
    plan = store.plan_capture_publish(
        cache, old, resolved.scope_key, resolved.window, rows, 2, AT, AT
    )
    store.commit_plan(cache, LEDGER_BALANCES.name, plan, AT)
    code, out, err = run_cli(
        [
            "liquidity",
            "ledger",
            "balances",
            "list",
            "--book-type",
            "OUTER",
            "--timezone",
            "+08:00",
            "--from-date",
            "20261002",
            "--to-date",
            "20261002",
            "--all",
            "--require-complete",
        ]
    )
    assert code == 0, (out, err)
    result = parse(out)
    assert result["data"] == rows[1:]
    assert result["meta"]["complete"] is True
    assert result["meta"]["matched_total"] == 1


def test_ledger_capture_rejects_invalid_native_date(tmp_path):
    cache = Cache(tmp_path / "cache.sqlite3")
    with pytest.raises(CliError, match="invalid series time valueDate"):
        store.plan_capture_publish(
            cache,
            LEDGER_BALANCES,
            "OUTER",
            ("20261001", "20261001"),
            [balance("2026-02-30")],
            1,
            AT,
            AT,
        )
    assert store.read_index(cache, LEDGER_BALANCES.name) is None
