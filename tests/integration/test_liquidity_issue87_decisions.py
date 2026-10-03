"""Decision list lifecycle through public CLI, fake CDP and real SQLite."""

from dataclasses import replace

import pytest

from dogopencli import catalog, helptree
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import leaves
from dogopencli.plugins.liquidity.decision_list import (
    DECISIONS,
    RELEASED,
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
    monkeypatch.setattr(helptree, "NODES", nodes)


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
        for row in sorted(rows, key=lambda row: str(row["id"]))
    ]


def test_decision_registration_matches_release_evidence(setup, run_cli):
    released = DECISIONS.name in RELEASED
    assert (DECISIONS.path in leaves.LIST_LEAVES) is released
    assert ((*DECISIONS.path, "list") in leaves.DEFERRED_BY_PATH) is not released
    if released:
        code, out, err = run_cli(["describe", *QUERY])
        assert code == 0, err
        assert parse(out)["read_guide"]["identity"] == ["id"]
        assert setup.state.business_requests == []
        return
    code, out, _ = run_cli(QUERY)
    assert code == 1
    assert parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


def test_decision_refresh_live_offline_privacy_and_description(
    setup, run_cli, decision_candidate_catalog
):
    rows = [decision(index) for index in range(12)]
    rows[-1].update(executionTimeStart=END, gmtCreate=END)
    setup.state.business_handler = listing(rows)
    code, out, err = run_cli([*REFRESH, *SCOPE, "--require-complete"])
    assert code == 0, err
    refresh = parse(out)
    assert refresh["meta"]["complete"] is True
    assert refresh["meta"]["published"] is True
    assert refresh["data"]["row_count"] == 12
    assert [body["rowStart"] for body in setup.state.business_requests] == [0, 10]
    cache_before = setup.cache_path.read_bytes()
    code, out, err = run_cli([*QUERY, *SCOPE, "--live", "--all"])
    assert code == 0, err
    live = parse(out)
    assert live["data"] == published(rows)
    assert live["meta"]["reported_total"] == 12
    assert live["meta"]["complete"] is True
    assert live["meta"]["source_observed_from"] is None
    assert setup.cache_path.read_bytes() == cache_before
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *SCOPE, "--all", "--require-complete"])
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == live["data"]
    assert cached["meta"]["fetched_at"] == refresh["meta"]["fetched_at"]
    assert cached["meta"]["scope"] == refresh["meta"]["scope"]
    assert cached["meta"]["complete"] is True
    for entry in ("help", "describe"):
        code, out, err = run_cli([entry, *QUERY])
        assert code == 0, err
        if entry == "describe":
            description = parse(out)
            assert description["read_guide"]["identity"] == ["id"]
            assert description["read_guide"]["offline_profile"] == "history"
            assert description["read_guide"]["live_verified"] == "2026-10-04"
            assert (
                description["data_schema"]["properties"]["id"]["x-observed-type"]
                == "int"
            )
            assert "operator" not in description["data_schema"]["properties"]
    assert len(setup.state.business_requests) == count
    for value in (
        b"private-user",
        b"private-account",
        b"private-name",
        b"private-text",
    ):
        assert value not in cache_before


def test_decision_empty_live_and_published_empty_are_distinct_from_cache_miss(
    setup, run_cli, decision_candidate_catalog
):
    setup.state.business_handler = listing([])
    code, out, err = run_cli([*QUERY, *SCOPE, "--live", "--all"])
    assert code == 0, err
    assert parse(out)["data"] == []
    assert not setup.cache_path.exists()
    code, out, err = run_cli([*REFRESH, *SCOPE])
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli([*QUERY, *SCOPE, "--live", "--all"])
    assert code == 0, err
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *SCOPE, "--all"])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == []
    assert result["meta"]["complete"] is True
    assert result["meta"]["retained_coverage"][0]["row_count"] == 0


@pytest.mark.parametrize(
    "scope",
    [
        [],
        SCOPE[:2],
        SCOPE[:-2],
        ["--start-from", "2026-09-30", *SCOPE[2:]],
        ["--start-from", "2026-09-31 00:00:00", *SCOPE[2:]],
        ["--start-from", "2026-10-01 00:00:00", *SCOPE[2:]],
        [*SCOPE[:4], "--created-from", END, "--created-to", START],
    ],
)
def test_decision_invalid_bounds_are_rejected_before_access(
    setup, run_cli, decision_candidate_catalog, scope
):
    for argv in ([*QUERY, *scope, "--live"], [*REFRESH, *scope]):
        code, out, _ = run_cli(argv)
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "1"},
        {"id": True},
        {"tntInstId": "OTHER"},
        {"decisionAmount": "NaN"},
        {"decisionAmount": 12},
        {"executionTimeStart": "2026-09-29 23:59:59"},
        {"gmtCreate": "2026-10-01 00:00:00"},
        {"gmtCreate": "invalid"},
        {"reportStatus": []},
    ],
)
def test_decision_hard_row_failure_preserves_prior_capture(
    setup, run_cli, decision_candidate_catalog, changes
):
    setup.state.business_handler = listing([decision(1)])
    code, _, err = run_cli([*REFRESH, *SCOPE])
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = listing([decision(1, **changes)])
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == before


