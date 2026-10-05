"""Verified task-result details, independently cached from task lists (#97)."""

import re
from decimal import Decimal
from typing import Any

from ...errors import INVALID_RESPONSE, CliError
from .investment_batch import TASK_TYPES, validate_business_date
from .spec import ENC_FORM, ENV_SUCCESS, RUNTIMES, DetailSpec, IdentityOption

STRATEGY_DETAIL = DetailSpec(
    path=("investment", "strategy-results"),
    action="get",
    kind=RUNTIMES,
    title="investment strategy result detail",
    endpoint="/api/increment/decision/task/taskDetail.json",
    method="POST",
    encoding=ENC_FORM,
    envelope=ENV_SUCCESS,
    container=("data",),
    identity=(
        IdentityOption(
            "task_id", "taskId", "Native task id from the list row id", echo="taskId"
        ),
        IdentityOption(
            "task_type",
            "taskType",
            "Expected native task type from the originating list",
            echo="taskType",
            choices=TASK_TYPES,
            virtual=True,
        ),
    ),
    tenant_field=False,
    list_leaf=("investment", "strategy-results"),
    table_columns=("taskId", "taskType", "taskStatus", "adoptionStatus", "resultTime"),
    projection="strategy_detail",
    schema_version="strategy-detail-native-v1",
    notes=(
        "Both native task variants require an explicit --task-type; taskId and"
        " taskType must echo exactly.",
        "Only taskId is sent in the native form POST; task type separates cache"
        " identity and validates the response.",
        "Native amount objects and date/time strings retain source representation"
        " and units; no conversion is inferred.",
        "Projection excludes user identities, free-text impact descriptions,"
        " operation logs, and unverified strategy subdocuments.",
        "Investable fund detail preserves per-currency totals by value date;"
        " native product null is retained.",
    ),
)

_SCALARS = (
    "taskId",
    "taskType",
    "taskStatus",
    "adoptionStatus",
    "expectedInvestEndDate",
    "expectedInvestStartDate",
    "investmentEndDate",
    "mainStrategyTemplateId",
    "resultTime",
    "triggerDate",
    "triggerType",
)
STRATEGY_DETAIL_FIELDS = {
    **{field: "str" for field in _SCALARS},
    "investableFundResultVo": "object | null",
    "riskIndicatorResultVoList": "list",
}

_MONEY = ("amount", "cent", "centFactor", "currency", "currencyCode", "currencyValue")


def _invalid(context: str) -> CliError:
    return CliError(INVALID_RESPONSE, f"strategy_detail: invalid native {context}")


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(context)
    return value


def _strings(value: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    result = {}
    for field in fields:
        if field not in value:
            continue
        item = value[field]
        if item is not None and not isinstance(item, str):
            raise _invalid(field)
        result[field] = item
    return result


def _currency(value: Any) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
        raise _invalid("currency")


def _money(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    native = _object(value, "amount object")
    amount = native.get("amount")
    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float, Decimal))
        or not Decimal(str(amount)).is_finite()
    ):
        raise _invalid("amount")
    _currency(native.get("currency"))
    result = _strings(native, _MONEY[3:])
    for field in _MONEY[:3]:
        if field not in native:
            continue
        item = native[field]
        if isinstance(item, bool) or (
            item is not None and not isinstance(item, (int, float, Decimal))
        ):
            raise _invalid(field)
        result[field] = item
    return result


def _rows(value: Any, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise _invalid(context)
    return [_object(row, context) for row in value]


def project_strategy_detail(row: Any) -> dict[str, Any]:
    """Allowlisted native business fields; unknown nested content never leaks."""
    native = _object(row, "detail object")
    result = _strings(native, _SCALARS)
    if native.get("taskType") not in TASK_TYPES:
        raise _invalid("taskType")
    if "investableFundResultVo" not in native:
        raise _invalid("investableFundResultVo")
    fund = native["investableFundResultVo"]
    projected: dict[str, Any] | None = None
    if fund is not None:
        fund = _object(fund, "investableFundResultVo")
        projected = {}
        if "currencyFundResultVoList" in fund:
            totals = []
            for item in _rows(
                fund["currencyFundResultVoList"], "currency fund results"
            ):
                _currency(item.get("currency"))
                if "amount" not in item:
                    raise _invalid("currency fund amount")
                total = _strings(item, ("currency", "tenor"))
                for field in (
                    "amount",
                    "meetRiskRuleAmount",
                    "meetRiskRuleAmountUsd",
                    "safetyBufferAmount",
                ):
                    if field in item:
                        total[field] = _money(item[field])
                totals.append(total)
            projected["currencyFundResultVoList"] = totals
        if "investableInvestableFundDetailMap" in fund:
            by_currency = _object(
                fund["investableInvestableFundDetailMap"], "fund detail map"
            )
            entries = {}
            for currency, items in by_currency.items():
                _currency(currency)
                details = []
                for item in _rows(items, "fund detail rows"):
                    if item.get("currency") != currency:
                        raise _invalid("fund detail currency")
                    try:
                        validate_business_date(item.get("valueDate"))
                    except ValueError:
                        raise _invalid("valueDate") from None
                    if "sumAmount" not in item:
                        raise _invalid("sumAmount")
                    detail = _strings(item, ("currency", "valueDate"))
                    if "sumAmount" in item:
                        detail["sumAmount"] = _money(item["sumAmount"])
                    details.append(detail)
                entries[currency] = details
            projected["investableInvestableFundDetailMap"] = entries
    result["investableFundResultVo"] = projected
    if "riskIndicatorResultVoList" in native:
        result["riskIndicatorResultVoList"] = [
            _strings(
                item,
                (
                    "riskIndicator",
                    "riskStrategyType",
                    "riskType",
                    "riskValue",
                    "status",
                ),
            )
            for item in _rows(native["riskIndicatorResultVoList"], "risk indicators")
        ]
    return result
