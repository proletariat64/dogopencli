"""Prefund aggregate inquiries through public CLI and synthetic CDP."""

import json

import pytest

from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.spec import TENANT

pytest_plugins = ["test_liquidity_cli_sit"]
COMMAND = ["liquidity", "operations", "prefunds", "get", "--id", "SYN-CURRENT"]


def application(identity="SYN-CURRENT", version=2, status="APPROVED"):
    return {
        "id": identity,
        "version": version,
        "instId": "SYN-ENTITY",
        "status": status,
        "prefundingBizNo": "SYN-BUSINESS",
        "tntInstId": TENANT,
        "amount": "100.000000000000000001",
        "allowUseAmount": "98.00",
        "usedAmount": "2.00",
        "memo": None,
        "fileUrlList": [],
    }


def transaction(identity="SYN-USE", application_id="SYN-OLD"):
    return {
        "preFundingUseDetailId": identity,
        "preFundingOrderId": application_id,
        "prefundingBizNo": "",
        "tntInstId": TENANT,
        "useDirection": "USE",
        "status": "FAIL",
        "applyCurrency": "USD",
        "exchangeAmount": "2.000000000000000001",
        "useRevertRelationVOList": [
            {"currency": "EUR", "amount": "1.234567890123456789"}
        ],
    }


def page(rows, count):
    return {
        "status": 200,
        "body": {"resultFlag": True, "result": {"dataValue": rows, "count": count}},
    }


def configure(setup, *, root=None, history=None, transactions=None, count=0):
    root = application() if root is None else root
    history = (
        [application("SYN-OLD", 1, "APPROVED_FINAL")] if history is None else history
    )
    transactions = [transaction()] if transactions is None else transactions

    def answer(payload, index):
        if "preFundingId" in payload:
            return {
                "status": 200,
                "body": {"resultFlag": True, "result": {"data": root, "count": 0}},
            }
        if "preFundingOrderQueryVO" in payload:
            query = json.loads(payload["preFundingOrderQueryVO"])
            assert query["prefundingBizNo"] == "SYN-BUSINESS"
            if query["statusList"] == ["APPROVED", "CLOSED"]:
                return page([application()], 1)
            return page(history, len(history))
        assert payload == {"tntInstId": TENANT, "prefundingBizNo": "SYN-BUSINESS"}
        return page(transactions, count)

    setup.state.business_handler = answer
    return root, history, transactions


def test_current_root_preserves_nested_cross_version_rows_and_count_anomaly(
    setup, run_cli
):
    root, history, transactions = configure(setup)
    code, out, err = run_cli(COMMAND)
    result = parse(out)
    assert code == 0, (out, err)
    assert result["data"] == {
        **root,
        "historyApplications": history,
        "drawdownDetails": transactions,
    }
    meta = result["meta"]
    assert meta["returned_count"] == meta["matched_total"] == 1
    assert meta["complete"] is False
    assert meta["components"]["drawdownDetails"]["reported_count"] == 0
    assert "ZERO_COUNT_NONEMPTY" in meta["components"]["drawdownDetails"]["reasons"]
    assert "INCOMPLETE_RESULT" in err
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 12),
        ("tntInstId", "OTHER"),
        ("prefundingBizNo", ""),
        ("version", True),
        ("historyApplications", []),
        ("drawdownDetails", None),
    ],
)
def test_invalid_selected_application_stops_before_associations(
    setup, run_cli, field, value
):
    root = application()
    root[field] = value
    configure(setup, root=root)
    code, out, _ = run_cli(COMMAND)
    result = parse(out)
    assert code == 1
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert len(setup.state.business_requests) == 1


