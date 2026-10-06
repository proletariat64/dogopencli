"""Canonical/legacy cache-compatibility matrix (Issue #127/#134, T07/T08/T13).

Equivalent canonical and legacy invocations must produce identical native
requests, identical cache identity, and identical reads. Legacy-seeded
caches answer canonical queries with no unexpected writes. Invalid
arguments and failed acquisition never overwrite a valid cache. All
offline: public CLI + fake CDP transport + real temporary SQLite.
"""


from test_liquidity_issue87_transfers import transfer, transfer_page
from test_liquidity_spec76_cli_sit import response as spec76_response

from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.cash_forecast import CASH_STATEMENTS_EOD

pytest_plugins = ["test_liquidity_cli_sit"]

EOD_ROW = {
    "instId": "E1",
    "bankAccountAliasName": "A1",
    "currency": "USD",
    "valueDate": "20260930",
    "bankTransNo": "T1",
    "fundDirection": "Dr",
    "amount": "123.4500",
}


def eod_listing(rows):
    return lambda payload, index: spec76_response(CASH_STATEMENTS_EOD, rows)


EOD_BASE = ["--entity", "E1", "--currency", "USD"]
EOD_QUERY = ["liquidity", "cash", "statements", "end-of-day", "list"]
EOD_REFRESH = ["refresh", "liquidity", "cash", "statements", "end-of-day"]

# Equivalent canonical/legacy spellings of the same logical scope (T07/T08).
EOD_CANONICAL = [
    "--from-date",
    "2026-09-30",
    "--to-date",
    "2026-09-30",
    "--account-alias",
    "A1",
]
EOD_LEGACY = ["--from", "20260930", "--to", "20260930", "--account", "A1"]
EOD_MIXED_FORMAT = [
    "--from-date",
    "20260930",
    "--to-date",
    "2026-09-30",
    "--account-alias",
    "A1",
]

TRANSFER_QUERY = ["liquidity", "operations", "transfers", "list"]
TRANSFER_REFRESH = ["refresh", "liquidity", "operations", "transfers"]
TRANSFER_CANONICAL = ["--from-date", "2026-09-01", "--to-date", "2026-10-01"]
TRANSFER_LEGACY = ["--transaction-from", "20260901", "--transaction-to", "20261001"]


def test_legacy_seeded_eod_cache_answers_canonical_query(setup, run_cli):
    """T07: cache written through legacy flags reads back via canonical flags."""
    setup.state.business_handler = eod_listing([EOD_ROW])
    code, out, err = run_cli([*EOD_REFRESH, *EOD_BASE, *EOD_LEGACY])
    assert code == 0, err
    assert "deprecated" in err  # legacy spellings warn on stderr
    seeded = setup.cache_path.read_bytes()
    setup.state.running = False
    code, out, err = run_cli([*EOD_QUERY, *EOD_BASE, *EOD_CANONICAL, "--all"])
    assert code == 0, err
    assert err == ""  # canonical path: no deprecation noise
    result = parse(out)
    assert result["data"][0]["bankTransNo"] == "T1"
    assert result["meta"]["complete"] is True
    # No unexpected cache writes from a pure read.
    assert setup.cache_path.read_bytes() == seeded


def test_canonical_seeded_eod_cache_answers_legacy_query(setup, run_cli):
    """T07 symmetric: canonical acquisition, legacy reads hit the same scope."""
    setup.state.business_handler = eod_listing([EOD_ROW])
    code, out, err = run_cli([*EOD_REFRESH, *EOD_BASE, *EOD_CANONICAL])
    assert code == 0, err
    assert "deprecated" not in err
    setup.state.running = False
    code, out, err = run_cli([*EOD_QUERY, *EOD_BASE, *EOD_LEGACY, "--all"])
    assert code == 0
    assert "deprecated" in err
    result = parse(out)
    assert result["data"][0]["bankTransNo"] == "T1"
    assert result["meta"]["complete"] is True


def test_iso_and_compact_date_values_reach_identical_request(setup, run_cli):
    """T08: date format alone never changes the emitted native request."""
    setup.state.business_handler = eod_listing([EOD_ROW])
    code, _, err = run_cli([*EOD_REFRESH, *EOD_BASE, *EOD_CANONICAL])
    assert code == 0, err
    setup.state.business_handler = eod_listing([EOD_ROW])
    code, _, err = run_cli([*EOD_REFRESH, *EOD_BASE, *EOD_MIXED_FORMAT])
    assert code == 0, err
    first, second = setup.state.business_requests
    assert first == second


