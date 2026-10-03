"""Projection whitelists, amount types and nested member validation (#76)."""

from decimal import Decimal
from typing import Any

import pytest

from dogopencli.errors import INVALID_RESPONSE, CliError
from dogopencli.plugins.liquidity.projection import project_record


def _group_member(member_id: Any = "m1") -> dict[str, Any]:
    return {
        "id": member_id,
        "bankAccountGroupId": "g1",
        "accountNo": "900000000001",
        "aliasName": "SYNTH-ACCT-1",
        "entity": "SYNTH-ENTITY",
        "bankId": "SYNTHBANK",
        "currencyCode": "USD",
        "accountUsageType": "PAYMENT",
        "memo": "synthetic member",
        "gmtCreate": "2026-01-01 00:00:00",
        "gmtModified": "2026-01-02 00:00:00",
        "currentBalance": "10.00",
        "forecastBalance": "11.00",
        "lastDayClosingBalance": "9.00",
        "equiCurrentBalance": "10.00",
        "equiForecastBalance": "11.00",
        "equiLastDayClosingBalance": "9.00",
        "currentBalanceTime": "2026-01-02 10:00:00",
        "forecastTime": "2026-01-02 12:00:00",
    }


def _group_row(members: Any) -> dict[str, Any]:
    return {
        "id": "g1",
        "userGroupCode": "SYNTH-GROUP",
        "groupName": "synthetic group",
        "type": "NORMAL",
        "memo": "synthetic",
        "version": "1",
        "tntInstId": "SYNTH-TNT",
        "operator": "synthetic-operator",
        "gmtCreate": "2026-01-01 00:00:00",
        "gmtModified": "2026-01-02 00:00:00",
        "valueDate": "2026-01-02",
        "currentBalance": "30.00",
        "forecastBalance": "33.00",
        "lastDayClosingBalance": "27.00",
        "memberList": members,
    }


def _swap_rule(rule_id: Any = "sr1") -> dict[str, Any]:
    return {
        "id": rule_id,
        "cashPoolMemberId": "pm1",
        "type": "SWEEP",
        "sweepingType": "TARGET",
        "sweepingDirection": "UP",
        "sweepingAmount": "100.00",
        "sweepTargetBalanceFrom": "10.00",
        "sweepTargetBalanceTo": "90.00",
        "currency": "USD",
        "timeZone": "Asia/Shanghai",
        "timePoint": "16:00",
        "beginTime": "2026-01-01",
        "endTime": "2027-01-01",
        "interval": 1,
        "conditionLogical": 1,
        "calendarCode": "SYNTH-CAL",
        "calendarType": "WORKDAY",
        "customCalendarId": "SYNTH-CUSTOM",
        "customeType": "NONE",
        "days": [],
        "exclude": False,
        "followActionAccountType": "MASTER",
        "operator": "synthetic-operator",
        "tntInstId": "SYNTH-TNT",
        "calendarConditionVos": [],
        "sweepingFreq": {
            "type": "DAILY",
            "timePoint": "16:00",
            "beginTime": "2026-01-01",
            "endTime": "2027-01-01",
            "interval": 1,
            "conditionLogical": 1,
            "calendarCode": "SYNTH-CAL",
            "calendarType": "WORKDAY",
            "customCalendarId": "SYNTH-CUSTOM",
            "customeType": "NONE",
            "days": [],
            "exclude": False,
            "followActionAccountType": "MASTER",
            "calendarConditionVos": [
                {
                    "calendarCode": "SYNTH-CAL",
                    "calendarType": "WORKDAY",
                    "customCalendarId": "SYNTH-CUSTOM",
                    "customeType": "NONE",
                    "days": [],
                    "exclude": False,
                    "followActionAccountType": "MASTER",
                    "order": 1,
                }
            ],
        },
    }


