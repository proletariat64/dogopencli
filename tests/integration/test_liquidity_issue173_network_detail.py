"""Realtime network aggregate through public CLI and synthetic CDP."""

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]

COMMAND = ["liquidity", "network", "realtime", "get", "--network-id", "SYN-NET"]


@pytest.mark.parametrize("reserved", ["operationHistory", "routeDetails"])
@pytest.mark.parametrize("value", [None, [], {"private": "PRIVATE"}])
def test_native_reserved_collision_withholds_business_data(
    setup, run_cli, reserved, value
):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"id": "SYN-NET", reserved: value}},
    }
    code, out, _ = run_cli(COMMAND)
    result = parse(out)
    assert code == 1
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert setup.state.business_requests == [{"id": "SYN-NET"}]
    assert not setup.cache_path.exists()
    assert "PRIVATE" not in out


def test_unverified_associations_preserve_root_and_disclose_partial_quality(
    setup, run_cli
):
    from dogopencli.plugins.liquidity.realtime_network import FIELDS

    native = dict.fromkeys(FIELDS, None)
    native.update(
        id="SYN-NET",
        version=7,
        routeId="SYN-ROUTE",
        debitAliasName=None,
        creditAliasName=None,
    )
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": native},
    }
    code, out, err = run_cli(COMMAND)
    result = parse(out)
    assert code == 0, (out, err)
    assert result["data"] == {**native, "operationHistory": None, "routeDetails": None}
    assert result["meta"]["complete"] is False
    assert result["meta"]["returned_count"] == 1
    assert result["meta"]["source_version"] == 7
    assert result["meta"]["warnings"]
    assert "INCOMPLETE_RESULT" in err
    for name in ("operationHistory", "routeDetails"):
        component = result["meta"]["components"][name]
        assert component["status"] == "unverified"
        assert component["complete"] is False
        assert component["captured_at"] is None
        assert component["returned_count"] is None
    assert setup.state.business_requests == [{"id": "SYN-NET"}]
    assert not setup.cache_path.exists()


def test_strict_unverified_associations_withhold_data_with_component_reasons(
    setup, run_cli
):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"id": "SYN-NET"}},
    }
    code, out, _ = run_cli([*COMMAND, "--require-complete"])
    result = parse(out)
    assert code == 1
    assert result["data"] is None
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["meta"]["components"]["operationHistory"]["status"] == "unverified"
    assert result["meta"]["warnings"]
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("fields", [[], ["--fields", "id"]])
def test_table_keeps_component_coverage_visible(setup, run_cli, fields):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"id": "SYN-NET"}},
    }
    code, out, err = run_cli([*COMMAND, "--format", "table", *fields])
    assert code == 0, err
    assert "complete: false" in out
    assert "operationHistory" in out and "routeDetails" in out
    assert "unverified" in out
    assert "HISTORY_CONTEXT_UNVERIFIED" in out
    assert "ROUTE_ASSOCIATION_UNVERIFIED" in out


def test_describe_publishes_component_boundary_and_exclusions(setup, run_cli):
    code, out, err = run_cli(["describe", *COMMAND[:4]])
    assert code == 0, (out, err)
    description = parse(out)
    properties = description["data_schema"]["properties"]
    assert len(properties) == 28
    assert properties["operationHistory"]["x-cli-association"] is True
    assert properties["routeDetails"]["x-cli-association"] is True
    assert (
        properties["operationHistory"]["items"]["properties"]["version"]["type"]
        == "integer"
    )
    route = properties["routeDetails"]
    assert route["additionalProperties"] is False
    assert route["properties"]["staticQuotas"]["items"]["additionalProperties"] is False
    window = route["properties"]["staticQuotas"]["items"]["properties"][
        "serviceWindowIntersection"
    ]
    assert window["items"]["additionalProperties"] is False
    assert (
        window["items"]["properties"]["timeSliceInfoList"]["items"][
            "additionalProperties"
        ]
        is False
    )
    code, public_out, _ = run_cli(
        ["describe", "liquidity", "network", "route-quotas", "get"]
    )
    assert code == 0
    assert (
        parse(public_out)["data_schema"]["properties"]["staticQuotas"]["items"][
            "additionalProperties"
        ]
        is True
    )
    assert "meta.components" in str(description)
    assert "--require-complete" in out
    assert "successRate" not in properties
    assert setup.state.transports == []


