"""Account ownership through public CLI, fake CDP and temporary datasets."""

import os
from pathlib import Path

import pytest

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "forecast", "account_demands"]
DATES = ["--from-date", "20261009", "--to-date", "20261015"]
EXPLICIT = ["--alias", "SYN-A", "--entity", "SYN-E", "--bank", "SYN-B"]


def demand(entity="SYN-E", bank="SYN-B"):
    return {
        "id": "D1",
        "aliasName": "SYN-A",
        "entity": entity,
        "bankID": bank,
        "amount": "123.000001",
        "expectValueDate": "20261012",
    }


def demands_handler(row=None):
    row = demand() if row is None else row

    def answer(payload, index):
        assert payload["entity"] == row["entity"]
        assert payload["bankId"] == row["bankID"]
        assert payload["aliasName"] == "SYN-A"
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": {
                    "data": [row] if payload["rowStart"] == 0 else [],
                    "totalCount": 1,
                },
            },
        }

    return answer


def configure_accounts(setup, rows=None, *, missing=False):
    config = Path(os.environ["DOGOPENCLI_CONFIG"])
    database = setup.tmp_path / "accounts.duckdb"
    if not missing:
        duckdb = pytest.importorskip("duckdb")
        with duckdb.connect(str(database)) as connection:
            connection.execute(
                'CREATE TABLE accounts ("aliasName" VARCHAR, "instId" VARCHAR, '
                '"bankId" VARCHAR)'
            )
            for row in rows or []:
                connection.execute("INSERT INTO accounts VALUES (?, ?, ?)", list(row))
    with config.open("a") as stream:
        stream.write(
            f'\n[duckdog]\npath="{database}"\n[duckdog.selectors]\n"liquidity/cash/accounts"="accounts"\n'
        )
