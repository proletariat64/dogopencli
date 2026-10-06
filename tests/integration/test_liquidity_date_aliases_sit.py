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


# --- operations transfers date-window rename --------------------------------

TRANSFER_CANONICAL = ["--from-date", "2026-09-01", "--to-date", "2026-10-01"]
TRANSFER_LEGACY = ["--transaction-from", "20260901", "--transaction-to", "20261001"]


def transfer_row(**overrides):
    return {
        "orderNo": "synthetic-transfer-001",
        "tntInstId": "GUAPW3SG",
        "gmtCreate": "2026-10-01 08:06:29（GMT+08）",
        "debitValueDate": "20260930",
        "creditValueDate": "20261001",
        "debitCurrency": "USD",
        "creditCurrency": "EUR",
        "debitAmount": "123.4500",
        "creditAmount": "111.0000",
        "orderStatus": "unknown-instruction-state",
        "receiptStatus": "unknown-bank-state",
        "executeResult": "unknown-execution-state",
        **overrides,
    }


def transfer_listing(rows):
    def handle(body, index):
        vo = json.loads(body["transferOrderQueryRequestVO"])
        # Day-start/day-end expansion is preserved exactly.
        assert vo["transactionStartDate"] == "2026-09-01 00:00:00"
        assert vo["transactionEndDate"] == "2026-10-01 23:59:59"
        offset = vo["rowStart"]
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": len(rows),
                "result": {
                    "success": True,
                    "data": rows[offset : offset + 10],
                    "count": len(rows),
                },
            },
        }

    return handle


@pytest.mark.parametrize(
    "window", [TRANSFER_CANONICAL, TRANSFER_LEGACY], ids=["canonical", "legacy"]
)
def test_transfers_window_spellings_expand_identically_and_share_cache(
    setup, run_cli, window
):
    """T06/T07: exact history scope and day expansion survive the rename."""
    setup.state.business_handler = transfer_listing([transfer_row()])
    code, out, err = run_cli(
        ["refresh", "liquidity", "operations", "transfers", *window]
    )
    assert code == 0, err
    refreshed = parse(out)
    if window is TRANSFER_LEGACY:
        assert "--transaction-from is deprecated; use --from-date" in err
        assert "--transaction-to is deprecated; use --to-date" in err
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    other = TRANSFER_LEGACY if window is TRANSFER_CANONICAL else TRANSFER_CANONICAL
    code, out, err = run_cli(
        ["liquidity", "operations", "transfers", "list", *other, "--all"]
    )
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == [transfer_row()]
    assert cached["meta"]["scope"] == refreshed["meta"]["scope"]
    assert len(setup.state.business_requests) == count


@pytest.mark.parametrize(
    "window,canonical,legacy_named",
    [
        # Argparse required-argument errors list every spelling, canonical first.
        (["--from-date", "2026-09-01"], "--to-date", True),
        (["--to-date", "2026-10-01"], "--from-date", True),
        # Scope validation errors identify canonical flags only.
        (["--from-date", "2026-10-02", "--to-date", "2026-10-01"], "--from-date", False),
        (["--from-date", "2026-02-30", "--to-date", "2026-10-01"], "--from-date", False),
    ],
    ids=["one-sided-from", "one-sided-to", "reversed", "invalid-day"],
)
def test_transfers_window_violations_name_canonical_flags(
    setup, run_cli, window, canonical, legacy_named
):
    for argv in (
        ["liquidity", "operations", "transfers", "list", *window, "--live"],
        ["refresh", "liquidity", "operations", "transfers", *window],
    ):
        code, out, _ = run_cli(argv)
        assert code == 2
        envelope = parse(out)
        assert envelope["error"]["code"] == "INVALID_ARGUMENT"
        message = envelope["error"]["message"]
        assert canonical in message
        if not legacy_named:
            assert "--transaction-from" not in message
            assert "--transaction-to" not in message
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


# --- operations swaps date-window rename ------------------------------------