def test_verified_history_uses_alias_action_scope_and_preserves_version_identities(
    setup, run_cli
):
    root = {
        "id": "SYN-NET",
        "routeId": "",
        "version": 7,
        "creditAliasName": "SYN-CREDIT",
        "debitAliasName": "SYN-DEBIT",
        "fundAction": "TRANSFER",
        "scene": "REALTIME",
        "operationTime": None,
        "singlePaymentLimit": None,
    }
    old = {**root, "id": "SYN-OLD-NET", "version": 6, "operator": "PRIVATE"}
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "success": True,
            "data": [old, root] if "fundAction" in payload else root,
        },
    }
    code, out, err = run_cli(COMMAND)
    result = parse(out)
    assert code == 0, (out, err)
    assert setup.state.business_requests == [
        {"id": "SYN-NET"},
        {
            "creditAliasName": ["SYN-CREDIT"],
            "debitAliasName": ["SYN-DEBIT"],
            "fundAction": "TRANSFER",
        },
    ]
    assert [row["id"] for row in result["data"]["operationHistory"]] == [
        "SYN-OLD-NET",
        "SYN-NET",
    ]
    assert [row["version"] for row in result["data"]["operationHistory"]] == [6, 7]
    assert result["data"]["operationTime"] is None
    assert result["data"]["routeDetails"] is None
    components = result["meta"]["components"]
    assert components["routeDetails"]["applicability"] == "inapplicable"
    assert components["routeDetails"]["complete"] is True
    assert components["operationHistory"]["status"] == "succeeded"
    assert components["operationHistory"]["returned_count"] == 2
    assert components["operationHistory"]["reported_count"] is None
    assert components["operationHistory"]["reasons"] == ["HISTORY_COVERAGE_UNPROVEN"]
    assert result["meta"]["returned_count"] == 1
    assert result["meta"]["complete"] is False
    assert "PRIVATE" not in out
    assert not setup.cache_path.exists()


def test_route_uses_debit_context_and_preserves_windows_and_network_nulls(
    setup, run_cli
):
    root = {
        "id": "SYN-NET",
        "routeId": "SYN-ROUTE",
        "version": 7,
        "creditAliasName": "SYN-CREDIT",
        "debitAliasName": "SYN-DEBIT",
        "fundAction": "TRANSFER",
        "scene": "REALTIME",
        "operationTime": None,
        "singlePaymentLimit": None,
    }
    quotas = {
        "dynamicQuotas": [
            {
                "individualLimit": {
                    "currency": "USD",
                    "hasLimit": False,
                    "limit": 999999999999999999,
                }
            }
        ],
        "staticQuotas": [
            {
                "quotaId": "",
                "currency": "USD",
                "individualLimit": "0.123456789012345678901",
                "serviceWindowIntersection": [
                    {
                        "timeSliceGroupId": "G1",
                        "timeSliceInfoList": [
                            {
                                "timeZone": "Asia/Shanghai",
                                "timeUnit": "WEEK",
                                "timeValue": "MON",
                                "holidayTypeCode": "WORKDAY",
                                "beginTime": "08:00:00",
                                "endTime": "23:00:00",
                                "beginFromPreviousDay": False,
                            }
                        ],
                    }
                ],
                "operator": "PRIVATE",
            }
        ],
    }

    def response(payload, index):
        if "routeId" in payload:
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "result": {"success": True, "count": 0, "data": quotas},
                },
            }
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": [root] if "fundAction" in payload else root,
            },
        }

    setup.state.business_handler = response
    code, out, err = run_cli(COMMAND)
    result = parse(out)
    assert code == 0, (out, err)
    assert setup.state.business_requests[-1] == {
        "routeId": "SYN-ROUTE",
        "aliasName": "SYN-DEBIT",
        "tntInstId": "GUAPW3SG",
    }
    assert len(setup.state.business_requests) == 3
    data = result["data"]
    assert data["operationTime"] is None and data["singlePaymentLimit"] is None
    assert (
        data["routeDetails"]["dynamicQuotas"][0]["individualLimit"]["limit"]
        == 999999999999999999
    )
    assert data["routeDetails"]["staticQuotas"][0]["quotaId"] == ""
    assert (
        data["routeDetails"]["staticQuotas"][0]["serviceWindowIntersection"]
        == quotas["staticQuotas"][0]["serviceWindowIntersection"]
    )
    route = result["meta"]["components"]["routeDetails"]
    assert route["reported_count"] == 0 and route["reported_count_unit"] == "unknown"
    assert route["member_counts"] == {"dynamicQuotas": 1, "staticQuotas": 1}
    assert route["native_context_echo"] == {
        "routeId": "absent",
        "aliasName": "absent",
        "tntInstId": "absent",
    }
    assert route["complete"] is True
    assert result["meta"]["complete"] is False
    assert "PRIVATE" not in out
    assert not setup.cache_path.exists()


