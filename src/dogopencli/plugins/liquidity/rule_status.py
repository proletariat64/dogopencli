"""Native transfer-rule run-overview records with an explicit trigger scope."""

import calendar
import sys
from datetime import datetime, timezone
from typing import Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from ...temporal import parse_iso_instant
from .decision_list import TIMESTAMP_FORMAT, validate_timestamp
from .spec import (
    ENV_RESULT_FLAG,
    PAGE_SINGLE,
    PROFILE_HISTORY,
    RUNTIMES,
    TENANT,
    ListSpec,
    ScopeOption,
)

FIELDS = {
    "id": "int",
    "ruleId": "str | int",
    "executeStatus": "str",
    "createdOrder": "str",
    "bizNo": "str",
    "orderStatus": "str",
    "expectTriggerTime": "int",
    "realTriggerTime": "int | null",
    "gmtCreate": "int",
    "gmtModified": "int",
}

RULE_STATUS = ListSpec(
    path=("operations", "rule-status"),
    kind=RUNTIMES,
    title="transfer rule run overview",
    endpoint="/queryTransferRulePreRunRecords.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    require_inner_success=True,
    container=("result", "data"),
    total=("result", "count"),
    identity=("id",),
    pagination=PAGE_SINGLE,
    profile=PROFILE_HISTORY,
    page_size=5000,
    template={
        "tntInstId": TENANT,
        "transferRuleRecordQueryRequesVO": {
            "tntInstId": TENANT,
            "queryDetailed": "false",
            "executeStatusList": [],
            "createdOrderList": [],
            "orderStatusList": [],
        },
    },
    vo_field="transferRuleRecordQueryRequesVO",
    scope_options=(
        ScopeOption(
            "trigger_from",
            "triggerStartTime",
            "Inclusive UTC expected-trigger lower bound YYYY-MM-DDTHH:mm:ssZ;"
            " explicit numeric offsets normalize to UTC. Deprecated legacy"
            " 'YYYY-MM-DD HH:mm:ss' is read as UTC.",
            required=True,
        ),
        ScopeOption(
            "trigger_to",
            "triggerEndTime",
            "Inclusive UTC expected-trigger upper bound YYYY-MM-DDTHH:mm:ssZ;"
            " explicit numeric offsets normalize to UTC. Deprecated legacy"
            " 'YYYY-MM-DD HH:mm:ss' is read as UTC.",
            required=True,
        ),
    ),
    projection="rule_status",
    schema_version="rule-status-v1",
    table_columns=(
        "id",
        "ruleId",
        "executeStatus",
        "createdOrder",
        "bizNo",
        "orderStatus",
        "expectTriggerTime",
        "realTriggerTime",
    ),
    notes=(
        "Summary TransferRunOverview records only; expanded queryDetailed"
        " records and getters stay unsupported.",
        "Both UTC expected-trigger bounds are required; equal endpoints select"
        " one exact second.",
        "One fixed-width 5000 response; reported totals above 5000, count or"
        " identity mismatches and duplicate native IDs are rejected before"
        " output or publication; narrow the trigger range instead of paging.",
        "The populated 30-row paging experiment is unstable (194 arrivals,"
        " 193 unique IDs) and is never used.",
        "Native id is the positive-integer record identity, preserved without"
        " float precision loss; ruleId, bizNo and order references are not"
        " identity.",
        "executeStatus, createdOrder and orderStatus stay raw native values;"
        " empty payment references are valid non-payment records.",
        "Trigger timestamps are integer epoch milliseconds rendered UTC by"
        " the native UI; null realTriggerTime stays null.",
        "debitAmount units are unestablished; amounts, account aliases,"
        " rule-name/business-type free text, operators and environment"
        " metadata are excluded.",
        "Exact trigger scopes retain separate history captures; failures"
        " never replace caches with empty data.",
    ),
)


# Native trigger-time fields and their canonical public flags (Issue #127).
TRIGGER_FLAGS = {
    "triggerStartTime": "--trigger-from",
    "triggerEndTime": "--trigger-to",
}


