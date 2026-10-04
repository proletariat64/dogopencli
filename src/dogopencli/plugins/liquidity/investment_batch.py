"""Issue #89 investment inquiry contracts verified in the native UI."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from .spec import (
    ENV_SUCCESS,
    PROFILE_DATED,
    PROFILE_HISTORY,
    RUNTIMES,
    TENANT,
    ListSpec,
    ScopeOption,
)

VERSION = "investment-batch-c-v0.1"
TASK_TYPES = ("FUND_DECISION_TASK", "PRODUCT_DECISION_TASK")
SOURCE_ZONE = timezone(timedelta(hours=8))
BENCHMARK_IDENTITY = ("effectiveDate", "strategyBenchmarkType", "currency", "colorType")
BENCHMARK_FIELDS = ("id", *BENCHMARK_IDENTITY, "value")
BENCHMARK_VALUES = ListSpec(
    path=("investment", "benchmark-values"),
    kind=RUNTIMES,
    title="daily market interest benchmarks by fund nature, strategy and currency",
    endpoint="/queryStrategyBenchmarkList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=BENCHMARK_IDENTITY,
    profile=PROFILE_DATED,
    series_field="effectiveDate",
    series_format="%Y%m%d",
    page_size=10,
    template={"tntInstId": TENANT, "timeZone": "GMT+08"},
    scope_options=(
        ScopeOption(
            "from_date",
            "valueDateStart",
            "Inclusive effective day start (YYYYMMDD), native GMT+08.",
            required=True,
            date=True,
            window="from",
        ),
        ScopeOption(
            "to_date",
            "valueDateEnd",
            "Inclusive effective day end (YYYYMMDD), native GMT+08.",
            required=True,
            date=True,
            window="to",
        ),
    ),
    table_columns=("primaryId", *BENCHMARK_IDENTITY, "value"),
    projection="benchmark_values",
    schema_version="investment-benchmark-values-v2",
    notes=(
        "Native inquiry: JSON POST, fixed tenant GUAPW3SG and timeZone GMT+08, "
        "rowStart offsets of width 10, data.data and data.totalCount.",
        "The operator confirmed one daily market interest benchmark per fund "
        "nature (red/yellow/green), investment strategy (passive interest/tenor) "
        "and currency. Identity is (effectiveDate, strategyBenchmarkType, "
        "currency, colorType) within the tenant namespace; all 165 observed "
        "records have blank native id and distinct business identities.",
        "value is a native decimal string displayed with percent by the source "
        "UI. Preserve precision, null, blank and zero; do not scale or derive "
        "realized interest. value and capture time are not identity fields.",
        "valueDateStart/valueDateEnd bound the native effectiveDate (YYYYMMDD), "
        "not fetched_at. Dated captures preserve source coverage.",
        "Same-identity conflicting content within one acquisition is a hard "
        "failure. A later refresh may publish a revised value for that identity.",
        "primaryId is locally derived: bmv1 followed by tenant, effectiveDate, "
        "strategyBenchmarkType, currency and colorType, separated by colons. "
        "Each UTF-8 component is percent-encoded with only RFC 3986 unreserved "
        "characters left literal. Value, capture time and query window are "
        "excluded; native id is preserved and the four-field identity is unchanged.",
        "Only the six observed benchmark business fields and local primaryId "
        "enter public/cache records. The v2 cache contract requires refresh; "
        "existing v1 captures are retained. Strategy definitions and investment "
        "execution are separate.",
    ),
)
STRATEGY_FIELDS = (
    "id",
    "taskType",
    "triggerDate",
    "valueDate",
    "expectedInvestStartDate",
    "expectedInvestEndDate",
    "fundDecisionStrategyId",
    "investmentPortfolioStrategyId",
    "mainStrategyId",
    "investmentAmount",
    "maximumExceptedIncome",
    "maximumExpectedRateOfReturn",
    "taskStatus",
    "adoptionStatus",
    "triggerType",
    "resultTime",
)

FUND_RESULTS = ListSpec(
    path=("investment", "strategy-results"),
    kind=RUNTIMES,
    title="investment strategy results",
    endpoint="/api/increment/decision/task/queryPage.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("taskType", "id"),
    profile=PROFILE_HISTORY,
    page_size=10,
    template={"tntInstId": TENANT, "taskType": TASK_TYPES[0]},
    scope_options=(
        ScopeOption(
            "task_type",
            "taskType",
            "Explicit native decision task variant.",
            required=True,
            virtual=True,
            choices=TASK_TYPES,
            match=TASK_TYPES[0],
        ),
        ScopeOption(
            "trigger_from",
            "triggerStartDate",
            "Inclusive trigger day start (YYYYMMDD), native GMT+08.",
            required=True,
            date=True,
        ),
        ScopeOption(
            "trigger_to",
            "triggerEndDate",
            "Inclusive trigger day end (YYYYMMDD), native GMT+08.",
            required=True,
            date=True,
        ),
    ),
    table_columns=(
        "id",
        "taskType",
        "triggerDate",
        "valueDate",
        "investmentAmount",
        "taskStatus",
        "adoptionStatus",
    ),
    projection="strategy_results",
    schema_version=VERSION,
    notes=(
        "Native inquiry: JSON POST, fixed width 10, rowStart offsets and "
        "data.totalCount.",
        "Both task types have independently verified nonempty native evidence; "
        "--task-type is required.",
        "Native id identifies the decision task; strategy IDs are separate "
        "references. Identity is (taskType, id).",
        "Trigger bounds encode YYYY-MM-DD 00:00:00 and YYYY-MM-DD 23:59:59 in the"
        " native GMT+08 business day; triggerDate and resultTime are epoch "
        "milliseconds.",
        "valueDate and expectedInvestStartDate/expectedInvestEndDate are separate"
        " YYYYMMDD business dates; capture time is not business time.",
        "investmentAmount is labeled Investable Amount equi.USD in the native UI."
        " Preserve its source string; no local currency conversion is performed.",
        "maximumExceptedIncome retains native spelling; the product UI labels it "
        "Maximum Expected Interest Income equi.USD. Its fund variant unit and "
        "maximumExpectedRateOfReturn unit remain unverified.",
        "Raw taskStatus/adoptionStatus are retained. A strategy result does not "
        "prove investment execution or realized income.",
        "decisionUser, mainStrategyVo and unknown free-text fields are excluded "
        "from the public/cache projection.",
        "History captures preserve the exact task type and trigger-date scope; no"
        " local date filtering establishes source coverage.",
    ),
)
PRODUCT_RESULTS = replace(
    FUND_RESULTS,
    template={"tntInstId": TENANT, "taskType": TASK_TYPES[1]},
    scope_options=(
        replace(FUND_RESULTS.scope_options[0], match=TASK_TYPES[1]),
        *FUND_RESULTS.scope_options[1:],
    ),
)
CANDIDATES = (BENCHMARK_VALUES, FUND_RESULTS, PRODUCT_RESULTS)
# Both variants passed nonempty native collection and CLI UAT on CDP 9223.
# Final local checks, review and registered CLI UAT gate each release commit.
RELEASED: frozenset[str] = frozenset({BENCHMARK_VALUES.name, FUND_RESULTS.name})


def benchmark_primary_id(record: dict[str, Any]) -> str:
    """Encode the validated business identity for stable single-field references."""
    components = (TENANT, *(record[field] for field in BENCHMARK_IDENTITY))
    return "bmv1:" + ":".join(quote(component, safe="") for component in components)


def validate_business_date(value: Any) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 8
        or not value.isascii()
        or not value.isdigit()
    ):
        raise ValueError
    datetime.strptime(value, "%Y%m%d")


def validate_strategy_query(values: dict[str, Any]) -> None:
    if values["triggerStartDate"] > values["triggerEndDate"]:
        raise CliError(
            INVALID_ARGUMENT,
            "strategy trigger start is after its end",
            exit_code=EXIT_USAGE,
        )


def strategy_wire_dates(body: dict[str, Any]) -> None:
    for field, suffix in (
        ("triggerStartDate", "00:00:00"),
        ("triggerEndDate", "23:59:59"),
    ):
        body[field] = (
            datetime.strptime(body[field], "%Y%m%d").strftime("%Y-%m-%d") + " " + suffix
        )


def validate_strategy_rows_scope(
    rows: list[dict[str, Any]], values: dict[str, Any]
) -> None:
    for row in rows:
        if row["taskType"] != values["taskType"]:
            raise CliError(
                INVALID_RESPONSE, "decision task type is outside requested scope"
            )
        try:
            day = datetime.fromtimestamp(
                row["triggerDate"] / 1000, SOURCE_ZONE
            ).strftime("%Y%m%d")
        except (ValueError, OverflowError, OSError) as error:
            raise CliError(
                INVALID_RESPONSE,
                "decision triggerDate is outside supported timestamp range",
            ) from error
        if not values["triggerStartDate"] <= day <= values["triggerEndDate"]:
            raise CliError(
                INVALID_RESPONSE, "decision triggerDate is outside requested scope"
            )
