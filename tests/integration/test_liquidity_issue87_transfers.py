"""Issue #87 transfer candidate acceptance through the existing public CLI seam.

Synthetic values follow observed native field shapes. Candidate registration
exercises public behavior while the production release gate remains closed.
"""

import json
from dataclasses import replace

import pytest

from dogopencli import catalog, helptree
from dogopencli.plugins.liquidity import leaves
from dogopencli.plugins.liquidity.transfer_list import TRANSFER_ORDERS

pytest_plugins = ["test_liquidity_cli_sit"]

TRANSACTION_SCOPE = ["--from-date", "20260901", "--to-date", "20261001"]


@pytest.fixture
def transfer_candidate_catalog(monkeypatch):
    """Candidate behavior is testable without bypassing the production gate."""
    declarations = {
        path: replace(node, children=()) for path, node in catalog.NODES.items()
    }
    leaf = leaves.ListLeaf((TRANSFER_ORDERS,))
    monkeypatch.setitem(leaves.LIST_LEAVES, TRANSFER_ORDERS.path, leaf)
    monkeypatch.delitem(
        leaves.DEFERRED_BY_PATH, (*TRANSFER_ORDERS.path, "list"), raising=False
    )
    monkeypatch.setattr(
        leaves,
        "LIST_SPECS",
        (
            *tuple(
                spec for spec in leaves.LIST_SPECS if spec.name != TRANSFER_ORDERS.name
            ),
            TRANSFER_ORDERS,
        ),
    )
    for node in (
        leaves.list_query_node(leaf),
        leaves.refresh_list_node(leaf),
        *leaves.group_nodes(),
    ):
        declarations[node.path] = node
    nodes = catalog.build_catalog(declarations.values())
    monkeypatch.setattr(catalog, "NODES", nodes)
    monkeypatch.setattr(helptree, "NODES", nodes)


def transfer(index, **overrides):
    return {
        "orderNo": f"synthetic-transfer-{index:03d}",
        "orderId": f"internal-{index}",
        "reportId": "associated-report",
        "tntInstId": "GUAPW3SG",
        "gmtCreate": "2026-10-01 08:06:29（GMT+08）",
        "gmtModified": "",
        "debitValueDate": "20260930",
        "creditValueDate": "20261001",
        "debitEntity": "entity-D",
        "creditEntity": "entity-C",
        "debitBankId": "bank-D",
        "creditBankId": "bank-C",
        "debitCurrency": "USD",
        "creditCurrency": "EUR",
        "debitAmount": "123.4500",
        "creditAmount": "111.0000",
        "orderStatus": "unknown-instruction-state",
        "receiptStatus": "unknown-bank-state",
        "executeResult": "unknown-execution-state",
        "gmtReturnFinnet": None,
        **overrides,
    }


def transfer_page(rows, total):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": total,
            "result": {"success": True, "data": rows, "count": total},
        },
    }


def transfer_listing(rows):
    def answer(payload, index):
        assert set(payload) == {"tntInstId", "transferOrderQueryRequestVO"}
        assert payload["tntInstId"] == "GUAPW3SG"
        scope = json.loads(payload["transferOrderQueryRequestVO"])
        assert set(scope) == {
            "tntInstId",
            "debitEntity",
            "creditEntity",
            "transactionStartDate",
            "transactionEndDate",
            "debitStartDate",
            "debitEndDate",
            "creditStartDate",
            "creditEndDate",
            "pageSize",
            "rowStart",
        }
        assert scope["tntInstId"] == "GUAPW3SG"
        assert scope["debitEntity"] == scope["creditEntity"] == []
        assert scope["pageSize"] == 10
        assert scope["transactionStartDate"] == "2026-09-01 00:00:00"
        assert scope["transactionEndDate"] == "2026-10-01 23:59:59"
        assert scope["debitStartDate"] == scope["debitEndDate"] == ""
        assert scope["creditStartDate"] == scope["creditEndDate"] == ""
        offset = scope["rowStart"]
        return transfer_page(rows[offset : offset + 10], len(rows))

    return answer


def transfer_query(*tail):
    return [
        "liquidity",
        "operations",
        "transfers",
        "list",
        *(TRANSACTION_SCOPE if "--live" in tail else ()),
        *tail,
    ]


def transfer_refresh(*tail):
    return [
        "refresh",
        "liquidity",
        "operations",
        "transfers",
        *TRANSACTION_SCOPE,
        *tail,
    ]
