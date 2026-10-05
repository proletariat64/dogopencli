"""Issue #103 fixed-scope transfer-rule configuration list."""

import re
from typing import Any

from ...errors import INVALID_RESPONSE, CliError
from .spec import ENV_RESULT_FLAG, PAGE_SINGLE, SETTINGS, TENANT, ListSpec

FIELDS = (
    "ruleId",
    "ruleNo",
    "ruleName",
    "title",
    "version",
    "tntInstId",
    "status",
    "transferRuleType",
    "transferType",
    "businessType",
    "subBusinessType",
    "businessScene",
    "sceneCode",
    "debitAliasName",
    "debitBankId",
    "debitCurrency",
    "debitEntity",
    "creditAliasName",
    "creditBankId",
    "creditCurrency",
    "creditEntity",
    "network",
    "paymentAmount",
    "triggerType",
    "bizConditions",
    "preCheckCondtions",
    "ruleCheckCondtions",
    "timeConditions",
    "timeZone",
    "effectiveTime",
    "expiryTime",
    "gmtCreate",
    "gmtModified",
)
# Known native configuration members only; no owners, contacts, notifications,
# action payloads, URLs, free text or arbitrary parameter maps.
CONDITION_FIELDS = frozenset(
    (
        "condition",
        "conditionLogical",
        "id",
        "order",
        "tntInstId",
        "gradeVOList",
        "gradeNo",
        "gradeSymbol",
        "maxValue",
        "minValue",
        "beginTime",
        "endTime",
        "calendarCode",
        "calendarConditionVos",
        "calendarType",
        "customCalendarId",
        "customeType",
        "days",
        "exclude",
        "followActionAccountType",
        "interval",
        "timePoint",
        "type",
    )
)
NESTED_FIELDS = frozenset(
    (
        "bizConditions",
        "preCheckCondtions",
        "ruleCheckCondtions",
        "timeConditions",
    )
)

TRANSFER_RULES = ListSpec(
    path=("rules", "transfer"),
    kind=SETTINGS,
    title="transfer rule configuration",
    endpoint="/transferRuleQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    require_inner_success=True,
    container=("result", "transferRuleVOS"),
    total=("result", "ruleCount"),
    identity=("ruleId",),
    pagination=PAGE_SINGLE,
    page_size=5000,
    template={
        "tntInstId": TENANT,
        "transferRuleQueryRequest": {
            "tntInstId": TENANT,
            "debitEntity": [],
            "creditEntity": [],
        },
    },
    vo_field="transferRuleQueryRequest",
    projection="transfer_rules",
    schema_version="transfer-rules-v1",
    table_columns=(
        "ruleId",
        "ruleNo",
        "ruleName",
        "version",
        "status",
        "debitEntity",
        "creditEntity",
        "paymentAmount",
    ),
    notes=(
        "One fixed GET inquiry: rowStart=0, pageSize=5000 and default empty "
        "entity arrays.",
        "Complete requires raw arrivals = unique ruleId count = native "
        "ruleCount; no offset fallback.",
        "ruleId is the native string identity; ruleNo and version remain "
        "separate source fields.",
        "Configuration summary only; genuine get and its detail cache "
        "remain independent.",
        "Unknown states, units, timezone, native precision, null, blank and "
        "zero remain raw.",
        "Effective and modification times describe configuration, never "
        "runtime observation.",
        "Nested conditions retain allowlisted configuration members; "
        "private fields and actions are omitted.",
    ),
)


_PRIVATE_VALUE = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|mailto:|\b[^\s@]+@[^\s@]+\.[^\s@]+)", re.I
)
_OMIT = object()


def _conditions(value: Any) -> Any:
    if isinstance(value, dict):
        if "tntInstId" in value and value["tntInstId"] != TENANT:
            raise CliError(
                INVALID_RESPONSE, "transfer rule condition tenant is outside scope"
            )
        projected = {}
        for key, item in value.items():
            if key in CONDITION_FIELDS:
                safe = _conditions(item)
                if safe is not _OMIT:
                    projected[key] = safe
        return projected
    if isinstance(value, list):
        return [safe for item in value if (safe := _conditions(item)) is not _OMIT]
    if isinstance(value, str) and _PRIVATE_VALUE.search(value):
        return _OMIT
    return value


def project_transfer_rule(row: dict[str, Any]) -> dict[str, Any]:
    """Preserve source configuration values; validate only identity and tenant."""
    identity = row.get("ruleId")
    if not isinstance(identity, str) or not identity.strip():
        raise CliError(
            INVALID_RESPONSE, "transfer rule ruleId must be a nonempty string"
        )
    if "tntInstId" in row and row["tntInstId"] != TENANT:
        raise CliError(INVALID_RESPONSE, "transfer rule tenant is outside query scope")
    projected = {}
    for field in FIELDS:
        if field in row:
            value = row[field]
            if field in NESTED_FIELDS:
                value = _conditions(value)
            elif (
                field in {"ruleName", "title"}
                and isinstance(value, str)
                and _PRIVATE_VALUE.search(value)
            ):
                value = _OMIT
            if value is not _OMIT:
                projected[field] = value
    return projected