def _pool_member(member_id: Any = "pm1") -> dict[str, Any]:
    return {
        "id": member_id,
        "cashPoolId": "p1",
        "aliasName": "SYNTH-POOL-ACCT",
        "entity": "SYNTH-ENTITY",
        "bankId": "SYNTHBANK",
        "currency": "USD",
        "bankCurrency": "USD",
        "masterAccount": "Y",
        "isShare": "N",
        "subLimit": "100.00",
        "creditAmount": "50.00",
        "creditRateType": "FIXED",
        "creditRateSource": "MANUAL",
        "creditRateValue": "0.01",
        "creditRateExtType": "NONE",
        "debitRateType": "FIXED",
        "debitRateSource": "MANUAL",
        "debitRateValue": "0.02",
        "debitRateExtType": "NONE",
        "penaltyRateType": "FIXED",
        "penaltyRateSource": "MANUAL",
        "penaltyRateValue": "0.03",
        "penaltyRateExtType": "NONE",
        "billingTimeType": "DAY",
        "billingTimeValue": "1",
        "balanceUpdateType": "AUTO",
        "outFlowCapability": "Y",
        "timeZone": "Asia/Shanghai",
        "tntInstId": "SYNTH-TNT",
        "operator": "synthetic-operator",
        "memo": "synthetic",
        "cashPoolName": "synthetic pool",
        "cashPoolSwapRuleVOS": [_swap_rule()],
        "currentBalance": "10.00",
        "currentAviBalance": "8.00",
        "closeBalance": "9.00",
        "closeAviBalance": "7.00",
        "equvCurrentBalance": "10.00",
        "equvCurrentAviBalance": "8.00",
        "equvCloseBalance": "9.00",
        "equvCloseAviBalance": "7.00",
        "expectBalance": "12.00",
        "avlCreditAmount": "40.00",
        "avlSubLimit": "90.00",
    }


def _pool_row(members: Any) -> dict[str, Any]:
    return {
        "id": "p1",
        "cashPoolName": "synthetic pool",
        "cashPoolType": "SWEEP",
        "cashPoolCategory": "BANK",
        "mainCurrency": "USD",
        "entity": ["SYNTH-ENTITY"],
        "status": "ACTIVE",
        "haircutRatio": "0.90",
        "memo": "synthetic",
        "operator": "synthetic-operator",
        "gmtModified": "2026-01-02 00:00:00",
        "tntInstId": "SYNTH-TNT",
        "processId": "SYNTH-PROC",
        "processStatus": "DONE",
        "cashPoolMemberVOS": members,
        "cashPoolCapacity": "1000.00",
        "currentBalance": "10.00",
        "currentAviBalance": "8.00",
        "closeBalance": "9.00",
        "closeAviBalance": "7.00",
        "valueDate": "2026-01-02",
        "pageNo": 1,
        "pageSize": 100,
        "rowStart": 0,
        "startindex": 0,
        "totalSize": 1,
        "cashPoolDetailUrl": "https://example.invalid/detail",
        "cashPoolRequest": None,
        "cashpoolCapacityVO": None,
        "isDelete": None,
        "operationStrategyRuleVO": None,
        "processType": None,
        "waterlevelRuleEditVO": None,
        "waterlevelRuleVO": None,
    }


def _credit_line_member(member_id: Any = "cm1") -> dict[str, Any]:
    return {
        "id": member_id,
        "creditLineId": "cl1",
        "accountNo": "900000000001",
        "aliasName": "SYNTH-ACCT-1",
        "bankId": "SYNTHBANK",
        "instId": "SYNTH-INST",
        "creditAmount": "100.00",
        "creditCurrency": "USD",
        "currency": "USD",
        "equvAmount": "100.00",
        "rateId": "SYNTH-RATE",
        "isMasterAccount": "Y",
        "mergeFlag": "N",
        "startTimestamp": "2026-01-01 00:00:00",
        "expiryTimestamp": "2027-01-01 00:00:00",
        "status": "ACTIVE",
        "gmtCreate": "2026-01-01 00:00:00",
        "gmtModified": "2026-01-02 00:00:00",
        "usedAmount": "5.00",
        "usedCreditAmount": "5.00",
        "availableAmount": "95.00",
        "availableCreditAmount": "95.00",
    }


