"""Refresh-hint canonical reconstruction and round-trip acceptance (#132).

Cache-miss hints must emit canonical flags with public-format values,
shell-quoted, reconstructing the resolved scope rather than printing
transformed native values (Issue #127 decision 13, acceptance T12). Each
hint is obtained from a real cache-miss path, split as shell arguments,
executed against the fake transport, and the resulting cache answers the
original canonical query. Row builders reuse the existing per-leaf SIT
fixtures. All offline; no network or browser access.
"""

import re
import shlex

from test_liquidity_account_capacity_cli_sit import capacity
from test_liquidity_account_capacity_cli_sit import response as capacity_response
from test_liquidity_batch_c_cli import page as batch_page
from test_liquidity_batch_c_cli import strategy
from test_liquidity_issue87_decisions import decision
from test_liquidity_issue87_decisions import page as decision_page
from test_liquidity_issue87_transfers import transfer, transfer_page
from test_liquidity_rule_status import record as rule_record
from test_liquidity_rule_status import response as rule_response
from test_liquidity_spec76_cli_sit import response as spec76_response

from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.cash_forecast import FORECAST_RESULTS

pytest_plugins = ["test_liquidity_cli_sit"]

HINT = re.compile(r"run: (dogopencli refresh [^\n]+)")


def miss_hint(out):
    """Extract the generated refresh hint from a CACHE_MISS envelope."""
    message = parse(out)["error"]["message"]
    match = HINT.search(message)
    assert match, message
    return shlex.split(match.group(1))


def roundtrip(setup, run_cli, query, expect_hint=()):
    """Cache-miss the query, execute its hint, then re-read offline."""
    code, out, _ = run_cli(query)
    assert code != 0
    hint = miss_hint(out)
    for token in expect_hint:
        assert token in hint
    code, out, err = run_cli(hint[1:])
    assert code == 0, err
    setup.state.running = False
    code, out, err = run_cli(query)
    assert code == 0, err
    return hint, parse(out)


def test_transfer_hint_uses_calendar_dates_and_round_trips(setup, run_cli):
    """Expanded native day bounds must invert to calendar dates (T12)."""
    setup.state.business_handler = lambda payload, index: transfer_page(
        [transfer(0)], 1
    )
    query = [
        "liquidity",
        "operations",
        "transfers",
        "list",
        "--from-date",
        "2026-09-01",
        "--to-date",
        "2026-10-01",
        "--all",
    ]
    hint, result = roundtrip(
        setup,
        run_cli,
        query,
        expect_hint=("--from-date", "2026-09-01", "--to-date", "2026-10-01"),
    )
    assert hint[1:5] == ["refresh", "liquidity", "operations", "transfers"]
    assert not any("00:00:00" in token or "23:59:59" in token for token in hint)
    assert result["data"][0]["orderNo"] == "synthetic-transfer-000"


def test_decisions_hint_prints_canonical_T_datetimes(setup, run_cli):
    """Unknown-zone datetimes print the offset-free T form (T12)."""
    setup.state.business_handler = lambda payload, index: decision_page(
        [decision(0)], 1
    )
    query = [
        "liquidity",
        "operations",
        "decisions",
        "list",
        "--start-from",
        "2026-09-01T00:00:00",
        "--start-to",
        "2026-09-30T23:59:59",
        "--created-from",
        "2026-09-01T00:00:00",
        "--created-to",
        "2026-09-30T23:59:59",
        "--all",
    ]
    hint, result = roundtrip(
        setup, run_cli, query, expect_hint=("2026-09-01T00:00:00",)
    )
    assert not any(" " in token for token in hint)
    assert result["data"][0]["reportId"] == "shared-report"


def test_rule_status_hint_prints_canonical_Z_datetimes(setup, run_cli):
    """Known-UTC rule-status bounds print the preferred Z form (T12)."""
    setup.state.business_handler = lambda payload, index: rule_response(
        [rule_record(0)]
    )
    query = [
        "liquidity",
        "operations",
        "rule-status",
        "list",
        "--trigger-from",
        "2026-01-01T00:00:00Z",
        "--trigger-to",
        "2026-01-31T23:59:59Z",
        "--all",
    ]
    hint, result = roundtrip(
        setup,
        run_cli,
        query,
        expect_hint=("2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z"),
    )
    assert result["data"][0]["ruleId"] == "synthetic-rule-0"


def test_account_capacity_hint_repeats_and_quotes_aliases(setup, run_cli):
    """Repeated aliases stay repeated; shell-special values are quoted (T12)."""
    tricky = "ALIAS WITH SPACE$AND*GLOB"
    setup.state.business_handler = lambda payload, index: capacity_response(
        capacity(payload["aliasName"])
    )
    query = [
        "liquidity",
        "risk",
        "account-capacity",
        "list",
        "--account-alias",
        tricky,
        "--account-alias",
        "SYN-A",
        "--all",
    ]
    hint, result = roundtrip(setup, run_cli, query)
    assert hint.count("--account-alias") == 2
    assert tricky in hint  # shlex.split already removed the quoting
    aliases = sorted(request["aliasName"] for request in setup.state.business_requests)
    assert aliases == sorted([tricky, "SYN-A"])
    assert sorted(row["aliasName"] for row in result["data"]) == aliases


def test_strategy_hint_preserves_task_type_selector_variant(setup, run_cli):
    """The required contract selector survives into the hint (T12)."""
    setup.state.business_handler = lambda payload, index: batch_page([strategy(0)], 1)
    query = [
        "liquidity",
        "investment",
        "strategy-results",
        "list",
        "--task-type",
        "FUND_DECISION_TASK",
        "--from-date",
        "2026-10-01",
        "--to-date",
        "2026-10-04",
        "--all",
    ]
    hint, result = roundtrip(
        setup,
        run_cli,
        query,
        expect_hint=("--task-type", "FUND_DECISION_TASK", "--from-date", "2026-10-01"),
    )
    assert len(result["data"]) == 1


def test_forecast_results_hint_canonicalizes_dates_and_clocks(setup, run_cli):
    """Compact internal dates/clocks print in canonical public forms (T12)."""
    row = {
        "id": "F1",
        "bankAccountAliasName": "A1",
        "currency": "USD",
        "valueDate": "20261001",
        "forecastBalance": "10.00",
    }
    setup.state.business_handler = lambda payload, index: spec76_response(
        FORECAST_RESULTS, [row]
    )
    query = [
        "liquidity",
        "forecast",
        "results",
        "list",
        "--from-date",
        "20261001",
        "--to-date",
        "20261001",
        "--account-alias",
        "A1",
        "--all",
    ]
    hint, result = roundtrip(
        setup,
        run_cli,
        query,
        expect_hint=("--from-date", "2026-10-01", "--account-alias", "A1"),
    )
    assert "00:00:00" in hint and "23:59:59" in hint
    assert not any(token == "20261001" for token in hint)
    assert not any(token in ("000000", "235959") for token in hint)
    assert result["data"][0]["id"] == "F1"


def test_cash_accounts_local_filter_never_reaches_refresh_hint(setup, run_cli):
    """List-only result filters stay off refresh hints (spec decision 13)."""
    row = {"id": "A1", "aliasName": "SYN-A", "accountNo": "9001", "currency": "USD"}
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"bankAccountPropertyVOList": [row]},
            "count": 1,
        },
    }
    query = ["liquidity", "cash", "accounts", "list", "--account-alias", "SYN-A"]
    hint, result = roundtrip(setup, run_cli, query)
    assert "--account-alias" not in hint
    assert "--alias" not in hint
    assert result["data"][0]["aliasName"] == "SYN-A"
