"""Settings/runtime field projections for the v0.2.3 liquidity leaves (#76).

Main calls ``project_record(projection_name, row)`` after native identity
validation. Each projection applies the spec whitelists (docs/design/
liquidity-v0.2.3.md): settings projections strip balance/used/available/
capacity fields including nested members; runtime projections keep native
amounts and native observation times without deriving, summing or scaling.

Amount precision is preserved (no /100). Projections using amount validation
accept null, empty string, decimal numeric string, int and finite Decimal;
bool, float, containers and non-decimal strings (including NaN/Infinity)
raise INVALID_RESPONSE. Credit usage and quotes deliberately skip business-value
validation: their projected amounts, currencies and unknown values remain raw,
with reading-protocol and identity checks, plus parent-link/tenant checks
where applicable to the source contract.
Zero, empty string and null stay distinct — projections never replace one
with another. Missing member lists stay absent and null
member lists stay null (never replaced by an empty list). Nested member and
rule identities must be non-empty str/int, unique within their parent, and
their parent echo (bankAccountGroupId/cashPoolId/creditLineId/
cashPoolMemberId), when present, must match the parent id.
"""

import re
from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from ...errors import INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from .account_capacity import project_capacity
from .decision_list import project_decision_record
from .fee_orders import project_fee_order
from .forecast_accuracy import project_accuracy
from .funding_demands import project_demand
from .operations_batch import validate_swap_business_date
from .realtime_network import project_network
from .rfqs import project_rfq_subtask
from .risk_batch import project_risk_record
from .risk_detail import project_risk_detail
from .risk_sla import project_risk_sla
from .strategy_detail import project_strategy_detail
from .transfer_list import project_transfer_order
from .transfer_rules import project_transfer_rule

# The verified group-balances request scope fixes the equivalent currency
# (spec #76: only the USD scope carries business evidence); it is declared
# here as scope metadata, never inferred from row values.
_GROUP_BALANCES_EQUI_CURRENCY = "USD"


def _invalid(message: str) -> CliError:
    return CliError(INVALID_RESPONSE, message)


def _require_row(row: Any, context: str) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    raise _invalid(f"{context}: record is not an object")


# Observed native amount strings: plain decimals ("100.00", "-3.5", "0") and
# thousands-grouped decimals ("12,345.67"); blank stays blank, null stays null.
_AMOUNT_TEXT = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


def _is_valid_amount(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, str):
        if not value.strip():
            return True
        return bool(_AMOUNT_TEXT.match(value))
    return False


def _validate_amounts(
    record: Mapping[str, Any], fields: tuple[str, ...], context: str
) -> None:
    for field in fields:
        if field not in record:
            continue
        if not _is_valid_amount(record[field]):
            raise _invalid(f"{context}.{field}: invalid amount value")


def _typed_id(value: Any, context: str) -> Any:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise _invalid(f"{context}: invalid identity type {type(value).__name__}")
    if isinstance(value, str) and not value.strip():
        raise _invalid(f"{context}: empty identity")
    return value


def _check_echo(
    member: Mapping[str, Any],
    echo_field: str,
    parent_id: Any,
    context: str,
) -> None:
    if echo_field not in member or parent_id is None:
        return
    echo = _typed_id(member[echo_field], f"{context}.{echo_field}")
    if echo != parent_id:
        raise _invalid(f"{context}.{echo_field}: parent relation echo mismatch")


_ABSENT = object()


def _project_members(
    row: Mapping[str, Any],
    key: str,
    fields: tuple[str, ...],
    context: str,
    amount_fields: tuple[str, ...] = (),
    echo_field: str | None = None,
    normalize: Callable[[dict[str, Any]], None] | None = None,
    nested: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
) -> Any:
    if key not in row:
        return _ABSENT
    members = row[key]
    if members is None:
        return None
    if not isinstance(members, list) or any(
        not isinstance(m, Mapping) for m in members
    ):
        raise _invalid(f"{context}.{key}: invalid nested member structure")
    parent_id = row.get("id")
    seen: set[Any] = set()
    projected: list[dict[str, Any]] = []
    for index, member in enumerate(members):
        member_context = f"{context}.{key}[{index}]"
        identity = _typed_id(member.get("id"), f"{member_context}.id")
        if identity in seen:
            raise _invalid(f"{member_context}.id: duplicate member identity")
        seen.add(identity)
        if echo_field is not None:
            _check_echo(member, echo_field, parent_id, member_context)
        _validate_amounts(member, amount_fields, member_context)
        record = {field: member[field] for field in fields if field in member}
        if nested is not None:
            record = nested(record, member_context)
        if normalize is not None:
            normalize(record)
        projected.append(record)
    return projected


