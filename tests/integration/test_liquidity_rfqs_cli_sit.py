"""TARGET_RFQ public CLI, fake CDP and real SQLite; every row is synthetic."""

import copy
import hashlib
from dataclasses import replace

import pytest

from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.capability import (
    LiquidityListCapability,
    encode_scope,
)
from dogopencli.plugins.liquidity.rfqs import RFQS
from dogopencli.transport import QueryRequest, validate_request

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "investment", "rfqs"]
BOUNDS = ["--from-date", "2026-01-01", "--to-date", "2026-10-05"]


def query(*extra, bounds=BOUNDS):
    return [*ROOT, "list", *bounds, "--all", *extra]


def refresh(*extra, bounds=BOUNDS):
    return ["refresh", *ROOT, *bounds, *extra]


def subtask(identity="SYN-SUBTASK"):
    return {
        "inquirySubTaskId": identity,
        "inquiryTaskId": "SYN-PARENT",
        "inquiryType": "TARGET_RFQ",
        "productType": "SYN-PRODUCT",
        "currency": "USD",
        "tenor": "O/N",
        "redemptionFeature": "",
        "inquiryStatus": "UNKNOWN-INQUIRY",
        "quotationStatus": None,
        "winStatus": "UNKNOWN-WIN",
        "quotedNum": 0,
        "inquiryNum": -2,
        "winNum": 7,
        "inquiryStartTime": "2026-01-01 11:22:33",
        "inquiryEndTime": "",
        "modifyTime": "unknown-time",
        "processStatus": "UNKNOWN-PROCESS",
    }


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


def digest(setup):
    return hashlib.sha256(setup.cache_path.read_bytes()).hexdigest()


def seed(setup, run_cli, rows=None, bounds=BOUNDS):
    setup.state.business_handler = lambda payload, index: response(
        [subtask()] if rows is None else rows
    )
    code, out, err = run_cli(refresh("--require-complete", bounds=bounds))
    assert code == 0, err
    return parse(out)


def test_native_contract_fidelity_and_disconnected_capture_lifecycle(setup, run_cli):
    code, out, _ = run_cli(query())
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    rows = [subtask("SYN-SUB-A"), subtask("SYN-SUB-B")]
    rows[1].update(currency="unknown", tenor=None, quotedNum="0.000000", winNum=None)
    raw = [
        {
            **row,
            "inquirer": "EXCLUDED",
            "memo": "EXCLUDED",
            "processId": "EXCLUDED",
            "unknownExtra": "EXCLUDED",
        }
        for row in rows
    ]
    seeded = seed(setup, run_cli, raw)
    assert setup.state.business_requests == [
        {
            "rowStart": 0,
            "pageSize": 5000,
            "inquiryType": "TARGET_RFQ",
            "inquiryStartDate": "20260101",
            "inquiryEndDate": "20261005",
        }
    ]
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any(
        "/rfq/subInquiryTask/querySubInquiryTask.json" in e
        and "application/json" in e
        and "POST" in e
        for e in expressions
    )
    created = [u for t in setup.state.transports for u in t.created]
    assert all(u.startswith("https://iliquidity.alipay.com/") for u in created)
    assert seeded["meta"]["complete"] is True
    assert seeded["meta"]["reported_total"] == 2
    before = digest(setup)
    code, out, err = run_cli(query("--live", "--require-complete"))
    assert code == 0, err
    live = parse(out)
    assert live["data"] == rows
    assert live["meta"]["collected_total"] == 2
    assert live["meta"]["acquisition"]["arrivals"] == 2
    assert len(setup.state.business_requests) == 2
    assert digest(setup) == before
    setup.state.reachable = False
    code, out, err = run_cli(query("--require-complete"))
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == rows
    for field in ("scope", "fetched_at", "acquisition", "complete", "reported_total"):
        assert cached["meta"][field] == seeded["meta"][field]
    assert cached["meta"]["source_observed_from"] is None
    assert cached["meta"]["source_observed_to"] is None
    assert "rfq-target-subtasks-v1" in cached["meta"]["scope"]
    assert "TARGET_RFQ" in cached["meta"]["scope"]
    assert len(setup.state.business_requests) == 2
    setup.state.reachable = True
    setup.state.business_handler = lambda payload, index: {
        "status": 401,
        "body": {"success": False},
    }
    code, out, _ = run_cli(query("--live"))
    assert code == 1 and parse(out)["data"] is None
    assert digest(setup) == before