@pytest.mark.parametrize(
    "history",
    [
        [
            application("SYN-OLD", 1, "APPROVED_FINAL"),
            application("SYN-OTHER", 1, "APPROVED_FINAL"),
        ],
        [application("SYN-CURRENT", 1, "APPROVED_FINAL")],
        [{**application("SYN-OLD", 1, "APPROVED_FINAL"), "prefundingBizNo": "OTHER"}],
        [{**application("SYN-OLD", 1, "APPROVED_FINAL"), "tntInstId": "OTHER"}],
    ],
)
def test_invalid_history_withholds_whole_aggregate(setup, run_cli, history):
    configure(setup, history=history)
    code, out, _ = run_cli(COMMAND)
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert len(setup.state.business_requests) in (2, 3)


@pytest.mark.parametrize(
    "field,value",
    [
        ("preFundingUseDetailId", None),
        ("preFundingOrderId", "SYN-OUTSIDE"),
        ("prefundingBizNo", "OTHER"),
        ("tntInstId", "OTHER"),
        ("useRevertRelationVOList", {}),
    ],
)
def test_invalid_transaction_withholds_whole_aggregate(setup, run_cli, field, value):
    row = transaction()
    row[field] = value
    configure(setup, transactions=[row])
    code, out, _ = run_cli(COMMAND)
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"


def test_strict_rejects_unproven_coverage_and_preserves_components(setup, run_cli):
    configure(setup)
    code, out, _ = run_cli([*COMMAND, "--require-complete"])
    result = parse(out)
    assert code == 1
    assert result["data"] is None
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["meta"]["components"]["drawdownDetails"]["reported_count"] == 0
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("fields", [[], ["--fields", "id"]])
def test_projection_keeps_quality_visible_and_table_discloses_nested_arrays(
    setup, run_cli, fields
):
    configure(setup)
    code, out, err = run_cli([*COMMAND, *fields])
    result = parse(out)
    assert code == 0, err
    if fields:
        assert result["data"] == {"id": "SYN-CURRENT"}
    assert result["meta"]["components"]["drawdownDetails"]["complete"] is False
    code, out, err = run_cli([*COMMAND, "--format", "table", *fields])
    assert code == 0, err
    assert "historyApplications" in out and "drawdownDetails" in out
    assert "Nested associations" in out
    assert "complete: false" in out


def test_duplicate_transaction_identity_is_safe_partial_but_conflicting_content_fails(
    setup, run_cli
):
    row = transaction()
    configure(setup, transactions=[row, row])
    code, out, _ = run_cli(COMMAND)
    assert code == 0
    result = parse(out)
    assert result["data"]["drawdownDetails"] == [row]
    assert (
        "DUPLICATE_IDENTITIES"
        in result["meta"]["components"]["drawdownDetails"]["reasons"]
    )
    configure(setup, transactions=[row, {**row, "status": "SUCCESS"}])
    code, out, _ = run_cli(COMMAND)
    assert code == 1
    assert parse(out)["data"] is None


@pytest.mark.parametrize("component", [1, 2, 3])
@pytest.mark.parametrize("failure", ["business", "parse", "http", "auth"])
def test_association_failures_never_become_empty_results(
    setup, run_cli, component, failure
):
    configure(setup)
    healthy = setup.state.business_handler

    def answer(payload, index):
        if index == component:
            return {
                "business": {"status": 200, "body": {"resultFlag": False}},
                "parse": {
                    "status": 200,
                    "body": {
                        "resultFlag": True,
                        "result": {"dataValue": None, "count": 0},
                    },
                },
                "http": {"status": 400, "body": {}},
                "auth": {"status": 401, "body": {}},
            }[failure]
        return healthy(payload, index)

    setup.state.business_handler = answer
    code, out, _ = run_cli(COMMAND)
    assert code == 1
    assert parse(out)["data"] is None
    assert not setup.cache_path.exists()