def test_shared_acquisition_deadline_hard_failure_withholds_root(
    setup, run_cli, monkeypatch
):
    from dogopencli import collect

    clock = {"now": 0.0}
    monkeypatch.setattr(collect, "_monotonic", lambda: clock["now"])
    root = {
        "id": "SYN-NET",
        "routeId": "",
        "creditAliasName": "SYN-CREDIT",
        "debitAliasName": "SYN-DEBIT",
        "fundAction": "TRANSFER",
        "scene": "REALTIME",
        "version": 7,
    }

    def response(payload, index):
        clock["now"] += collect.REFRESH_BUDGET_SECONDS * 0.6
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": [root] if "fundAction" in payload else root,
            },
        }

    setup.state.business_handler = response
    code, out, _ = run_cli(COMMAND)
    result = parse(out)
    assert code == 1
    assert result["data"] is None
    assert result["error"]["code"] == "TIMEOUT"
    assert len(setup.state.business_requests) == 2
    assert not setup.cache_path.exists()


def bound_root():
    return {
        "id": "SYN-NET",
        "routeId": "SYN-ROUTE",
        "creditAliasName": "SYN-CREDIT",
        "debitAliasName": "SYN-DEBIT",
        "fundAction": "TRANSFER",
        "scene": "REALTIME",
        "version": 7,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("creditAliasName", "OTHER"),
        ("debitAliasName", "OTHER"),
        ("fundAction", "OTHER"),
        ("tntInstId", "OTHER"),
        ("id", 7),
        ("version", "7"),
        ("scene", "OTHER"),
    ],
)
def test_history_identity_and_scope_conflicts_are_hard_errors(
    setup, run_cli, field, value
):
    root = bound_root()
    history = {**root, field: value}
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "success": True,
            "data": [history] if "fundAction" in payload else root,
        },
    }
    code, out, _ = run_cli(COMMAND)
    result = parse(out)
    assert code == 1 and result["data"] is None
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert len(setup.state.business_requests) == 2


@pytest.mark.parametrize("association", ["history", "route"])
@pytest.mark.parametrize("failure", ["auth", "business", "malformed", "wrong-context"])
def test_association_hard_failures_withhold_aggregate(
    setup, run_cli, association, failure
):
    root = bound_root()

    def response(payload, index):
        selected = (
            ("fundAction" in payload)
            if association == "history"
            else ("routeId" in payload)
        )
        if not selected:
            if "fundAction" in payload:
                return {"status": 200, "body": {"success": True, "data": [root]}}
            return {"status": 200, "body": {"success": True, "data": root}}
        if failure == "auth":
            return {"status": 401, "body": {}}
        if failure == "business":
            return {
                "status": 200,
                "body": {"success": False}
                if association == "history"
                else {"resultFlag": True, "result": {"success": False}},
            }
        if association == "history":
            data = (
                {} if failure == "malformed" else [{**root, "debitAliasName": "OTHER"}]
            )
            return {"status": 200, "body": {"success": True, "data": data}}
        data = (
            {"dynamicQuotas": None, "staticQuotas": []}
            if failure == "malformed"
            else {"routeId": "OTHER", "dynamicQuotas": [], "staticQuotas": []}
        )
        return {
            "status": 200,
            "body": {"resultFlag": True, "result": {"success": True, "data": data}},
        }

    setup.state.business_handler = response
    code, out, _ = run_cli(COMMAND)
    result = parse(out)
    assert code == 1 and result["data"] is None
    expected = (
        "AUTH_REQUIRED"
        if failure == "auth"
        else "BUSINESS_QUERY_FAILED"
        if failure == "business"
        else "INVALID_RESPONSE"
    )
    assert result["error"]["code"] == expected
    assert not setup.cache_path.exists()


