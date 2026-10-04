"""Issue #88 candidate risk lists through public CLI, fake CDP and real SQLite.

All records are synthetic. Candidate registration here does not enable either
leaf in the production catalog or waive its independent production UAT gate.
"""

from dataclasses import replace
from functools import partial

import pytest
from fake_cdp import SSO_URL
from test_liquidity_cli_sit import LIQUIDITY_URL, route_probes

from dogopencli import catalog, helptree, plugins, snapshot
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import leaves
from dogopencli.plugins.liquidity import store as capture_store
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
    monkeypatch.setattr(helptree, "NODES", nodes)
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
    return ["liquidity", "risk", resource, "list", *scope, *tail]


def refresh(resource="events", *tail, scope=SCOPE):
    return ["refresh", "liquidity", "risk", resource, *scope, *tail]


@pytest.mark.parametrize("resource,mode", RESOURCES)
def test_candidate_complete_capture_roundtrips_without_browser(
    setup, run_cli, resource, mode
):
    rows = [risk(i, mode) for i in range(12)]
    # Native display time is independent of the still-unproven filter clock.
    rows[0]["gmtCreate"] = "2026-09-24 23:00:00（GMT+08）"
    rows[1]["gmtCreate"] = "2026-09-26 07:00:00（GMT+08）"
    native_rows = [
        {
            **row,
            "memo": "private text",
            "operator": "private operator",
            "nested": {"secret": True},
        }
        for row in rows
    ]
    setup.state.business_handler = listing(native_rows, mode)
    code, out, err = run_cli(refresh(resource, "--require-complete"))
    assert code == 0, err
    captured = parse(out)
    assert captured["data"]["row_count"] == 12
    assert captured["meta"]["complete"] is True
    assert captured["meta"]["published"] is True
    assert [p["rowStart"] for p in setup.state.business_requests] == [0, 10]
    fetches = [
        expression
        for transport in setup.state.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert all("/api/risk/event/getAll.json" in expression for expression in fetches)
    assert all("application/json" in expression for expression in fetches)
    before = setup.cache_path.read_bytes()
    request_count = len(setup.state.business_requests)
    transport_count = len(setup.state.transports)
    setup.state.running = False
    code, out, err = run_cli(query(resource, "--all", "--require-complete"))
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == rows
    assert cached["meta"]["source"] == "cache"
    assert cached["meta"]["kind"] == "runtimes"
    assert cached["meta"]["complete"] is True
    assert cached["meta"]["scope"] == captured["meta"]["scope"]
    assert cached["meta"]["snapshot_id"] == captured["meta"]["snapshot_id"]
    assert cached["meta"]["fetched_at"] == captured["meta"]["fetched_at"]
    assert cached["meta"]["acquisition"] == captured["meta"]["acquisition"]
    assert (
        cached["meta"]["retained_coverage"][0]["acquisition"]
        == captured["meta"]["acquisition"]
    )
    assert cached["meta"]["reported_total"] == 12
    assert cached["meta"]["source_observed_from"] is None
    assert cached["meta"]["source_observed_to"] is None
    assert cached["data"][0]["gmtCreate"] != cached["meta"]["fetched_at"]
    for command in ("help", "describe"):
        code, out, err = run_cli([command, "liquidity", "risk", resource, "list"])
        assert code == 0, err
        if command == "describe":
            description = parse(out)
            assert description["read_guide"]["identity"] == ["id"]
            assert description["read_guide"]["offline_profile"] == "history"
            assert (
                description["data_schema"]["properties"]["gmtCreate"]["x-observed-type"]
                == "str"
            )
    code, out, err = run_cli(["snapshot", "liquidity", "--format", "json"])
    assert code == 0, err

    def terminal_nodes(node):
        if "availability" in node:
            yield node
        for child in node["children"]:
            yield from terminal_nodes(child)

    report = parse(out)
    target = next(
        node
        for node in terminal_nodes(report["tree"])
        if node["command"] == f"dogopencli liquidity risk {resource} list"
    )
    assert target["availability"] == "supported"
    assert target["cache"]["status"] == "present"
    assert target["cache"]["complete"] is True
    assert target["rows"] == 12
    assert len(setup.state.business_requests) == request_count
    assert len(setup.state.transports) == transport_count
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("resource,mode", RESOURCES)
def test_live_isolation_and_complete_empty_capture(setup, run_cli, resource, mode):
    setup.state.business_handler = listing([risk(0, mode)], mode)
    code, out, err = run_cli(query(resource, "--live", "--all"))
    assert code == 0, err
    assert parse(out)["data"] == [risk(0, mode)]
    assert parse(out)["meta"]["source"] == "live"
    assert not setup.cache_path.exists()
    setup.state.business_handler = listing([], mode)
    code, out, err = run_cli(query(resource, "--live", "--all"))
    assert code == 0, err
    assert parse(out)["data"] == []
    assert parse(out)["meta"]["complete"] is True
    assert not setup.cache_path.exists()
    code, out, _ = run_cli(query(resource))
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    code, out, err = run_cli(refresh(resource, "--require-complete"))
    assert code == 0, err
    captured = parse(out)
    assert captured["meta"]["published"] is True
    setup.state.running = False
    code, out, err = run_cli(query(resource, "--all", "--require-complete"))
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == []
    assert cached["error"] is None
    assert cached["meta"]["complete"] is True
    assert cached["meta"]["reported_total"] == 0
    assert cached["meta"]["retained_coverage"][0]["row_count"] == 0


@pytest.mark.parametrize("resource,mode", RESOURCES)
def test_complete_empty_live_does_not_fall_back_to_populated_capture(
    setup, run_cli, resource, mode
):
    rows = [risk(0, mode)]
    setup.state.business_handler = listing(rows, mode)
    code, out, err = run_cli(refresh(resource, "--require-complete"))
    assert code == 0, err
    captured = parse(out)
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = listing([], mode)
    code, out, err = run_cli(query(resource, "--live", "--all", "--require-complete"))
    assert code == 0, err
    live = parse(out)
    assert live["data"] == []
    assert live["meta"]["source"] == "live"
    assert live["meta"]["complete"] is True
    assert live["meta"]["reported_total"] == 0
    assert setup.cache_path.read_bytes() == before
    request_count = len(setup.state.business_requests)
    setup.state.running = False
    code, out, err = run_cli(query(resource, "--all", "--require-complete"))
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == rows
    assert cached["meta"]["snapshot_id"] == captured["meta"]["snapshot_id"]
    assert cached["meta"]["acquisition"] == captured["meta"]["acquisition"]
    assert len(setup.state.business_requests) == request_count
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("resource,mode", RESOURCES)
def test_history_retention_caps_all_date_scopes_and_reports_old_scope_gap(
    setup, run_cli, monkeypatch, resource, mode
):
    monkeypatch.setattr(
        capture_store,
        "plan_capture_publish",
        partial(capture_store.plan_capture_publish, cap=3),
    )
    old_rows = [
        risk(i, mode, gmtCreate="2026-10-04 08:00:00（GMT+08）") for i in range(2)
    ]
    new_rows = [
        risk(i, mode, gmtCreate="2026-01-01 08:00:00（GMT+08）") for i in (10, 11)
    ]
    newer_scope = ["--from-date", "20260926", "--to-date", "20260927"]

    def answer(payload, index):
        assert payload["riskMode"] == mode
        rows = old_rows if payload["startTime"] == "2026-09-25" else new_rows
        return page(rows, len(rows))

    setup.state.business_handler = answer
    code, out, err = run_cli(refresh(resource, "--require-complete"))
    assert code == 0, err
    old_capture = parse(out)
    code, out, err = run_cli(refresh(resource, "--require-complete", scope=newer_scope))
    assert code == 0, err
    new_capture = parse(out)
    assert new_capture["meta"]["complete"] is True
    assert new_capture["meta"]["retention"]["dropped"] == 1
    assert new_capture["meta"]["retention"]["retained"] == 3
    assert "retention evicted 1" in err
    assert new_capture["meta"]["fetched_at"] > old_capture["meta"]["fetched_at"]
    before = setup.cache_path.read_bytes()
    request_count = len(setup.state.business_requests)
    setup.state.running = False
    code, out, err = run_cli(
        query(resource, "--all", "--require-complete", scope=newer_scope)
    )
    assert code == 0, err
    current = parse(out)
    assert current["data"] == new_rows
    assert current["meta"]["complete"] is True
    assert current["meta"]["snapshot_id"] == new_capture["meta"]["snapshot_id"]
    assert current["meta"]["acquisition"] == new_capture["meta"]["acquisition"]
    code, out, err = run_cli(query(resource, "--all"))
    assert code == 0
    retained = parse(out)
    assert retained["data"] == old_rows[1:]
    assert retained["error"] is None
    assert retained["meta"]["complete"] is False
    assert retained["meta"]["reported_total"] == 2
    assert retained["meta"]["collected_total"] == 1
    assert retained["meta"]["missing_count"] == 1
    assert "RETENTION_GAP" in retained["meta"]["acquisition"]["reasons"]
    assert "INCOMPLETE_RESULT" in err
    assert retained["meta"]["retained_coverage"][0]["row_count"] == 1
    assert retained["meta"]["scope"] != current["meta"]["scope"]
    code, out, _ = run_cli(query(resource, "--all", "--require-complete"))
    assert code == 1
    strict = parse(out)
    assert strict["data"] is None
    assert strict["error"]["code"] == "INCOMPLETE_RESULT"
    assert "RETENTION_GAP" in strict["meta"]["acquisition"]["reasons"]
    assert len(setup.state.business_requests) == request_count
    assert setup.cache_path.read_bytes() == before


def test_partial_overlap_warns_publishes_by_default_and_strict_refuses(setup, run_cli):
    setup.state.business_handler = listing([risk(0)])
    assert run_cli(refresh())[0] == 0
    before = setup.cache_path.read_bytes()

    def overlap(payload, index):
        rows = (
            [risk(i) for i in range(10)]
            if payload["rowStart"] == 0
            else [risk(0), risk(10)]
        )
        return page(rows, 12)

    setup.state.business_handler = overlap
    code, out, err = run_cli(query("events", "--live", "--all"))
    result = parse(out)
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    assert len(result["data"]) == 11
    assert result["meta"]["complete"] is False
    assert result["meta"]["missing_count"] == 1
    assert setup.cache_path.read_bytes() == before
    for argv in (
        query("events", "--live", "--all", "--require-complete"),
        refresh("events", "--require-complete"),
    ):
        code, out, _ = run_cli(argv)
        result = parse(out)
        assert code == 1
        assert result["data"] is None
        assert result["error"]["code"] == "INCOMPLETE_RESULT"
        assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(refresh())
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["published"] is True
    assert parse(out)["meta"]["complete"] is False
    setup.state.running = False
    code, out, err = run_cli(query("events", "--all"))
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    assert len(parse(out)["data"]) == 11
    assert parse(out)["meta"]["complete"] is False
    code, out, _ = run_cli(query("events", "--all", "--require-complete"))
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"


@pytest.mark.parametrize("defect", ["identity-conflict", "total-drift"])
def test_hard_pagination_failure_preserves_capture(setup, run_cli, defect):
    setup.state.business_handler = listing([risk(0)])
    assert run_cli(refresh())[0] == 0
    before = setup.cache_path.read_bytes()

    def failure(payload, index):
        if payload["rowStart"] == 0:
            return page([risk(i) for i in range(10)], 12)
        if defect == "identity-conflict":
            return page([risk(0, riskStatus="DIFFERENT_NATIVE_STATUS"), risk(10)], 12)
        return page([risk(10), risk(11)], 13)

    setup.state.business_handler = failure
    for argv in (query("events", "--live", "--all"), refresh()):
        code, out, _ = run_cli(argv)
        assert code == 1
        assert parse(out)["data"] is None
        assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
        assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"id": ""},
        {"id": True},
        {"id": 42},
        {"riskMode": "RISK_ALERT"},
        {"gmtCreate": "2026-02-30 08:00:00（GMT+08）"},
        {"gmtCreate": 123},
        {"alertNum": True},
        {"riskProcessingTime": "0"},
        {"riskStatus": []},
    ],
)
def test_invalid_native_rows_never_replace_cache(setup, run_cli, changes):
    setup.state.business_handler = listing([risk(0)])
    assert run_cli(refresh())[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = listing([risk(0, **changes)])
    for argv in (query("events", "--live"), refresh()):
        code, out, _ = run_cli(argv)
        assert code == 1
        assert parse(out)["data"] is None
        assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
        assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize(
    "response,expected_error",
    [
        ({"status": 403, "body": "forbidden"}, "BUSINESS_QUERY_FAILED"),
        (
            {
                "status": 200,
                "body": {"success": True, "data": {"data": {}, "totalCount": 1}},
            },
            "INVALID_RESPONSE",
        ),
        (
            {
                "status": 200,
                "body": {"success": True, "data": {"data": [], "totalCount": True}},
            },
            "INVALID_RESPONSE",
        ),
        (
            {"status": 200, "body": {"success": False, "data": None}},
            "BUSINESS_QUERY_FAILED",
        ),
    ],
)
def test_failed_http_or_envelope_does_not_publish(
    setup, run_cli, response, expected_error
):
    setup.state.business_handler = listing([risk(0)])
    assert run_cli(refresh())[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = lambda payload, index: response
    code, out, _ = run_cli(refresh())
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == expected_error
    assert setup.cache_path.read_bytes() == before


def test_auth_expiry_preserves_previous_capture(setup, run_cli):
    setup.state.business_handler = listing([risk(0)])
    assert run_cli(refresh())[0] == 0
    before = setup.cache_path.read_bytes()
    route_probes(setup.state, (LIQUIDITY_URL, LIQUIDITY_URL, SSO_URL))
    setup.state.business_handler = lambda payload, index: {"error": "AbortError"}
    code, out, _ = run_cli(refresh())
    assert code == 1
    assert parse(out)["error"]["code"] == "AUTH_REQUIRED"
    assert setup.cache_path.read_bytes() == before


def test_date_scopes_and_native_modes_do_not_share_captures(setup, run_cli):
    def answer(payload, index):
        rows = (
            [risk(0, payload["riskMode"])]
            if payload["startTime"] == "2026-09-25"
            else []
        )
        return page(rows, len(rows))

    setup.state.business_handler = answer
    assert run_cli(refresh("events"))[0] == 0
    assert run_cli(refresh("anomalies"))[0] == 0
    empty_scope = ["--from-date", "20260926", "--to-date", "20260927"]
    assert run_cli(refresh("events", scope=empty_scope))[0] == 0
    setup.state.running = False
    results = []
    for resource, scope in (
        ("events", SCOPE),
        ("anomalies", SCOPE),
        ("events", empty_scope),
    ):
        code, out, err = run_cli(query(resource, "--all", scope=scope))
        assert code == 0, err
        results.append(parse(out))
    assert results[0]["data"] == [risk(0)]
    assert results[1]["data"] == [risk(0, "RISK_ALERT")]
    assert results[2]["data"] == []
    assert results[0]["meta"]["scope"] != results[2]["meta"]["scope"]
    code, out, _ = run_cli(query("anomalies", scope=empty_scope))
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize(
    "scope",
    [
        [],
        ["--from-date", "20260925"],
        ["--from-date", "20260230", "--to-date", "20260301"],
        ["--from-date", "2026-09-25", "--to-date", "20260926"],
        ["--from-date", "20260926", "--to-date", "20260925"],
        ["--from-date", "20260925", "--to-date", "20260925"],
        ["--from-date", "20260925", "--to-date", "20260927"],
    ],
)
def test_invalid_or_unbounded_scope_is_rejected_before_transport(setup, run_cli, scope):
    for argv in (
        query("events", "--live", scope=scope),
        refresh("events", scope=scope),
    ):
        code, out, _ = run_cli(argv)
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("resource", ["events", "anomalies"])
def test_candidate_does_not_enable_get_or_history(setup, run_cli, resource):
    for action in ("get", "history"):
        code, out, _ = run_cli(["liquidity", "risk", resource, action])
        assert code == (1 if action == "get" else 2)
        assert parse(out)["data"] is None
        assert parse(out)["error"]["code"] == (
            "UNSUPPORTED_CAPABILITY" if action == "get" else "INVALID_ARGUMENT"
        )
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()