def test_historical_selection_keeps_root_and_accepts_current_and_old_transactions(
    setup, run_cli
):
    old = application("SYN-OLD", 1, "APPROVED_FINAL")
    rows = [transaction(), transaction("SYN-REVERT", "SYN-CURRENT")]
    rows[1].update(status="SUCCESS", useDirection="REVERT")
    configure(setup, root=old, history=[old], transactions=rows)
    code, out, err = run_cli([*COMMAND[:5], "SYN-OLD"])
    result = parse(out)
    assert code == 0, (out, err)
    assert result["data"]["id"] == "SYN-OLD"
    assert result["data"]["version"] == 1
    assert result["data"]["drawdownDetails"] == rows
    membership = result["meta"]["components"]["historyApplications"][
        "version_membership"
    ]
    assert membership["request_scope"]["statusList"] == ["APPROVED", "CLOSED"]
    assert membership["returned_count"] == 1


def test_history_pagination_uses_native_inner_offsets_and_keeps_raw_fields(
    setup, run_cli
):
    configure(setup)
    rows = [application(f"SYN-OLD-{i}", i, "APPROVED_FINAL") for i in range(12)]
    root = application(version=12)

    def answer(payload, index):
        if "preFundingId" in payload:
            return {
                "status": 200,
                "body": {"resultFlag": True, "result": {"data": root, "count": 0}},
            }
        if "preFundingOrderQueryVO" in payload:
            scope = json.loads(payload["preFundingOrderQueryVO"])
            assert "rowStart" not in payload and "pageSize" not in payload
            if scope["statusList"] == ["APPROVED_FINAL"]:
                start = scope["rowStart"]
                return page(rows[start : start + scope["pageSize"]], 12)
            return page([root], 1)
        return page([transaction(application_id="SYN-OLD-0")], 0)

    setup.state.business_handler = answer
    code, out, err = run_cli(COMMAND)
    result = parse(out)
    assert code == 0, (out, err)
    assert result["data"]["historyApplications"] == rows
    queries = [
        json.loads(p["preFundingOrderQueryVO"])
        for p in setup.state.business_requests
        if "preFundingOrderQueryVO" in p
    ]
    assert [p["rowStart"] for p in queries] == [0, 10, 0]
    assert result["meta"]["components"]["historyApplications"]["complete"] is True


def test_describe_documents_aggregate_arrays_and_projection_contract(setup, run_cli):
    code, out, err = run_cli(["describe", *COMMAND[:4]])
    assert code == 0, err
    description = parse(out)
    properties = description["data_schema"]["properties"]
    assert properties["historyApplications"]["x-cli-association"] is True
    assert properties["drawdownDetails"]["x-cli-association"] is True
    assert properties["drawdownDetails"]["items"]["properties"][
        "useRevertRelationVOList"
    ]["type"] == ["array", "null"]
    assert "meta.components" in out
    assert "--require-complete" in out
    assert setup.state.transports == []


def test_successful_empty_components_are_fetched_and_coverage_remains_unproven(
    setup, run_cli
):
    configure(setup, history=[], transactions=[])
    code, out, err = run_cli(COMMAND)
    result = parse(out)
    assert code == 0, err
    assert result["data"]["historyApplications"] == []
    assert result["data"]["drawdownDetails"] == []
    components = result["meta"]["components"]
    assert components["historyApplications"]["complete"] is True
    assert components["drawdownDetails"]["status"] == "succeeded"
    assert components["drawdownDetails"]["complete"] is False
    assert components["drawdownDetails"]["reported_count"] == 0
    assert len(setup.state.business_requests) == 4
    assert setup.state.business_requests[-1] == {
        "tntInstId": TENANT,
        "prefundingBizNo": "SYN-BUSINESS",
    }


