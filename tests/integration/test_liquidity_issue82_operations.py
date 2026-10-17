"""Issue #82 release prerequisites through the existing public CLI seam.

The empty historical inquiries are not runnable list contracts. These tests
exercise the gate without inventing native records or passing production UAT.
"""

import json
from dataclasses import replace

import pytest

from dogopencli import catalog
from dogopencli.plugins.liquidity import leaves
from dogopencli.plugins.liquidity.operations_batch import SWAP_ORDERS

pytest_plugins = ["test_liquidity_cli_sit"]

OPERATIONS = ("executions",)
TRADE_SCOPE = ["--from-date", "20260901", "--to-date", "20261001"]


@pytest.fixture
def swap_candidate_catalog(monkeypatch):
    """Candidate behavior is testable without bypassing the production gate."""
    declarations = {
        path: replace(node, children=()) for path, node in catalog.NODES.items()
    }
    leaf = leaves.ListLeaf((SWAP_ORDERS,))
    monkeypatch.setitem(leaves.LIST_LEAVES, SWAP_ORDERS.path, leaf)
    monkeypatch.delitem(
        leaves.DEFERRED_BY_PATH, (*SWAP_ORDERS.path, "list"), raising=False
    )
    monkeypatch.setattr(leaves, "LIST_SPECS", (*leaves.LIST_SPECS, SWAP_ORDERS))
    for node in (
        leaves.list_query_node(leaf),
        leaves.refresh_list_node(leaf),
        *leaves.group_nodes(),
    ):
        declarations[node.path] = node
    nodes = catalog.build_catalog(declarations.values())
    monkeypatch.setattr(catalog, "NODES", nodes)


def swap(index, **overrides):
    return {
        "dealId": f"synthetic-swap-{index:03d}",
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


def swap_page(rows, total):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"success": True, "swapOrderVOList": rows, "count": total},
        },
    }


def swap_listing(rows):
    def answer(payload, index):
        assert set(payload) == {"tntInstId", "swapOrderQueryVO"}
        assert payload["tntInstId"] == "GUAPW3SG"
        scope = json.loads(payload["swapOrderQueryVO"])
        assert scope["tntInstId"] == "GUAPW3SG"
        assert scope["nearLegDebitEntity"] == []
        assert scope["nearLegCreditEntity"] == []
        assert scope["pageSize"] == 10
        assert scope["tradeStartDate"] == "20260901"
        assert scope["tradeEndDate"] == "20261001"
        assert scope["nearLegStartDate"] == scope["nearLegEndDate"] == ""
        assert scope["farLegStartDate"] == scope["farLegEndDate"] == ""
        offset = scope["rowStart"]
        return swap_page(rows[offset : offset + 10], len(rows))

    return answer


def swap_query(*tail):
    return [
        "liquidity",
        "operations",
        "swaps",
        "list",
        *(TRADE_SCOPE if "--live" in tail else ()),
        *tail,
    ]


def swap_refresh(*tail):
    return ["refresh", "liquidity", "operations", "swaps", *TRADE_SCOPE, *tail]
