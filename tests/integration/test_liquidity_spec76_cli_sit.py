"""Spec #76 candidates: public CLI, fake CDP and independent SQLite caches."""

import json
from dataclasses import replace

import pytest

from dogopencli import catalog, helptree
from dogopencli.plugins.liquidity import leaves
from dogopencli.plugins.liquidity.cash_forecast import (
    ACCEPTED_LIST_SPECS,
    CASH_BALANCES,
    CASH_CREDIT_LINES,
    CASH_GROUP_BALANCES,
    CASH_POOLS,
    CASH_POOLS_GET,
    CASH_STATEMENTS_EOD,
    FORECAST_RESULTS,
)

# Reuse synthetic browser/config fixtures without registering a real transport.
pytest_plugins = ["test_liquidity_cli_sit"]


@pytest.fixture(autouse=True)
def candidate_catalog(monkeypatch):
    """Test candidate declarations without changing the production UAT gate."""
    declarations = {
        path: replace(node, children=()) for path, node in catalog.NODES.items()
    }
    grouped = {}
    for item in ACCEPTED_LIST_SPECS:
        grouped.setdefault(item.path, []).append(item)
    for variants in grouped.values():
        item = variants[0]
        leaf = leaves.ListLeaf(tuple(variants))
        monkeypatch.setitem(leaves.LIST_LEAVES, item.path, leaf)
        monkeypatch.delitem(
            leaves.DEFERRED_BY_PATH, (*item.path, "list"), raising=False
        )
        for node in (leaves.list_query_node(leaf), leaves.refresh_list_node(leaf)):
            declarations[node.path] = node
    leaf = leaves.DetailLeaf(CASH_POOLS_GET)
    monkeypatch.setattr(leaves, "DETAIL_SPECS", (*leaves.DETAIL_SPECS, CASH_POOLS_GET))
    monkeypatch.setattr(
        leaves, "LIST_SPECS", (*leaves.LIST_SPECS, *ACCEPTED_LIST_SPECS)
    )
    monkeypatch.setitem(leaves.DETAIL_LEAVES, leaf.path, leaf)
    monkeypatch.delitem(leaves.DEFERRED_BY_PATH, leaf.path, raising=False)
    for node in (
        leaves.detail_query_node(leaf),
        *leaves.group_nodes(),
    ):
        declarations[node.path] = node
    nodes = catalog.build_catalog(declarations.values())
    monkeypatch.setattr(catalog, "NODES", nodes)
    monkeypatch.setattr(helptree, "NODES", nodes)


def synthetic_balance_id(row):
    account = [row.get(field) for field in ("entity", "aliasName", "currency")]
    return f"synthetic:{json.dumps(account, separators=(',', ':'), ensure_ascii=True)}"


def expected_balance_record(entity, alias, currency, balance):
    return {
        "balance_record_id": synthetic_balance_id(
            {"entity": entity, "aliasName": alias, "currency": currency}
        ),
        "account_holder_entity_id": entity,
        "account_alias": alias,
        "currency": currency,
        "current_balance": balance,
    }


def response(item, rows, total=None):
    if item is CASH_BALANCES:
        rows = [
            row if "balId" in row else {**row, "balId": synthetic_balance_id(row)}
            for row in rows
        ]
    total = len(rows) if total is None else total
    if item.envelope == "success":
        body = {"success": True, "data": {"data": rows, "totalCount": total}}
    else:
        key = item.container[-1]
        body = {
            "resultFlag": True,
            "count": total,
            "result": {"success": True, key: rows, "count": total},
        }
    return {"status": 200, "body": body}


CASES = [
    (
        CASH_BALANCES,
        ["--entity", "E1", "--account-alias", "A1"],
        {
            "entity": "E1",
            "aliasName": "A1",
            "currency": "USD",
            "curBalance": "123.4500",
            "statementCreateTime": "",
            "timeZone": "GMT+08",
        },
    ),
    (
        CASH_GROUP_BALANCES,
        ["--group-code", "G1"],
        {
            "id": "G1",
            "currentBalance": "123.4500",
            "memberList": [
                {
                    "id": "M1",
                    "aliasName": "A1",
                    "currentBalanceTime": "",
                    "forecastTime": None,
                    "equiCurrentBalance": "123.4500",
                }
            ],
        },
    ),
    (
        CASH_POOLS,
        [],
        {
            "id": "P1",
            "cashPoolCategory": "BANK",
            "cashPoolName": "pool",
            "curBalance": "900",
            "cashPoolMemberVOS": [
                {"id": "M1", "aliasName": "A1", "availableAmount": "900"}
            ],
        },
    ),
    (
        CASH_CREDIT_LINES,
        [],
        {
            "id": "C1",
            "currency": "USD",
            "amount": "123.4500",
            "usedAmount": "900",
            "bankAccountCreditLineList": [
                {"id": "M1", "aliasName": "A1", "usedAmount": "900"}
            ],
        },
    ),
    (
        CASH_STATEMENTS_EOD,
        [
            "--entity",
            "E1",
            "--account-alias",
            "A1",
            "--currency",
            "USD",
            "--from-date",
            "20260930",
            "--to-date",
            "20260930",
        ],
        {
            "instId": "E1",
            "bankAccountAliasName": "A1",
            "currency": "USD",
            "valueDate": "20260930",
            "bankTransNo": "T1",
            "fundDirection": "Dr",
            "amount": "123.4500",
        },
    ),
    (
        FORECAST_RESULTS,
        ["--from-date", "20261001", "--to-date", "20261001", "--account-alias", "A1"],
        {
            "id": "F1",
            "bankAccountAliasName": "A1",
            "currency": "USD",
            "valueDate": "20261001",
            "baseValueDate": "20260930",
            "forecastBalance": "123.4500",
            "gmtCreate": 100,
            "recordCreateTime": "unconverted",
        },
    ),
]
