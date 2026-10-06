"""Issue #127 date-window aliases and canonical calendar dates (public CLI).

Every supported calendar-date input accepts preferred YYYY-MM-DD and legacy
compact YYYYMMDD, normalized to the existing internal compact form before
scope and request construction. Renamed date windows keep their legacy flags
as deprecated aliases: identical requests, scope keys and retained windows;
deprecation diagnostics on stderr only. All data synthetic.
"""

import json
from pathlib import Path

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]

FEE_ROW = dict(
    json.loads(
        (Path(__file__).parents[1] / "fixtures/liquidity_fee_orders.json").read_text()
    )["result"]["data"][0],
    id="synthetic-fee-1",
)


def fee_page(rows, total):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": total,
            "result": {"success": True, "count": total, "data": rows},
        },
    }


def fee_listing(rows):
    def handle(body, index):
        vo = json.loads(body["feeOrderListQueryVO"])
        assert vo["beginDate"] == "20260801"
        assert vo["endDate"] == "20260831"
        return fee_page(rows[vo["rowStart"] : vo["rowStart"] + 10], len(rows))

    return handle


@pytest.mark.parametrize(
    "window",
    [
        ["--from-date", "20260801", "--to-date", "20260831"],
        ["--from-date", "2026-08-01", "--to-date", "2026-08-31"],
        ["--from-date=2026-08-01", "--to-date=20260831"],
    ],
    ids=["compact", "iso", "equals-mixed"],
)
def test_fee_orders_iso_and_compact_windows_are_byte_identical(
    setup, run_cli, window
):
    """ISO and compact spellings select the same request, scope and cache."""
    setup.state.business_handler = fee_listing([FEE_ROW])
    code, out, err = run_cli(["refresh", "liquidity", "pricing", "fee-orders", *window])
    assert code == 0, err
    refreshed = parse(out)
    assert len(setup.state.business_requests) == 1
    code, out, err = run_cli(
        ["liquidity", "pricing", "fee-orders", "list", *window, "--live", "--all"]
    )
    assert code == 0, err
    assert parse(out)["meta"]["scope"] == refreshed["meta"]["scope"]
    assert len(setup.state.business_requests) == 2
    setup.state.reachable = False
    code, out, err = run_cli(
        ["liquidity", "pricing", "fee-orders", "list", *window, "--all"]
    )
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == [FEE_ROW]
    assert cached["meta"]["scope"] == refreshed["meta"]["scope"]
    assert len(setup.state.business_requests) == 2


def test_fee_orders_width_rule_applies_after_normalization(setup, run_cli):
    """The 1-31 calendar-day bound rejects normalized ISO windows too."""
    for window in (
        ["--from-date", "2026-08-01", "--to-date", "2026-09-01"],
        ["--from-date", "2026-08-02", "--to-date", "2026-08-01"],
        ["--from-date", "2026-08-01", "--to-date", "2026-02-30"],
    ):
        code, out, _ = run_cli(
            ["liquidity", "pricing", "fee-orders", "list", *window, "--live"]
        )
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.business_requests == []


def holdings_listing(rows):
    def handle(body, index):
        assert body["date"] == "20240229"
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": {"data": rows, "totalCount": len(rows)},
            },
        }

    return handle


@pytest.mark.parametrize("day", ["20240229", "2024-02-29"], ids=["compact", "iso"])
def test_holdings_snapshot_leap_day_normalizes_to_identical_scope(
    setup, run_cli, day
):
    row = {"investmentNo": "H0001", "valueDate": "20240229", "amount": "1.00"}
    setup.state.business_handler = holdings_listing([row])
    code, out, err = run_cli(["refresh", "liquidity", "investment", "holdings", "--date", day])
    assert code == 0, err
    refreshed = parse(out)
    setup.state.reachable = False
    code, out, err = run_cli(
        ["liquidity", "investment", "holdings", "list", "--date", day, "--all"]
    )
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == [row]
    assert cached["meta"]["scope"] == refreshed["meta"]["scope"]


@pytest.mark.parametrize(
    "day",
    ["2025-02-29", "2026-02-30", "2026-2-9", "2026101", "20261301"],
)
def test_invalid_calendar_dates_rejected_before_any_access(setup, run_cli, day):
    for argv in (
        ["liquidity", "investment", "holdings", "list", "--date", day, "--live"],
        ["refresh", "liquidity", "investment", "holdings", "--date", day],
    ):
        code, out, _ = run_cli(argv)
        assert code == 2
        envelope = parse(out)
        assert envelope["error"]["code"] == "INVALID_ARGUMENT"
        assert "--date" in envelope["error"]["message"]
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


# --- cash statements end-of-day / forecast results date-window renames ------


def eod_row(**overrides):
    return {
        "instId": "E1",
        "bankAccountAliasName": "A1",
        "currency": "USD",
        "valueDate": "20260930",
        "bankTransNo": "T1",
        "fundDirection": "Dr",
        "amount": "123.4500",
        **overrides,
    }


EOD_BASE = ["--entity", "E1", "--account", "A1", "--currency", "USD"]
EOD_CANONICAL = ["--from-date", "2026-09-30", "--to-date", "2026-09-30"]
EOD_LEGACY = ["--from", "20260930", "--to", "20260930"]


def eod_listing(rows):
    def handle(body, index):
        assert body["queryDateBegin"] == "20260930"
        assert body["queryDateEnd"] == "20260930"
        assert body["instIds"] == ["E1"]
        assert body["bankAccountAliasName"] == ["A1"]
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": {"data": rows, "totalCount": len(rows)},
            },
        }

    return handle