def normalize_trigger_time(value: Any) -> tuple[str, bool]:
    """Known-UTC public datetime to the native UTC representation.

    Returns ``(normalized, legacy)``: preferred ISO 8601 second precision
    with ``Z`` or an explicit numeric offset normalizes to the existing
    ``YYYY-MM-DD HH:mm:ss`` UTC string; the offset-free space-separated form
    is retained as deprecated legacy-as-UTC. ``-00:00``, fractional seconds,
    leap seconds and missing offsets are rejected.
    """
    if isinstance(value, str) and "T" in value:
        instant = parse_iso_instant(value)
        return instant.astimezone(timezone.utc).strftime(TIMESTAMP_FORMAT), False
    validate_timestamp(value)
    return value, True


def validate_rule_status_query(values: dict[str, Any]) -> None:
    for field in ("triggerStartTime", "triggerEndTime"):
        try:
            normalized, legacy = normalize_trigger_time(values.get(field))
        except ValueError as error:
            raise CliError(
                INVALID_ARGUMENT,
                f"{field} ({TRIGGER_FLAGS[field]}) requires YYYY-MM-DDTHH:mm:ssZ"
                " or an explicit numeric offset (UTC)",
                exit_code=EXIT_USAGE,
            ) from error
        values[field] = normalized
        if legacy:
            print(
                f"warning: {TRIGGER_FLAGS[field]} uses the deprecated"
                " 'YYYY-MM-DD HH:mm:ss' UTC form; use YYYY-MM-DDTHH:mm:ssZ",
                file=sys.stderr,
            )
    if values["triggerStartTime"] > values["triggerEndTime"]:
        raise CliError(
            INVALID_ARGUMENT,
            "trigger time start is after its end",
            exit_code=EXIT_USAGE,
        )


def _epoch_ms(value: str) -> int:
    """Exact UTC epoch milliseconds of a validated native timestamp."""
    parsed = datetime.strptime(value, TIMESTAMP_FORMAT)
    return calendar.timegm(parsed.timetuple()) * 1000


def _require_epoch_ms(row: dict[str, Any], field: str, *, nullable: bool) -> None:
    value = row.get(field)
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CliError(
            INVALID_RESPONSE,
            f"rule status {field} must be positive epoch milliseconds",
        )


def project_rule_status(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("tntInstId") != TENANT:
        raise CliError(INVALID_RESPONSE, "rule status tenant is outside scope")
    identity = row.get("id")
    if isinstance(identity, bool) or not isinstance(identity, int) or identity <= 0:
        raise CliError(
            INVALID_RESPONSE, "rule status id must be a positive native integer"
        )
    rule_id = row.get("ruleId")
    if (
        rule_id is None
        or isinstance(rule_id, bool)
        or not isinstance(rule_id, (str, int))
        or (isinstance(rule_id, str) and not rule_id.strip())
    ):
        raise CliError(INVALID_RESPONSE, "rule status ruleId is missing or blank")
    for field in ("executeStatus", "createdOrder"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise CliError(INVALID_RESPONSE, f"rule status {field} is missing or blank")
    for field in ("bizNo", "orderStatus"):
        if not isinstance(row.get(field), str):
            raise CliError(
                INVALID_RESPONSE, f"rule status {field} must be a native string"
            )
    if "realTriggerTime" not in row:
        raise CliError(INVALID_RESPONSE, "rule status realTriggerTime is missing")
    _require_epoch_ms(row, "expectTriggerTime", nullable=False)
    _require_epoch_ms(row, "realTriggerTime", nullable=True)
    for field in ("gmtCreate", "gmtModified"):
        if field in row:
            _require_epoch_ms(row, field, nullable=False)
    return {field: row[field] for field in FIELDS if field in row}


def validate_rule_status_rows_scope(
    rows: list[dict[str, Any]], values: dict[str, Any]
) -> None:
    start = _epoch_ms(values["triggerStartTime"])
    end = _epoch_ms(values["triggerEndTime"]) + 999
    for row in rows:
        if not start <= row["expectTriggerTime"] <= end:
            raise CliError(
                INVALID_RESPONSE,
                "rule status expected trigger time is outside requested scope",
            )
