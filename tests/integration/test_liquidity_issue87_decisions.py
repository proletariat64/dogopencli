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
    code, out, err = run_cli([*QUERY, *SCOPE, "--live", "--limit", "0"])
    assert code == 0, err
    live = parse(out)
    assert live["data"] == published(rows)
    for record in live["data"]:
        assert "debitAliasName" not in record
        assert "creditAliasName" not in record
        assert record["debitEntity"] == "synthetic-debit-entity"
        assert record["creditEntity"] == "synthetic-credit-entity"
        assert record["debitBankId"] == "synthetic-debit-bank"
        assert record["creditBankId"] == "synthetic-credit-bank"
    assert live["meta"]["reported_total"] == 12
    assert live["meta"]["complete"] is True
    assert live["meta"]["source_observed_from"] is None
    assert setup.cache_path.read_bytes() == cache_before
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, "--limit", "0", "--require-complete"])
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
            assert (
                description["read_guide"]["offline_profile"]
                == "single temporary leaf result"
            )
            assert description["read_guide"]["live_verified"] == "2026-10-04"
            assert (
                description["data_schema"]["properties"]["id"]["x-observed-type"]
                == "int"
            )
            fields = description["data_schema"]["properties"]
            for field in ("operator", "debitAliasName", "creditAliasName"):
                assert field not in fields
            for field in ("debitEntity", "creditEntity", "debitBankId", "creditBankId"):
                assert fields[field]["x-observed-type"] == "str"
    assert len(setup.state.business_requests) == count
    for value in (
        b"private-user",
        b"private-account",
        b"private-name",
        b"private-text",
        b"private-debit-alias",
        b"private-credit-alias",
    ):
        assert value not in cache_before


def test_decision_empty_refresh_does_not_create_slot(
    setup, run_cli, decision_candidate_catalog
):
    setup.state.business_handler = listing([])
    for argv in ([*QUERY, *SCOPE, "--live", "--limit", "0"], [*REFRESH, *SCOPE]):
        code, out, err = run_cli(argv)
        assert code == 0, err
        result = parse(out)
        if argv[0] == "refresh":
            assert result["meta"]["published"] is False
        else:
            assert result["data"] == []
        assert not setup.cache_path.exists()
    setup.state.reachable = False
    code, out, _ = run_cli([*QUERY, "--limit", "0"])
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"


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
    code, out, err = run_cli([*QUERY, "--limit", "0"])
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is False
    assert parse(out)["data"] == published(rows[:11])
    assert err
    code, out, _ = run_cli([*QUERY, "--limit", "0", "--require-complete"])
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


def test_decisions_native_get_preserves_list_slot(
    setup, run_cli, decision_candidate_catalog
):
    setup.state.business_handler = listing([decision(7)])
    assert run_cli([*REFRESH, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()
    detail = {"id": 7, "detailOnly": "actual-detail"}
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": detail},
    }
    argv = ["liquidity", "operations", "decisions", "get", *["--id", "7"]]
    count = len(setup.state.business_requests)
    code, out, err = run_cli(argv)
    assert code == 0, err
    assert parse(out)["data"] == detail
    assert parse(out)["meta"]["source"] == "live"
    assert len(setup.state.business_requests) == count + 1
    assert setup.cache_path.read_bytes() == before
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
    code, out, err = run_cli(
        ["liquidity", "operations", "decisions", "history", "--id", "7"]
    )
    assert code == 0, err
    assert parse(out)["data"] == versions
    assert parse(out)["meta"]["source"] == "live"
    assert len(setup.state.business_requests) == count + 3
    assert setup.cache_path.read_bytes() == before
    setup.state.running = False
    code, out, _ = run_cli(argv)
    assert code == 1
    assert parse(out)["data"] is None
    assert setup.cache_path.read_bytes() == before


def test_decision_empty_later_scope_preserves_last_slot(
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
    code, out, err = run_cli([*QUERY, "--limit", "0", "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"] == published([decision(1)])
    code, out, _ = run_cli([*QUERY, *separate_scope])
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"


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


def test_decision_canonical_t_form_shares_the_legacy_space_scope(
    setup, run_cli, decision_candidate_catalog
):
    rows = [decision(index) for index in range(3)]
    setup.state.business_handler = listing(rows)
    code, _, err = run_cli([*REFRESH, *T_SCOPE])
    assert code == 0, err
    # The emitted native request keeps the space-separated representation.
    for body in setup.state.business_requests:
        assert body["startTime"] == body["createStartTime"] == START
        assert body["endTime"] == body["createEndTime"] == END
    canonical_meta = parse(run_cli([*QUERY, "--limit", "0"])[1])["meta"]
    # The legacy space form reads the identical cached scope offline.
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, "--limit", "0"])
    assert code == 0, err
    legacy = parse(out)
    assert legacy["data"] == published(rows)
    assert legacy["meta"]["scope"] == canonical_meta["scope"]


@pytest.mark.parametrize(
    "value",
    [
        "2026-09-30T00:00:00+08:00",  # offset-bearing: source zone unknown
        "2026-09-30T00:00:00Z",
        "2026-09-30T00:00:00-00:00",
        "2026-09-30T00:00:00.5",  # fractional seconds
        "2026-09-30T23:59:60",  # leap second
    ],
)
def test_decision_offset_bearing_values_rejected_before_access(
    setup, run_cli, decision_candidate_catalog, value
):
    scope = ["--start-from", value, *SCOPE[2:]]
    for argv in ([*QUERY, *scope, "--live"], [*REFRESH, *scope]):
        code, out, _ = run_cli(argv)
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


def test_decision_help_declares_unknown_timezone(
    setup, run_cli, decision_candidate_catalog
):
    code, out, err = run_cli(["help", *QUERY])
    assert code == 0, err
    options = {option["name"]: option for option in parse(out)["options"]}
    for name in ("start_from", "start_to", "created_from", "created_to"):
        assert "YYYY-MM-DDTHH:mm:ss" in options[name]["summary"]
        assert "timezone unknown" in options[name]["summary"]
