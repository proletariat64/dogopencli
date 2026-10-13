"""Rule-status run-overview public CLI, native request shape and cache safety."""

import json

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]

SCOPE = [
    "--trigger-from",
    "2026-01-01 00:00:00",
    "--trigger-to",
    "2026-01-31 23:59:59",
]
QUERY = ["liquidity", "operations", "rule-status", "list"]
REFRESH = ["refresh", "liquidity", "operations", "rule-status"]

# UTC epoch milliseconds for the inclusive scope bounds.
TRIGGER_MS = 1768478400000  # 2026-01-15 12:00:00 UTC


def record(index=0, **changes):
    return {
        "id": 9007199254740993 + index,  # beyond float-exact 2**53
        "ruleId": f"synthetic-rule-{index}",
        "ruleName": "excluded free text",
        "tntInstId": "GUAPW3SG",
        "executeStatus": "EXECUTED",
        "createdOrder": "Y",
        "bizNo": f"synthetic-biz-{index}",
        "orderStatus": "PAID",
        "expectTriggerTime": TRIGGER_MS + index * 1000,
        "realTriggerTime": TRIGGER_MS + index * 1000 + 1,
        "gmtCreate": TRIGGER_MS - 1000,
        "gmtModified": TRIGGER_MS - 999,
        "expectTriggerDate": "20260115",
        "debitAmount": "excluded-amount",
        "accountNo": "excluded-account",
        "aliasName": "excluded-alias",
        **changes,
    }


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "data": rows,
                "count": len(rows) if total is None else total,
            },
        },
    }


def listing(rows, start=SCOPE[1], end=SCOPE[3]):
    def answer(payload, index):
        assert set(payload) == {"tntInstId", "transferRuleRecordQueryRequesVO"}
        vo = json.loads(payload["transferRuleRecordQueryRequesVO"])
        assert vo["tntInstId"] == payload["tntInstId"] == "GUAPW3SG"
        assert vo["queryDetailed"] == "false"
        assert vo["executeStatusList"] == []
        assert vo["createdOrderList"] == []
        assert vo["orderStatusList"] == []
        assert vo["rowStart"] == 0
        assert vo["pageSize"] == 5000
        assert vo["triggerStartTime"] == start
        assert vo["triggerEndTime"] == end
        return response(rows)

    return answer


@pytest.mark.parametrize(
    "scope",
    [
        [],
        SCOPE[:2],
        ["--trigger-from", "2026-01-32 00:00:00", *SCOPE[2:]],
        ["--trigger-from", "2026-01-01T00:00:00", *SCOPE[2:]],
        ["--trigger-from", SCOPE[3], "--trigger-to", SCOPE[1]],
    ],
)
def test_invalid_scope_is_rejected_before_browser_work(setup, run_cli, scope):
    code, out, _ = run_cli([*QUERY, *scope, "--live"])
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert not setup.state.transports
    assert not setup.cache_path.exists()


SCOPE_START_MS = 1767225600000  # 2026-01-01 00:00:00 UTC
SCOPE_END_MS = 1769903999000  # 2026-01-31 23:59:59 UTC


@pytest.mark.parametrize("offset_ms", [0, 500, 999])
def test_equal_endpoints_are_allowed_and_inclusive(setup, run_cli, offset_ms):
    point = [
        "--trigger-from",
        "2026-01-15 12:00:00",
        "--trigger-to",
        "2026-01-15 12:00:00",
    ]
    timestamp = TRIGGER_MS + offset_ms
    setup.state.business_handler = listing(
        [record(expectTriggerTime=timestamp)], point[1], point[3]
    )
    code, out, err = run_cli([*QUERY, *point, "--live"])
    assert code == 0, err
    assert parse(out)["data"][0]["expectTriggerTime"] == timestamp