def _pick(row: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: row[field] for field in fields if field in row}


# --- groups: settings and runtime projections over the same native row ------

_GROUP_SETTINGS_FIELDS = (
    "id",
    "userGroupCode",
    "groupName",
    "type",
    "memo",
    "version",
    "tntInstId",
    "operator",
    "gmtCreate",
    "gmtModified",
)
_GROUP_MEMBER_SETTINGS_FIELDS = (
    "id",
    "bankAccountGroupId",
    "accountNo",
    "aliasName",
    "entity",
    "bankId",
    "currencyCode",
    "accountUsageType",
    "memo",
    "gmtCreate",
    "gmtModified",
)
_GROUP_BALANCES_FIELDS = (
    "id",
    "userGroupCode",
    "groupName",
    "type",
    "memo",
    "operator",
    "gmtCreate",
    "gmtModified",
    "valueDate",
    "currentBalance",
    "forecastBalance",
    "lastDayClosingBalance",
)
_GROUP_MEMBER_BALANCES_FIELDS = (
    "id",
    "bankAccountGroupId",
    "accountNo",
    "aliasName",
    "entity",
    "bankId",
    "currencyCode",
    "accountUsageType",
    "memo",
    "currentBalance",
    "forecastBalance",
    "lastDayClosingBalance",
    "equiCurrentBalance",
    "equiForecastBalance",
    "equiLastDayClosingBalance",
    "currentBalanceTime",
    "forecastTime",
)
_GROUP_MEMBER_AMOUNT_FIELDS = (
    "currentBalance",
    "forecastBalance",
    "lastDayClosingBalance",
    "equiCurrentBalance",
    "equiForecastBalance",
    "equiLastDayClosingBalance",
)


def _project_groups_settings(row: Any) -> dict[str, Any]:
    record = _require_row(row, "groups_settings")
    projected = _pick(record, _GROUP_SETTINGS_FIELDS)
    members = _project_members(
        record,
        "memberList",
        _GROUP_MEMBER_SETTINGS_FIELDS,
        "groups_settings",
        echo_field="bankAccountGroupId",
    )
    if members is not _ABSENT:
        projected["memberList"] = members
    return projected


def _normalize_forecast_time(record: dict[str, Any]) -> None:
    # Only one observed member carried forecastTime. A missing key stays
    # unknown (null); an observed empty string stays empty — never replaced
    # by gmtModified or any other timestamp (spec #76).
    record.setdefault("forecastTime", None)


def _project_group_balances(row: Any) -> dict[str, Any]:
    record = _require_row(row, "group_balances")
    _validate_amounts(record, _GROUP_MEMBER_AMOUNT_FIELDS[:3], "group_balances")
    projected = _pick(record, _GROUP_BALANCES_FIELDS)
    projected["equiCurrency"] = _GROUP_BALANCES_EQUI_CURRENCY
    members = _project_members(
        record,
        "memberList",
        _GROUP_MEMBER_BALANCES_FIELDS,
        "group_balances",
        amount_fields=_GROUP_MEMBER_AMOUNT_FIELDS,
        echo_field="bankAccountGroupId",
        normalize=_normalize_forecast_time,
    )
    if members is not _ABSENT:
        projected["memberList"] = members
    return projected


# --- pools settings ----------------------------------------------------------