def test_empty_history_is_unproven_but_empty_scoped_quota_arrays_are_success(
    setup, run_cli
):
    root = bound_root()

    def response(payload, index):
        if "routeId" in payload:
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "result": {
                        "success": True,
                        "count": 0,
                        "data": {"dynamicQuotas": [], "staticQuotas": []},
                    },
                },
            }
        return {
            "status": 200,
            "body": {"success": True, "data": [] if "fundAction" in payload else root},
        }

    setup.state.business_handler = response
    code, out, _ = run_cli(COMMAND)
    result = parse(out)
    assert code == 0
    assert result["data"]["operationHistory"] == []
    assert result["data"]["routeDetails"] == {"dynamicQuotas": [], "staticQuotas": []}
    assert result["meta"]["components"]["operationHistory"]["complete"] is False
    assert result["meta"]["components"]["routeDetails"]["complete"] is True
    code, out, _ = run_cli([*COMMAND, "--require-complete"])
    assert code == 1 and parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"


def test_source_change_is_disclosed_without_replacing_selected_root(setup, run_cli):
    root = {**bound_root(), "routeId": ""}
    later = {**root, "version": 8}
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": [later] if "fundAction" in payload else root},
    }
    code, out, _ = run_cli(COMMAND)
    result = parse(out)
    assert code == 0
    assert result["data"]["version"] == 7
    assert result["data"]["operationHistory"][0]["version"] == 8
    assert (
        "SOURCE_CHANGED" in result["meta"]["components"]["operationHistory"]["reasons"]
    )
    assert "SOURCE_CHANGED" in result["meta"]["warnings"][0]["reason_codes"]


def test_association_reads_leave_seeded_list_bytes_and_replay_scope_unchanged(
    setup, run_cli
):
    from test_liquidity_realtime_network_cli_sit import network, response

    setup.state.business_handler = lambda payload, index: response([network("SYN-NET")])
    assert run_cli(["refresh", "liquidity", "network", "realtime"])[0] == 0
    assert setup.state.business_requests == [{"rowStart": 0, "pageSize": 5000}]
    prior = setup.cache_path.read_bytes()
    root = {**bound_root(), "routeId": ""}
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": [root] if "fundAction" in payload else root},
    }
    assert run_cli(COMMAND)[0] == 0
    assert setup.cache_path.read_bytes() == prior
    before = len(setup.state.business_requests)
    assert run_cli(["liquidity", "network", "realtime", "list"])[0] == 0
    assert len(setup.state.business_requests) == before
    assert setup.cache_path.read_bytes() == prior


def test_conflicting_duplicate_history_versions_withhold_aggregate(setup, run_cli):
    root = {**bound_root(), "routeId": ""}
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "success": True,
            "data": [root, {**root, "version": 8}] if "fundAction" in payload else root,
        },
    }
    code, out, _ = run_cli(COMMAND)
    assert code == 1 and parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("scene", [None, "OTHER"])
def test_unverified_root_scene_never_enables_history_query(setup, run_cli, scene):
    root = {**bound_root(), "routeId": "", "scene": scene}
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": root},
    }
    code, out, _ = run_cli(COMMAND)
    assert code == 0
    assert parse(out)["data"]["operationHistory"] is None
    assert (
        parse(out)["meta"]["components"]["operationHistory"]["status"] == "unverified"
    )
    assert setup.state.business_requests == [{"id": "SYN-NET"}]


def test_raw_root_tenant_conflict_rejected_before_projection(setup, run_cli):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {**bound_root(), "tntInstId": "OTHER"}},
    }
    code, out, _ = run_cli(COMMAND)
    assert code == 1 and parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.state.business_requests == [{"id": "SYN-NET"}]