def test_get_does_not_change_seeded_list_cache_and_list_refresh_have_no_fanout(
    setup, run_cli
):
    rows = [application()]
    setup.state.business_handler = lambda payload, index: page(rows, 1)
    code, out, err = run_cli(
        ["refresh", "liquidity", "operations", "prefunds", "--status", "APPROVED"]
    )
    assert code == 0, (out, err)
    assert len(setup.state.business_requests) == 1
    query = json.loads(setup.state.business_requests[0]["preFundingOrderQueryVO"])
    assert query["statusList"] == ["APPROVED"]
    assert "prefundingBizNo" not in query
    before = setup.cache_path.read_bytes()
    setup.state.business_requests.clear()
    configure(setup)
    code, out, err = run_cli(COMMAND)
    assert code == 0, (out, err)
    assert setup.cache_path.read_bytes() == before
    setup.state.business_requests.clear()
    code, out, err = run_cli(["liquidity", "operations", "prefunds", "list"])
    assert code == 0, (out, err)
    assert setup.state.business_requests == []
    assert setup.cache_path.read_bytes() == before


def test_shared_deadline_exhaustion_withholds_aggregate(setup, run_cli, monkeypatch):
    from dogopencli import collect

    configure(setup)
    healthy = setup.state.business_handler
    exhausted = False

    def answer(payload, index):
        nonlocal exhausted
        result = healthy(payload, index)
        if index == 1:
            exhausted = True
        return result

    start = collect._monotonic()
    monkeypatch.setattr(
        collect, "_monotonic", lambda: start + (1000 if exhausted else 0)
    )
    setup.state.business_handler = answer
    code, out, _ = run_cli(COMMAND)
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "TIMEOUT"
    assert len(setup.state.business_requests) == 2


def test_selected_version_movement_is_explicit_safe_partial(setup, run_cli):
    configure(setup, root={**application(), "usedAmount": "3.00"})
    code, out, err = run_cli(COMMAND)
    result = parse(out)
    assert code == 0, (out, err)
    assert result["data"]["usedAmount"] == "3.00"
    assert "SOURCE_CHANGED" in result["meta"]["components"]["application"]["reasons"]


@pytest.mark.parametrize("modified", [None, "2026-01-01 00:00:00"])
@pytest.mark.parametrize("current_status", ["APPROVED", "CLOSED"])
def test_status_only_movement_updates_application_evidence(
    setup, run_cli, modified, current_status
):
    root = application()
    if modified is not None:
        root["gmtModified"] = modified
    configure(setup, root=root)
    healthy = setup.state.business_handler

    def answer(payload, index):
        result = healthy(payload, index)
        if "preFundingOrderQueryVO" in payload:
            query = json.loads(payload["preFundingOrderQueryVO"])
            if query["statusList"] == ["APPROVED", "CLOSED"]:
                return page([{**root, "status": current_status}], 1)
        return result

    setup.state.business_handler = answer
    code, out, err = run_cli(COMMAND)
    result = parse(out)
    assert code == 0, (out, err)
    assert result["data"]["status"] == "APPROVED"
    component = result["meta"]["components"]["application"]
    changed = current_status != root["status"]
    assert component["selected_version_relation"] == (
        "changed" if changed else "matched"
    )
    assert component["complete"] is (not changed)
    assert ("SOURCE_CHANGED" in component["reasons"]) is changed


def test_missing_transaction_tenant_is_not_silent_binding(setup, run_cli):
    row = transaction()
    del row["tntInstId"]
    configure(setup, transactions=[row])
    code, out, _ = run_cli(COMMAND)
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("component", ["history", "current"])
def test_foreign_application_entity_withholds_aggregate(setup, run_cli, component):
    configure(setup)
    original = setup.state.business_handler

    def answer(payload, index):
        response = original(payload, index)
        if "preFundingOrderQueryVO" in payload:
            statuses = json.loads(payload["preFundingOrderQueryVO"])["statusList"]
            if (component == "history") == (statuses == ["APPROVED_FINAL"]):
                response["body"]["result"]["dataValue"][0]["instId"] = "SYN-FOREIGN"
        return response

    setup.state.business_handler = answer
    code, out, _ = run_cli(COMMAND)
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"