def test_transfer_legacy_and_canonical_scopes_share_cache(setup, run_cli):
    """T08: transfer day expansion is identical across spellings (T12 pair)."""
    rows = [transfer(0)]
    setup.state.business_handler = lambda payload, index: transfer_page(rows, 1)
    code, _, err = run_cli([*TRANSFER_REFRESH, *TRANSFER_LEGACY])
    assert code == 0, err
    assert "deprecated" in err
    assert setup.state.business_requests[0]
    setup.state.running = False
    code, out, err = run_cli([*TRANSFER_QUERY, *TRANSFER_CANONICAL, "--all"])
    assert code == 0, err
    assert err == ""
    assert parse(out)["data"][0]["orderNo"] == "synthetic-transfer-000"


def test_live_never_writes_cache_and_refresh_stays_explicit(setup, run_cli):
    """T08: --live reads the backend without touching the cache."""
    setup.state.business_handler = eod_listing([EOD_ROW])
    code, out, err = run_cli([*EOD_QUERY, *EOD_BASE, *EOD_CANONICAL, "--live", "--all"])
    assert code == 0, err
    assert parse(out)["meta"]["source"] == "live"
    assert not setup.cache_path.exists()


def test_invalid_arguments_never_overwrite_a_valid_cache(setup, run_cli):
    """T13: a valid cache survives invalid canonical and legacy invocations."""
    setup.state.business_handler = eod_listing([EOD_ROW])
    code, _, err = run_cli([*EOD_REFRESH, *EOD_BASE, *EOD_CANONICAL])
    assert code == 0, err
    seeded = setup.cache_path.read_bytes()
    bad_windows = (
        ["--from-date", "2026-13-01", "--to-date", "2026-09-30"],
        ["--from-date", "2026-09-30", "--to-date", "2026-09-01"],
        ["--from", "2026-09-30"],  # one-sided legacy
        ["--from-date", "2026-09-30", "--from", "20260930"],  # mixed scalar
    )
    for window in bad_windows:
        for command in (EOD_QUERY, EOD_REFRESH):
            code, out, err = run_cli(
                [*command, *EOD_BASE, "--account-alias", "A1", *window]
            )
            assert code == 2, (command, window, out)
            assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.cache_path.read_bytes() == seeded
    setup.state.running = False
    code, out, err = run_cli([*EOD_QUERY, *EOD_BASE, *EOD_CANONICAL, "--all"])
    assert code == 0, err
    assert parse(out)["data"][0]["bankTransNo"] == "T1"


def test_failed_acquisition_preserves_the_prior_cache(setup, run_cli):
    """T13: a failing refresh cannot replace a valid capture."""
    setup.state.business_handler = eod_listing([EOD_ROW])
    code, _, err = run_cli([*EOD_REFRESH, *EOD_BASE, *EOD_CANONICAL])
    assert code == 0, err
    seeded = setup.cache_path.read_bytes()

    def failing(payload, index):
        return {"status": 500, "body": {}, "error": "synthetic backend failure"}

    setup.state.business_handler = failing
    code, out, _ = run_cli(
        [*EOD_REFRESH, *EOD_BASE, *EOD_CANONICAL, "--require-complete"]
    )
    assert code != 0
    assert setup.cache_path.read_bytes() == seeded
    setup.state.running = False
    code, out, err = run_cli([*EOD_QUERY, *EOD_BASE, *EOD_CANONICAL, "--all"])
    assert code == 0, err
    assert parse(out)["data"][0]["bankTransNo"] == "T1"


def test_forecast_accuracy_virtual_variant_reads_across_spellings(setup, run_cli):
    """T07: the virtual record-date variant shares identity across spellings."""
    from test_liquidity_forecast_accuracy import ROW, handler

    setup.state.business_handler = handler([ROW])
    code, _, err = run_cli(
        [
            "refresh",
            "liquidity",
            "forecast",
            "accuracy",
            "--account",
            "TEST-ACCOUNT",
            "--record-date",
            "2026-10-05",
            "--require-complete",
        ]
    )
    assert code == 0, err
    assert "deprecated" in err
    setup.state.running = False
    code, out, err = run_cli(
        [
            "liquidity",
            "forecast",
            "accuracy",
            "list",
            "--account-alias",
            "TEST-ACCOUNT",
            "--record-date",
            "2026-10-05",
            "--all",
        ]
    )
    assert code == 0, err
    assert "deprecated" not in err
    assert parse(out)["data"][0]["id"] == ROW["id"]


def test_holdings_snapshot_scope_reads_across_date_spellings(setup, run_cli):
    """T07: an exact snapshot scope is shared by ISO and compact spellings."""
    from test_liquidity_cli_sit import holding, holdings_listing

    setup.state.business_handler = holdings_listing(
        lambda start, size: [holding(1, day="20261001")], 1
    )
    code, _, err = run_cli(
        ["refresh", "liquidity", "investment", "holdings", "--date", "20261001"]
    )
    assert code == 0, err
    seeded = setup.cache_path.read_bytes()
    setup.state.running = False
    code, out, err = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", "2026-10-01", "--all"]
    )
    assert code == 0, err
    assert parse(out)["data"][0]["investmentNo"] == "H0001"
    assert setup.cache_path.read_bytes() == seeded