_POOL_SETTINGS_FIELDS = (
    "id",
    "cashPoolName",
    "cashPoolType",
    "cashPoolCategory",
    "mainCurrency",
    "entity",
    "status",
    "haircutRatio",
    "memo",
    "operator",
    "gmtModified",
)
_POOL_MEMBER_FIELDS = (
    "id",
    "cashPoolId",
    "aliasName",
    "entity",
    "bankId",
    "currency",
    "bankCurrency",
    "masterAccount",
    "isShare",
    "subLimit",
    "creditAmount",
    "creditRateType",
    "creditRateSource",
    "creditRateValue",
    "creditRateExtType",
    "debitRateType",
    "debitRateSource",
    "debitRateValue",
    "debitRateExtType",
    "penaltyRateType",
    "penaltyRateSource",
    "penaltyRateValue",
    "penaltyRateExtType",
    "billingTimeType",
    "billingTimeValue",
    "balanceUpdateType",
    "outFlowCapability",
    "timeZone",
    "tntInstId",
    "operator",
    "memo",
    "cashPoolName",
    "cashPoolSwapRuleVOS",
)
_POOL_MEMBER_AMOUNT_FIELDS = ("subLimit", "creditAmount")
# Swap rules are shared pool sweep configuration observed in the verified
# pool detail contract (request-023/025); nested whitelists below cover the
# exact observed structure. Sweep target amounts are configured thresholds,
# not observed balances.
_POOL_SWAP_CONDITION_FIELDS = (
    "calendarCode",
    "calendarType",
    "customCalendarId",
    "customeType",
    "days",
    "exclude",
    "followActionAccountType",
    "order",
)
_POOL_SWAP_FREQ_FIELDS = (
    "type",
    "timePoint",
    "beginTime",
    "endTime",
    "interval",
    "conditionLogical",
    "calendarCode",
    "calendarType",
    "customCalendarId",
    "customeType",
    "days",
    "exclude",
    "followActionAccountType",
)
_POOL_SWAP_RULE_FIELDS = (
    "id",
    "cashPoolMemberId",
    "type",
    "sweepingType",
    "sweepingDirection",
    "sweepingAmount",
    "sweepTargetBalanceFrom",
    "sweepTargetBalanceTo",
    "currency",
    "timeZone",
    "operator",
    "tntInstId",
) + _POOL_SWAP_FREQ_FIELDS
_POOL_SWAP_AMOUNT_FIELDS = (
    "sweepingAmount",
    "sweepTargetBalanceFrom",
    "sweepTargetBalanceTo",
)


def _project_string_list(value: Any, context: str) -> Any:
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(e, str) for e in value):
        raise _invalid(f"{context}: invalid string list structure")
    return list(value)


def _project_swap_conditions(value: Any, context: str) -> Any:
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(c, Mapping) for c in value):
        raise _invalid(f"{context}: invalid calendar condition structure")
    conditions: list[dict[str, Any]] = []
    for index, condition in enumerate(value):
        condition_context = f"{context}[{index}]"
        projected = _pick(condition, _POOL_SWAP_CONDITION_FIELDS)
        if "days" in projected:
            projected["days"] = _project_string_list(
                projected["days"], f"{condition_context}.days"
            )
        conditions.append(projected)
    return conditions


def _project_swap_freq(rule: Mapping[str, Any], context: str) -> Any:
    if "sweepingFreq" not in rule or rule["sweepingFreq"] is None:
        return None
    freq = rule["sweepingFreq"]
    if not isinstance(freq, Mapping):
        raise _invalid(f"{context}.sweepingFreq: invalid sweep frequency structure")
    projected = _pick(freq, _POOL_SWAP_FREQ_FIELDS)
    if "days" in projected:
        projected["days"] = _project_string_list(
            projected["days"], f"{context}.sweepingFreq.days"
        )
    if "calendarConditionVos" in freq:
        projected["calendarConditionVos"] = _project_swap_conditions(
            freq["calendarConditionVos"], f"{context}.sweepingFreq.calendarConditionVos"
        )
    return projected