def eod_query(*tail, window=EOD_CANONICAL):
    return [
        "liquidity",
        "cash",
        "statements",
        "end-of-day",
        "list",
        *EOD_BASE,
        *window,
        *tail,
    ]


def eod_refresh(*tail, window=EOD_CANONICAL):
    return [
        "refresh",
        "liquidity",
        "cash",
        "statements",
        "end-of-day",
        *EOD_BASE,
        *window,
        *tail,
    ]


@pytest.mark.parametrize("window", [EOD_CANONICAL, EOD_LEGACY], ids=["canonical", "legacy"])
def test_eod_canonical_and_legacy_windows_reach_identical_request_and_cache(
    setup, run_cli, window
):
    """T02/T06/T07: both spellings emit the same body and scope identity."""
    setup.state.business_handler = eod_listing([eod_row()])
    code, out, err = run_cli(eod_refresh(window=window))
    assert code == 0, err
    refreshed = parse(out)
    assert len(setup.state.business_requests) == 1
    if window is EOD_LEGACY:
        assert "--from is deprecated; use --from-date" in err
        assert "--to is deprecated; use --to-date" in err
    else:
        assert "deprecated" not in err
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    # The other spelling reads the same retained window offline.
    other = EOD_LEGACY if window is EOD_CANONICAL else EOD_CANONICAL
    code, out, err = run_cli(eod_query("--all", window=other))
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == [eod_row()]
    assert cached["meta"]["scope"] == refreshed["meta"]["scope"]
    assert cached["meta"]["retained_coverage"]
    assert len(setup.state.business_requests) == count


def test_eod_live_iso_matches_compact_request_bytes(setup, run_cli):
    """T06: ISO and compact public values emit the identical native body."""
    setup.state.business_handler = eod_listing([])
    code, out, err = run_cli(eod_query("--live", window=EOD_CANONICAL))
    assert code == 0, err
    code, out, err = run_cli(eod_query("--live", window=EOD_LEGACY))
    assert code == 0, err
    assert len(setup.state.business_requests) == 2
    assert setup.state.business_requests[0] == setup.state.business_requests[1]


def test_eod_mixed_canonical_and_legacy_scalar_is_rejected(setup, run_cli):
    """T10: one scalar bound through both spellings is INVALID_ARGUMENT."""
    for mixed, canonical in (
        (
            ["--from-date", "2026-09-30", "--from", "20260930", "--to-date", "20260930"],
            "--from-date",
        ),
        (
            ["--from-date", "20260930", "--to-date", "20260930", "--to", "2026-09-30"],
            "--to-date",
        ),
    ):
        for argv in (eod_query("--live", window=mixed), eod_refresh(window=mixed)):
            code, out, _ = run_cli(argv)
            assert code == 2
            envelope = parse(out)
            assert envelope["error"]["code"] == "INVALID_ARGUMENT"
            assert canonical in envelope["error"]["message"]
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


def test_eod_help_names_canonical_flags_and_value_date_axis(setup, run_cli):
    code, out, err = run_cli(
        ["help", "liquidity", "cash", "statements", "end-of-day", "list"]
    )
    assert code == 0, err
    options = {option["name"]: option for option in parse(out)["options"]}
    assert options["from"]["flags"] == ["--from-date", "--from"]
    assert options["to"]["flags"] == ["--to-date", "--to"]
    assert "value date" in options["from"]["summary"]
    assert "value date" in options["to"]["summary"]
    assert setup.state.business_requests == []


FORECAST_CANONICAL = ["--from-date", "2026-10-01", "--to-date", "2026-10-01"]
FORECAST_LEGACY = ["--from", "20261001", "--to", "20261001"]


def forecast_row(**overrides):
    return {
        "id": "F1",
        "bankAccountAliasName": "A1",
        "currency": "USD",
        "valueDate": "20261001",
        "baseValueDate": "20260930",
        "forecastBalance": "123.4500",
        "gmtCreate": 100,
        "recordCreateTime": "unconverted",
        **overrides,
    }


def forecast_listing(rows):
    def handle(body, index):
        vo = json.loads(body["bankCashForecastRecordQueryVo"])
        assert vo["valueStartDay"] == "20261001"
        assert vo["valueEndDay"] == "20261001"
        assert vo["recordStartTime"] == "000000"
        assert vo["recordEndTime"] == "235959"
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": len(rows),
                "result": {
                    "success": True,
                    "dataValue": rows,
                    "count": len(rows),
                },
            },
        }

    return handle


@pytest.mark.parametrize(
    "window", [FORECAST_CANONICAL, FORECAST_LEGACY], ids=["canonical", "legacy"]
)
def test_forecast_results_canonical_legacy_and_defaults_are_identical(
    setup, run_cli, window
):
    """Both spellings keep the existing compact window and clock defaults."""
    setup.state.business_handler = forecast_listing([forecast_row()])
    code, out, err = run_cli(
        ["refresh", "liquidity", "forecast", "results", *window]
    )
    assert code == 0, err
    refreshed = parse(out)
    if window is FORECAST_LEGACY:
        assert "deprecated" in err
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    other = FORECAST_LEGACY if window is FORECAST_CANONICAL else FORECAST_CANONICAL
    code, out, err = run_cli(
        ["liquidity", "forecast", "results", "list", *other, "--all"]
    )
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == [forecast_row()]
    assert cached["meta"]["scope"] == refreshed["meta"]["scope"]
    assert len(setup.state.business_requests) == count
