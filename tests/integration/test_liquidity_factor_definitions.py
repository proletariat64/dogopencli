"""Factor definition catalog: public CLI, fake CDP, real SQLite; invented data."""

import copy

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "pricing", "factors"]


def query(*extra):
    return [*ROOT, "list", "--limit", "0", *extra]


def refresh(*extra):
    return ["refresh", *ROOT, *extra]


def factor(code="SYN-FACTOR"):
    return {"code": code, "description": "原生合成标签", "englishName": "Synthetic"}


def response(rows):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"success": True, "data": {"factorTypes": rows}},
        },
    }


def seed(setup, run_cli, rows=None):
    setup.state.business_handler = lambda payload, index: response(
        [factor()] if rows is None else rows
    )
    code, out, err = run_cli(refresh("--require-complete"))
    assert code == 0, err
    return parse(out)


def test_definition_contract_disconnected_capture_and_live_no_write(setup, run_cli):
    code, out, _ = run_cli(query())
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    rows = [
        factor(),
        {"code": "FUTURE-UNKNOWN", "description": None},
        {"code": "SYN-BLANK", "englishName": ""},
        {"code": "SYN-UNKNOWN", "description": {"native": "unknown"}},
    ]
    raw = [{**row, "price": "excluded", "gmtModified": "excluded"} for row in rows]
    seeded = seed(setup, run_cli, raw)
    assert setup.state.business_requests == [{"tntInstId": "GUAPW3SG"}]
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert len(expressions) == 1
    assert "getPriceEnv.json" in expressions[0] and '"GET"' in expressions[0]
    assert "costFactorList" not in expressions[0]
    assert "queryCostParameters" not in expressions[0]
    assert seeded["meta"]["reported_total"] is None
    assert seeded["meta"]["complete"] is True
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(query("--live", "--require-complete"))
    assert code == 0, err
    live = parse(out)
    assert live["data"] == rows
    assert live["meta"]["kind"] == "reference"
    assert live["meta"]["reported_total"] is None
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    code, out, err = run_cli(query("--require-complete"))
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == live["data"]
    for key in ("scope", "fetched_at", "complete", "reported_total"):
        assert cached["meta"][key] == seeded["meta"][key]
    assert cached["meta"]["capability"].endswith(".list")
    assert cached["meta"]["source_observed_from"] is None
    assert cached["meta"]["source_observed_to"] is None
    assert len(setup.state.business_requests) == 2


@pytest.mark.parametrize(
    "defect",
    [
        "flag",
        "flag-missing",
        "success",
        "success-missing",
        "data-missing",
        "container",
        "container-missing",
        "row",
        "code-missing",
        "code-empty",
        "code-int",
        "code-bool",
        "conflict",
        "excluded-conflict",
        "auth",
        "permission",
        "transport",
    ],
)
def test_hard_failures_preserve_previous_capture(setup, run_cli, defect):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    row = factor()
    answer = response([row])
    inner = answer["body"]["result"]
    if defect == "flag":
        answer["body"]["resultFlag"] = False
    elif defect == "flag-missing":
        del answer["body"]["resultFlag"]
    elif defect == "success":
        inner["success"] = False
    elif defect == "success-missing":
        del inner["success"]
    elif defect == "data-missing":
        del inner["data"]
    elif defect == "container":
        inner["data"]["factorTypes"] = {}
    elif defect == "container-missing":
        del inner["data"]["factorTypes"]
    elif defect == "row":
        inner["data"]["factorTypes"] = [None]
    elif defect == "code-missing":
        del row["code"]
    elif defect == "code-empty":
        row["code"] = " "
    elif defect == "code-int":
        row["code"] = 123
    elif defect == "code-bool":
        row["code"] = True
    elif defect == "conflict":
        inner["data"]["factorTypes"].append({**row, "description": "different"})
    elif defect == "excluded-conflict":
        inner["data"]["factorTypes"].append({**row, "unpublished": "different"})
    elif defect in ("auth", "permission", "transport"):
        answer = {
            "status": {"auth": 401, "permission": 403, "transport": 500}[defect],
            "body": {"resultFlag": False},
        }
    setup.state.business_handler = lambda payload, index: answer
    for command in (query("--live"), refresh()):
        code, out, _ = run_cli(command)
        assert code == 1 and parse(out)["data"] is None
        assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    code, out, err = run_cli(query())
    assert code == 0, err
    assert parse(out)["data"] == [factor()]


