"""Single-account operations inquiries from DemandsDetails (#191)."""

from typing import Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from .spec import (
    ENV_SUCCESS,
    PROFILE_DATED,
    RUNTIMES,
    DeferredLeaf,
    ListSpec,
    ScopeOption,
)

DATES = (
    ScopeOption(
        "from_date",
        "startDate",
        "Inclusive native start date YYYYMMDD.",
        required=True,
        date=True,
        window="from",
    ),
    ScopeOption(
        "to_date",
        "endDate",
        "Inclusive native end date YYYYMMDD.",
        required=True,
        date=True,
        window="to",
    ),
)
ACCOUNT_OPTIONS = (
    ScopeOption("alias", "aliasName", "One exact account alias.", required=True),
    ScopeOption("entity", "entity", "Account business entity; resolved if omitted."),
    ScopeOption("bank", "bankId", "Account bank; resolved if omitted."),
    *DATES,
)
ACCOUNT_DEMANDS = ListSpec(
    path=("forecast", "account_demands"),
    kind=RUNTIMES,
    title="account fund demands",
    endpoint="/passiveFundDemandList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("id",),
    profile=PROFILE_DATED,
    series_field="expectValueDate",
    series_format="%Y%m%d",
    scope_options=ACCOUNT_OPTIONS,
    page_size=5000,
    projection="account_demands",
    schema_version="account-demands-v1",
    table_columns=(
        "id",
        "aliasName",
        "entity",
        "bankID",
        "currency",
        "amount",
        "expectValueDate",
        "originalBizNo",
        "demandsStatus",
    ),
    notes=(
        "One account only; alias and both YYYYMMDD date bounds required online.",
        "Account context resolves from duckdog, cash accounts cache, then live.",
        "Fixed pageSize 5000; complete coverage requires an empty terminal probe.",
        "Demand status is not bank execution status; native times stay unchanged.",
        "Native date bounds select Expect Value Date; local date filtering uses it.",
    ),
)
ACCOUNT_CASHFLOWS = ListSpec(
    path=("forecast", "account_cashflows"),
    kind=RUNTIMES,
    title="account initiative cashflows",
    endpoint="/cashFlowList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=(
        "bankAccountAliasName",
        "bankAccountFlowDateSourceTypeStr",
        "originalBizNo",
        "expectValueDate",
        "expectValueTime",
        "currency",
    ),
    profile=PROFILE_DATED,
    series_field="expectValueDate",
    series_format="%Y%m%d",
    scope_options=ACCOUNT_OPTIONS,
    page_size=5000,
    projection="account_cashflows",
    schema_version="account-cashflows-v1",
    table_columns=(
        "bankAccountAliasName",
        "entity",
        "bankId",
        "currency",
        "amountStr",
        "expectValueDate",
        "originalBizNo",
        "status",
    ),
    notes=(
        "Single-account native Initiative Cashflow; not forecast cashflows or demands.",
        "Inclusive Expect Value Date range YYYYMMDD; native timezone stays sourced.",
        "Raw bankAccountFlowDateSourceType may be null;"
        " its Str field carries source code.",
        "Received Time UI uses receivedTime or gmtCreateStr;"
        " no receivedTime is synthesized.",
        "Composite source/account/business-number/value-date/time/currency identity was"
        " qualified across two dates; duplicate content conflicts are hard errors.",
        "Fixed native pageSize 5000, full acquisition plus empty terminal probe.",
    ),
)
ACCOUNT_T3 = ListSpec(
    path=("forecast", "account_t3"),
    kind=RUNTIMES,
    title="account T3 forecast demands",
    endpoint="/t3ForecastDemandList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=(
        "aliasName",
        "currency",
        "entity",
        "bankId",
        "forecastDate",
        "expectValueDate",
        "fundActionType",
        "dateFlag",
    ),
    profile=PROFILE_DATED,
    series_field="forecastDate",
    series_format="%Y%m%d",
    scope_options=(
        ScopeOption("account_alias", "aliasName", "One account alias.", required=True),
        *DATES,
    ),
    page_size=10,
    projection="account_t3",
    schema_version="account-t3-v1",
    table_columns=(
        "aliasName",
        "forecastDate",
        "expectValueDate",
        "currency",
        "amount",
        "fundActionType",
        "dateFlag",
    ),
    notes=(
        "Native T3 forecast dates select forecastDate, distinct from expectValueDate.",
        "Inclusive YYYYMMDD source calendar dates; timeZone is kept as sourced.",
        "Native pageSize 10 with rowStart; empty terminal proves full coverage.",
        "Business dimensions identify rows within this account/query scope;"
        " no fabricated id.",
    ),
)
ACCOUNT_LISTS = (ACCOUNT_DEMANDS, ACCOUNT_CASHFLOWS, ACCOUNT_T3)
ACCOUNT_PATHS = {item.path for item in ACCOUNT_LISTS}
CONTEXT_PATHS = {ACCOUNT_DEMANDS.path, ACCOUNT_CASHFLOWS.path}
DEMAND_FIELDS = (
    "id",
    "accountType",
    "localCrossBorder",
    "aliasName",
    "amount",
    "bankID",
    "bookId",
    "businessCategory",
    "businessEntity",
    "currency",
    "demandsStatus",
    "effectiveness",
    "entity",
    "expectValueDate",
    "expectValueTime",
    "fundActionType",
    "fundDirection",
    "originalBizNo",
    "receivedTime",
    "completionTime",
    "timezone",
)