def test_decision_overlap_default_partial_and_strict_preserve_capture(
    setup, run_cli, decision_candidate_catalog
):
    rows = [decision(index) for index in range(12)]
    setup.state.business_handler = listing(rows)
    code, _, err = run_cli([*REFRESH, *SCOPE])
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    def overlap(payload, index):
        return page(rows[:10] if payload["rowStart"] == 0 else [rows[9], rows[10]], 12)

    setup.state.business_handler = overlap
    code, out, _ = run_cli([*REFRESH, *SCOPE, "--require-complete"])
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli([*REFRESH, *SCOPE])
    assert code == 0, err
    result = parse(out)
    assert result["error"] is None
    assert result["meta"]["complete"] is False
    assert result["meta"]["published"] is True
    assert result["meta"]["reported_total"] == 12
    assert err
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *SCOPE, "--all"])
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is False
    assert parse(out)["data"] == published(rows[:11])
    assert err
    code, out, _ = run_cli([*QUERY, *SCOPE, "--all", "--require-complete"])
    assert code == 1
    assert parse(out)["data"] is None


@pytest.mark.parametrize("failure", ["drift", "conflict", "auth", "envelope"])
def test_decision_hard_collection_failures_preserve_prior_capture(
    setup, run_cli, decision_candidate_catalog, failure
):
    rows = [decision(index) for index in range(12)]
    setup.state.business_handler = listing(rows)
    code, _, err = run_cli([*REFRESH, *SCOPE])
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    def fail(payload, index):
        if failure == "auth":
            return {"status": 401, "body": {}}
        if failure == "envelope":
            return {"status": 200, "body": {"success": False, "data": {}}}
        if payload["rowStart"] == 0:
            return page(rows[:10], 12)
        if failure == "drift":
            return page(rows[10:], 13)
        return page([decision(9, reportStatus="changed"), rows[10]], 12)

    setup.state.business_handler = fail
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["data"] is None
    assert setup.cache_path.read_bytes() == before


def test_decision_list_refresh_keeps_native_detail_cache_independent(
    setup, run_cli, decision_candidate_catalog
):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"id": 7, "detailOnly": "actual-detail"}},
    }
    code, _, err = run_cli(
        [
            "refresh",
            "liquidity",
            "operations",
            "decisions",
            "detail",
            "get",
            "--id",
            "7",
        ]
    )
    assert code == 0, err
    from collections import deque

    lineage = {
        "id": 7,
        "reportId": "report-a",
        "groupId": "group-a",
        "tntInstId": "GUAPW3SG",
    }
    versions = [dict(lineage, id=6, version=2)]
    setup.state.business_handler = None
    setup.state.business_script = deque(
        {"status": 200, "body": {"success": True, "data": data}}
        for data in (lineage, versions)
    )
    code, _, err = run_cli(
        [
            "refresh",
            "liquidity",
            "operations",
            "decisions",
            "detail",
            "history",
            "--id",
            "7",
        ]
    )
    assert code == 0, err
    setup.state.business_handler = listing([decision(7)])
    code, _, err = run_cli([*REFRESH, *SCOPE])
    assert code == 0, err
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(
        ["liquidity", "operations", "decisions", "get", "--id", "7"]
    )
    assert code == 0, err
    assert parse(out)["data"] == {"id": 7, "detailOnly": "actual-detail"}
    assert len(setup.state.business_requests) == count

    code, out, err = run_cli(
        ["liquidity", "operations", "decisions", "history", "--id", "7"]
    )
    assert code == 0, err
    assert parse(out)["data"] == versions
    assert len(setup.state.business_requests) == count


def test_decision_exact_native_scopes_retain_independent_captures(
    setup, run_cli, decision_candidate_catalog
):
    setup.state.business_handler = listing([decision(1)])
    code, _, err = run_cli([*REFRESH, *SCOPE])
    assert code == 0, err
    later = "2026-10-01 00:00:00"
    separate_scope = [
        "--start-from",
        later,
        "--start-to",
        later,
        "--created-from",
        later,
        "--created-to",
        later,
    ]
    setup.state.business_handler = lambda payload, index: page([], 0)
    code, _, err = run_cli([*REFRESH, *separate_scope])
    assert code == 0, err
    setup.state.reachable = False
    for scope, expected in ((SCOPE, published([decision(1)])), (separate_scope, [])):
        code, out, err = run_cli([*QUERY, *scope, "--all", "--require-complete"])
        assert code == 0, err
        assert parse(out)["data"] == expected
        assert parse(out)["meta"]["complete"] is True