def test_duplicates_are_incomplete_strict_rollback_safe_partial_publication(
    setup, run_cli
):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    rows = [factor("SYN-NEW"), factor("SYN-NEW")]
    setup.state.business_handler = lambda payload, index: response(copy.deepcopy(rows))
    code, out, _ = run_cli(refresh("--require-complete"))
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(query("--live"))
    assert code == 0, err
    assert parse(out)["data"] == rows[:1]
    assert parse(out)["meta"]["complete"] is False
    assert parse(out)["meta"]["reported_total"] is None
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(refresh())
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is False
    setup.state.reachable = False
    code, out, err = run_cli(query())
    assert code == 0, err
    assert parse(out)["data"] == rows[:1]
    assert parse(out)["meta"]["complete"] is False
    code, out, _ = run_cli(query("--require-complete"))
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"


def test_complete_empty_replaces_one_current_reference_capture(setup, run_cli):
    seed(setup, run_cli)
    empty = seed(setup, run_cli, [])
    assert empty["meta"]["complete"] is True
    assert empty["meta"]["reported_total"] is None
    setup.state.reachable = False
    code, out, err = run_cli(query("--require-complete"))
    assert code == 0, err
    assert parse(out)["data"] == [factor()]
    assert empty["meta"]["published"] is False


def test_discovery_kind_factor_values_and_get_boundaries(setup, run_cli):
    from dogopencli.plugins.liquidity.leaves import (
        PRICING_FACTOR_VALUES,
        PRICING_FACTORS,
    )
    from dogopencli.plugins.liquidity.spec import PROFILE_DATED, REFERENCE, RUNTIMES

    assert PRICING_FACTORS.kind == REFERENCE
    assert PRICING_FACTOR_VALUES.kind == RUNTIMES
    assert PRICING_FACTOR_VALUES.profile == PROFILE_DATED
    assert PRICING_FACTOR_VALUES.endpoint == "/costFactorList.json"
    code, out, err = run_cli(["describe", *ROOT, "list"])
    assert code == 0, err
    assert parse(out)["read_guide"]["live_verified"] == "2026-10-05"
    assert "factor-definitions-v1" in out and "reference" in out
    assert "description" in out and "englishName" in out
    code, out, _ = run_cli([*ROOT, "get"])
    assert code == 1 and parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    for extra in (
        ["--date", "20260101"],
        ["--status", "ACTIVE"],
        ["--tenant", "OTHER"],
    ):
        code, out, _ = run_cli(query("--live", *extra))
        assert code == 2
    assert setup.state.transports == []


def test_old_placeholder_capture_not_reused_and_factor_values_cache_is_independent(
    setup, run_cli
):
    from dataclasses import replace

    from dogopencli.cache import Cache
    from dogopencli.plugins.liquidity.leaves import PRICING_FACTORS

    # A legacy settings capture with no schema-specific scope cannot satisfy
    # the reference definition contract; default reads must demand refresh.
    legacy = replace(PRICING_FACTORS, kind="settings", schema_version="")
    cache = Cache(setup.cache_path)
    at = "2026-10-05T00:00:00+00:00"
    from dogopencli.cache import SnapshotMeta
    from dogopencli.jsonutil import canonical

    meta = SnapshotMeta(
        namespace="legacy-liquidity",
        capability=legacy.name,
        scope="{}",
        source_kind="cdp",
        snapshot_id="old",
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at=at,
        loaded_at=at,
        source_observed_from=None,
        source_observed_to=None,
        row_count=1,
    )
    cache.publish(meta, [(1, canonical(factor("OLD")))])
    code, out, _ = run_cli(query())
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    value = {
        "id": "SYN-VALUE",
        "factorType": "SYN-FACTOR",
        "value": "1.2500",
        "costDate": "20261005",
        "version": 1,
    }
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"success": True, "dataValue": [value], "count": 1},
        },
    }
    value_root = ["liquidity", "pricing", "factor-values"]
    bounds = ["--from-date", "20261005", "--to-date", "20261005"]
    code, out, err = run_cli(["refresh", *value_root, *bounds])
    assert code == 0, err
    value_capture = parse(out)
    seed(setup, run_cli)
    setup.state.reachable = False
    code, out, err = run_cli([*value_root, "list", *bounds, "--limit", "0"])
    assert code == 0, err
    values = parse(out)
    assert values["data"] == [value]
    assert values["meta"]["kind"] == "runtimes"
    assert values["meta"]["fetched_at"] == value_capture["meta"]["fetched_at"]
    code, out, err = run_cli(query())
    assert code == 0, err
    assert parse(out)["data"] == [factor()]
