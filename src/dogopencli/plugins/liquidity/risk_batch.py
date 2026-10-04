"""Issue #88 risk inquiries verified against populated native UI responses."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from .spec import ENV_SUCCESS, PROFILE_HISTORY, RUNTIMES, TENANT, ListSpec, ScopeOption

VERSION = "risk-b-v1"
FIELDS = (
    "id",
    "riskMode",
    "gmtCreate",
    "gmtModified",
    "riskScenario",
    "riskCategory",
    "riskEvent",
    "riskStatus",
    "riskLevel",
    "riskAlertLevel",
    "riskObject",
    "riskSourceObject",
    "riskProcessingTime",
    "alertNum",
    "firstAlertTime",
    "nextAlertTime",
    "closeRiskTime",
)


def _risk_spec(resource: str, mode: str) -> ListSpec:
    return ListSpec(
        path=("risk", resource),
        kind=RUNTIMES,
        title=f"risk {resource}",
        endpoint="/api/risk/event/getAll.json",
        method="POST",
        envelope=ENV_SUCCESS,
        container=("data", "data"),
        total=("data", "totalCount"),
        identity=("id",),
        profile=PROFILE_HISTORY,
        page_size=10,
        template={"tntInstId": TENANT, "riskMode": mode, "timeZone": "GMT+08"},
        scope_options=(
            ScopeOption(
                "from_date",
                "startTime",
                "Native date-bound start (YYYYMMDD); pair with --to-date"
                " one day later.",
                required=True,
                date=True,
            ),
            ScopeOption(
                "to_date",
                "endTime",
                "Native date-bound end (YYYYMMDD), exactly one day after --from-date.",
                required=True,
                date=True,
            ),
        ),
        table_columns=("id", "gmtCreate", "riskEvent", "riskStatus", "riskAlertLevel"),
        projection=f"risk_{resource}",
        schema_version=VERSION,
        notes=(
            f"Inquiry-only JSON query with fixed native riskMode={mode}, tenant"
            " GUAPW3SG, timeZone=GMT+08 and rowStart/pageSize=10 pagination.",
            "Required adjacent date bounds are sent as native YYYY-MM-DD; the"
            " unbounded 90-day UI default has duplicate arrivals and is excluded.",
            "Native id is a nonempty string within the tenant, mode and request"
            " scope; events and anomalies retain separate caches.",
            "gmtCreate is native Risk Time; GMT+08 strings are preserved."
            " gmtModified, firstAlertTime, nextAlertTime and closeRiskTime are"
            " distinct source times. fetched_at records acquisition only.",
            "Native date filters are sent unchanged in meaning; timezone input"
            " did not change observed source times. Exact server boundary clock"
            " and inclusivity are unproven; displayed dates are not coverage.",
            "riskProcessingTime is the native UI's integer processing duration"
            " in minutes; alertNum retains the native integer counter.",
            "Native status and level codes stay open and unchanged; no local"
            " anomaly classification, severity mapping or risk score is computed.",
            "Only declared business fields are published; operators, free text,"
            " nested treatment/log records and unknown additive fields are excluded.",
            "History retains captures by fetched_at for each exact native date"
            " scope; it does not infer dated coverage from displayed timestamps.",
            "Repeated arrivals remain incomplete evidence. Validated partial"
            " rows warn by default; --require-complete refuses partial results."
            " Identity conflicts and total drift are hard failures.",
        ),
    )


RISK_EVENTS = _risk_spec("events", "RISK_EVENT")
RISK_ANOMALIES = _risk_spec("anomalies", "RISK_ALERT")
ACCEPTED_LIST_SPECS = (RISK_EVENTS, RISK_ANOMALIES)

# Sep 25-26 populated acquisition and isolated CLI UAT passed independently.
# Monitoring remains deferred; see the issue #88 evidence report for CI/review.
RELEASED: frozenset[str] = frozenset(spec.name for spec in ACCEPTED_LIST_SPECS)

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S（GMT+08）"
_TIME_FIELDS = (
    "gmtCreate",
    "gmtModified",
    "firstAlertTime",
    "nextAlertTime",
    "closeRiskTime",
)
_INTEGER_FIELDS = ("riskProcessingTime", "alertNum")


def validate_risk_query(values: Mapping[str, Any]) -> None:
    """Keep the evidenced native date request bounded to one day."""
    try:
        start = datetime.strptime(values["startTime"], "%Y%m%d")
        end = datetime.strptime(values["endTime"], "%Y%m%d")
    except (KeyError, TypeError, ValueError) as error:
        raise CliError(
            INVALID_ARGUMENT,
            "risk inquiries require valid --from-date and --to-date YYYYMMDD",
            exit_code=EXIT_USAGE,
        ) from error
    if end - start != timedelta(days=1):
        raise CliError(
            INVALID_ARGUMENT,
            "risk --to-date must be exactly one day after --from-date",
            exit_code=EXIT_USAGE,
        )


def risk_request_dates(body: dict[str, Any]) -> dict[str, Any]:
    """Translate validated CLI dates to the native UI's YYYY-MM-DD encoding."""
    validate_risk_query(body)
    return {
        **body,
        **{
            field: datetime.strptime(body[field], "%Y%m%d").strftime("%Y-%m-%d")
            for field in ("startTime", "endTime")
        },
    }


def project_risk_record(row: Any, mode: str) -> dict[str, Any]:
    """Publish the observed business fields, preserving native source values."""
    if not isinstance(row, Mapping):
        raise CliError(INVALID_RESPONSE, "risk record is not an object")
    identity = row.get("id")
    if not isinstance(identity, str) or not identity.strip():
        raise CliError(INVALID_RESPONSE, "risk id must be a nonempty native string")
    if row.get("riskMode") != mode:
        raise CliError(
            INVALID_RESPONSE, "risk record mode is outside the native query scope"
        )
    if not row.get("gmtCreate"):
        raise CliError(INVALID_RESPONSE, "risk record has no native Risk Time")
    for field in FIELDS:
        if field not in row:
            continue
        value = row[field]
        if field in _INTEGER_FIELDS:
            if isinstance(value, bool) or not isinstance(value, int):
                raise CliError(
                    INVALID_RESPONSE, f"risk {field} must be a native integer"
                )
        elif not isinstance(value, str):
            raise CliError(INVALID_RESPONSE, f"risk {field} must be a native string")
        if field in _TIME_FIELDS and value:
            try:
                parsed = datetime.strptime(value, _TIME_FORMAT)
                if parsed.strftime(_TIME_FORMAT) != value:
                    raise ValueError
            except (TypeError, ValueError) as error:
                raise CliError(
                    INVALID_RESPONSE,
                    f"risk {field} has an unverified native time format",
                ) from error
    return {field: row[field] for field in FIELDS if field in row}
