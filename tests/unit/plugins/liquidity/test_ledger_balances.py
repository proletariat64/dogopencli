"""Ledger balance retirement at public discovery and execution seams."""

from dogopencli.jsonutil import parse


def test_ledger_balances_retired(run_cli):
    code, out, err = run_cli(["liquidity", "ledger", "balances", "list"])
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