def test_refresh_offline_live_precision_omissions_and_exact_scope(setup, run_cli):
    rows = [record(0), record(1)]
    setup.state.business_handler = listing(rows)
    code, out, err = run_cli([*REFRESH, *SCOPE, "--require-complete"])
    assert code == 0, err
    result = parse(out)
    assert result["data"]["row_count"] == 2
    assert result["meta"]["complete"] is True
    assert result["meta"]["published"] is True
    assert len(setup.state.business_requests) == 1
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli([*QUERY, *SCOPE, "--live", "--limit", "0"])
    assert code == 0, err
    live = parse(out)
    first = live["data"][0]
    assert first["id"] == 9007199254740993  # lossless beyond float 2**53
    assert first["executeStatus"] == "EXECUTED"
    assert first["expectTriggerTime"] == TRIGGER_MS
    assert first["gmtCreate"] == TRIGGER_MS - 1000
    assert first["gmtModified"] == TRIGGER_MS - 999
    excluded = {
        "ruleName",
        "tntInstId",
        "expectTriggerDate",
        "debitAmount",
        "accountNo",
        "aliasName",
    }
    assert not excluded & set(first)
    assert setup.cache_path.read_bytes() == before
    request_count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, "--limit", "0"])
    assert code == 0, err
    assert parse(out)["data"] == live["data"]
    assert len(setup.state.business_requests) == request_count
    changed = [*SCOPE[:2], "--trigger-to", "2026-02-01 00:00:00"]
    code, out, _ = run_cli([*QUERY, *changed])
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "changes",
    [
        {"tntInstId": "other-tenant"},
        {"tntInstId": None},
        {"id": True},
        {"id": "9007199254740993"},
        {"id": 0},
        {"id": -3},
        {"id": 1.5},
        {"id": None},
        {"ruleId": ""},
        {"ruleId": None},
        {"ruleId": ["nested"]},
        {"executeStatus": ""},
        {"executeStatus": 3},
        {"createdOrder": None},
        {"createdOrder": " "},
        {"bizNo": 7},
        {"orderStatus": None},
        {"expectTriggerTime": str(TRIGGER_MS)},
        {"expectTriggerTime": True},
        {"expectTriggerTime": SCOPE_START_MS - 1},
        {"expectTriggerTime": SCOPE_START_MS - 1000},
        {"expectTriggerTime": SCOPE_END_MS + 1000},
        {"realTriggerTime": str(TRIGGER_MS)},
        {"gmtCreate": "2026-01-15 12:00:00"},
        {"gmtModified": False},
    ],
)
def test_invalid_native_rows_fail_without_publishing(setup, run_cli, changes):
    setup.state.business_handler = lambda payload, index: response([record(**changes)])
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()
    code, out, _ = run_cli(
        [
            *QUERY,
        ]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"


def test_missing_real_trigger_time_key_is_rejected(setup, run_cli):
    row = record()
    del row["realTriggerTime"]
    setup.state.business_handler = lambda payload, index: response([row])
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "body,code_expected",
    [
        (
            {"resultFlag": True, "result": {"success": True, "data": []}},
            "INVALID_RESPONSE",
        ),
        (
            {"resultFlag": True, "result": {"success": True, "data": [], "count": "0"}},
            "INVALID_RESPONSE",
        ),
        (
            {
                "resultFlag": True,
                "result": {"success": True, "data": [], "count": True},
            },
            "INVALID_RESPONSE",
        ),
        (
            {"resultFlag": True, "result": {"success": True, "data": [], "count": -1}},
            "INVALID_RESPONSE",
        ),
        (
            {"resultFlag": True, "result": {"success": True, "data": {}, "count": 0}},
            "INVALID_RESPONSE",
        ),
        (
            {"resultFlag": True, "result": {"success": True, "data": [1], "count": 1}},
            "INVALID_RESPONSE",
        ),
        (
            {"resultFlag": True, "result": {"success": False, "data": [], "count": 0}},
            "BUSINESS_QUERY_FAILED",
        ),
    ],
)
def test_invalid_envelope_or_count_fails_without_publishing(
    setup, run_cli, body, code_expected
):
    setup.state.business_handler = lambda payload, index: {"status": 200, "body": body}
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"]["code"] == code_expected
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "rows,total",
    [
        ([record(0)], 2),  # shortfall
        ([record(0), record(1)], 1),  # extra rows
        ([record(0)], 0),  # zero count with rows
        ([], 2),  # empty array below count
    ],
)
def test_count_row_mismatch_fails_without_publishing(setup, run_cli, rows, total):
    setup.state.business_handler = lambda payload, index: response(rows, total)
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


