"""Issue #88 candidate risk lists through public CLI, fake CDP and real SQLite.

All records are synthetic. Candidate registration here does not enable either
leaf in the production catalog or waive its independent production UAT gate.
"""

from dataclasses import replace

import pytest

from dogopencli import catalog, plugins, snapshot
from dogopencli.plugins.liquidity import leaves
from dogopencli.plugins.liquidity.risk_batch import RISK_ANOMALIES, RISK_EVENTS

pytest_plugins = ["test_liquidity_cli_sit"]

RESOURCES = (("events", "RISK_EVENT"), ("anomalies", "RISK_ALERT"))
SCOPE = ["--from-date", "20260925", "--to-date", "20260926"]


@pytest.fixture(autouse=True)
def risk_candidate_catalog(monkeypatch):
    declarations = {
        path: replace(node, children=()) for path, node in catalog.NODES.items()
    }
    for spec in (RISK_EVENTS, RISK_ANOMALIES):
        leaf = leaves.ListLeaf((spec,))
        monkeypatch.setitem(leaves.LIST_LEAVES, spec.path, leaf)
        monkeypatch.delitem(
            leaves.DEFERRED_BY_PATH, (*spec.path, "list"), raising=False
        )
        query_node = leaves.list_query_node(leaf)
        refresh_node = leaves.refresh_list_node(leaf)
        capability = leaf.capability(spec)
        # Snapshot ownership comes from plugin registrations, independently
        # of the catalog used for CLI dispatch and help.
        monkeypatch.setitem(plugins._REGISTRY, capability.name, capability)
        monkeypatch.setitem(plugins._COMMANDS, capability.name, (query_node,))
        monkeypatch.setitem(plugins._REFRESH_COMMANDS, capability.name, (refresh_node,))
        for node in (query_node, refresh_node):
            declarations[node.path] = node
    monkeypatch.setattr(
        leaves, "LIST_SPECS", (*leaves.LIST_SPECS, RISK_EVENTS, RISK_ANOMALIES)
    )
    for node in leaves.group_nodes():
        declarations[node.path] = node
    nodes = catalog.build_catalog(declarations.values())
    monkeypatch.setattr(catalog, "NODES", nodes)
    monkeypatch.setattr(snapshot, "NODES", nodes)


def risk(index, mode="RISK_EVENT", **overrides):
    return {
        "id": f"synthetic-risk-{index:03d}",
        "riskMode": mode,
        "gmtCreate": "2026-09-25 08:00:00（GMT+08）",
        "gmtModified": "2026-09-25 08:01:00（GMT+08）",
        "riskScenario": "synthetic-scenario",
        "riskCategory": "synthetic-category",
        "riskEvent": "synthetic-event",
        "riskStatus": "SOURCE_FUTURE_STATUS",
        "riskLevel": "SOURCE_FUTURE_LEVEL",
        "riskAlertLevel": "SOURCE_FUTURE_ALERT_LEVEL",
        "riskObject": "synthetic-object",
        "riskSourceObject": "synthetic-source-object",
        "riskProcessingTime": 0,
        "alertNum": 1,
        "firstAlertTime": "2026-09-25 08:00:00（GMT+08）",
        "nextAlertTime": "2026-09-25 08:01:00（GMT+08）",
        "closeRiskTime": "2026-09-25 08:02:00（GMT+08）",
        **overrides,
    }


def page(rows, total):
    return {
        "status": 200,
        "body": {"success": True, "data": {"data": rows, "totalCount": total}},
    }


def listing(rows, mode="RISK_EVENT"):
    def answer(payload, index):
        assert set(payload) == {
            "tntInstId",
            "riskMode",
            "timeZone",
            "pageSize",
            "rowStart",
            "startTime",
            "endTime",
        }
        assert payload["tntInstId"] == "GUAPW3SG"
        assert payload["riskMode"] == mode
        assert payload["timeZone"] == "GMT+08"
        assert payload["pageSize"] == 10
        assert payload["startTime"] == "2026-09-25"
        assert payload["endTime"] == "2026-09-26"
        offset = payload["rowStart"]
        return page(rows[offset : offset + 10], len(rows))

    return answer


def query(resource="events", *tail, scope=SCOPE):
    return [
        "liquidity",
        "risk",
        resource,
        "list",
        *(scope if "--live" in tail else ()),
        *tail,
    ]


def refresh(resource="events", *tail, scope=SCOPE):
    return ["refresh", "liquidity", "risk", resource, *scope, *tail]
