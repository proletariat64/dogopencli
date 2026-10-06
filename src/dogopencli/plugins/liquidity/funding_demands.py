"""Native funding-demand tasks with an explicit execution-time scope."""

from decimal import Decimal, InvalidOperation
from typing import Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from .decision_list import validate_timestamp
from .spec import (
    ENV_RESULT_FLAG,
    PAGE_SINGLE,
    PROFILE_HISTORY,
    RUNTIMES,
    TENANT,
    ListSpec,
    ScopeOption,
)

FIELDS = dict.fromkeys(
    (
        "taskId",
        "tntInstId",
        "source",
        "sourceId",
        "instId",
        "bankId",
        "currency",
        "amount",
        "executeTime",
        "status",
        "instructionStatus",
        "riskActionType",
        "isNeedReview",
    ),
    "str",
)

DEMANDS = ListSpec(
    path=("operations", "demands"),
    kind=RUNTIMES,
    title="funding demand tasks",
    endpoint="/riskActionTaskQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    require_inner_success=True,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("taskId",),
    pagination=PAGE_SINGLE,
    profile=PROFILE_HISTORY,
    page_size=5000,
    template={
        "tntInstId": TENANT,
        "riskActionTaskQueryVO": {"tntInstId": TENANT, "source": ["FUND_REQUIRE"]},
    },
    vo_field="riskActionTaskQueryVO",
    scope_options=(
        ScopeOption(
            "execute_from",
            "startExecuteTime",
            "Inclusive native execution time lower bound (YYYY-MM-DD HH:mm:ss).",
            required=True,
        ),
        ScopeOption(
            "execute_to",
            "endExecuteTime",
            "Inclusive native execution time upper bound (YYYY-MM-DD HH:mm:ss).",
            required=True,
        ),
    ),
    projection="funding_demands",
    schema_version="funding-demands-v1",
    table_columns=(
        "taskId",
        "instId",
        "bankId",
        "currency",
        "amount",
        "executeTime",
        "status",
    ),
    notes=(
        "Inquiry-only FUND_REQUIRE source; both execution-time bounds are required.",
        "Native timestamps pass through without an inferred timezone.",
        "One fixed-width 5000 response; native totals above 5000 require a narrower"
        " execution-time scope and are rejected before output or publication.",
        "No offset loop; observed small-page overlaps are not used.",
        "taskId identifies tasks; sourceId identifies a separate associated source.",
        "Amounts preserve decimal strings; unknown statuses remain raw.",
        "Exact timestamp scopes retain separate history captures.",
        "Wide scopes can fail with 099; failures never replace caches with empty data.",
        "Account numbers, aliases, nested details and paging fields are excluded.",
    ),
)


def validate_demand_query(values: dict[str, Any]) -> None:
    for field in ("startExecuteTime", "endExecuteTime"):
        try:
            validate_timestamp(values.get(field))
        except ValueError as error:
            raise CliError(
                INVALID_ARGUMENT,
                f"{field} requires YYYY-MM-DD HH:mm:ss",
                exit_code=EXIT_USAGE,
            ) from error
    if values["startExecuteTime"] > values["endExecuteTime"]:
        raise CliError(
            INVALID_ARGUMENT,
            "execution time start is after its end",
            exit_code=EXIT_USAGE,
        )


def project_demand(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("tntInstId") != TENANT or row.get("source") != "FUND_REQUIRE":
        raise CliError(
            INVALID_RESPONSE, "funding demand tenant or source is outside scope"
        )
    for field in FIELDS:
        if field in row and not isinstance(row[field], str):
            raise CliError(
                INVALID_RESPONSE, f"funding demand {field} must be a native string"
            )
    for field in ("taskId", "currency", "amount", "executeTime"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise CliError(
                INVALID_RESPONSE, f"funding demand {field} is missing or blank"
            )
    try:
        if not Decimal(row["amount"]).is_finite():
            raise InvalidOperation
        validate_timestamp(row["executeTime"])
    except (InvalidOperation, ValueError) as error:
        raise CliError(
            INVALID_RESPONSE, "funding demand amount or execution time is invalid"
        ) from error
    return {field: row[field] for field in FIELDS if field in row}


def validate_demand_rows_scope(
    rows: list[dict[str, Any]], values: dict[str, Any]
) -> None:
    for row in rows:
        if (
            not values["startExecuteTime"]
            <= row["executeTime"]
            <= values["endExecuteTime"]
        ):
            raise CliError(
                INVALID_RESPONSE,
                "funding demand execution time is outside requested scope",
            )
