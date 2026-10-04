"""Genuine risk detail contracts, independently verified for events and alerts."""

from collections.abc import Mapping
from typing import Any

from ...errors import INVALID_RESPONSE, CliError
from .risk_batch import FIELDS, project_risk_record
from .spec import ENC_FORM, ENV_SUCCESS, RUNTIMES, DetailSpec, IdentityOption

DETAIL_FIELDS = (
    *FIELDS,
    "groupNo",
    "riskType",
    "notificationFrequency",
    "riskPendingEndTime",
    "treatmentRiskSourceObject",
)


def _spec(resource: str, mode: str) -> DetailSpec:
    return DetailSpec(
        path=("risk", resource),
        action="get",
        kind=RUNTIMES,
        title=f"risk {resource} detail",
        endpoint="/api/risk/event/detail.json",
        method="POST",
        encoding=ENC_FORM,
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "risk_event_id",
                "riskEventId",
                "Native id from the corresponding risk list; never groupNo.",
                echo="id",
            ),
        ),
        tenant_field=False,
        list_leaf=("risk", resource),
        projection=f"risk_{resource}_detail",
        schema_version="risk-detail-v1",
        table_columns=("id", "riskMode", "riskEvent", "riskStatus"),
        notes=(
            f"Genuine form POST detail; response id must equal --risk-event-id "
            f"and riskMode must equal {mode}.",
            "Only riskEventId is sent; tenant GUAPW3SG and mode isolate the "
            "detail cache without invented request fields.",
            "groupNo is the native grouping reference, riskType the source "
            "type code; neither replaces id.",
            "notificationFrequency is the native notification frequency string "
            "(minutes in the UI); riskPendingEndTime preserves the source "
            "pending end time string, including empty values.",
            "treatmentRiskSourceObject retains only native riskSourceObject "
            "references; operator/owner identities and private free text are "
            "excluded.",
            "This single detail response does not acquire or claim "
            "completeness of separately paginated sub-events or treatment "
            "history.",
            "Refresh updates only this object in the independent detail store; "
            "offline misses require explicit detail refresh; live does not "
            "write cache.",
        ),
    )


RISK_DETAIL_SPECS = (_spec("events", "RISK_EVENT"), _spec("anomalies", "RISK_ALERT"))


def project_risk_detail(row: Any, mode: str) -> dict[str, Any]:
    result = project_risk_record(row, mode)
    for field in ("groupNo", "riskType", "notificationFrequency", "riskPendingEndTime"):
        if field not in row or not isinstance(row[field], str):
            raise CliError(
                INVALID_RESPONSE, f"risk detail {field} must be a native string"
            )
        result[field] = row[field]
    objects = row.get("treatmentRiskSourceObject")
    if not isinstance(objects, list):
        raise CliError(
            INVALID_RESPONSE, "risk detail treatmentRiskSourceObject must be a list"
        )
    projected = []
    for item in objects:
        if not isinstance(item, Mapping) or not isinstance(
            item.get("riskSourceObject"), str
        ):
            raise CliError(
                INVALID_RESPONSE,
                "risk detail treatment source must have a native riskSourceObject "
                "string",
            )
        projected.append({"riskSourceObject": item["riskSourceObject"]})
    result["treatmentRiskSourceObject"] = projected
    return result