def _project_swap_rules(member: dict[str, Any], context: str) -> dict[str, Any]:
    if "cashPoolSwapRuleVOS" not in member:
        return member
    rules = member.pop("cashPoolSwapRuleVOS")
    if rules is None:
        member["cashPoolSwapRuleVOS"] = None
        return member
    if not isinstance(rules, list) or any(not isinstance(r, Mapping) for r in rules):
        raise _invalid(f"{context}.cashPoolSwapRuleVOS: invalid swap rule structure")
    seen: set[Any] = set()
    projected_rules: list[dict[str, Any]] = []
    for index, rule in enumerate(rules):
        rule_context = f"{context}.cashPoolSwapRuleVOS[{index}]"
        identity = _typed_id(rule.get("id"), f"{rule_context}.id")
        if identity in seen:
            raise _invalid(f"{rule_context}.id: duplicate swap rule identity")
        seen.add(identity)
        _check_echo(rule, "cashPoolMemberId", member.get("id"), rule_context)
        _validate_amounts(rule, _POOL_SWAP_AMOUNT_FIELDS, rule_context)
        projected = _pick(rule, _POOL_SWAP_RULE_FIELDS)
        if "days" in projected:
            projected["days"] = _project_string_list(
                projected["days"], f"{rule_context}.days"
            )
        if "calendarConditionVos" in rule:
            projected["calendarConditionVos"] = _project_swap_conditions(
                rule["calendarConditionVos"], f"{rule_context}.calendarConditionVos"
            )
        freq = _project_swap_freq(rule, rule_context)
        if freq is not None:
            projected["sweepingFreq"] = freq
        elif "sweepingFreq" in rule:
            projected["sweepingFreq"] = None
        projected_rules.append(projected)
    member["cashPoolSwapRuleVOS"] = projected_rules
    return member


def _project_pools_settings(row: Any) -> dict[str, Any]:
    record = _require_row(row, "pools_settings")
    _validate_amounts(record, ("haircutRatio",), "pools_settings")
    entity = record.get("entity")
    if entity is not None and (
        not isinstance(entity, list) or any(not isinstance(e, str) for e in entity)
    ):
        raise _invalid("pools_settings.entity: invalid entity structure")
    projected = _pick(record, _POOL_SETTINGS_FIELDS)
    members = _project_members(
        record,
        "cashPoolMemberVOS",
        _POOL_MEMBER_FIELDS,
        "pools_settings",
        amount_fields=_POOL_MEMBER_AMOUNT_FIELDS,
        echo_field="cashPoolId",
        nested=_project_swap_rules,
    )
    if members is not _ABSENT:
        projected["cashPoolMemberVOS"] = members
    return projected


# --- pool balance snapshots --------------------------------------------------

_POOL_BALANCE_AMOUNTS = (
    "currentBalance",
    "currentAviBalance",
    "closeBalance",
    "closeAviBalance",
)
_POOL_MEMBER_BALANCE_AMOUNTS = _POOL_BALANCE_AMOUNTS + (
    "equvCurrentBalance",
    "equvCurrentAviBalance",
    "equvCloseBalance",
    "equvCloseAviBalance",
)
_POOL_BALANCE_FIELDS = (
    "cashPoolType",
    "id",
    "cashPoolName",
    "cashPoolCategory",
    "mainCurrency",
    "valueDate",
    "tntInstId",
) + _POOL_BALANCE_AMOUNTS
_POOL_MEMBER_BALANCE_FIELDS = (
    "id",
    "cashPoolId",
    "aliasName",
    "entity",
    "bankId",
    "currency",
    "bankCurrency",
    "masterAccount",
    "isShare",
    "timeZone",
    "tntInstId",
) + _POOL_MEMBER_BALANCE_AMOUNTS


def _validate_pool_balance_scope(record: Mapping[str, Any], context: str) -> None:
    from .spec import TENANT

    if "tntInstId" in record and record["tntInstId"] != TENANT:
        raise _invalid(f"{context}: tenant is outside requested scope")
    for field in ("mainCurrency", "currency", "bankCurrency"):
        value = record.get(field)
        if (
            value is not None
            and value != ""
            and (not isinstance(value, str) or re.fullmatch(r"[A-Z]{3}", value) is None)
        ):
            raise _invalid(f"{context}.{field}: invalid currency")


