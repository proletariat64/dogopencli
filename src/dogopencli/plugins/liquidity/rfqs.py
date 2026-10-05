"""TARGET_RFQ subtask inquiries verified in issue #112 (2026-10-05)."""

from datetime import datetime
from typing import Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from .spec import (
    ENV_SUCCESS,
    PAGE_SINGLE,
    PROFILE_HISTORY,
    RUNTIMES,
    ListSpec,
    ScopeOption,
)

FIELDS = (
    "inquirySubTaskId",
    "inquiryTaskId",
    "inquiryType",
    "productType",
    "currency",
    "tenor",
    "redemptionFeature",
    "inquiryStatus",
    "quotationStatus",
    "winStatus",
    "quotedNum",
    "inquiryNum",
    "winNum",
    "inquiryStartTime",
    "inquiryEndTime",
    "modifyTime",
    "processStatus",
)
RFQS = ListSpec(
    path=("investment", "rfqs"),
    kind=RUNTIMES,
    title="bounded TARGET_RFQ inquiry subtasks",
    endpoint="/rfq/subInquiryTask/querySubInquiryTask.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    pagination=PAGE_SINGLE,
    identity=("inquirySubTaskId",),
    profile=PROFILE_HISTORY,
    page_size=5000,
    template={"rowStart": 0, "pageSize": 5000, "inquiryType": "TARGET_RFQ"},
    scope_options=(
        ScopeOption(
            "from_date",
            "inquiryStartDate",
            "Native inquiry-date start (YYYY-MM-DD); both bounds required.",
            required=True,
        ),
        ScopeOption(
            "to_date",
            "inquiryEndDate",
            "Native inquiry-date end (YYYY-MM-DD); both bounds required.",
            required=True,
        ),
    ),
    table_columns=(
        "inquirySubTaskId",
        "inquiryTaskId",
        "inquiryType",
        "currency",
        "tenor",
        "inquiryStatus",
        "quotationStatus",
        "winStatus",
    ),
    projection="rfq_subtasks",
    schema_version="rfq-target-subtasks-v1",
    notes=(
        "Only TARGET_RFQ is supported. FULL_RANGE_RFQ still fails upstream with 099; "
        "no alternate type, product, status, parent or subtask filters are exposed.",
        "One JSON POST fixes rowStart=0/pageSize=5000. Completeness requires raw "
        "arrivals = unique inquirySubTaskId = native data.totalCount. No offset "
        "paging, repeated acquisition or cross-type supplementation is verified.",
        "Both public YYYY-MM-DD dates map to native inquiryStartDate/inquiryEndDate "
        "YYYYMMDD. The exact type/date history scope never merges or falls back "
        "to another range. Native boundary semantics and source timezone are unknown.",
        "inquirySubTaskId is a nonempty native string identity within tenant, "
        "TARGET_RFQ and exact dates. inquiryTaskId is a parent reference; different "
        "subtasks sharing it remain distinct. No quote session is inferred.",
        "Counts, dates, times, currency, tenor and statuses remain native, including "
        "null, blank, zero, negative and unknown values. No count, date or financial "
        "arithmetic is performed; inquiry/quotation/win states do not prove execution.",
        "inquiryStartTime/inquiryEndTime/modifyTime are source fields, not fetched_at. "
        "Their timezone is unknown and does not inherit the investment quotes "
        "timezone. "
        "Unknown time interpretation is never used to filter or manufacture coverage.",
        "inquirer, memo, processId, personnel, free text and unknown fields are "
        "excluded from public and cache records. Existing quote and native "
        "detail caches stay separate.",
    ),
)
SAMPLED_FIELDS = {
    field: "int" if field in {"quotedNum", "inquiryNum", "winNum"} else "str"
    for field in FIELDS
}


def validate_rfq_query(values: dict[str, Any]) -> None:
    """Validate public date bounds without interpreting native source timestamps."""
    for field in ("inquiryStartDate", "inquiryEndDate"):
        value = values.get(field)
        try:
            if not isinstance(value, str) or not value.isascii():
                raise ValueError
            if datetime.strptime(value, "%Y-%m-%d").date().isoformat() != value:
                raise ValueError
        except ValueError as error:
            raise CliError(
                INVALID_ARGUMENT, f"{field} requires YYYY-MM-DD", exit_code=EXIT_USAGE
            ) from error
    if values["inquiryStartDate"] > values["inquiryEndDate"]:
        raise CliError(
            INVALID_ARGUMENT,
            "RFQ inquiry-date start is after its end",
            exit_code=EXIT_USAGE,
        )


def rfq_wire_dates(body: dict[str, Any]) -> None:
    """Map validated public bounds to the verified native request shape."""
    for field in ("inquiryStartDate", "inquiryEndDate"):
        body[field] = body[field].replace("-", "")


def project_rfq_subtask(record: dict[str, Any]) -> dict[str, Any]:
    """Only identity/type are asserted; preserve the allowlisted business values."""
    identity = record.get("inquirySubTaskId")
    if not isinstance(identity, str) or not identity.strip():
        raise CliError(
            INVALID_RESPONSE, "RFQ subtask identity requires a nonempty string"
        )
    if record.get("inquiryType") != "TARGET_RFQ":
        raise CliError(INVALID_RESPONSE, "RFQ inquiryType is outside TARGET_RFQ scope")
    return {field: record[field] for field in FIELDS if field in record}
