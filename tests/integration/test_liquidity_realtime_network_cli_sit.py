"""Issue #104 public CLI/fake CDP/real SQLite acceptance; invented records only."""

import copy

import pytest

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.realtime_network import FIELDS

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "network", "realtime"]


def query(*extra):
    return [*ROOT, "list", "--all", *extra]


def refresh(*extra):
    return ["refresh", *ROOT, *extra]


def network(identity="SYN-NETWORK"):
    row = dict.fromkeys(FIELDS, "SYN-UNKNOWN")
    row.update(
        id=identity,
        routeId="SYN-ROUTE",
        version=0,
        debitAliasName="SYN-DEBIT",
        creditAliasName="SYN-CREDIT",
        debitCurrency="USD",
        creditCurrency="unknown-currency",
        operationCalendar=None,
        operationTime="",
        singlePaymentLimit="0.000000",
        gmtCreate="unknown-time",
        gmtModified=None,
        timeZone=None,
    )
    return row


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
        [network()] if rows is None else rows
    )
    code, out, err = run_cli(refresh("--require-complete"))
    assert code == 0, err
    return parse(out)


def test_configuration_projection_exact_request_and_disconnected_lifecycle(
    setup, run_cli
):
    assert run_cli(query())[0] == 1
    assert setup.state.transports == []
    rows = [network("SYN-NETWORK-A"), network("SYN-NETWORK-B")]
    raw = [
        {
            **row,
            "avgEffectiveness": 0,
            "successRate": "99.99",
            "effectiveness": "private",
            "effectivenessLevel": "private",
            "lastOperationTime": "private",
            "creator": "private",
            "updater": "private",
            "memo": "private",
            "antProcessURL": "private",
            "operationPayload": {"private": True},
        }
        for row in rows
    ]
    capture = seed(setup, run_cli, raw)
    assert setup.state.business_requests == [{"rowStart": 0, "pageSize": 5000}]
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert len(expressions) == 1
    assert all(
        text in expressions[0]
        for text in (
            "/api/ai/decision/network/queryDecisionNetwork.json",
            "application/json",
            "POST",
            "iliquidity.alipay.com",
        )
    )
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(query("--live", "--require-complete"))
    assert code == 0, err
    live = parse(out)
    assert live["data"] == rows
    assert live["meta"]["kind"] == "settings"
    assert live["meta"]["complete"] is True
    assert live["meta"]["reported_total"] == live["meta"]["collected_total"] == 2
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    requests = len(setup.state.business_requests)
    code, out, err = run_cli(query("--require-complete"))
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == rows
    for field in ("scope", "fetched_at", "complete", "acquisition"):
        assert cached["meta"][field] == capture["meta"][field]
    assert "realtime-network-settings-v1" in cached["meta"]["scope"]
    assert len(setup.state.business_requests) == requests
    assert cached["meta"]["source_observed_from"] is None
    assert cached["meta"]["source_observed_to"] is None


@pytest.mark.parametrize("total", [1, 2, 5001])
def test_duplicates_and_missing_coverage_stay_partial_without_extra_requests(
    setup, run_cli, total
):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    row = network()
    setup.state.business_handler = lambda payload, index: response(
        [row, copy.deepcopy(row)], total
    )
    count = len(setup.state.business_requests)
    code, out, _ = run_cli(refresh("--require-complete"))
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    assert len(setup.state.business_requests) == count + 1
    code, out, err = run_cli(refresh())
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["complete"] is False
    assert len(setup.state.business_requests) == count + 2
    setup.state.reachable = False
    code, out, err = run_cli(query())
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert parse(out)["data"] == [row]
    assert parse(out)["meta"]["reported_total"] == total
    assert run_cli(query("--require-complete"))[0] == 1


def test_covered_arbitrary_count_and_empty_are_complete(setup, run_cli):
    rows = [network(f"SYN-NETWORK-{i:02d}") for i in range(17)]
    seed(setup, run_cli, rows)
    code, out, err = run_cli(query("--require-complete"))
    assert code == 0, err
    assert parse(out)["data"] == rows
    seed(setup, run_cli, [])
    setup.state.reachable = False
    code, out, err = run_cli(query("--require-complete"))
    assert code == 0, err
    assert parse(out)["data"] == [] and parse(out)["meta"]["complete"] is True


