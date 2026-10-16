"""Issue #98 pool balances: native shape, synthetic values, public CLI seam."""

import json
from pathlib import Path

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
QUERY = ["liquidity", "cash", "pool-balances", "list", "--limit", "0"]
REFRESH = ["refresh", "liquidity", "cash", "pool-balances"]
FIXTURE = Path(__file__).parents[1] / "fixtures/liquidity/pool-balances.json"


def pool():
    return json.loads(FIXTURE.read_text())


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


def seed(setup, run_cli, rows=None):
    rows = [pool()] if rows is None else rows
    setup.state.business_handler = lambda payload, index: response(rows)
    code, out, err = run_cli(REFRESH)
    assert code == 0, err
    return parse(out)
