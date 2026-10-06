"""Funding-demand public CLI, native request shape and cache safety."""

import json

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]

SCOPE = ["--execute-from", "2026-04-01 00:00:00", "--execute-to", "2026-04-02 00:00:00"]
QUERY = ["liquidity", "operations", "demands", "list"]
REFRESH = ["refresh", "liquidity", "operations", "demands"]


def demand(index=0, **changes):
    return {
        "taskId": f"synthetic-demand-{index}",
        "tntInstId": "GUAPW3SG",
        "source": "FUND_REQUIRE",
        "sourceId": "synthetic-source",
        "instId": "synthetic-entity",
        "bankId": "synthetic-bank",
        "currency": "USD",
        "amount": "123456789012345678.123400",
        "executeTime": "2026-04-01 12:34:56",
        "status": "unknown-native-state",
        "accountNo": "excluded-account",
        "aliasName": "excluded-alias",
        "fundsRiskActionResult": {"private": "excluded"},
        **changes,
    }


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "dataValue": rows,
                "count": len(rows) if total is None else total,
            },
        },
    }


def listing(rows):
    def answer(payload, index):
        assert set(payload) == {"tntInstId", "riskActionTaskQueryVO"}
        vo = json.loads(payload["riskActionTaskQueryVO"])
        assert vo["tntInstId"] == payload["tntInstId"] == "GUAPW3SG"
        assert vo["source"] == ["FUND_REQUIRE"]
        assert vo["pageSize"] == 5000
        assert vo["startExecuteTime"] == SCOPE[1]
        assert vo["endExecuteTime"] == SCOPE[3]
        return response(rows[vo["rowStart"] : vo["rowStart"] + 5000], len(rows))

    return answer


def test_refresh_offline_and_live_preserve_projection_precision_and_exact_scope(
    setup, run_cli
):
    rows = [demand(i) for i in range(2)]
    setup.state.business_handler = listing(rows)
    code, out, err = run_cli([*REFRESH, *SCOPE, "--require-complete"])
    assert code == 0, err
    result = parse(out)
    assert result["data"]["row_count"] == 2
    assert result["meta"]["complete"] is True
    assert result["meta"]["published"] is True
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli([*QUERY, *SCOPE, "--live", "--all", "--require-complete"])
    assert code == 0, err
    live = parse(out)
    assert live["data"][0]["amount"] == rows[0]["amount"]
    assert live["data"][0]["status"] == "unknown-native-state"
    assert not {"accountNo", "aliasName", "fundsRiskActionResult"} & set(
        live["data"][0]
    )
    assert setup.cache_path.read_bytes() == before
    request_count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *SCOPE, "--all", "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"] == live["data"]
    assert len(setup.state.business_requests) == request_count
    changed = [*SCOPE[:2], "--execute-to", "2026-04-03 00:00:00"]
    code, out, _ = run_cli([*QUERY, *changed])
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize(
    "scope",
    [
        [],
        SCOPE[:2],
        ["--execute-from", "2026-04-31 00:00:00", *SCOPE[2:]],
        ["--execute-from", SCOPE[3], "--execute-to", SCOPE[1]],
    ],
)
def test_invalid_scope_is_rejected_before_browser_work(setup, run_cli, scope):
    code, out, _ = run_cli([*QUERY, *scope, "--live"])
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert not setup.state.transports
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"taskId": ""},
        {"source": "INSTRUCTION_ACCOUNT_FLOW"},
        {"tntInstId": "other-tenant"},
        {"amount": "NaN"},
        {"amount": 1.25},
        {"executeTime": "2026-04-03 00:00:00"},
        {"executeTime": "invalid"},
        {"currency": ""},
    ],
)
def test_invalid_native_rows_fail_without_publishing(setup, run_cli, changes):
    setup.state.business_handler = lambda payload, index: response([demand(**changes)])
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    code, out, _ = run_cli([*QUERY, *SCOPE])
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"


def test_business_failure_preserves_previously_published_capture(setup, run_cli):
    setup.state.business_handler = listing([demand()])
    assert run_cli([*REFRESH, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "resultFlag": False,
            "result": {
                "success": False,
                "errorCode": "099",
                "dataValue": [],
                "count": 0,
            },
        },
    }
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"] is not None
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli([*QUERY, *SCOPE])
    assert code == 0, err
    assert parse(out)["data"][0]["taskId"] == demand()["taskId"]


def test_verified_empty_capture_is_published_and_read_offline(setup, run_cli):
    setup.state.business_handler = listing([])
    code, out, err = run_cli([*REFRESH, *SCOPE, "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"]["row_count"] == 0
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *SCOPE, "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"] == []


def test_duplicate_arrivals_warn_and_strict_refresh_preserves_cache(setup, run_cli):
    setup.state.business_handler = listing([demand()])
    assert run_cli([*REFRESH, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = lambda payload, index: response(
        [demand(), demand()], 2
    )
    code, out, err = run_cli([*QUERY, *SCOPE, "--live", "--all"])
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["complete"] is False
    assert len(parse(out)["data"]) == 1
    code, out, _ = run_cli([*REFRESH, *SCOPE, "--require-complete"])
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("timestamp", [SCOPE[1], SCOPE[3]])
def test_native_execution_time_boundaries_are_inclusive(setup, run_cli, timestamp):
    setup.state.business_handler = listing([demand(executeTime=timestamp)])
    code, out, err = run_cli([*QUERY, *SCOPE, "--live", "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"][0]["executeTime"] == timestamp