def test_exact_scope_isolation_and_complete_empty(setup, run_cli):
    populated = seed(setup, run_cli)
    adjacent = ["--from-date", "2026-01-01", "--to-date", "2026-01-01"]
    setup.state.reachable = False
    code, out, _ = run_cli(query(bounds=adjacent))
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    setup.state.reachable = True
    empty = seed(setup, run_cli, [], bounds=adjacent)
    assert empty["meta"]["complete"] is True and empty["meta"]["reported_total"] == 0
    assert empty["meta"]["scope"] != populated["meta"]["scope"]
    before = digest(setup)
    code, out, err = run_cli(query("--live", "--require-complete", bounds=adjacent))
    assert code == 0, err
    assert parse(out)["data"] == [] and digest(setup) == before
    setup.state.reachable = False
    code, out, err = run_cli(query("--require-complete", bounds=adjacent))
    assert code == 0, err
    assert parse(out)["data"] == []
    assert parse(out)["meta"]["fetched_at"] == empty["meta"]["fetched_at"]
    code, out, err = run_cli(query())
    assert code == 0, err
    assert parse(out)["data"] == [subtask()]
    assert parse(out)["meta"]["fetched_at"] == populated["meta"]["fetched_at"]
    code, out, _ = run_cli(["liquidity", "investment", "quotes", "list", *BOUNDS])
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize(
    "bounds",
    [
        [],
        ["--from-date", "2026-01-01"],
        ["--from-date", "2026-02-30", "--to-date", "2026-03-01"],
        ["--from-date", "20260101", "--to-date", "2026-10-05"],
        ["--from-date", "2026-1-1", "--to-date", "2026-10-05"],
        ["--from-date", "2026-10-06", "--to-date", "2026-10-05"],
        [*BOUNDS, "--inquiry-type", "FULL_RANGE_RFQ"],
        [*BOUNDS, "--product-type", "SYN-PRODUCT"],
        [*BOUNDS, "--status", "SYN-STATUS"],
        [*BOUNDS, "--parent-id", "SYN-PARENT"],
        [*BOUNDS, "--task-id", "SYN-TASK"],
        [*BOUNDS, "--page-size", "10"],
    ],
)
def test_invalid_unbounded_and_unverified_filters_fail_before_browser(
    setup, run_cli, bounds
):
    for command in (query("--live", bounds=bounds), refresh(bounds=bounds)):
        code, out, _ = run_cli(command)
        assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "defect",
    [
        "099",
        "success-missing",
        "container",
        "row-shape",
        "identity-empty",
        "identity-int",
        "identity-conflict",
        "type",
        "total-missing",
        "total-bool",
        "total-negative",
        "total-string",
        "total-excess-unique",
        "empty-shortfall",
        "auth",
        "permission",
        "transport",
    ],
)
def test_hard_failures_preserve_capture_without_live_fallback(setup, run_cli, defect):
    seed(setup, run_cli)
    before = digest(setup)
    row = subtask()
    answer = response([row])
    body = answer["body"]
    if defect == "099":
        body.update(success=False, errorCode="099", errorMsg="SYN failure")
    elif defect == "success-missing":
        del body["success"]
    elif defect == "container":
        body["data"]["data"] = {}
    elif defect == "row-shape":
        body["data"]["data"] = [None]
    elif defect == "identity-empty":
        row["inquirySubTaskId"] = ""
    elif defect == "identity-int":
        row["inquirySubTaskId"] = 123
    elif defect == "identity-conflict":
        body["data"]["data"].append({**row, "winNum": 999})
        body["data"]["totalCount"] = 2
    elif defect == "type":
        row["inquiryType"] = "FULL_RANGE_RFQ"
    elif defect == "total-missing":
        del body["data"]["totalCount"]
    elif defect.startswith("total-"):
        body["data"]["totalCount"] = {
            "total-bool": True,
            "total-negative": -1,
            "total-string": "1",
            "total-excess-unique": 0,
        }[defect]
    elif defect == "empty-shortfall":
        body["data"]["data"] = []
    elif defect in {"auth", "permission", "transport"}:
        answer = {
            "status": {"auth": 401, "permission": 403, "transport": 500}[defect],
            "body": {"success": False},
        }
    setup.state.business_handler = lambda payload, index: answer
    for command in (query("--live"), refresh()):
        code, out, _ = run_cli(command)
        assert code == 1 and parse(out)["data"] is None
        assert digest(setup) == before
    setup.state.reachable = False
    code, out, err = run_cli(query())
    assert code == 0, err
    assert parse(out)["data"] == [subtask()]