def _project_pool_balance_member(
    record: dict[str, Any], context: str
) -> dict[str, Any]:
    _validate_pool_balance_scope(record, context)
    return record


def _project_pool_balances(row: Any) -> dict[str, Any]:
    record = _require_row(row, "pool_balances")
    _typed_id(record.get("id"), "pool_balances.id")
    _validate_pool_balance_scope(record, "pool_balances")
    if record.get("cashPoolCategory") != "BANK":
        raise _invalid("pool_balances: category is outside requested BANK scope")
    _validate_amounts(record, _POOL_BALANCE_AMOUNTS, "pool_balances")
    value = record.get("valueDate")
    if value is not None and value != "":
        try:
            if (
                not isinstance(value, str)
                or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None
            ):
                raise ValueError("not YYYY-MM-DD")
            date.fromisoformat(value)
        except ValueError as error:
            raise _invalid("pool_balances.valueDate: invalid YYYY-MM-DD") from error
    projected = _pick(record, _POOL_BALANCE_FIELDS)
    members = _project_members(
        record,
        "cashPoolMemberVOS",
        _POOL_MEMBER_BALANCE_FIELDS,
        "pool_balances",
        amount_fields=_POOL_MEMBER_BALANCE_AMOUNTS,
        echo_field="cashPoolId",
        nested=_project_pool_balance_member,
    )
    if members is not _ABSENT:
        projected["cashPoolMemberVOS"] = members
    return projected


# --- credit lines settings ----------------------------------------------------

_CREDIT_LINE_SETTINGS_FIELDS = (
    "id",
    "creditLineType",
    "currency",
    "amount",
    "dateType",
    "startTimestamp",
    "expiryTimestamp",
    "bankId",
    "masterBankId",
    "instId",
    "shareTag",
    "status",
    "manageStatus",
    "memo",
    "version",
    "tntInstId",
)
_CREDIT_LINE_MEMBER_FIELDS = (
    "id",
    "creditLineId",
    "accountNo",
    "aliasName",
    "bankId",
    "instId",
    "creditAmount",
    "creditCurrency",
    "currency",
    "equvAmount",
    "rateId",
    "isMasterAccount",
    "mergeFlag",
    "startTimestamp",
    "expiryTimestamp",
    "status",
    "gmtCreate",
    "gmtModified",
)


def _project_credit_lines_settings(row: Any) -> dict[str, Any]:
    record = _require_row(row, "credit_lines_settings")
    _validate_amounts(record, ("amount",), "credit_lines_settings")
    projected = _pick(record, _CREDIT_LINE_SETTINGS_FIELDS)
    members = _project_members(
        record,
        "bankAccountCreditLineList",
        _CREDIT_LINE_MEMBER_FIELDS,
        "credit_lines_settings",
        amount_fields=("creditAmount", "equvAmount"),
        echo_field="creditLineId",
    )
    if members is not _ABSENT:
        projected["bankAccountCreditLineList"] = members
    return projected


# --- credit usage runtime ----------------------------------------------------

_CREDIT_USAGE_FIELDS = (
    "id",
    "creditLineType",
    "currency",
    "amount",
    "usedAmount",
    "availableAmount",
    "bankId",
    "masterBankId",
    "instId",
    "shareTag",
    "status",
    "manageStatus",
    "tntInstId",
)
_CREDIT_USAGE_MEMBER_FIELDS = (
    "id",
    "creditLineId",
    "accountNo",
    "aliasName",
    "bankId",
    "instId",
    "creditAmount",
    "usedCreditAmount",
    "availableCreditAmount",
    "creditCurrency",
    "currency",
    "equvAmount",
    "usedAmount",
    "availableAmount",
    "isMasterAccount",
    "mergeFlag",
    "status",
    "tntInstId",
)


def _credit_usage_tenant(record: dict[str, Any], context: str) -> dict[str, Any]:
    from .spec import TENANT

    if "tntInstId" in record and record["tntInstId"] != TENANT:
        raise _invalid(f"{context}: tenant is outside requested scope")
    return record