def test_duplicate_native_identities_fail_live_and_refresh(setup, run_cli):
    setup.state.business_handler = lambda payload, index: response(
        [record(0), record(0)], 2
    )
    code, out, _ = run_cli([*QUERY, *SCOPE, "--live"])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


def test_oversized_array_is_rejected_before_row_validation(setup, run_cli):
    rows = [{} for _ in range(5001)]
    setup.state.business_handler = lambda payload, index: response(rows, 5001)
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    result = parse(out)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert "narrow" in result["error"]["message"]
    assert not setup.cache_path.exists()


def test_unverified_larger_scope_is_rejected_without_offset_followup(setup, run_cli):
    setup.state.business_handler = listing([record()])
    assert run_cli([*REFRESH, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()
    request_count = len(setup.state.business_requests)
    setup.state.business_handler = lambda payload, index: response([record()], 5001)
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    result = parse(out)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert "narrow" in result["error"]["message"]
    assert len(setup.state.business_requests) == request_count + 1
    last = json.loads(
        setup.state.business_requests[-1]["transferRuleRecordQueryRequesVO"]
    )
    assert last["rowStart"] == 0
    assert setup.cache_path.read_bytes() == before


def test_business_failure_preserves_previously_published_capture(setup, run_cli):
    setup.state.business_handler = listing([record()])
    assert run_cli([*REFRESH, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "resultFlag": False,
            "result": {"success": False, "data": [], "count": 0},
        },
    }
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(
        [
            *QUERY,
        ]
    )
    assert code == 0, err
    assert parse(out)["data"][0]["id"] == record()["id"]


def test_transport_failure_preserves_previously_published_capture(setup, run_cli):
    from dogopencli.browser import cdp

    setup.state.business_handler = listing([record()])
    assert run_cli([*REFRESH, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()

    def fail(payload, index):
        return cdp.CdpError("connection refused")

    setup.state.business_handler = fail
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"] is not None
    assert setup.cache_path.read_bytes() == before


def test_auth_expiry_preserves_previously_published_capture(setup, run_cli):
    from fake_cdp import SSO_URL
    from test_liquidity_cli_sit import LIQUIDITY_URL, route_probes

    setup.state.business_handler = listing([record()])
    assert run_cli([*REFRESH, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()
    route_probes(setup.state, (LIQUIDITY_URL, SSO_URL))
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"]["code"] == "AUTH_REQUIRED"
    assert setup.cache_path.read_bytes() == before


def test_verified_empty_capture_is_published_and_read_offline(setup, run_cli):
    setup.state.business_handler = listing([])
    code, out, err = run_cli([*REFRESH, *SCOPE, "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"]["row_count"] == 0
    assert not setup.cache_path.exists()
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, "--require-complete"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    setup.state.reachable = True
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"resultFlag": False, "result": {"success": False}},
    }
    code, out, _ = run_cli([*REFRESH, *SCOPE])
    assert code == 1
    assert parse(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    setup.state.reachable = False
    code, out, err = run_cli(
        [
            *QUERY,
        ]
    )
    assert code == 1, err
    assert parse(out)["error"]["code"] == "CACHE_MISS"


def test_nullable_trigger_and_empty_payment_refs_stay_raw(setup, run_cli):
    rows = [
        record(
            0,
            executeStatus="PRE_CONDITION_BLOCK",
            createdOrder="N",
            bizNo="",
            orderStatus="",
            realTriggerTime=None,
        ),
        record(1, executeStatus="NON-EXECUTION", orderStatus="PAYMENT_FAILURE"),
    ]
    setup.state.business_handler = listing(rows)
    assert run_cli([*REFRESH, *SCOPE])[0] == 0
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, "--limit", "0"])
    assert code == 0, err
    data = parse(out)["data"]
    assert data[0]["realTriggerTime"] is None
    assert data[0]["executeStatus"] == "PRE_CONDITION_BLOCK"
    assert data[0]["createdOrder"] == "N"
    assert data[0]["bizNo"] == ""
    assert data[0]["orderStatus"] == ""
    assert data[0]["expectTriggerTime"] == TRIGGER_MS
    assert data[1]["executeStatus"] == "NON-EXECUTION"
    assert data[1]["orderStatus"] == "PAYMENT_FAILURE"


@pytest.mark.parametrize(
    "timestamp",
    [SCOPE_START_MS, SCOPE_END_MS, SCOPE_END_MS + 500, SCOPE_END_MS + 999],
)
def test_native_trigger_time_boundaries_are_inclusive(setup, run_cli, timestamp):
    setup.state.business_handler = listing(
        [record(expectTriggerTime=timestamp, realTriggerTime=timestamp)]
    )
    code, out, err = run_cli([*QUERY, *SCOPE, "--live", "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"][0]["expectTriggerTime"] == timestamp


def test_help_and_describe_expose_supported_contract(setup, run_cli):
    code, out, err = run_cli(["help", *QUERY])
    assert code == 0, err
    document = parse(out)
    assert document["kind"] == "runtimes"
    options = {option["name"]: option for option in document["options"]}
    assert options["trigger_from"]["required"] is False
    assert options["trigger_to"]["required"] is False
    assert "UTC" in options["trigger_from"]["summary"]
    assert document["effects"]["network"] is False
    code, out, err = run_cli(["describe", *QUERY])
    assert code == 0, err
    document = parse(out)
    properties = document["data_schema"]["properties"]
    assert set(properties) == set(record()) - {
        "ruleName",
        "tntInstId",
        "expectTriggerDate",
        "debitAmount",
        "accountNo",
        "aliasName",
    }
    assert properties["expectTriggerTime"]["x-unit"] == "epoch milliseconds"
    assert "UTC" in properties["expectTriggerTime"]["description"]
    guide = document["read_guide"]
    assert guide["kind"] == "runtimes"
    assert guide["offline_profile"] == "single temporary leaf result"
    assert guide["identity"] == ["id"]
    assert guide["live_verified"] == "2026-10-06"
    request = guide["request"]
    assert request["method"] == "GET"
    assert request["path"] == "/queryTransferRulePreRunRecords.json"
    assert request["pagination"] == "single"
    assert request["page_size"] == 5000
    assert request["record_container"] == "$.result.data"
    assert request["reported_total"] == "$.result.count"


def test_snapshot_reports_supported_availability(setup, run_cli):
    code, out, err = run_cli(["snapshot", "liquidity", "--format", "json"])
    assert code == 0, err
    document = parse(out)

    def leaves(node):
        if "availability" in node:
            yield node
        for child in node["children"]:
            yield from leaves(child)

    command = "dogopencli liquidity operations rule-status list"
    node = next(leaf for leaf in leaves(document["tree"]) if leaf["command"] == command)
    assert node["availability"] == "supported"
    assert node["cache"]["status"] == "missing"


def test_getter_remains_refused_without_browser_work(setup, run_cli):
    code, out, _ = run_cli(["liquidity", "operations", "rule-status", "get", "1"])
    assert code == 2
    envelope = parse(out)
    assert envelope["error"]["code"] == "INVALID_ARGUMENT"
    assert "unknown command: get" in envelope["error"]["message"]
    assert not setup.state.transports
    assert not setup.cache_path.exists()


Z_SCOPE = [
    "--trigger-from",
    "2026-01-01T00:00:00Z",
    "--trigger-to",
    "2026-01-31T23:59:59Z",
]
# Explicit numeric offsets spelling the same instants (UTC/+08 day rollover).
OFFSET_SCOPE = [
    "--trigger-from",
    "2026-01-01T08:00:00+08:00",
    "--trigger-to",
    "2026-02-01T07:59:59+08:00",
]


def test_canonical_z_and_offset_forms_share_the_legacy_utc_scope(setup, run_cli):
    rows = [record(0), record(1)]
    setup.state.business_handler = listing(rows)
    code, _, err = run_cli([*REFRESH, *Z_SCOPE])
    assert code == 0, err
    assert "deprecated" not in err
    canonical_request = setup.state.business_requests[-1]
    assert run_cli([*REFRESH, *OFFSET_SCOPE])[0] == 0
    assert setup.state.business_requests[-1] == canonical_request
    assert run_cli([*REFRESH, *SCOPE])[0] == 0
    assert setup.state.business_requests[-1] == canonical_request
    # The emitted native request keeps the UTC space-separated representation.
    setup.state.business_handler = listing(rows)
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, "--limit", "0"])
    assert code == 0, err
    canonical = parse(out)
    # Explicit numeric offsets of the same instants read the identical scope.
    code, out, err = run_cli([*QUERY, "--limit", "0"])
    assert code == 0, err
    offset = parse(out)
    assert offset["data"] == canonical["data"]
    assert offset["meta"]["scope"] == canonical["meta"]["scope"]
    # The deprecated legacy space form reads the same scope with a diagnostic.
    code, out, err = run_cli([*QUERY, "--limit", "0"])
    assert code == 0, err
    legacy = parse(out)
    assert legacy["data"] == canonical["data"]
    assert legacy["meta"]["scope"] == canonical["meta"]["scope"]
    assert "deprecated" not in err
    assert legacy["error"] is None  # stdout stays a parseable envelope


def test_offset_input_normalizes_across_the_utc_day_boundary(setup, run_cli):
    # 2026-01-01T00:00:00+08:00 is 2025-12-31 16:00:00 UTC.
    scope = [
        "--trigger-from",
        "2026-01-01T00:00:00+08:00",
        "--trigger-to",
        "2026-01-02T00:00:00+08:00",
    ]
    setup.state.business_handler = listing(
        [], "2025-12-31 16:00:00", "2026-01-01 16:00:00"
    )
    code, out, err = run_cli([*QUERY, *scope, "--live"])
    assert code == 0, err
    assert "deprecated" not in err


@pytest.mark.parametrize(
    "value",
    [
        "2026-01-01T00:00:00-00:00",  # unknown-offset form
        "2026-01-01T00:00:00",  # missing offset on the canonical form
        "2026-01-01T00:00:00.5Z",  # fractional seconds
        "2026-01-01T23:59:60Z",  # leap second
        "2026-01-01t00:00:00Z",  # lowercase t
        "2026-01-01T00:00:00z",  # lowercase z
        "2026-01-01T00:00:00+0800",  # compact offset
        "2026-01-01",  # date only
    ],
)
def test_malformed_instants_rejected_before_browser_work(setup, run_cli, value):
    scope = ["--trigger-from", value, "--trigger-to", SCOPE[3]]
    for argv in ([*QUERY, *scope, "--live"], [*REFRESH, *scope]):
        code, out, _ = run_cli(argv)
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert not setup.state.transports
    assert not setup.cache_path.exists()


def test_canonical_equal_bounds_keep_exact_second_meaning(setup, run_cli):
    point = [
        "--trigger-from",
        "2026-01-15T12:00:00Z",
        "--trigger-to",
        "2026-01-15T12:00:00Z",
    ]
    setup.state.business_handler = listing(
        [record(expectTriggerTime=TRIGGER_MS)],
        "2026-01-15 12:00:00",
        "2026-01-15 12:00:00",
    )
    code, out, err = run_cli([*QUERY, *point, "--live"])
    assert code == 0, err
    assert parse(out)["data"][0]["expectTriggerTime"] == TRIGGER_MS


def test_help_declares_utc_instant_contract(setup, run_cli):
    code, out, err = run_cli(["help", *QUERY])
    assert code == 0, err
    options = {option["name"]: option for option in parse(out)["options"]}
    for name in ("trigger_from", "trigger_to"):
        assert "YYYY-MM-DDTHH:mm:ssZ" in options[name]["summary"]
        assert "UTC" in options[name]["summary"]
        assert "deprecated" in options[name]["summary"].lower()