@pytest.mark.parametrize("duplicate", [True, False])
def test_partial_quality_and_strict_atomicity_without_offset_retries(
    setup, run_cli, duplicate
):
    seed(setup, run_cli)
    before = digest(setup)
    row = subtask()
    rows = [row, copy.deepcopy(row)] if duplicate else [row]
    setup.state.business_handler = lambda payload, index: response(rows, 2)
    count = len(setup.state.business_requests)
    code, out, _ = run_cli(refresh("--require-complete"))
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert digest(setup) == before
    assert len(setup.state.business_requests) == count + 1
    code, out, err = run_cli(refresh())
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["complete"] is False
    assert len(setup.state.business_requests) == count + 2
    setup.state.reachable = False
    code, out, err = run_cli(query())
    assert code == 0 and "INCOMPLETE_RESULT" in err
    cached = parse(out)
    assert cached["data"] == [row]
    assert cached["meta"]["reported_total"] == 2
    assert cached["meta"]["acquisition"]["arrivals"] == len(rows)
    assert "COUNT_SHORTFALL" in cached["meta"]["acquisition"]["reasons"]
    assert run_cli(query("--require-complete"))[0] == 1


def test_offline_description_help_snapshot_and_child_identity_required(setup, run_cli):
    code, out, err = run_cli(["describe", *ROOT, "list"])
    assert code == 0, err
    description = parse(out)
    guide = description["read_guide"]
    assert guide["kind"] == "runtimes"
    assert guide["schema_version"] == "rfq-target-subtasks-v1"
    assert guide["offline_profile"] == "history"
    assert guide["request"]["pagination"] == "single"
    assert guide["request"]["reported_total"] == "$.data.totalCount"
    assert guide["request"]["page_size"] == 5000
    assert guide["identity"] == ["inquirySubTaskId"]
    schema = description["data_schema"]
    assert schema["x-source-timezone"] == "unknown"
    assert schema["x-boundary-semantics"] == "unknown"
    assert "Parent task" in schema["properties"]["inquiryTaskId"]["description"]
    assert set(schema["properties"]) == set(subtask())
    assert all(
        schema["properties"][f]["x-timezone"] == "unknown"
        for f in ("inquiryStartTime", "inquiryEndTime", "modifyTime")
    )
    code, _, err = run_cli(["help", *ROOT, "list"])
    assert code == 0, err
    code, out, _ = run_cli([*ROOT, "get"])
    assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    code, out, err = run_cli(["snapshot", *ROOT, "list", "--format", "json"])
    assert code == 0, err
    tree = parse(out)["tree"]
    assert tree["availability"] == "supported"
    assert tree["cache"]["status"] == "missing"
    assert setup.state.transports == []


@pytest.mark.parametrize(
    "mutation",
    ["type", "offset", "width", "filter", "method", "host", "path"],
)
def test_shared_transport_rejects_contract_mutations(mutation):
    capability = LiquidityListCapability(RFQS)
    body = capability.page_body(
        encode_scope(
            {"inquiryStartDate": "2026-01-01", "inquiryEndDate": "2026-10-05"}
        ),
        0,
    )
    request = QueryRequest(
        capability.name, "POST", "iliquidity.alipay.com", RFQS.endpoint, body
    )
    validate_request(request, capability.contract)
    if mutation == "type":
        body["inquiryType"] = "FULL_RANGE_RFQ"
    elif mutation == "offset":
        body["rowStart"] = 5000
    elif mutation == "width":
        body["pageSize"] = 10
    elif mutation == "filter":
        body["inquiryTaskId"] = "SYN-PARENT"
    else:
        changes = {
            "method": {"method": "GET"},
            "host": {"host": "ifundcontrol.alipay.com"},
            "path": {"path": "/rfq/subInquiryTask/update.json"},
        }[mutation]
        request = replace(request, **changes)
    with pytest.raises(CliError) as caught:
        validate_request(request, capability.contract)
    assert caught.value.code == "REQUEST_NOT_ALLOWED"


def test_request_budget_failure_preserves_capture(setup, run_cli, monkeypatch):
    from dogopencli import collect

    seed(setup, run_cli)
    before = digest(setup)
    requests = len(setup.state.business_requests)
    monkeypatch.setattr(collect, "REFRESH_BUDGET_SECONDS", 0)
    code, out, _ = run_cli(refresh())
    assert code == 1 and parse(out)["error"]["code"] == "TIMEOUT"
    assert digest(setup) == before
    assert len(setup.state.business_requests) == requests