def _project_credit_usage(row: Any) -> dict[str, Any]:
    record = _require_row(row, "credit_usage")
    _typed_id(record.get("id"), "credit_usage.id")
    _credit_usage_tenant(record, "credit_usage")
    projected = _pick(record, _CREDIT_USAGE_FIELDS)
    # This reader deliberately does not parse or validate business field values.
    members = _project_members(
        record,
        "bankAccountCreditLineList",
        _CREDIT_USAGE_MEMBER_FIELDS,
        "credit_usage",
        echo_field="creditLineId",
        nested=_credit_usage_tenant,
    )
    if members is not _ABSENT:
        projected["bankAccountCreditLineList"] = members
    return projected


# --- balances runtime ----------------------------------------------------------

_BALANCE_AMOUNT_FIELDS = (
    "curBalance",
    "avlBalance",
    "avlBalanceAfterAdj",
    "openBalance",
    "openAvlBalance",
    "openAvlBalanceAfterAdj",
    "equvCurBalance",
    "equvAvlBalance",
    "equvOpenBalance",
    "equvOpenAvlBalance",
)
_BALANCE_NESTED_FIELDS = {
    "leastDayendBalVo": (
        "accountNo",
        "aliasName",
        "bankId",
        "entity",
        "currency",
        "openBalance",
        "openAvlBalance",
        "closeBalance",
        "closeAvlBalance",
        "source",
        "statementCreateTime",
        "timeZone",
        "updateTime",
        "valueDate",
    ),
    "leastDaytimeBalVo": (
        "accountNo",
        "aliasName",
        "bankId",
        "entity",
        "currency",
        "instradayBalance",
        "instradayAvlBalance",
        "source",
        "statementCreateTime",
        "timeZone",
        "updateTime",
        "valueDate",
    ),
}
_BALANCE_FIELDS = (
    "accountNo",
    "accountNumbers",
    "accountType",
    "aliasName",
    "balId",
    "bankId",
    "bizTag",
    "blockChainAccountType",
    "colorType",
    "companyName",
    "currency",
    "digitalCurrency",
    "entity",
    "equvCurrency",
    "fundAttribute1",
    "statementCreateTime",
    "timeZone",
    "avlBalanceSwitch",
    "openAvlBalanceSwitch",
) + _BALANCE_AMOUNT_FIELDS


def _project_balances(row: Any) -> dict[str, Any]:
    record = _require_row(row, "balances")
    _validate_amounts(record, _BALANCE_AMOUNT_FIELDS, "balances")
    projected = _pick(record, _BALANCE_FIELDS)
    for key, fields in _BALANCE_NESTED_FIELDS.items():
        if key not in record:
            continue
        nested = record[key]
        if nested is None:
            # Explicit null stays null; absence above stays absent.
            projected[key] = None
            continue
        if not isinstance(nested, Mapping):
            raise _invalid(f"balances.{key}: invalid nested balance structure")
        nested_amounts = tuple(f for f in fields if "alance" in f)
        _validate_amounts(nested, nested_amounts, f"balances.{key}")
        projected[key] = _pick(nested, fields)
    return projected


# --- end-of-day statements runtime ---------------------------------------------

_EOD_FIELDS = (
    "instId",
    "bankAccountAliasName",
    "bankId",
    "accountType",
    "currency",
    "valueDate",
    "transDate",
    "transTime",
    "date",
    "bankTransNo",
    "end2EndId",
    "fundDirection",
    "amount",
    "transType",
    "transDetail",
    "memo",
    "otherAccountName",
    "otherAccountNo",
    "otherBankName",
)


def _project_eod(row: Any) -> dict[str, Any]:
    record = _require_row(row, "eod")
    _validate_amounts(record, ("amount",), "eod")
    trans_no = record.get("bankTransNo")
    # Positive samples carry a unique number; an empty number must fail
    # explicitly here (duplicates are caught by pagination, not projection).
    if isinstance(trans_no, str) and not trans_no.strip():
        raise _invalid("eod.bankTransNo: empty transaction number")
    return _pick(record, _EOD_FIELDS)