SWAP_CANONICAL = ["--from-date", "2026-09-01", "--to-date", "2026-10-01"]
SWAP_LEGACY = ["--trade-from", "20260901", "--trade-to", "20261001"]


def swap_row(**overrides):
    return {
        "dealId": "synthetic-swap-001",
        "tntInstId": "GUAPW3SG",
        "tradeDate": "20260930",
        "nearLegValueDate": "20261002",
        "farLegValueDate": "20261102",
        "nearLegDebitCcy": "USD",
        "nearLegCreditCcy": "EUR",
        "nearLegDebitAmount": "123.4500",
        "nearLegCreditAmount": "111.0000",
        "farLegDebitAmount": "111.0000",
        "farLegCreditAmount": "123.4500",
        "nearLegFxRate": "0.899149",
        "farLegFxRate": "0.899149",
        "status": "source-state",
        "gmtCreate": 1759190400000,
        "gmtModified": 1759190400000,
        "gmtSend": None,
        "gmtReturn": None,
        "needReview": False,
        "nodeNum": 0,
        **overrides,
    }


def swap_listing(rows):
    def handle(body, index):
        vo = json.loads(body["swapOrderQueryVO"])
        # The inclusive trade-date pair stays compact on the wire.
        assert vo["tradeStartDate"] == "20260901"
        assert vo["tradeEndDate"] == "20261001"
        offset = vo["rowStart"]
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "result": {
                    "success": True,
                    "swapOrderVOList": rows[offset : offset + 10],
                    "count": len(rows),
                },
            },
        }

    return handle


@pytest.mark.parametrize(
    "window", [SWAP_CANONICAL, SWAP_LEGACY], ids=["canonical", "legacy"]
)
def test_swaps_window_spellings_keep_identical_scope_and_cache(
    setup, run_cli, window
):
    setup.state.business_handler = swap_listing([swap_row()])
    code, out, err = run_cli(["refresh", "liquidity", "operations", "swaps", *window])
    assert code == 0, err
    refreshed = parse(out)
    if window is SWAP_LEGACY:
        assert "--trade-from is deprecated; use --from-date" in err
        assert "--trade-to is deprecated; use --to-date" in err
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    other = SWAP_LEGACY if window is SWAP_CANONICAL else SWAP_CANONICAL
    code, out, err = run_cli(
        ["liquidity", "operations", "swaps", "list", *other, "--all"]
    )
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == [swap_row()]
    assert cached["meta"]["scope"] == refreshed["meta"]["scope"]
    assert len(setup.state.business_requests) == count


@pytest.mark.parametrize(
    "window,fragment",
    [
        (["--from-date", "2026-09-01"], "--to-date"),
        (["--from-date", "2026-10-02", "--to-date", "2026-10-01"], "after its end"),
    ],
    ids=["one-sided", "reversed"],
)
def test_swaps_window_violations_rejected_before_access(
    setup, run_cli, window, fragment
):
    for argv in (
        ["liquidity", "operations", "swaps", "list", *window, "--live"],
        ["refresh", "liquidity", "operations", "swaps", *window],
    ):
        code, out, _ = run_cli(argv)
        assert code == 2
        envelope = parse(out)
        assert envelope["error"]["code"] == "INVALID_ARGUMENT"
        assert fragment in envelope["error"]["message"]
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


# --- investment strategy-results date-window rename --------------------------

STRATEGY_CANONICAL = ["--from-date", "2026-10-01", "--to-date", "2026-10-04"]
STRATEGY_LEGACY = ["--trigger-from", "20261001", "--trigger-to", "20261004"]


def strategy_row(task_type, **overrides):
    return {
        "id": "synthetic-task-0",
        "taskType": task_type,
        "triggerDate": 1790899200000,  # 2026-10-02 UTC, same GMT+08 business day
        "resultTime": None,
        "valueDate": "20261002",
        "expectedInvestStartDate": "20261002",
        "expectedInvestEndDate": "20261003",
        "fundDecisionStrategyId": "synthetic-fund",
        "investmentPortfolioStrategyId": "",
        "mainStrategyId": "synthetic-main",
        "investmentAmount": "10.0000",
        "maximumExceptedIncome": "",
        "maximumExpectedRateOfReturn": "0",
        "taskStatus": "future-native-state",
        "adoptionStatus": "future-native-adoption",
        "triggerType": "source-type",
        **overrides,
    }