def _credit_line_row(members: Any) -> dict[str, Any]:
    return {
        "id": "cl1",
        "creditLineType": "NORMAL",
        "currency": "USD",
        "amount": "100.00",
        "dateType": "FIXED",
        "startTimestamp": "2026-01-01 00:00:00",
        "expiryTimestamp": "2027-01-01 00:00:00",
        "bankId": "SYNTHBANK",
        "masterBankId": "SYNTHBANK",
        "instId": "SYNTH-INST",
        "shareTag": "N",
        "status": "ACTIVE",
        "manageStatus": "NORMAL",
        "memo": "synthetic",
        "version": "1",
        "tntInstId": "SYNTH-TNT",
        "operator": "synthetic-operator",
        "gmtCreate": "2026-01-01 00:00:00",
        "gmtModified": "2026-01-02 00:00:00",
        "timeZone": "Asia/Shanghai",
        "processId": "SYNTH-PROC",
        "processStatus": "DONE",
        "bankAccountCreditLineList": members,
        "usedAmount": "5.00",
        "availableAmount": "95.00",
    }


def _balance_row() -> dict[str, Any]:
    return {
        "accountNo": "900000000001",
        "accountNumbers": "900000000001",
        "accountType": "CURRENT",
        "aliasName": "SYNTH-ACCT-1",
        "balId": "SYNTH-BAL",
        "bankId": "SYNTHBANK",
        "bizTag": "SYNTH",
        "blockChainAccountType": "NONE",
        "colorType": "NONE",
        "companyName": "SYNTH-CO",
        "currency": "USD",
        "digitalCurrency": "N",
        "entity": "SYNTH-ENTITY",
        "equvCurrency": "USD",
        "fundAttribute1": "NONE",
        "statementCreateTime": "2026-01-02 10:00:00",
        "timeZone": "Asia/Shanghai",
        "curBalance": "10.00",
        "avlBalance": "8.00",
        "avlBalanceAfterAdj": "8.00",
        "openBalance": "9.00",
        "openAvlBalance": "7.00",
        "openAvlBalanceAfterAdj": "7.00",
        "equvCurBalance": "10.00",
        "equvAvlBalance": "8.00",
        "equvOpenBalance": "9.00",
        "equvOpenAvlBalance": "7.00",
        "avlBalanceSwitch": True,
        "openAvlBalanceSwitch": False,
        "leastDayendBalVo": {
            "accountNo": "900000000001",
            "aliasName": "SYNTH-ACCT-1",
            "bankId": "SYNTHBANK",
            "entity": "SYNTH-ENTITY",
            "currency": "USD",
            "openBalance": "9.00",
            "openAvlBalance": "7.00",
            "closeBalance": "9.50",
            "closeAvlBalance": "7.50",
            "source": "SYNTH-SRC",
            "statementCreateTime": "2026-01-02 09:00:00",
            "timeZone": "Asia/Shanghai",
            "updateTime": "2026-01-02 09:30:00",
            "valueDate": "2026-01-01",
        },
        "leastDaytimeBalVo": {
            "accountNo": "900000000001",
            "aliasName": "SYNTH-ACCT-1",
            "bankId": "SYNTHBANK",
            "entity": "SYNTH-ENTITY",
            "currency": "USD",
            "instradayBalance": "9.10",
            "instradayAvlBalance": "7.10",
            "source": "SYNTH-SRC",
            "statementCreateTime": "2026-01-02 10:00:00",
            "timeZone": "Asia/Shanghai",
            "updateTime": "2026-01-02 10:05:00",
            "valueDate": "2026-01-02",
        },
    }


def _eod_row() -> dict[str, Any]:
    return {
        "instId": "SYNTH-INST",
        "bankAccountAliasName": "SYNTH-ACCT-1",
        "bankId": "SYNTHBANK",
        "accountType": "CURRENT",
        "currency": "USD",
        "valueDate": "2026-01-02",
        "transDate": "2026-01-02",
        "transTime": "10:00:00",
        "date": "2026-01-02",
        "bankTransNo": "SYNTH-TXN-1",
        "end2EndId": "SYNTH-E2E-1",
        "fundDirection": "CR",
        "amount": "1234.50",
        "transType": "TRANSFER",
        "transDetail": "synthetic detail",
        "memo": "synthetic",
        "otherAccountName": "SYNTH-OTHER",
        "otherAccountNo": "900000000002",
        "otherBankName": "SYNTH-OTHER-BANK",
    }


