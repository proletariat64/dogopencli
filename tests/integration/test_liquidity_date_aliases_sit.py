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
