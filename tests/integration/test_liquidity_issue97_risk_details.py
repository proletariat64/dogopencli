"""Public risk detail CLI with native-shape, wholly synthetic fixture values."""

import json
from pathlib import Path

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]


@pytest.fixture(autouse=True)
def native_details_do_not_create_cache(setup, request):
    yield
    if request.node.originalname not in {
        "test_populated_parent_list_does_not_substitute_native_get",
        "test_native_get_does_not_touch_parent_list_cache",
        "test_asset_list_cache_cannot_satisfy_or_be_changed_by_native_get",
    }:
        assert not setup.cache_path.exists()


FIXTURE = Path(__file__).parents[1] / "fixtures/liquidity/risk_detail_sanitized.json"


def response(mode):
    doc = json.loads(FIXTURE.read_text())
    doc["data"]["riskMode"] = mode
    return doc


def command(resource, *, identity="synthetic-risk-001"):
    return ["liquidity", "risk", resource, "get", "--risk-event-id", identity]


@pytest.mark.parametrize(
    "resource,mode", [("events", "RISK_EVENT"), ("anomalies", "RISK_ALERT")]
)
def test_native_risk_detail_projection_and_mode_identity(
    setup, run_cli, resource, mode
):
    def answer(payload, index):
        assert payload == {"riskEventId": "synthetic-risk-001"}
        return {"status": 200, "body": response(mode)}

    setup.state.business_handler = answer
    code, out, err = run_cli(command(resource))
    assert code == 0, (out, err)
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any(
        "/api/risk/event/detail.json" in e and "application/x-www-form-urlencoded" in e
        for e in expressions
    )
    result = parse(out)
    live = result["data"]
    assert result["meta"]["source"] == "live"
    assert result["meta"]["kind"] == "runtimes"
    assert live["riskMode"] == mode
    assert "notificationFrequency" in live and "groupNo" in live
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
    other = "anomalies" if resource == "events" else "events"
    code, out, _ = run_cli(command(other))
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "resource,mode", [("events", "RISK_EVENT"), ("anomalies", "RISK_ALERT")]
)
@pytest.mark.parametrize(
    "bad", ["wrong-id", "numeric-id", "wrong-mode", "missing-detail", "failure"]
)
def test_native_risk_detail_hard_failure_never_replays_previous_result(
    setup, run_cli, resource, mode, bad
):
    doc = response(mode)
    setup.state.business_handler = lambda payload, index: {"status": 200, "body": doc}
    assert run_cli(command(resource))[0] == 0
    assert not setup.cache_path.exists()
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
    code, out, _ = run_cli(command(resource))
    assert code == 1
    assert parse(out)["error"]["code"] == (
        "BUSINESS_QUERY_FAILED" if bad == "failure" else "INVALID_RESPONSE"
    )
    assert not setup.cache_path.exists()
    assert parse(out)["data"] is None


@pytest.mark.parametrize("resource", ["events", "anomalies"])
def test_help_describe_and_missing_identity_are_offline(setup, run_cli, resource):
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