def _forecast_row() -> dict[str, Any]:
    return {
        "id": "fr1",
        "accountNo": "900000000001",
        "autoFlag": "Y",
        "bankAccountAliasName": "SYNTH-ACCT-1",
        "bankId": "SYNTHBANK",
        "baseValueDate": "2026-01-01",
        "valueDate": "2026-01-02",
        "cashForecastType": "DAILY",
        "currency": "USD",
        "forecastTaskId": "SYNTH-TASK",
        "forecastRuleId": "SYNTH-RULE",
        "forecastBatchNo": 7,
        "instId": "SYNTH-INST",
        "isCoverIod": "N",
        "isNeedReview": "N",
        "minimumBalanceValueTime": "2026-01-02 10:00:00",
        "recordCreateTime": "2026-01-02 09:00:00",
        "tntInstId": "SYNTH-TNT",
        "forecastBalance": "10.00",
        "minimumBalance": "1.00",
        "openBalance": "9.00",
        "cashFlowTransIn": "5.00",
        "cashFlowTransOut": "4.00",
        "gmtCreate": 1767225600000,
        "gmtModified": 1767225600000,
        "lastestFlag": 1,
        "pageNo": 1,
        "pageSize": 5000,
        "rowStart": 0,
        "startindex": 0,
        "totalSize": 1,
    }


def _assert_invalid(excinfo):
    assert excinfo.value.code == INVALID_RESPONSE


# --- groups settings ----------------------------------------------------------


def test_groups_settings_strips_balances_and_keeps_member_identity():
    projected = project_record("groups_settings", _group_row([_group_member()]))
    for field in (
        "currentBalance",
        "forecastBalance",
        "lastDayClosingBalance",
        "valueDate",
    ):
        assert field not in projected
    assert projected["id"] == "g1"
    assert projected["gmtModified"] == "2026-01-02 00:00:00"
    (member,) = projected["memberList"]
    assert member["id"] == "m1"
    assert member["bankAccountGroupId"] == "g1"
    assert member["accountUsageType"] == "PAYMENT"
    for field in (
        "currentBalance",
        "forecastBalance",
        "lastDayClosingBalance",
        "equiCurrentBalance",
        "currentBalanceTime",
        "forecastTime",
    ):
        assert field not in member


@pytest.mark.parametrize(
    "bad_id", ["", "   ", None, True, ["m1"], {"id": "m1"}, Decimal("1")]
)
def test_groups_settings_rejects_invalid_member_identity(bad_id):
    with pytest.raises(CliError) as excinfo:
        project_record("groups_settings", _group_row([_group_member(bad_id)]))
    _assert_invalid(excinfo)


def test_groups_settings_rejects_duplicate_member_identity():
    with pytest.raises(CliError) as excinfo:
        project_record(
            "groups_settings",
            _group_row([_group_member("m1"), _group_member("m1")]),
        )
    _assert_invalid(excinfo)


def test_groups_settings_rejects_member_echo_mismatch():
    member = _group_member()
    member["bankAccountGroupId"] = "other-group"
    with pytest.raises(CliError) as excinfo:
        project_record("groups_settings", _group_row([member]))
    _assert_invalid(excinfo)


def test_groups_settings_preserves_null_and_missing_member_list():
    row = _group_row(None)
    projected = project_record("groups_settings", row)
    assert projected["memberList"] is None
    row = _group_row([_group_member()])
    del row["memberList"]
    projected = project_record("groups_settings", row)
    assert "memberList" not in projected


@pytest.mark.parametrize("bad_members", [{"id": "m1"}, "m1", [None], ["m1"]])
def test_groups_settings_rejects_invalid_member_structure(bad_members):
    with pytest.raises(CliError) as excinfo:
        project_record("groups_settings", _group_row(bad_members))
    _assert_invalid(excinfo)


# --- group balances runtime ----------------------------------------------------


def test_group_balances_keeps_amounts_times_and_member_nested_identity():
    projected = project_record("group_balances", _group_row([_group_member()]))
    assert projected["currentBalance"] == "30.00"
    assert projected["forecastBalance"] == "33.00"
    assert projected["lastDayClosingBalance"] == "27.00"
    assert projected["valueDate"] == "2026-01-02"
    assert projected["equiCurrency"] == "USD"
    (member,) = projected["memberList"]
    assert member["id"] == "m1"
    assert member["currentBalance"] == "10.00"
    assert member["equiForecastBalance"] == "11.00"
    assert member["currentBalanceTime"] == "2026-01-02 10:00:00"
    assert member["forecastTime"] == "2026-01-02 12:00:00"


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_group_balances_forecast_time_empty_and_null_stay_distinct(raw):
    member = _group_member()
    member["forecastTime"] = raw
    projected = project_record("group_balances", _group_row([member]))
    assert projected["memberList"][0]["forecastTime"] == raw


