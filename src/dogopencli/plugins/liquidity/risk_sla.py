"""Issue #109 native risk SLA configuration summaries."""

from typing import Any

from ...errors import INVALID_RESPONSE, CliError
from .spec import ENV_SUCCESS, PAGE_SINGLE, SETTINGS, TENANT, ListSpec

FIELDS = (
    "slaConfigId",
    "riskEventType",
    "effectiveStatus",
    "processStatus",
    "version",
    "tntInstId",
    "gmtCreate",
    "gmtModified",
)

RISK_SLA = ListSpec(
    path=("risk", "sla"),
    kind=SETTINGS,
    title="risk SLA configuration summaries",
    endpoint="/api/risk/sla/slaConfigPageQuery.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("slaConfigId",),
    pagination=PAGE_SINGLE,
    page_size=5000,
    template={"rowStart": 0, "pageSize": 5000},
    projection="risk_sla",
    schema_version="risk-sla-list-v1",
    table_columns=(
        "slaConfigId",
        "riskEventType",
        "effectiveStatus",
        "processStatus",
        "version",
    ),
    notes=(
        "One inquiry-only JSON POST with exactly rowStart=0 and pageSize=5000; "
        "fixed values are enforced by the shared transport.",
        "Complete requires raw arrivals = unique slaConfigId = native totalCount; "
        "there is no offset fallback or additional detail inquiry.",
        "slaConfigId is the nonempty native string identity within the application "
        "tenant and source scope; version is a separate native string.",
        "Configuration summaries only; existing get and its detail cache remain "
        "independent. Rule arrays and notification recipients are excluded.",
        "Native statuses remain raw; no alert effectiveness or processing outcome "
        "is inferred. Unknown additive fields do not create missing pages.",
        "gmtCreate and gmtModified describe configuration source times; timezone "
        "and runtime observation age remain unknown. fetched_at is capture time.",
        "Explicit refresh publishes a settings snapshot; ordinary reads stay "
        "offline and live inquiry writes no cache and has no fallback.",
        "Safe partial results warn by default; --require-complete refuses them. "
        "Protocol, tenant and identity failures preserve the previous capture.",
    ),
)


def project_risk_sla(row: dict[str, Any]) -> dict[str, Any]:
    """Keep only public summary fields without interpreting business states."""
    identity = row.get("slaConfigId")
    if not isinstance(identity, str) or not identity.strip():
        raise CliError(
            INVALID_RESPONSE, "risk SLA slaConfigId must be a nonempty string"
        )
    if "tntInstId" in row and row["tntInstId"] != TENANT:
        raise CliError(INVALID_RESPONSE, "risk SLA tenant is outside application scope")
    version = row.get("version")
    if version is not None and not isinstance(version, str):
        raise CliError(INVALID_RESPONSE, "risk SLA version must be a native string")
    return {field: row[field] for field in FIELDS if field in row}
