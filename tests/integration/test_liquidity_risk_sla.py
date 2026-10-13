"""Issue #109 public CLI, fake CDP and real SQLite; synthetic records only."""

import copy
import hashlib
import json

import pytest

from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.risk_sla import FIELDS

pytest_plugins = ["test_liquidity_cli_sit"]
QUERY = ["liquidity", "risk", "sla", "list", "--limit", "0"]
REFRESH = ["refresh", "liquidity", "risk", "sla"]


def row(identity="SYN-SLA"):
    return {
        "slaConfigId": identity,
        "riskEventType": "UNKNOWN-EVENT",
        "effectiveStatus": "UNKNOWN-STATE",
        "processStatus": "",
        "version": "0007.0100",
        "tntInstId": "GUAPW3SG",
        "gmtCreate": None,
        "gmtModified": "unknown-native-time",
        "slaRuleVOList": [{"notificationRecipients": ["SYN-PRIVATE"]}],
        "creator": "SYN-PRIVATE",
        "detailUrl": "https://example.invalid/private",
        "processId": "SYN-PRIVATE",
    }


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


def seed(setup, run_cli, rows=None):
    setup.state.business_handler = lambda payload, index: response(
        [row()] if rows is None else rows
    )
    code, out, err = run_cli([*REFRESH, "--require-complete"])
    assert code == 0, (out, err)
    return parse(out)


