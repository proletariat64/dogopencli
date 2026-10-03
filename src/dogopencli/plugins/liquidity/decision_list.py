"""Bounded decision-list contract for issue #87; release remains gated."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from .spec import ENV_SUCCESS, PROFILE_HISTORY, RUNTIMES, TENANT, ListSpec, ScopeOption

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
VERSION = "decisions-list-v1"
VERIFIED_DATE = "2026-10-04"
STRING_FIELDS = (
    "reportId",
    "groupId",
    "orderNo",
    "reportStatus",
    "operationStatus",
    "status",
    "operationType",
    "decisionMode",
    "executionTimeStart",
    "executionTimeEnd",
    "gmtCreate",
    "gmtModified",
    "decisionCurrency",
    "decisionAmount",
    "debitEntity",
    "creditEntity",
    "debitAliasName",
    "creditAliasName",
    "debitBankId",
    "creditBankId",
    "debitCurrency",
    "creditCurrency",
    "debitAmount",
    "creditAmount",
    "debitValueDate",
    "creditValueDate",
    "strategyType",
    "needReview",
    "linkType",
    "assetTransactionType",
)
INTEGER_FIELDS = ("version", "genOrder", "timeliness")
SAMPLED_FIELDS = {
    "id": "int",
    "tntInstId": "str",
    **dict.fromkeys(STRING_FIELDS, "str"),
    **dict.fromkeys(INTEGER_FIELDS, "int"),
}

DECISIONS = ListSpec(
    path=("operations", "decisions"),
    kind=RUNTIMES,
    title="decision reports",
    endpoint="/api/ai/decision/report/getAllNew.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("id",),
    profile=PROFILE_HISTORY,
    page_size=10,
    template={"tntInstId": TENANT},
    scope_options=tuple(
        ScopeOption(
            flag, field, summary + " Format: YYYY-MM-DD HH:mm:ss.", required=True
        )
        for flag, field, summary in (
            (
                "start_from",
                "startTime",
                "Inclusive native Start Time range lower bound.",
            ),
            ("start_to", "endTime", "Inclusive native Start Time range upper bound."),
            (
                "created_from",
                "createStartTime",
                "Inclusive native Created Time range lower bound.",
            ),
            (
                "created_to",
                "createEndTime",
                "Inclusive native Created Time range upper bound.",
            ),
        )
    ),
    projection="decision_reports",
    schema_version=VERSION,
    table_columns=(
        "id",
        "reportId",
        "orderNo",
        "reportStatus",
        "decisionCurrency",
        "decisionAmount",
        "executionTimeStart",
        "gmtCreate",
    ),
    notes=(
        "Both native Start Time and Created Time ranges are required and inclusive.",
        "Start Time filters executionTimeStart; Created Time filters gmtCreate.",
        "Native timestamp strings pass through unchanged;"
        " no source timezone is inferred.",
        "Exact tenant and filter scope captures are retained independently;"
        " dates are not merged.",
        "Integer id identifies a report within this tenant; reportId, groupId"
        " and associated orderNo are separate identifiers.",
        "Amounts preserve native decimal strings without unit conversion;"
        " unknown statuses remain source values.",
        "Only allowed business fields are published; operators, account numbers,"
        " free text and nested detail data are excluded.",
    ),
)

# First release requires nonempty complete acquisition, production CLI UAT,
# automated checks and local Kimi review. Candidate tests do not waive this gate.
RELEASED: frozenset[str] = frozenset()


def validate_timestamp(value: Any) -> None:
    if not isinstance(value, str) or not value.isascii() or len(value) != 19:
        raise ValueError
    parsed = datetime.strptime(value, TIMESTAMP_FORMAT)
    if parsed.strftime(TIMESTAMP_FORMAT) != value:
        raise ValueError


def validate_decision_query(values: dict[str, Any]) -> None:
    for lower, upper in (
        ("startTime", "endTime"),
        ("createStartTime", "createEndTime"),
    ):
        for field in (lower, upper):
            try:
                validate_timestamp(values.get(field))
            except ValueError as error:
                raise CliError(
                    INVALID_ARGUMENT,
                    f"{field} requires YYYY-MM-DD HH:mm:ss",
                    exit_code=EXIT_USAGE,
                ) from error
        if values[lower] > values[upper]:
            raise CliError(
                INVALID_ARGUMENT, f"{lower} is after {upper}", exit_code=EXIT_USAGE
            )


def validate_decision_rows_scope(
    rows: list[dict[str, Any]], values: dict[str, Any]
) -> None:
    for row in rows:
        if row.get("tntInstId") != TENANT:
            raise CliError(INVALID_RESPONSE, "decision tenant is outside query scope")
        for field, lower, upper in (
            ("executionTimeStart", "startTime", "endTime"),
            ("gmtCreate", "createStartTime", "createEndTime"),
        ):
            value = row.get(field)
            try:
                validate_timestamp(value)
            except ValueError as error:
                raise CliError(
                    INVALID_RESPONSE, f"decision {field} is not a native timestamp"
                ) from error
            if not values[lower] <= value <= values[upper]:
                raise CliError(
                    INVALID_RESPONSE, f"decision {field} is outside requested range"
                )


def project_decision_record(row: dict[str, Any]) -> dict[str, Any]:
    if type(row.get("id")) is not int:
        raise CliError(INVALID_RESPONSE, "decision id must be a native integer")
    if row.get("tntInstId") != TENANT:
        raise CliError(INVALID_RESPONSE, "decision tenant is outside query scope")
    for field in STRING_FIELDS:
        if field in row and not isinstance(row[field], str):
            raise CliError(
                INVALID_RESPONSE, f"decision {field} must be a native string"
            )
    for field in INTEGER_FIELDS:
        if field in row and type(row[field]) is not int:
            raise CliError(
                INVALID_RESPONSE, f"decision {field} must be a native integer"
            )
    for field in ("decisionAmount", "debitAmount", "creditAmount"):
        if field not in row or row[field] == "":
            continue
        try:
            amount = Decimal(row[field])
            if not amount.is_finite():
                raise InvalidOperation
        except InvalidOperation as error:
            raise CliError(
                INVALID_RESPONSE, f"decision {field} is not a decimal string"
            ) from error
    return {field: row[field] for field in SAMPLED_FIELDS if field in row}