def test_group_balances_absent_forecast_time_key_becomes_null():
    member = _group_member()
    del member["forecastTime"]
    projected = project_record("group_balances", _group_row([member]))
    assert projected["memberList"][0]["forecastTime"] is None


@pytest.mark.parametrize(
    "bad",
    [
        True,
        ["1.00"],
        {"v": "1.00"},
        1.5,
        "abc",
        "NaN",
        "Infinity",
        "1,00.00",
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_group_balances_rejects_invalid_amount_types(bad):
    member = _group_member()
    member["equiCurrentBalance"] = bad
    with pytest.raises(CliError) as excinfo:
        project_record("group_balances", _group_row([member]))
    _assert_invalid(excinfo)


@pytest.mark.parametrize(
    "good",
    ["10.005", "", "   ", "-3.50", "1,000.00", "0", 0, Decimal("10.005"), None],
)
def test_group_balances_accepts_observed_amount_types(good):
    member = _group_member()
    member["currentBalance"] = good
    projected = project_record("group_balances", _group_row([member]))
    assert projected["memberList"][0]["currentBalance"] == good


# --- pools settings -------------------------------------------------------------


def test_pools_settings_strips_capacity_balances_and_pagination_junk():
    projected = project_record("pools_settings", _pool_row([_pool_member()]))
    for field in (
        "cashPoolCapacity",
        "currentBalance",
        "currentAviBalance",
        "closeBalance",
        "closeAviBalance",
        "valueDate",
        "pageNo",
        "pageSize",
        "rowStart",
        "startindex",
        "totalSize",
        "cashPoolDetailUrl",
        "processId",
        "processStatus",
    ):
        assert field not in projected
    assert projected["entity"] == ["SYNTH-ENTITY"]
    (member,) = projected["cashPoolMemberVOS"]
    assert member["id"] == "pm1"
    assert member["masterAccount"] == "Y"
    assert member["isShare"] == "N"
    assert member["subLimit"] == "100.00"
    for field in (
        "currentBalance",
        "currentAviBalance",
        "closeBalance",
        "closeAviBalance",
        "equvCurrentBalance",
        "equvCloseAviBalance",
        "expectBalance",
        "avlCreditAmount",
        "avlSubLimit",
    ):
        assert field not in member


def test_pools_settings_projects_swap_rules_with_nested_whitelist():
    projected = project_record("pools_settings", _pool_row([_pool_member()]))
    (rule,) = projected["cashPoolMemberVOS"][0]["cashPoolSwapRuleVOS"]
    assert rule["id"] == "sr1"
    assert rule["cashPoolMemberId"] == "pm1"
    assert rule["sweepingAmount"] == "100.00"
    assert rule["sweepTargetBalanceFrom"] == "10.00"
    assert rule["calendarConditionVos"] == []
    freq = rule["sweepingFreq"]
    assert freq["type"] == "DAILY"
    (condition,) = freq["calendarConditionVos"]
    assert condition["order"] == 1
    assert condition["calendarCode"] == "SYNTH-CAL"


def test_pools_settings_rejects_duplicate_swap_rule_identity():
    member = _pool_member()
    member["cashPoolSwapRuleVOS"] = [_swap_rule("sr1"), _swap_rule("sr1")]
    with pytest.raises(CliError) as excinfo:
        project_record("pools_settings", _pool_row([member]))
    _assert_invalid(excinfo)


def test_pools_settings_rejects_swap_rule_member_echo_mismatch():
    rule = _swap_rule()
    rule["cashPoolMemberId"] = "other-member"
    member = _pool_member()
    member["cashPoolSwapRuleVOS"] = [rule]
    with pytest.raises(CliError) as excinfo:
        project_record("pools_settings", _pool_row([member]))
    _assert_invalid(excinfo)


def test_pools_settings_rejects_invalid_swap_freq_structure():
    rule = _swap_rule()
    rule["sweepingFreq"] = ["broken"]
    member = _pool_member()
    member["cashPoolSwapRuleVOS"] = [rule]
    with pytest.raises(CliError) as excinfo:
        project_record("pools_settings", _pool_row([member]))
    _assert_invalid(excinfo)


def test_pools_settings_preserves_null_and_missing_member_list():
    row = _pool_row(None)
    projected = project_record("pools_settings", row)
    assert projected["cashPoolMemberVOS"] is None
    row = _pool_row([_pool_member()])
    del row["cashPoolMemberVOS"]
    projected = project_record("pools_settings", row)
    assert "cashPoolMemberVOS" not in projected


def test_pools_settings_rejects_member_echo_mismatch():
    member = _pool_member()
    member["cashPoolId"] = "other-pool"
    with pytest.raises(CliError) as excinfo:
        project_record("pools_settings", _pool_row([member]))
    _assert_invalid(excinfo)


def test_pools_settings_rejects_invalid_entity_structure():
    row = _pool_row([_pool_member()])
    row["entity"] = "SYNTH-ENTITY"
    with pytest.raises(CliError) as excinfo:
        project_record("pools_settings", row)
    _assert_invalid(excinfo)


def test_pools_settings_rejects_duplicate_member_identity():
    with pytest.raises(CliError) as excinfo:
        project_record(
            "pools_settings",
            _pool_row([_pool_member("pm1"), _pool_member("pm1")]),
        )
    _assert_invalid(excinfo)


# --- credit lines settings --------------------------------------------------------


def test_credit_lines_settings_strips_used_and_available_including_nested():
    projected = project_record(
        "credit_lines_settings", _credit_line_row([_credit_line_member()])
    )
    assert "usedAmount" not in projected
    assert "availableAmount" not in projected
    assert projected["amount"] == "100.00"
    (member,) = projected["bankAccountCreditLineList"]
    assert member["id"] == "cm1"
    assert member["creditLineId"] == "cl1"
    assert member["creditAmount"] == "100.00"
    for field in (
        "usedAmount",
        "usedCreditAmount",
        "availableAmount",
        "availableCreditAmount",
    ):
        assert field not in member


def test_credit_lines_settings_rejects_missing_member_identity():
    member = _credit_line_member()
    del member["id"]
    with pytest.raises(CliError) as excinfo:
        project_record("credit_lines_settings", _credit_line_row([member]))
    _assert_invalid(excinfo)


def test_credit_lines_settings_rejects_member_echo_mismatch():
    member = _credit_line_member()
    member["creditLineId"] = "other-line"
    with pytest.raises(CliError) as excinfo:
        project_record("credit_lines_settings", _credit_line_row([member]))
    _assert_invalid(excinfo)


def test_credit_lines_settings_preserves_null_member_list():
    row = _credit_line_row(None)
    projected = project_record("credit_lines_settings", row)
    assert projected["bankAccountCreditLineList"] is None


def test_credit_lines_settings_rejects_bool_amount():
    row = _credit_line_row([_credit_line_member()])
    row["amount"] = False
    with pytest.raises(CliError) as excinfo:
        project_record("credit_lines_settings", row)
    _assert_invalid(excinfo)


# --- balances runtime --------------------------------------------------------------


def test_balances_keeps_source_times_and_nested_native_times():
    projected = project_record("balances", _balance_row())
    assert projected["statementCreateTime"] == "2026-01-02 10:00:00"
    assert projected["timeZone"] == "Asia/Shanghai"
    assert projected["curBalance"] == "10.00"
    dayend = projected["leastDayendBalVo"]
    assert dayend["valueDate"] == "2026-01-01"
    assert dayend["updateTime"] == "2026-01-02 09:30:00"
    assert dayend["statementCreateTime"] == "2026-01-02 09:00:00"
    daytime = projected["leastDaytimeBalVo"]
    assert daytime["valueDate"] == "2026-01-02"
    assert daytime["instradayBalance"] == "9.10"
    assert projected["avlBalanceSwitch"] is True


@pytest.mark.parametrize("bad", [True, ["1.00"], {"v": "1.00"}, 1.5])
def test_balances_rejects_invalid_amount_types(bad):
    row = _balance_row()
    row["curBalance"] = bad
    with pytest.raises(CliError) as excinfo:
        project_record("balances", row)
    _assert_invalid(excinfo)


def test_balances_rejects_invalid_nested_amount():
    row = _balance_row()
    row["leastDayendBalVo"]["closeBalance"] = [1]
    with pytest.raises(CliError) as excinfo:
        project_record("balances", row)
    _assert_invalid(excinfo)


def test_balances_rejects_invalid_nested_structure():
    row = _balance_row()
    row["leastDaytimeBalVo"] = ["broken"]
    with pytest.raises(CliError) as excinfo:
        project_record("balances", row)
    _assert_invalid(excinfo)


def test_balances_explicit_null_nested_balances_stay_null():
    row = _balance_row()
    row["leastDayendBalVo"] = None
    row["leastDaytimeBalVo"] = None
    projected = project_record("balances", row)
    assert projected["leastDayendBalVo"] is None
    assert projected["leastDaytimeBalVo"] is None


def test_balances_absent_nested_balances_stay_absent():
    row = _balance_row()
    del row["leastDayendBalVo"]
    del row["leastDaytimeBalVo"]
    projected = project_record("balances", row)
    assert "leastDayendBalVo" not in projected
    assert "leastDaytimeBalVo" not in projected


def test_balances_valid_nested_balances_project_whitelisted_fields():
    row = _balance_row()
    row["leastDayendBalVo"]["junk"] = "dropped"
    projected = project_record("balances", row)
    dayend = projected["leastDayendBalVo"]
    assert dayend["closeBalance"] == "9.50"
    assert dayend["valueDate"] == "2026-01-01"
    assert "junk" not in dayend


# --- end-of-day runtime -------------------------------------------------------------


def test_eod_keeps_dates_and_direction_without_guessing():
    projected = project_record("eod", _eod_row())
    assert projected["valueDate"] == "2026-01-02"
    assert projected["transDate"] == "2026-01-02"
    assert projected["transTime"] == "10:00:00"
    assert projected["date"] == "2026-01-02"
    assert projected["fundDirection"] == "CR"
    assert projected["amount"] == "1234.50"
    assert projected["bankTransNo"] == "SYNTH-TXN-1"


def test_eod_rejects_empty_transaction_number():
    row = _eod_row()
    row["bankTransNo"] = ""
    with pytest.raises(CliError) as excinfo:
        project_record("eod", row)
    _assert_invalid(excinfo)


def test_eod_rejects_invalid_amount_type():
    row = _eod_row()
    row["amount"] = {"value": "1.00"}
    with pytest.raises(CliError) as excinfo:
        project_record("eod", row)
    _assert_invalid(excinfo)


# --- forecast results runtime -------------------------------------------------


def test_forecast_results_keeps_distinct_ids_dates_and_int_create_time():
    projected = project_record("forecast_results", _forecast_row())
    assert projected["id"] == "fr1"
    assert projected["forecastTaskId"] == "SYNTH-TASK"
    assert projected["forecastBatchNo"] == 7
    assert projected["forecastRuleId"] == "SYNTH-RULE"
    assert projected["baseValueDate"] == "2026-01-01"
    assert projected["valueDate"] == "2026-01-02"
    assert projected["gmtCreate"] == 1767225600000
    assert projected["recordCreateTime"] == "2026-01-02 09:00:00"
    for field in ("pageNo", "pageSize", "rowStart", "startindex", "totalSize"):
        assert field not in projected


def test_forecast_results_rejects_non_integer_create_time():
    row = _forecast_row()
    row["gmtCreate"] = "1767225600000"
    with pytest.raises(CliError) as excinfo:
        project_record("forecast_results", row)
    _assert_invalid(excinfo)


def test_forecast_results_rejects_bool_integer_field():
    row = _forecast_row()
    row["lastestFlag"] = True
    with pytest.raises(CliError) as excinfo:
        project_record("forecast_results", row)
    _assert_invalid(excinfo)


def test_forecast_results_rejects_invalid_amount():
    row = _forecast_row()
    row["forecastBalance"] = ["10.00"]
    with pytest.raises(CliError) as excinfo:
        project_record("forecast_results", row)
    _assert_invalid(excinfo)


# --- seam ---------------------------------------------------------------------


def test_unknown_projection_name_rejected():
    with pytest.raises(CliError):
        project_record("unknown_projection", {})


def test_non_mapping_row_rejected():
    bad_row: Any = ["not-a-record"]
    with pytest.raises(CliError) as excinfo:
        project_record("balances", bad_row)
    _assert_invalid(excinfo)