# --- forecast results runtime --------------------------------------------------

_FORECAST_AMOUNT_FIELDS = (
    "forecastBalance",
    "minimumBalance",
    "openBalance",
    "cashFlowTransIn",
    "cashFlowTransOut",
)
_FORECAST_INT_FIELDS = ("forecastBatchNo", "gmtCreate", "gmtModified", "lastestFlag")
_FORECAST_FIELDS = (
    (
        "id",
        "accountNo",
        "autoFlag",
        "bankAccountAliasName",
        "bankId",
        "baseValueDate",
        "valueDate",
        "cashForecastType",
        "currency",
        "forecastTaskId",
        "forecastRuleId",
        "instId",
        "isCoverIod",
        "isNeedReview",
        "minimumBalanceValueTime",
        "recordCreateTime",
        "tntInstId",
    )
    + _FORECAST_AMOUNT_FIELDS
    + _FORECAST_INT_FIELDS
)


def _project_forecast_results(row: Any) -> dict[str, Any]:
    record = _require_row(row, "forecast_results")
    _validate_amounts(record, _FORECAST_AMOUNT_FIELDS, "forecast_results")
    for field in _FORECAST_INT_FIELDS:
        value = record.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            raise _invalid(f"forecast_results.{field}: unobserved integer field type")
    return _pick(record, _FORECAST_FIELDS)


def _project_swap_orders(row: Any) -> dict[str, Any]:
    """Preserve native swap records and precision, validating observed fields."""
    record = _require_row(row, "swap_orders")
    deal_id = record.get("dealId")
    if not isinstance(deal_id, str) or not deal_id.strip():
        raise _invalid("swap_orders.dealId: native identity is a nonempty string")
    amount_fields = (
        "nearLegCreditAmount",
        "nearLegDebitAmount",
        "farLegCreditAmount",
        "farLegDebitAmount",
        "nearLegFxRate",
        "farLegFxRate",
        "expectNearLegFxRate",
        "expectFarLegFxRate",
    )
    for field in amount_fields:
        value = record.get(field)
        if value is not None and not isinstance(value, str):
            raise _invalid(f"swap_orders.{field}: expected native decimal string")
    _validate_amounts(record, amount_fields, "swap_orders")
    for field in ("nearLegValueDate", "farLegValueDate"):
        value = record.get(field)
        if value is None or value == "":
            continue
        try:
            validate_swap_business_date(value)
        except ValueError as error:
            raise _invalid(f"swap_orders.{field}: invalid YYYYMMDD") from error
    for field in ("gmtCreate", "gmtModified", "gmtSend", "gmtReturn", "nodeNum"):
        value = record.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            raise _invalid(f"swap_orders.{field}: invalid native integer")
    value = record.get("needReview")
    if value is not None and not isinstance(value, bool):
        raise _invalid("swap_orders.needReview: invalid native boolean")
    return record


def _project_benchmark_values(row: Any) -> dict[str, Any]:
    from .investment_batch import (
        BENCHMARK_FIELDS,
        BENCHMARK_IDENTITY,
        benchmark_primary_id,
        validate_business_date,
    )
    from .spec import TENANT

    record = _require_row(row, "benchmark_values")
    if "tntInstId" in record and record["tntInstId"] != TENANT:
        raise _invalid("benchmark_values: tenant is outside requested scope")
    for field in BENCHMARK_FIELDS:
        value = record.get(field)
        if value is not None and not isinstance(value, str):
            raise _invalid(f"benchmark_values.{field}: expected native string")
        if field in BENCHMARK_IDENTITY and (
            not isinstance(value, str) or not value.strip()
        ):
            raise _invalid(
                f"benchmark_values.{field}: expected nonempty identity string"
            )
    try:
        validate_business_date(record["effectiveDate"])
    except ValueError as error:
        raise _invalid("benchmark_values.effectiveDate: invalid YYYYMMDD") from error
    _validate_amounts(record, ("value",), "benchmark_values")
    projected = _pick(record, BENCHMARK_FIELDS)
    projected["primaryId"] = benchmark_primary_id(projected)
    return projected


