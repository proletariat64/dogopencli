"""Focused tests for the #76 cash/forecast native contracts (cash_forecast).

Covers request construction (method/path/VO JSON-string shape/fixed page
widths), scope validation, strict envelope/total/identity parsing, amount
precision through the projection schemas, the BANK pool detail getter,
offset collection behavior for the credit-line leaf, and cache-scope
isolation between contract variants. All data is synthetic.
"""

import json
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from dogopencli.errors import (
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.plugins.liquidity import spec
from dogopencli.plugins.liquidity.capability import (
    LiquidityDetailCapability,
    LiquidityListCapability,
    encode_scope,
    scope_values,
)
from dogopencli.plugins.liquidity.cash_forecast import (
    ACCEPTED_DETAIL_SPECS,
    ACCEPTED_LIST_SPECS,
    CASH_BALANCES,
    CASH_CREDIT_LINES,
    CASH_GROUP_BALANCES,
    CASH_GROUPS,
    CASH_POOLS,
    CASH_POOLS_GET,
    CASH_STATEMENTS_EOD,
    FORECAST_RESULTS,
    UAT_PASSED,
    VERSION,
    WITHDRAWN_GETTERS,
)
from dogopencli.plugins.liquidity.collect import collect_liquidity_scope
from dogopencli.plugins.liquidity.leaves import (
    DEFERRED_BY_PATH,
    DETAIL_LEAVES,
    LIST_LEAVES,
    ListLeaf,
)
from dogopencli.plugins.liquidity.projection import project_record
from dogopencli.transport import OriginMetadata, TransportResponse

ORIGIN = OriginMetadata(
    backend="cdp",
    simulated=False,
    dataset_id=None,
    dataset_complete=None,
    backend_complete=None,
    source_observed_from=None,
    source_observed_to=None,
)


class FakeQueryTransport:
    """Answers each request from a handler keyed by the request body."""

    def __init__(self, handler: Callable[[dict], dict]) -> None:
        self.handler = handler
        self.requests: list[dict[str, Any]] = []

    def execute(self, request, *, timeout=None):
        self.requests.append(request.body)
        document = self.handler(request.body)
        return TransportResponse(
            status=200, body=json.dumps(document).encode(), origin=ORIGIN
        )


def success_page(rows, total):
    return {"success": True, "data": {"data": rows, "totalCount": total}}


def result_flag_page(rows, total, container="data", inner_success=True):
    return {
        "resultFlag": True,
        "result": {"success": inner_success, container: rows, "count": total},
        "count": total,
    }


# --- explicitly reviewed release and UAT evidence -----------------------------


def test_release_distinguishes_complete_and_backend_compatible_uat():
    from dogopencli.plugins.liquidity.cash_forecast import (
        RELEASED,
        UAT_COMPATIBILITY_PASSED,
        UAT_COMPLETE_PASSED,
    )

    assert len(UAT_COMPLETE_PASSED) == 9
    assert FORECAST_RESULTS.name not in UAT_COMPLETE_PASSED
    assert UAT_COMPATIBILITY_PASSED == {FORECAST_RESULTS.name}
    assert RELEASED == UAT_PASSED == UAT_COMPLETE_PASSED | UAT_COMPATIBILITY_PASSED
    for list_spec in ACCEPTED_LIST_SPECS:
        assert list_spec.schema_version == (
            "cash-daily-balances-v1"
            if list_spec.endpoint == "/balStatisticalQuery.json"
            else "pool-balances-v1"
            if list_spec.path == ("cash", "pool-balances")
            else "credit-usage-v1"
            if list_spec.path == ("cash", "credit-usage")
            else VERSION
        )
        assert (list_spec.path in LIST_LEAVES) == (list_spec.path != ("cash", "groups"))
        assert (*list_spec.path, "list") not in DEFERRED_BY_PATH
    for detail_spec in ACCEPTED_DETAIL_SPECS:
        assert detail_spec.schema_version == VERSION
        assert (*detail_spec.path, detail_spec.action) in DETAIL_LEAVES
        assert (*detail_spec.path, detail_spec.action) not in DEFERRED_BY_PATH
    for withdrawn in WITHDRAWN_GETTERS:
        assert withdrawn not in DETAIL_LEAVES
        assert withdrawn not in DEFERRED_BY_PATH


# --- request construction: method, path, body shape, fixed page widths -------


def test_balances_post_body_with_entity_and_account_arrays():
    capability = LiquidityListCapability(CASH_BALANCES)
    contract = capability.contract
    assert contract.method == "POST"
    assert contract.path == "/latestBalanceQuery.json"
    assert contract.page_size == 100
    fields, window = scope_values(
        CASH_BALANCES.scope_options, {"account": ["A1", "A2"]}
    )
    assert window == (None, None)
    assert fields == {
        "entitys": ["ALIPAYGM"],  # verified default, native JSON array
        "aliasNames": ["A1", "A2"],
        "timeZone": "GMT+08",
    }
    body = capability.page_body(encode_scope(fields), 100)
    assert body == {
        "tntInstId": "GUAPW3SG",
        "entitys": ["ALIPAYGM"],
        "aliasNames": ["A1", "A2"],
        "timeZone": "GMT+08",
        "rowStart": 100,
        "pageSize": 100,
    }
    assert set(body) <= contract.allowed_body_keys
    assert contract.fixed_body_values == (("tntInstId", "GUAPW3SG"),)


def test_group_balances_get_carries_vo_as_one_json_string():
    capability = LiquidityListCapability(CASH_GROUP_BALANCES)
    contract = capability.contract
    assert contract.method == "GET"
    assert contract.path == "/bankAccountGroupQuery.json"
    assert contract.page_size == 100
    fields, _ = scope_values(CASH_GROUPS.scope_options, {"group_code": ["G1", "G2"]})
    body = capability.page_body(encode_scope(fields), 100)
    assert set(body) == {"tntInstId", "bankAccountManageUnitQueryVO"}
    vo_raw = body["bankAccountManageUnitQueryVO"]
    assert isinstance(vo_raw, str)  # nested VO travels as one JSON string
    vo = json.loads(vo_raw)
    assert vo == {
        "tntInstId": "GUAPW3SG",
        "userGroupCode": ["G1", "G2"],
        "equiCurrency": "USD",
        "rowStart": 100,
        "pageSize": 100,
    }
    # GET VO leaves allowlist exactly the top-level tenant plus the VO field.
    assert contract.allowed_body_keys == frozenset(
        {"tntInstId", "bankAccountManageUnitQueryVO"}
    )
    assert contract.fixed_body_values == (("tntInstId", "GUAPW3SG"),)


def test_group_balances_share_endpoint_but_fix_usd_scope():
    assert CASH_GROUP_BALANCES.method == "GET"
    assert CASH_GROUP_BALANCES.endpoint == CASH_GROUPS.endpoint
    assert CASH_GROUP_BALANCES.kind == spec.RUNTIMES
    assert CASH_GROUPS.kind == spec.SETTINGS
    fields, _ = scope_values(CASH_GROUP_BALANCES.scope_options, {})
    assert fields == {"equiCurrency": "USD"}
    with pytest.raises(CliError, match="one of"):
        scope_values(CASH_GROUP_BALANCES.scope_options, {"equi_currency": "EUR"})


def test_pools_post_body_has_fixed_bank_category():
    capability = LiquidityListCapability(CASH_POOLS)
    contract = capability.contract
    assert contract.method == "POST"
    assert contract.path == "/cashPoolList.json"
    assert contract.page_size == 100
    body = capability.page_body("", 0)
    assert body == {
        "tntInstId": "GUAPW3SG",
        "cashPoolCategory": "BANK",
        "rowStart": 0,
        "pageSize": 100,
    }
    assert set(body) <= contract.allowed_body_keys
    assert contract.fixed_body_values == (
        ("tntInstId", "GUAPW3SG"),
        ("cashPoolCategory", "BANK"),
    )


def test_credit_lines_get_carries_query_vo_json_string():
    capability = LiquidityListCapability(CASH_CREDIT_LINES)
    contract = capability.contract
    assert contract.method == "GET"
    assert contract.path == "/queryBankCreditLineByParams.json"
    assert contract.page_size == 100
    body = capability.page_body("", 200)
    assert set(body) == {"tntInstId", "bankCreditLineQuery"}
    # The verified VO carries no nested tenant; only pagination fields.
    vo = json.loads(body["bankCreditLineQuery"])
    assert vo == {"rowStart": 200, "pageSize": 100}
    assert contract.allowed_body_keys == frozenset({"tntInstId", "bankCreditLineQuery"})


def test_eod_post_body_with_window_and_lists():
    capability = LiquidityListCapability(CASH_STATEMENTS_EOD)
    contract = capability.contract
    assert contract.method == "POST"
    assert contract.path == "/bankAccountDetailDayQuery.json"
    assert contract.page_size == 1000
    fields, window = scope_values(
        CASH_STATEMENTS_EOD.scope_options,
        {
            "entity": ["I1", "I2"],
            "account": "A1",
            "currency": "USD",
            "from": "20261001",
            "to": "20261031",
        },
    )
    assert window == ("20261001", "20261031")
    body = capability.page_body(encode_scope(fields), 1000)
    assert body == {
        "tntInstId": "GUAPW3SG",
        "instIds": ["I1", "I2"],
        "bankAccountAliasName": ["A1"],
        "currency": "USD",
        "timeZone": "GMT+08",
        "queryDateBegin": "20261001",
        "queryDateEnd": "20261031",
        "rowStart": 1000,
        "pageSize": 1000,
    }
    assert set(body) <= contract.allowed_body_keys


def test_eod_scope_requires_lists_and_valid_calendar_date_window():
    options = CASH_STATEMENTS_EOD.scope_options
    valid = {
        "entity": "I1",
        "account": "A1",
        "currency": "USD",
        "from": "20261001",
        "to": "20261031",
    }
    for missing in ("entity", "account", "currency"):
        provided = {key: value for key, value in valid.items() if key != missing}
        with pytest.raises(CliError, match="required"):
            scope_values(options, provided)
    # Preferred ISO dates normalize to the internal compact form (Issue #127).
    fields, window = scope_values(options, {**valid, "from": "2026-10-01"})
    assert fields["queryDateBegin"] == "20261001"
    assert window == ("20261001", "20261031")
    for bad_date in ("2026-10-1", "2026101", "20260230", "2026-02-29"):
        with pytest.raises(CliError, match="valid calendar date"):
            scope_values(options, {**valid, "from": bad_date})
    with pytest.raises(CliError, match="after its end"):
        scope_values(options, {**valid, "from": "20261031", "to": "20261001"})
    with pytest.raises(CliError, match="must be nonempty"):
        scope_values(options, {**valid, "account": ["A1", "  "]})
    with pytest.raises(CliError, match="one of"):
        scope_values(options, {**valid, "timezone": "UTC"})


def test_forecast_get_vo_keeps_null_amount_filters_and_no_timezone():
    capability = LiquidityListCapability(FORECAST_RESULTS)
    contract = capability.contract
    assert contract.method == "GET"
    assert contract.path == "/bankCashForecastRecordQuery.json"
    assert contract.page_size == 5000
    fields, window = scope_values(
        FORECAST_RESULTS.scope_options,
        {"from": "20261001", "to": "20261007", "account": ["A1", "A2"]},
    )
    assert window == ("20261001", "20261007")
    body = capability.page_body(encode_scope(fields), 5000)
    assert set(body) == {"tntInstId", "bankCashForecastRecordQueryVo"}
    vo = json.loads(body["bankCashForecastRecordQueryVo"])
    assert vo["valueStartDay"] == "20261001"
    assert vo["valueEndDay"] == "20261007"
    assert vo["recordStartTime"] == "000000"
    assert vo["recordEndTime"] == "235959"
    assert vo["aliasName"] == ["A1", "A2"]
    assert vo["rowStart"] == 5000
    assert vo["pageSize"] == 5000
    assert contract.allowed_body_keys == frozenset(
        {"tntInstId", "bankCashForecastRecordQueryVo"}
    )
    # Amount filters stay null; discovering wire fields is not a CLI release.
    for null_filter in (
        "expectInflowStart",
        "expectInflowEnd",
        "expectOutflowStart",
        "expectOutflowEnd",
        "expectMinBalance",
        "expectMaxBalance",
    ):
        assert vo[null_filter] is None
    # No timezone is requested and no server timezone is inferred.
    assert "timeZone" not in vo
    assert "timeZone" not in body
    with pytest.raises(CliError, match="unknown scope options"):
        scope_values(
            FORECAST_RESULTS.scope_options,
            {"from": "20261001", "to": "20261007", "timezone": "GMT+08"},
        )


def test_forecast_record_creation_times_are_hhmmss_and_ordered():
    options = FORECAST_RESULTS.scope_options
    window = {"from": "20261001", "to": "20261007"}
    fields, _ = scope_values(
        options, {**window, "record_from_time": "091500", "record_to_time": "173000"}
    )
    assert fields["recordStartTime"] == "091500"
    assert fields["recordEndTime"] == "173000"
    # Canonical colon form normalizes to the compact native representation.
    colon, _ = scope_values(
        options,
        {**window, "record_from_time": "09:15:00", "record_to_time": "17:30:00"},
    )
    assert colon == fields
    for bad_time in ("240000", "24:00:00", "1261", "091560", "09:15", "09:15:00.5"):
        with pytest.raises(CliError, match="HH:mm:ss"):
            scope_values(options, {**window, "record_from_time": bad_time})
    with pytest.raises(CliError, match="record creation time start is after its end"):
        scope_values(
            options,
            {**window, "record_from_time": "23:59:59", "record_to_time": "000000"},
        )
    with pytest.raises(CliError, match="required"):
        scope_values(options, {"to": "20261007"})


# --- response parsing: envelopes, totals, identity ----------------------------


def test_groups_inner_and_top_level_counts_must_agree():
    capability = LiquidityListCapability(CASH_GROUPS)
    rows, total = capability.parse_rows(
        json.dumps(result_flag_page([{"id": "G1"}], 1)).encode()
    )
    assert total == 1
    assert rows[0]["id"] == "G1"
    disagreeing = {
        "resultFlag": True,
        "result": {"success": True, "data": [{"id": "G1"}], "count": 1},
        "count": 2,
    }
    with pytest.raises(CliError, match="totals disagree"):
        capability.parse_rows(json.dumps(disagreeing).encode())


def test_inner_success_marker_is_strictly_boolean_true():
    capability = LiquidityListCapability(CASH_GROUPS)
    missing_success = result_flag_page([{"id": "G1"}], 1)
    del missing_success["result"]["success"]
    with pytest.raises(CliError, match="missing the registered record path"):
        capability.parse_rows(json.dumps(missing_success).encode())
    for marker in ("true", 1):
        document = result_flag_page([{"id": "G1"}], 1)
        document["result"]["success"] = marker
        with pytest.raises(CliError, match="inner result success marker"):
            capability.parse_rows(json.dumps(document).encode())
    explicit_false = result_flag_page([{"id": "G1"}], 1, inner_success=False)
    with pytest.raises(CliError, match="business failure"):
        capability.parse_rows(json.dumps(explicit_false).encode())
    flag_false = {"resultFlag": False, "result": {"success": True, "data": []}}
    with pytest.raises(CliError, match="business failure"):
        capability.parse_rows(json.dumps(flag_false).encode())


def test_balances_parse_preserves_amount_precision_and_drops_extras():
    capability = LiquidityListCapability(CASH_BALANCES)
    row = {
        "balId": "B1",
        "entity": "Z21",
        "aliasName": "A1",
        "currency": "USD",
        "curBalance": "1234.56",  # string amounts stay exact, never /100
        "avlBalance": None,  # null stays null
        "openBalance": "",  # empty stays empty and distinct from null
        "equvCurBalance": 7,
        "unrelatedField": "dropped",
    }
    rows, total = capability.parse_rows(json.dumps(success_page([row], 1)).encode())
    assert total == 1
    projected = rows[0]
    assert projected["balId"] == "B1"
    assert projected["curBalance"] == "1234.56"
    assert projected["avlBalance"] is None
    assert projected["openBalance"] == ""
    assert projected["equvCurBalance"] == 7
    assert "unrelatedField" not in projected


def test_eod_empty_transaction_identity_is_rejected():
    capability = LiquidityListCapability(CASH_STATEMENTS_EOD)
    row = {
        "instId": "I1",
        "bankAccountAliasName": "A1",
        "currency": "USD",
        "valueDate": "20261001",
        "bankTransNo": "",
    }
    with pytest.raises(CliError, match="identity field"):
        capability.parse_rows(json.dumps(success_page([row], 1)).encode())
    with pytest.raises(CliError, match="empty transaction number"):
        project_record("eod", {"bankTransNo": "   "})
    kept = project_record(
        "eod",
        {
            "instId": "I1",
            "bankAccountAliasName": "A1",
            "currency": "USD",
            "valueDate": "20261001",
            "bankTransNo": "T001",
            "amount": "0.01",
            "fundDirection": "Credit",
            "unknown": "dropped",
        },
    )
    assert kept["amount"] == "0.01"
    assert "unknown" not in kept


def test_projection_rejects_bool_and_container_amounts():
    balance = {"curBalance": True}
    with pytest.raises(CliError, match="invalid amount value"):
        project_record("balances", balance)
    with pytest.raises(CliError, match="invalid amount value"):
        project_record("balances", {"curBalance": ["1.00"]})
    with pytest.raises(CliError, match="invalid amount value"):
        project_record("balances", {"curBalance": {"raw": "1.00"}})
    # Decimal amounts survive projection untouched.
    projected = project_record("balances", {"curBalance": Decimal("1.10")})
    assert projected["curBalance"] == Decimal("1.10")
    # Forecast integer fields reject bools and strings.
    with pytest.raises(CliError, match="unobserved integer field type"):
        project_record("forecast_results", {"forecastBatchNo": True})
    with pytest.raises(CliError, match="unobserved integer field type"):
        project_record("forecast_results", {"lastestFlag": "1"})
    forecast = project_record(
        "forecast_results",
        {"id": "F1", "forecastBalance": "0.01", "forecastBatchNo": 7},
    )
    assert forecast["forecastBalance"] == "0.01"
    assert forecast["forecastBatchNo"] == 7


def test_group_projection_split_and_member_rules():
    member = {
        "id": "M1",
        "aliasName": "A1",
        "currentBalance": "10.00",
        "forecastTime": "",
        "bankAccountGroupId": "G1",
    }
    row = {
        "id": "G1",
        "userGroupCode": "GC1",
        "groupName": "synthetic",
        "type": "NORMAL",
        "currentBalance": "10.00",
        "memberList": [member],
    }
    settings = project_record("groups_settings", row)
    assert "currentBalance" not in settings  # settings strip balance fields
    assert "currentBalance" not in settings["memberList"][0]
    balances = project_record("group_balances", row)
    assert balances["currentBalance"] == "10.00"
    # Unknown source time never becomes modification/capture time; blank and
    # null remain distinct native states.
    assert balances["memberList"][0]["forecastTime"] == ""
    duplicate = {**row, "memberList": [member, dict(member)]}
    with pytest.raises(CliError, match="duplicate member identity"):
        project_record("group_balances", duplicate)
    with pytest.raises(CliError, match="empty identity"):
        project_record("groups_settings", {**row, "memberList": [{"id": " "}]})


def test_pool_projection_rejects_untyped_swap_rule_identity():
    row = {
        "id": "P1",
        "cashPoolMemberVOS": [{"id": "M1", "cashPoolSwapRuleVOS": [{"rule": 1}]}],
    }
    with pytest.raises(CliError, match="invalid identity type"):
        project_record("pools_settings", row)
    clean = project_record(
        "pools_settings",
        {"id": "P1", "cashPoolMemberVOS": [{"id": "M1", "cashPoolSwapRuleVOS": []}]},
    )
    assert clean["cashPoolMemberVOS"][0]["id"] == "M1"


# --- schema_version strict primary identity -----------------------------------


def test_schema_version_makes_primary_identity_strict():
    capability = LiquidityListCapability(CASH_POOLS)
    for bad in (None, True, False, "", "   ", ["P1"], {"id": "P1"}):
        with pytest.raises(CliError, match="identity field"):
            capability.identity_key({"id": bad})
    assert capability.identity_key({"id": "P1"}) == ('"P1"',)
    assert capability.identity_key({"id": 0}) == ("0",)
    # Strictness is bound to the schema version, not to the field alone:
    # legacy leaves without a version keep the pre-#76 atomic-only check.
    legacy = LiquidityListCapability(replace(CASH_POOLS, schema_version=""))
    assert legacy.identity_key({"id": True}) == ("true",)
    assert legacy.identity_key({"id": ""}) == ('""',)
    with pytest.raises(CliError, match="identity field"):
        legacy.identity_key({"id": ["P1"]})


# --- BANK pool detail getter ----------------------------------------------------


def test_pool_get_body_fixes_bank_in_use_and_tenant():
    capability = LiquidityDetailCapability(CASH_POOLS_GET)
    contract = capability.contract
    assert contract.method == "POST"
    assert contract.path == "/cashPoolDetail.json"
    assert capability.detail_body({"pool_id": "P001"}) == {
        "inUse": "Y",
        "cashPoolCategory": "BANK",
        "id": "P001",
        "tntInstId": "GUAPW3SG",
    }
    assert contract.allowed_body_keys == frozenset(
        {"tntInstId", "id", "inUse", "cashPoolCategory"}
    )
    assert contract.fixed_body_values == (
        ("inUse", "Y"),
        ("cashPoolCategory", "BANK"),
        ("tntInstId", "GUAPW3SG"),
    )


def test_pool_get_rejects_unknown_or_empty_identity_options():
    capability = LiquidityDetailCapability(CASH_POOLS_GET)
    with pytest.raises(CliError, match="unknown identity options") as error:
        capability.detail_body({"pool_id": "P001", "account": "A1"})
    assert error.value.code == REQUEST_NOT_ALLOWED
    with pytest.raises(CliError, match="required and nonempty"):
        capability.detail_body({"pool_id": "  "})
    with pytest.raises(CliError, match="required and nonempty"):
        capability.detail_body({})


def test_pool_get_echo_must_repeat_typed_identity():
    capability = LiquidityDetailCapability(CASH_POOLS_GET)
    body = json.dumps(
        {"success": True, "data": {"id": "P001", "cashPoolName": "synthetic"}}
    ).encode()
    detail = capability.parse_detail(body, {"pool_id": "P001"})
    assert detail["id"] == "P001"
    assert "cashPoolMemberVOS" not in detail  # missing is not a fake empty list
    for bad_echo in ({"id": "P002"}, {"id": True}, {"name": "no-id"}):
        document = json.dumps({"success": True, "data": bad_echo}).encode()
        with pytest.raises(CliError, match="does not match"):
            capability.parse_detail(document, {"pool_id": "P001"})
    not_object = json.dumps({"success": True, "data": [{"id": "P001"}]}).encode()
    with pytest.raises(CliError, match="not an object"):
        capability.parse_detail(not_object, {"pool_id": "P001"})


def test_pool_get_versioned_echo_requires_exact_type_and_value():
    capability = LiquidityDetailCapability(CASH_POOLS_GET)

    def document(echo: Any) -> bytes:
        return json.dumps({"success": True, "data": {"id": echo}}).encode()

    detail = capability.parse_detail(document("123"), {"pool_id": "123"})
    assert detail["id"] == "123"
    # A native int echo never satisfies the requested string identity, and
    # bool/null echoes reject outright.
    for bad_echo in (123, True, False, None):
        with pytest.raises(CliError, match="does not match"):
            capability.parse_detail(document(bad_echo), {"pool_id": "123"})


def test_unversioned_detail_echo_keeps_legacy_string_comparison():
    legacy = LiquidityDetailCapability(replace(CASH_POOLS_GET, schema_version=""))
    document = json.dumps({"success": True, "data": {"id": 123}}).encode()
    detail = legacy.parse_detail(document, {"pool_id": "123"})
    assert detail["id"] == 123


# --- offset collection over the credit-line leaf -------------------------------


def credit(index, amount="1000.00"):
    return {
        "id": f"C{index:03d}",
        "creditLineType": "BANK",
        "currency": "USD",
        "amount": amount,
        "status": "NORMAL",
    }


def collect_credit_lines(rows_by_offset, total, page_size=2):
    capability = LiquidityListCapability(
        replace(CASH_CREDIT_LINES, page_size=page_size)
    )

    def answer(body):
        vo = json.loads(body["bankCreditLineQuery"])
        return result_flag_page(rows_by_offset(vo["rowStart"]), total)

    transport = FakeQueryTransport(answer)
    return transport, collect_liquidity_scope(capability, transport, "")


def test_credit_lines_cross_page_duplicate_stays_incomplete():
    def rows(row_start):
        return [credit(0), credit(1)] if row_start == 0 else [credit(1), credit(2)]

    _, result = collect_credit_lines(rows, 3)
    assert not result.complete
    assert result.total_count == 3
    assert len(result.records) == 3


def test_credit_lines_conflicting_row_across_pages_is_a_hard_failure():
    def rows(row_start):
        if row_start == 0:
            return [credit(0), credit(1)]
        return [credit(1, amount="9999.00"), credit(2)]

    with pytest.raises(CliError, match="conflicting content"):
        collect_credit_lines(rows, 3)


def test_credit_lines_short_page_keeps_the_verified_stride():
    def rows(row_start):
        return [credit(0)] if row_start == 0 else [credit(1), credit(2)]

    transport, result = collect_credit_lines(rows, 3)
    offsets = [
        json.loads(body["bankCreditLineQuery"])["rowStart"]
        for body in transport.requests
    ]
    assert offsets == [0, 2]
    assert result.complete
    assert len(result.records) == 3


def test_credit_lines_total_change_mid_collection_fails():
    counts = iter([3, 4])
    capability = LiquidityListCapability(replace(CASH_CREDIT_LINES, page_size=2))
    transport = FakeQueryTransport(
        lambda body: result_flag_page([credit(0), credit(1)], next(counts))
    )
    with pytest.raises(CliError, match="total changed"):
        collect_liquidity_scope(capability, transport, "")


def test_credit_lines_unordered_pages_complete_without_stable_sort():
    # No arrival ordering is assumed: identities reconcile coverage.
    def rows(row_start):
        return [credit(1), credit(0)] if row_start == 0 else [credit(3), credit(2)]

    _, result = collect_credit_lines(rows, 4)
    assert result.complete
    assert [record["id"] for record in result.records] == [
        "C001",
        "C000",
        "C003",
        "C002",
    ]


# --- cache scope isolation ------------------------------------------------------


def test_scope_cache_isolation_between_group_leaves_and_versions():
    groups = ListLeaf((CASH_GROUPS,)).resolve({})
    group_balances = ListLeaf((CASH_GROUP_BALANCES,)).resolve({})
    # Same endpoint, different kind/projection: the contract block isolates
    # the two caches.
    assert groups.spec.endpoint == group_balances.spec.endpoint
    assert groups.spec.kind == spec.SETTINGS
    assert group_balances.spec.kind == spec.RUNTIMES
    assert groups.scope_key != group_balances.scope_key
    # The fixed USD scope participates in both cache keys.
    assert groups.request_values == {"equiCurrency": "USD"}
    assert 'equiCurrency="USD"' in groups.scope_key
    assert 'equiCurrency="USD"' in group_balances.scope_key
    # A schema version change is a different cache namespace.
    other_version = replace(CASH_GROUPS, schema_version="cash-forecast-v0.0.0")
    assert ListLeaf((other_version,)).resolve({}).scope_key != groups.scope_key


def test_dated_window_binds_request_scope_not_cache_scope():
    resolved = ListLeaf((CASH_STATEMENTS_EOD,)).resolve(
        {
            "entity": "I1",
            "account": "A1",
            "currency": "USD",
            "from": "20261001",
            "to": "20261031",
        }
    )
    assert resolved.window == ("20261001", "20261031")
    assert "queryDateBegin" not in resolved.scope_key
    assert "queryDateEnd" not in resolved.scope_key
    assert "queryDateBegin" in resolved.request_scope


@pytest.mark.parametrize(
    "path",
    [
        (*item.path, "list")
        for item in ACCEPTED_LIST_SPECS
        if item.path != ("cash", "groups")
    ]
    + [(*item.path, item.action) for item in ACCEPTED_DETAIL_SPECS],
)
def test_released_public_help_and_describe_do_not_contact_browser(path, monkeypatch):
    import contextlib
    import io

    from dogopencli.browser import cdp
    from dogopencli.cli import main

    def forbidden(*args, **kwargs):
        raise AssertionError("pending leaf opened a browser transport")

    monkeypatch.setenv("DOGOPENCLI_CONFIG", "/nonexistent-spec76-config.toml")
    cdp.set_transport_factory(forbidden)
    try:
        for command in ("help", "describe"):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = main([command, "liquidity", *path])
            document = json.loads(output.getvalue())
            assert code == 0
            if command == "describe":
                assert document["data_schema"]["properties"]
                assert document["read_guide"]["live_verified"] == (
                    "2026-10-05"
                    if path
                    in {
                        ("cash", "pool-balances", "list"),
                        ("cash", "credit-usage", "list"),
                    }
                    else "2026-10-02"
                )
                if path == (*FORECAST_RESULTS.path, "list"):
                    assert any(
                        "Compatibility is not backend repair" in note
                        for note in document["read_guide"]["notes"]
                    )
    finally:
        cdp.set_transport_factory(None)