def strategy_listing(rows, task_type):
    def handle(body, index):
        # Inclusive dates expand to native GMT+08 day bounds on the wire.
        assert body["taskType"] == task_type
        assert body["triggerStartDate"] == "2026-10-01 00:00:00"
        assert body["triggerEndDate"] == "2026-10-04 23:59:59"
        offset = body["rowStart"]
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": {
                    "data": rows[offset : offset + 10],
                    "totalCount": len(rows),
                },
            },
        }

    return handle


@pytest.mark.parametrize("task_type", ["FUND_DECISION_TASK", "PRODUCT_DECISION_TASK"])
@pytest.mark.parametrize(
    "window", [STRATEGY_CANONICAL, STRATEGY_LEGACY], ids=["canonical", "legacy"]
)
def test_strategy_results_variants_keep_gmt8_expansion_and_shared_cache(
    setup, run_cli, task_type, window
):
    """FUND/PRODUCT variants, inclusive dates and expansion are preserved."""
    rows = [strategy_row(task_type)]
    setup.state.business_handler = strategy_listing(rows, task_type)
    scope = ["--task-type", task_type, *window]
    code, out, err = run_cli(
        ["refresh", "liquidity", "investment", "strategy-results", *scope]
    )
    assert code == 0, err
    refreshed = parse(out)
    if window is STRATEGY_LEGACY:
        assert "--trigger-from is deprecated; use --from-date" in err
        assert "--trigger-to is deprecated; use --to-date" in err
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    other = STRATEGY_LEGACY if window is STRATEGY_CANONICAL else STRATEGY_CANONICAL
    code, out, err = run_cli(
        [
            "liquidity",
            "investment",
            "strategy-results",
            "list",
            "--task-type",
            task_type,
            *other,
            "--all",
        ]
    )
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == rows
    assert cached["meta"]["scope"] == refreshed["meta"]["scope"]
    assert len(setup.state.business_requests) == count


def test_strategy_results_reversed_pair_names_canonical_flags(setup, run_cli):
    window = ["--from-date", "2026-10-05", "--to-date", "2026-10-04"]
    for argv in (
        ["liquidity", "investment", "strategy-results", "list",
         "--task-type", "FUND_DECISION_TASK", *window, "--live"],
        ["refresh", "liquidity", "investment", "strategy-results",
         "--task-type", "FUND_DECISION_TASK", *window],
    ):
        code, out, _ = run_cli(argv)
        assert code == 2
        envelope = parse(out)
        assert envelope["error"]["code"] == "INVALID_ARGUMENT"
        assert "--trigger-from" not in envelope["error"]["message"]
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


def test_strategy_help_renamed_but_rule_status_keeps_trigger_prefix(setup, run_cli):
    code, out, err = run_cli(["help", "liquidity", "investment", "strategy-results", "list"])
    assert code == 0, err
    options = {option["name"]: option for option in parse(out)["options"]}
    assert options["trigger_from"]["flags"] == ["--from-date", "--trigger-from"]
    assert options["trigger_to"]["flags"] == ["--to-date", "--trigger-to"]
    assert "trigger" in options["trigger_from"]["summary"]
    code, out, err = run_cli(["help", "liquidity", "operations", "rule-status", "list"])
    assert code == 0, err
    options = {option["name"]: option for option in parse(out)["options"]}
    # The rule-status expected-trigger interval is a full datetime pair and
    # keeps its business prefix (Issue #127 rename table).
    assert options["trigger_from"]["flags"] == ["--trigger-from"]
    assert options["trigger_to"]["flags"] == ["--trigger-to"]
    assert setup.state.business_requests == []