def test_fixed_request_same_capture_offline_live_and_detail_isolation(setup, run_cli):
    assert parse(run_cli(QUERY)[1])["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    get = ["liquidity", "risk", "sla", "get", "--sla-config-id", "SYN-SLA"]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": row()},
    }
    assert run_cli(get)[0] == 0
    assert not setup.cache_path.exists()
    detail_before = parse(run_cli(get)[1])
    start = len(setup.state.business_requests)
    refreshed = seed(setup, run_cli, [row("SYN-A"), row("SYN-B")])
    assert setup.state.business_requests[start:] == [{"rowStart": 0, "pageSize": 5000}]
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    listing = next(e for e in expressions if "slaConfigPageQuery.json" in e)
    assert "iliquidity.alipay.com" in listing and "POST" in listing
    assert "application/json" in listing
    assert all(
        "PortfolioMgmt" in url for t in setup.state.transports for url in t.created
    )
    before = hashlib.sha256(setup.cache_path.read_bytes()).hexdigest()
    code, out, err = run_cli([*QUERY, "--live", "--require-complete"])
    assert code == 0, (out, err)
    assert hashlib.sha256(setup.cache_path.read_bytes()).hexdigest() == before
    setup.state.reachable = False
    count = len(setup.state.business_requests)
    code, out, err = run_cli([*QUERY, "--require-complete"])
    assert code == 0, (out, err)
    offline = parse(out)
    assert offline["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert (
        offline["meta"]["reported_total"] == 2 and offline["meta"]["complete"] is True
    )
    assert offline["meta"]["kind"] == "settings"
    assert offline["meta"]["scope"] == {}
    assert offline["data"] == [
        {key: source[key] for key in FIELDS} for source in [row("SYN-A"), row("SYN-B")]
    ]
    assert "SYN-PRIVATE" not in json.dumps(offline["data"])
    setup.state.reachable = True
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": row()},
    }
    assert parse(run_cli(get)[1])["data"] == detail_before["data"]
    assert hashlib.sha256(setup.cache_path.read_bytes()).hexdigest() == before
    assert len(setup.state.business_requests) == count + 1
    setup.state.business_handler = lambda payload, index: {"status": 401, "body": {}}
    code, out, _ = run_cli([*QUERY, "--live"])
    assert code == 1 and parse(out)["error"]["code"] == "AUTH_REQUIRED"
    assert hashlib.sha256(setup.cache_path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize(
    "case",
    [
        "id_int",
        "id_blank",
        "id_missing",
        "tenant",
        "version_int",
        "conflict",
        "missing_total",
        "boolean_total",
        "negative_total",
        "string_total",
        "container",
        "outer_failure",
        "success_missing",
        "success_string",
        "auth",
        "permission",
        "transport",
    ],
)
def test_hard_failures_preserve_capture(setup, run_cli, case):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    source = row()
    rows = [source]
    answer = response(rows)
    data = answer["body"]["data"]
    if case == "id_int":
        source["slaConfigId"] = 5
    elif case == "id_blank":
        source["slaConfigId"] = " "
    elif case == "id_missing":
        del source["slaConfigId"]
    elif case == "tenant":
        source["tntInstId"] = "OTHER"
    elif case == "version_int":
        source["version"] = 7
    elif case == "conflict":
        rows.append({**copy.deepcopy(source), "version": "8"})
    elif case == "missing_total":
        del data["totalCount"]
    elif case == "boolean_total":
        data["totalCount"] = True
    elif case == "negative_total":
        data["totalCount"] = -1
    elif case == "string_total":
        data["totalCount"] = "1"
    elif case == "container":
        data["data"] = {}
    elif case == "outer_failure":
        answer["body"]["success"] = False
    elif case == "success_missing":
        del answer["body"]["success"]
    elif case == "success_string":
        answer["body"]["success"] = "true"
    elif case == "auth":
        answer["status"] = 401
    elif case == "permission":
        answer["status"] = 403
    elif case == "transport":
        answer["status"] = 500
    setup.state.business_handler = lambda payload, index: answer
    for command in ([*QUERY, "--live"], REFRESH):
        code, out, _ = run_cli(command)
        assert code == 1 and parse(out)["error"] is not None
        assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize(
    "rows,total", [([row()], 5001), ([row(), row()], 1), ([row(), row()], 2)]
)
def test_single_response_partial_and_strict_keep_quality(setup, run_cli, rows, total):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = lambda payload, index: response(rows, total)
    start = len(setup.state.business_requests)
    code, out, _ = run_cli([*REFRESH, "--require-complete"])
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert len(setup.state.business_requests) == start + 1
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(REFRESH)
    assert code == 0 and "INCOMPLETE_RESULT" in err
    setup.state.reachable = False
    code, out, err = run_cli(QUERY)
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["complete"] is False
    assert len(parse(out)["data"]) == 1
    assert run_cli([*QUERY, "--require-complete"])[0] == 1


def test_empty_and_catalog_do_not_connect(setup, run_cli):
    for command in (
        ["help", "liquidity", "risk", "sla"],
        ["describe", *QUERY[:-2]],
        ["snapshot", "liquidity", "risk", "sla", "list"],
    ):
        assert run_cli(command)[0] == 0
    assert setup.state.transports == []
    description = parse(run_cli(["describe", *QUERY[:-2]])[1])
    guide = description["read_guide"]
    assert guide["kind"] == "settings" and guide["identity"] == ["slaConfigId"]
    assert guide["schema_version"] == "risk-sla-list-v1"
    assert guide["offline_profile"] == "single temporary leaf result"
    assert guide["request"]["pagination"] == "single"
    assert guide["request"]["page_size"] == 5000
    schema = description["data_schema"]
    assert set(schema["properties"]) == set(FIELDS)
    assert schema["additionalProperties"] is False
    assert schema["x-source-timezone"] == "unknown"
    for args in (
        ["--page-size", "10"],
        ["--row-start", "10"],
        ["--risk-event-type", "SYN"],
    ):
        assert run_cli([*QUERY, *args])[0] == 2
    assert setup.state.business_requests == []
    seed(setup, run_cli, [])
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, "--require-complete"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert run_cli(["liquidity", "rules", "monitoring", "list"])[0] != 0


@pytest.mark.parametrize("mutation", ["offset", "width", "extra", "missing", "boolean"])
def test_transport_rejects_modified_fixed_request_before_fetch(
    setup, run_cli, monkeypatch, mutation
):
    from dogopencli.plugins.liquidity.capability import LiquidityListCapability

    original = LiquidityListCapability.page_body

    def altered(self, scope, row_start, page_size=None):
        body = original(self, scope, row_start, page_size)
        if mutation == "offset":
            body["rowStart"] = 5000
        elif mutation == "width":
            body["pageSize"] = 10
        elif mutation == "extra":
            body["unverified"] = "SYN"
        elif mutation == "missing":
            del body["pageSize"]
        elif mutation == "boolean":
            body["rowStart"] = False
        return body

    monkeypatch.setattr(LiquidityListCapability, "page_body", altered)
    code, out, _ = run_cli(REFRESH)
    assert code == 1 and parse(out)["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []


def test_projected_conflict_and_raw_private_difference(setup, run_cli):
    # Private-only differences are not distinct business projections. Repeated
    # arrivals are still incomplete, even when the reported total is one.
    setup.state.business_handler = lambda payload, index: response(
        [row(), {**row(), "creator": "OTHER"}], 1
    )
    code, out, err = run_cli(REFRESH)
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert parse(run_cli(QUERY)[1])["meta"]["complete"] is False


@pytest.mark.parametrize("value", [None, "", 0, -1, "0.00000", "UNRECOGNIZED"])
def test_raw_statuses_are_not_business_audited(setup, run_cli, value):
    source = row()
    source["effectiveStatus"] = value
    seed(setup, run_cli, [source])
    got = parse(run_cli(QUERY)[1])["data"][0]
    assert got["effectiveStatus"] == value
    assert got["version"] == "0007.0100"


def test_request_budget_exhaustion_preserves_capture(setup, run_cli, monkeypatch):
    from dogopencli import collect

    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    count = len(setup.state.business_requests)
    monkeypatch.setattr(collect, "REFRESH_BUDGET_SECONDS", 0)
    for command in ([*QUERY, "--live"], REFRESH):
        code, out, _ = run_cli(command)
        assert code == 1 and parse(out)["error"]["code"] == "TIMEOUT"
        assert setup.cache_path.read_bytes() == before
    assert len(setup.state.business_requests) == count