@pytest.mark.parametrize(
    "defect",
    [
        "false",
        "missing-success",
        "container",
        "row-shape",
        "identity-empty",
        "identity-int",
        "identity-conflict",
        "private-conflict",
        "missing-total",
        "negative-total",
        "bool-total",
        "string-total",
        "auth",
        "permission",
        "redirect",
        "transport",
    ],
)
def test_hard_failures_preserve_capture_and_never_return_empty_success(
    setup, run_cli, defect
):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    row = network()
    answer = response([row])
    if defect == "false":
        answer["body"]["success"] = False
    elif defect == "missing-success":
        del answer["body"]["success"]
    elif defect == "container":
        answer["body"]["data"]["data"] = {}
    elif defect == "row-shape":
        answer["body"]["data"]["data"] = [None]
    elif defect == "identity-empty":
        row["id"] = " "
    elif defect == "identity-int":
        row["id"] = 123
    elif defect in ("identity-conflict", "private-conflict"):
        answer["body"]["data"]["data"].append(
            {
                **row,
                "routeId"
                if defect == "identity-conflict"
                else "successRate": "different",
            }
        )
    elif defect == "missing-total":
        del answer["body"]["data"]["totalCount"]
    elif defect in ("negative-total", "bool-total", "string-total"):
        answer["body"]["data"]["totalCount"] = {
            "negative-total": -1,
            "bool-total": True,
            "string-total": "1",
        }[defect]
    elif defect in ("auth", "permission", "redirect"):
        answer = {
            "status": {"auth": 401, "permission": 403, "redirect": 302}[defect],
            "body": {"success": False},
        }
    elif defect == "transport":
        answer = cdp.CdpError("synthetic connection failure")
    setup.state.business_handler = lambda payload, index: answer
    for command in (query("--live"), refresh()):
        code, out, _ = run_cli(command)
        assert code == 1 and parse(out)["data"] is None
        assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    code, out, err = run_cli(query())
    assert code == 0, err
    assert parse(out)["data"] == [network()]


@pytest.mark.parametrize(
    "flag",
    [
        "--status",
        "--tenant",
        "--account",
        "--url",
        "--payload",
        "--row-start",
        "--page-size",
    ],
)
def test_unverified_request_arguments_are_rejected_before_browser(setup, run_cli, flag):
    for command in (query("--live", flag, "anything"), refresh(flag, "anything")):
        code, out, _ = run_cli(command)
        assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert not setup.cache_path.exists()


def test_discovery_snapshot_and_unrelated_guards_stay_offline(setup, run_cli):
    code, out, err = run_cli(["describe", *ROOT, "list"])
    assert code == 0, err
    assert parse(out)["read_guide"]["live_verified"] == "2026-10-05"
    description = parse(out)
    guide = description["read_guide"]
    assert guide["offline_profile"] == "snapshot"
    assert guide["request"]["pagination"] == "single"
    assert guide["request"]["page_size"] == 5000
    assert guide["identity"] == ["id"]
    assert set(description["data_schema"]["properties"]) == set(FIELDS)
    assert run_cli(["help", *ROOT, "list"])[0] == 0
    for path in (
        [*ROOT, "get"],
        ["liquidity", "network", "routes", "list"],
        ["liquidity", "rules", "monitoring", "list"],
    ):
        code, out, _ = run_cli(path)
        assert code == 1 and parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert setup.state.transports == []


def test_other_list_capture_isolation_and_partial_snapshot_quality(setup, run_cli):
    other = ["liquidity", "rules", "realtime"]
    rule = {"id": "SYN-RULE", "ruleName": "SYN-RULE-NAME", "runStatus": "UNKNOWN"}
    setup.state.business_handler = lambda payload, index: response([rule])
    assert run_cli(["refresh", *other])[0] == 0
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = lambda payload, index: response([network()], 5001)
    code, out, _ = run_cli(refresh("--require-complete"))
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(refresh())
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["complete"] is False
    setup.state.reachable = False
    count = len(setup.state.business_requests)
    code, out, err = run_cli([*other, "list", "--all"])
    assert code == 0, err
    assert parse(out)["data"] == [rule]
    code, out, err = run_cli(query())
    assert code == 0 and "INCOMPLETE_RESULT" in err
    cached = parse(out)
    assert cached["data"] == [network()]
    assert cached["meta"]["reported_total"] == 5001
    code, out, err = run_cli(["snapshot", *ROOT, "--format", "json"])
    assert code == 0, err
    snapshot = parse(out)
    assert snapshot["inspection_complete"] is True
    assert "incomplete" in str(snapshot)
    assert len(setup.state.business_requests) == count


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"rowStart": 0},
        {"pageSize": 5000},
        {"rowStart": 5000, "pageSize": 5000},
        {"rowStart": 0, "pageSize": 1},
        {"rowStart": 5000, "pageSize": 1},
        {"rowStart": 0, "pageSize": 5000, "tntInstId": "SYN-TENANT"},
    ],
)
def test_changed_or_missing_fixed_pagination_rejected_before_browser(setup, body):
    from dogopencli.errors import CliError
    from dogopencli.plugins.liquidity.capability import LiquidityListCapability
    from dogopencli.plugins.liquidity.realtime_network import REALTIME_NETWORK
    from dogopencli.transport import QueryRequest
    from dogopencli.transport.cdp import CdpQueryTransport

    capability = LiquidityListCapability(REALTIME_NETWORK)
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url=capability.page_url,
    )
    request = QueryRequest(
        capability.name,
        capability.contract.method,
        capability.contract.host,
        capability.contract.path,
        body,
    )
    with pytest.raises(CliError) as caught:
        transport.execute(request)
    assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
    assert not any(t.created for t in setup.state.transports)
    assert not any(t.expressions for t in setup.state.transports)
