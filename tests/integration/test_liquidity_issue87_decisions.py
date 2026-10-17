"""Decision list lifecycle through public CLI, fake CDP and real SQLite."""

from dataclasses import replace

import pytest

from dogopencli import catalog
from dogopencli.plugins.liquidity import leaves
from dogopencli.plugins.liquidity.decision_list import (
    DECISIONS,
    SAMPLED_FIELDS,
)

pytest_plugins = ["test_liquidity_cli_sit"]
START = "2026-09-30 00:00:00"
END = "2026-09-30 23:59:59"
SCOPE = [
    "--start-from",
    START,
    "--start-to",
    END,
    "--created-from",
    START,
    "--created-to",
    END,
]
QUERY = ["liquidity", "operations", "decisions", "list"]
REFRESH = ["refresh", "liquidity", "operations", "decisions"]


@pytest.fixture
def decision_candidate_catalog(monkeypatch):
    """Candidate behavior is testable without bypassing the production gate."""
    declarations = {
        path: replace(node, children=()) for path, node in catalog.NODES.items()
    }
    leaf = leaves.ListLeaf((DECISIONS,))
    monkeypatch.setitem(leaves.LIST_LEAVES, DECISIONS.path, leaf)
    monkeypatch.delitem(
        leaves.DEFERRED_BY_PATH, (*DECISIONS.path, "list"), raising=False
    )
    monkeypatch.setattr(
        leaves,
        "LIST_SPECS",
        (
            *tuple(spec for spec in leaves.LIST_SPECS if spec.name != DECISIONS.name),
            DECISIONS,
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


def decision(index, **changes):
    # Sanitized structure from the verified nonempty native Sep30 sample.
    return {
        "id": index,
        "tntInstId": "GUAPW3SG",
        "reportId": "shared-report",
        "groupId": "shared-group",
        "orderNo": "",
        "reportStatus": "source-state",
        "executionTimeStart": START,
        "executionTimeEnd": END,
        "gmtCreate": START,
        "gmtModified": END,
        "decisionTime": None,
        "decisionCurrency": "USD",
        "decisionAmount": "123.4500",
        "debitEntity": "synthetic-debit-entity",
        "creditEntity": "synthetic-credit-entity",
        "debitBankId": "synthetic-debit-bank",
        "creditBankId": "synthetic-credit-bank",
        "debitAliasName": "private-debit-alias",
        "creditAliasName": "private-credit-alias",
        "operator": "private-user",
        "creditAccountNo": "private-account",
        "strategyName": "private-name",
        "extParams": "private-text",
        "riskEventVOS": [{"private": "nested"}],
        **changes,
    }


def page(rows, total):
    return {
        "status": 200,
        "body": {"success": True, "data": {"data": rows, "totalCount": total}},
    }


def listing(rows):
    def answer(payload, index):
        assert set(payload) == {
            "tntInstId",
            "startTime",
            "endTime",
            "createStartTime",
            "createEndTime",
            "rowStart",
            "pageSize",
        }
        assert payload["tntInstId"] == "GUAPW3SG"
        assert payload["startTime"] == payload["createStartTime"] == START
        assert payload["endTime"] == payload["createEndTime"] == END
        assert payload["pageSize"] == 10
        offset = payload["rowStart"]
        return page(rows[offset : offset + 10], len(rows))

    return answer


def published(rows):
    return [
        {key: value for key, value in row.items() if key in SAMPLED_FIELDS}
        for row in rows
    ]


T_START = START.replace(" ", "T")
T_END = END.replace(" ", "T")
T_SCOPE = [
    "--start-from",
    T_START,
    "--start-to",
    T_END,
    "--created-from",
    T_START,
    "--created-to",
    T_END,
]