def _project_strategy_results(row: Any) -> dict[str, Any]:
    from .investment_batch import STRATEGY_FIELDS, TASK_TYPES, validate_business_date
    from .spec import TENANT

    record = _require_row(row, "strategy_results")
    if "tntInstId" in record and record["tntInstId"] != TENANT:
        raise _invalid("strategy_results: tenant is outside requested scope")
    if not isinstance(record.get("id"), str) or not record["id"].strip():
        raise _invalid("strategy_results.id: expected nonempty native string")
    for field in STRATEGY_FIELDS:
        value = record.get(field)
        if field in ("triggerDate", "resultTime"):
            if value is None and field == "resultTime":
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise _invalid(f"strategy_results.{field}: expected epoch milliseconds")
        elif value is not None and not isinstance(value, str):
            raise _invalid(f"strategy_results.{field}: expected native string")
    for field in ("valueDate", "expectedInvestStartDate", "expectedInvestEndDate"):
        value = record.get(field)
        if value is None or value == "":
            continue
        try:
            validate_business_date(value)
        except ValueError as error:
            raise _invalid(f"strategy_results.{field}: invalid YYYYMMDD") from error
    if record.get("taskType") not in TASK_TYPES:
        raise _invalid("strategy_results.taskType: unverified task variant")
    _validate_amounts(
        record,
        ("investmentAmount", "maximumExceptedIncome", "maximumExpectedRateOfReturn"),
        "strategy_results",
    )
    return _pick(record, STRATEGY_FIELDS)


def _project_quotes(row: Any) -> dict[str, Any]:
    from .investment_batch import QUOTE_FIELDS

    record = _require_row(row, "quotes")
    identity = record.get("quotationOrderId")
    if not isinstance(identity, str) or not identity.strip():
        raise _invalid("quotes.quotationOrderId: expected nonempty native string")
    return _pick(record, QUOTE_FIELDS)


def _project_factor_definitions(row: Any) -> dict[str, Any]:
    record = _require_row(row, "factor_definitions")
    code = record.get("code")
    if not isinstance(code, str) or not code.strip():
        raise _invalid("factor_definitions.code: expected nonempty native string")
    return _pick(record, ("code", "description", "englishName"))


_PROJECTORS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "funding_demands": project_demand,
    "account_capacity": project_capacity,
    "strategy_detail": project_strategy_detail,
    "groups_settings": _project_groups_settings,
    "group_balances": _project_group_balances,
    "pools_settings": _project_pools_settings,
    "pool_balances": _project_pool_balances,
    "credit_lines_settings": _project_credit_lines_settings,
    "credit_usage": _project_credit_usage,
    "balances": _project_balances,
    "eod": _project_eod,
    "forecast_results": _project_forecast_results,
    "forecast_accuracy": project_accuracy,
    "swap_orders": _project_swap_orders,
    "risk_events_detail": lambda row: project_risk_detail(row, "RISK_EVENT"),
    "risk_anomalies_detail": lambda row: project_risk_detail(row, "RISK_ALERT"),
    "risk_events": lambda row: project_risk_record(row, "RISK_EVENT"),
    "risk_anomalies": lambda row: project_risk_record(row, "RISK_ALERT"),
    "transfer_orders": project_transfer_order,
    "transfer_rules": project_transfer_rule,
    "decision_reports": project_decision_record,
    "strategy_results": _project_strategy_results,
    "benchmark_values": _project_benchmark_values,
    "quotes": _project_quotes,
    "rfq_subtasks": project_rfq_subtask,
    "factor_definitions": _project_factor_definitions,
    "fee_orders": project_fee_order,
    "realtime_network": project_network,
    "risk_sla": project_risk_sla,
}


def project_record(name: str, row: dict[str, Any]) -> dict[str, Any]:
    """Project one native row into the named settings/runtime schema."""
    projector = _PROJECTORS.get(name)
    if projector is None:
        raise CliError(INVALID_ARGUMENT, f"unknown projection: {name}")
    return projector(row)