def validate_account_query(values: dict[str, Any]) -> None:
    """Reject batch/blank values before directory or browser access."""
    for field in ("aliasName", "entity", "bankId"):
        value = values.get(field)
        if value is not None and (
            not isinstance(value, str)
            or not value.strip()
            or "," in value
            or value == "ANY"
        ):
            raise CliError(
                INVALID_ARGUMENT,
                f"{field} requires one nonempty value",
                exit_code=EXIT_USAGE,
            )


def project_account_demand(row: dict[str, Any]) -> dict[str, Any]:
    for field in DEMAND_FIELDS:
        value = row.get(field)
        if value is not None and not isinstance(value, str):
            raise CliError(INVALID_RESPONSE, f"account demand {field} must be a string")
    return {field: row[field] for field in DEMAND_FIELDS if field in row}


def validate_account_rows(rows, values):
    for row in rows:
        for field, native in (
            ("aliasName", "aliasName"),
            ("entity", "entity"),
            ("bankId", "bankID"),
        ):
            if values.get(field) is not None and row.get(native) != values[field]:
                raise CliError(
                    INVALID_RESPONSE, f"account demand {native} outside scope"
                )
        day = row.get("expectValueDate")
        if (
            not isinstance(day, str)
            or not values["startDate"] <= day <= values["endDate"]
        ):
            raise CliError(INVALID_RESPONSE, "account demand value date outside scope")


T3_FIELDS = (
    "accountType",
    "aliasName",
    "amount",
    "bankId",
    "currency",
    "dateFlag",
    "entity",
    "expectValueDate",
    "forecastDate",
    "fundActionType",
    "gmtCreate",
    "inflowAmount",
    "outflowAmount",
    "timeZone",
)
CASHFLOW_FIELDS = (
    "accountType",
    "amount",
    "amountStr",
    "bankAccountAliasName",
    "bankAccountFlowDateSourceType",
    "bankAccountFlowDateSourceTypeStr",
    "bankId",
    "currency",
    "entity",
    "expectValueDate",
    "expectValueDateTime",
    "expectValueTime",
    "fundDirection",
    "originalBizNo",
    "gmtCreate",
    "gmtCreateStr",
    "gmtModified",
    "gmtModifiedStr",
    "status",
    "extBizType",
    "subBizType",
    "timeZone",
    "receivedTime",
)


def project_account_record(name, row):
    if name == "account_demands":
        return project_account_demand(row)
    fields = T3_FIELDS if name == "account_t3" else CASHFLOW_FIELDS
    for field in fields:
        value = row.get(field)
        if field == "amount" and name == "account_cashflows":
            if value is not None and not isinstance(value, dict):
                raise CliError(
                    INVALID_RESPONSE, "cashflow amount must be a native object"
                )
        elif (
            field not in ("gmtCreate", "gmtModified", "bankAccountFlowDateSourceType")
            and value is not None
            and not isinstance(value, str)
        ):
            raise CliError(INVALID_RESPONSE, f"{name} {field} must be a native string")
    return {field: row[field] for field in fields if field in row}


def validate_account_record_scope(name, rows, values):
    if name == "account_demands":
        return validate_account_rows(rows, values)
    alias = "bankAccountAliasName" if name == "account_cashflows" else "aliasName"
    for row in rows:
        if row.get(alias) != values.get("aliasName"):
            raise CliError(INVALID_RESPONSE, "account inquiry alias outside scope")
        for field in ("entity", "bankId"):
            if field in values and row.get(field) != values[field]:
                raise CliError(
                    INVALID_RESPONSE, f"account inquiry {field} outside scope"
                )


PENDING = (
    DeferredLeaf(
        ("forecast", "account_t0", "list"),
        RUNTIMES,
        "native-qualification-pending",
        "R06 F01: independent nonempty schema, identity and pagination unproved.",
    ),
    DeferredLeaf(
        ("forecast", "account_hours_max", "list"),
        RUNTIMES,
        "native-qualification-pending",
        "R06 F03: independent nonempty schema, identity and pagination unproved.",
    ),
    DeferredLeaf(
        ("forecast", "account_daily_max", "list"),
        RUNTIMES,
        "native-qualification-pending",
        "R06 F04: independent nonempty schema, identity and pagination unproved.",
    ),
)