def test_detail_counter_is_raw_evidence_separate_from_parent_cardinality(
    setup, run_cli
):
    configure(setup)
    code, out, err = run_cli(COMMAND)
    result = parse(out)
    assert code == 0, err
    component = result["meta"]["components"]["application"]
    assert component["reported_count"] == 0
    assert component["reported_count_unit"] == "unknown"
    assert component["returned_count"] == result["meta"]["returned_count"] == 1
    assert component["request_scope"] == {
        "preFundingId": "SYN-CURRENT",
        "tntInstId": TENANT,
    }


@pytest.mark.parametrize(
    "variant", ["shortfall", "overlap", "changed_total", "page_budget"]
)
def test_history_coverage_and_budget_follow_verified_offset_contract(
    setup, run_cli, monkeypatch, variant
):
    from dogopencli import collect

    configure(setup)
    original = setup.state.business_handler
    old = application("SYN-OLD", 1, "APPROVED_FINAL")
    if variant == "page_budget":
        monkeypatch.setattr(collect, "MAX_PAGES", 1)

    def answer(payload, index):
        if "preFundingOrderQueryVO" in payload:
            query = json.loads(payload["preFundingOrderQueryVO"])
            if query["statusList"] == ["APPROVED_FINAL"]:
                if variant == "shortfall":
                    return page([old], 2)
                if variant == "overlap":
                    return page([old, old], 2)
                if variant == "page_budget":
                    return page([old], 11)
                if query["rowStart"]:
                    return page([old], 12)
                return page([old], 11)
        return original(payload, index)

    setup.state.business_handler = answer
    code, out, _ = run_cli(COMMAND)
    result = parse(out)
    if variant in ("shortfall", "overlap"):
        assert code == 0
        assert result["data"]["historyApplications"] == [old]
        component = result["meta"]["components"]["historyApplications"]
        assert component["complete"] is False
        assert "COUNT_SHORTFALL" in component["reasons"]
        if variant == "overlap":
            assert component["collected_count"] == 2
            assert component["unique_count"] == 1
    else:
        assert code == 1
        assert result["data"] is None
        assert result["error"]["code"] == (
            "TIMEOUT" if variant == "page_budget" else "INVALID_RESPONSE"
        )


def test_native_root_fields_and_null_empty_precision_survive(setup, run_cli):
    root = {
        "allowUseAmount": "98.00",
        "amount": "100.000000000000000001",
        "amountUSD": "100.000000000000000001",
        "applyType": "SYN-TYPE",
        "approverList": ["SYN-PERSON"],
        "bizLine": "SYN-LINE",
        "bizProject": "SYN-PROJECT",
        "businessCountEvaluate": "",
        "currency": "USD",
        "department": "SYN-DEPARTMENT",
        "detailReason": "",
        "endDate": "20261231",
        "fileUrlList": [],
        "fundingActionType": "SYN-ACTION",
        "fundingSource": "SYN-SOURCE",
        "gmtCreate": "20260101010203",
        "gmtModified": "20260102010203",
        "id": "SYN-CURRENT",
        "instId": "SYN-ENTITY",
        "lastOperator": "SYN-PERSON",
        "memo": None,
        "operator": "SYN-PERSON",
        "preFundingManage": "",
        "prefundingAliasName": "SYN-ALIAS",
        "prefundingBizNo": "SYN-BUSINESS",
        "prefundingPrice": "0.000000000000000001",
        "prefundingType": "SYN-TYPE",
        "processId": "SYN-PROCESS",
        "quotaExplain": None,
        "reason": "",
        "returnPlain": "",
        "reviewDate": "20260102",
        "startDate": "20260101",
        "status": "APPROVED",
        "usedAmount": "2.00",
        "version": 2,
    }
    configure(setup, root=root)
    code, out, err = run_cli(COMMAND)
    result = parse(out)
    assert code == 0, (out, err)
    assert len(root) == 36
    assert {field: result["data"][field] for field in root} == root
    assert "tntInstId" not in result["data"]
