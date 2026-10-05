"""Public risk detail CLI with native-shape, wholly synthetic fixture values."""

import json
from pathlib import Path

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]

FIXTURE = Path(__file__).parents[1] / "fixtures/liquidity/risk_detail_sanitized.json"


def response(mode):
    doc = json.loads(FIXTURE.read_text())
    doc["data"]["riskMode"] = mode
    return doc


def command(resource, *, refresh=False, identity="synthetic-risk-001"):
    prefix = ["refresh"] if refresh else []
    return (
        prefix
        + ["liquidity", "risk", resource]
        + (["detail", "get"] if refresh else ["get"])
        + ["--risk-event-id", identity]
    )


@pytest.mark.parametrize(
    "resource,mode", [("events", "RISK_EVENT"), ("anomalies", "RISK_ALERT")]
)
def test_detail_refresh_offline_live_and_isolation(setup, run_cli, resource, mode):
    def answer(payload, index):
        assert payload == {"riskEventId": "synthetic-risk-001"}
        return {"status": 200, "body": response(mode)}

    setup.state.business_handler = answer
    code, out, err = run_cli(command(resource, refresh=True))
    assert code == 0, (out, err)
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any(
        "/api/risk/event/detail.json" in e and "application/x-www-form-urlencoded" in e
        for e in expressions
    )
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(command(resource) + ["--live"])
    assert code == 0, (out, err)
    assert setup.cache_path.read_bytes() == before
    live = parse(out)["data"]
    assert live["riskMode"] == mode
    assert "notificationFrequency" in live
    assert "groupNo" in live
    assert all(
        set(item) == {"riskSourceObject"} for item in live["treatmentRiskSourceObject"]
    )
    assert (
        not {
            "creator",
            "lastOperator",
            "riskDetail",
            "riskIdentification",
            "disposeContext",
        }
        & live.keys()
    )
    setup.state.reachable = False
    count = len(setup.state.business_requests)
    code, out, err = run_cli(command(resource))
    assert code == 0, (out, err)
    assert parse(out)["data"] == live
    assert parse(out)["meta"]["kind"] == "runtimes"
    assert len(setup.state.business_requests) == count
    for target, identity in [
        (resource, "uncached-id"),
        ("anomalies" if resource == "events" else "events", "synthetic-risk-001"),
    ]:
        code, out, _ = run_cli(command(target, identity=identity))
        assert code == 1
        error = parse(out)["error"]
        assert error["code"] == "CACHE_MISS"
        assert f"refresh liquidity risk {target} detail get" in error["message"]


@pytest.mark.parametrize(
    "resource,mode", [("events", "RISK_EVENT"), ("anomalies", "RISK_ALERT")]
)
@pytest.mark.parametrize(
    "bad", ["wrong-id", "numeric-id", "wrong-mode", "missing-detail", "failure"]
)
def test_hard_failure_preserves_old_detail(setup, run_cli, resource, mode, bad):
    doc = response(mode)
    setup.state.business_handler = lambda payload, index: {"status": 200, "body": doc}
    assert run_cli(command(resource, refresh=True))[0] == 0
    old = setup.cache_path.read_bytes()
    if bad == "wrong-id":
        doc["data"]["id"] = "another-id"
    elif bad == "numeric-id":
        doc["data"]["id"] = 1
    elif bad == "wrong-mode":
        doc["data"]["riskMode"] = "RISK_ALERT" if mode == "RISK_EVENT" else "RISK_EVENT"
    elif bad == "missing-detail":
        del doc["data"]["treatmentRiskSourceObject"]
    else:
        doc["success"] = False
    code, out, _ = run_cli(command(resource, refresh=True))
    assert code == 1
    assert parse(out)["error"]["code"] == (
        "BUSINESS_QUERY_FAILED" if bad == "failure" else "INVALID_RESPONSE"
    )
    assert setup.cache_path.read_bytes() == old
    setup.state.reachable = False
    assert run_cli(command(resource))[0] == 0


@pytest.mark.parametrize("resource", ["events", "anomalies"])
def test_help_describe_and_missing_identity_are_offline(setup, run_cli, resource):
    setup.state.reachable = False
    for args in [
        ["liquidity", "risk", resource, "get", "--help"],
        ["describe", "liquidity", "risk", resource, "get"],
    ]:
        code, out, err = run_cli(args)
        assert code == 0, (out, err)
        assert "risk-event-id" in out or "risk_event_id" in out
        if args[0] == "describe":
            assert parse(out)["read_guide"]["live_verified"] == "2026-10-04"
    code, out, _ = run_cli(["liquidity", "risk", resource, "get"])
    assert code != 0
    assert not setup.state.business_requests
