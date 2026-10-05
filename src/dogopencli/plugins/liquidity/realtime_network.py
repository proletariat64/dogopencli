"""Native settings list contract for issue #104; observed 2026-10-05."""

from typing import Any

from ...errors import INVALID_RESPONSE, CliError
from ...jsonutil import canonical
from .spec import ENV_SUCCESS, PAGE_SINGLE, PROFILE_SNAPSHOT, SETTINGS, ListSpec

FIELDS = (
    "id",
    "routeId",
    "version",
    "scene",
    "fundAction",
    "debitAliasName",
    "debitBankId",
    "debitCurrency",
    "debitLegalEntityCode",
    "creditAliasName",
    "creditBankId",
    "creditCurrency",
    "creditLegalEntityCode",
    "clearingNetworkName",
    "clearingNetworkType",
    "networkStatus",
    "runStatus",
    "processStatus",
    "operationCalendar",
    "operationDateType",
    "operationTime",
    "operationTool",
    "singlePaymentLimit",
    "timeZone",
    "gmtCreate",
    "gmtModified",
)
# Only id's type is required by the reading protocol. Optional configuration
# values stay native; this is a sampled description, not business validation.
SAMPLED_FIELDS = dict.fromkeys(FIELDS, "unknown")
SAMPLED_FIELDS["id"] = "str"

REALTIME_NETWORK = ListSpec(
    path=("network", "realtime"),
    kind=SETTINGS,
    title="realtime decision network configuration",
    endpoint="/api/ai/decision/network/queryDecisionNetwork.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("id",),
    pagination=PAGE_SINGLE,
    page_size=5000,
    profile=PROFILE_SNAPSHOT,
    projection="realtime_network",
    schema_version="realtime-network-settings-v1",
    table_columns=(
        "id",
        "routeId",
        "debitCurrency",
        "creditCurrency",
        "networkStatus",
        "runStatus",
    ),
    notes=(
        "Exactly one JSON POST with rowStart=0 and pageSize=5000; no filters or "
        "offset collection.",
        "Complete requires arrivals = unique native id count = data.totalCount; "
        "future scopes beyond the fixed page capacity are not proven.",
        "Native id identifies a network; routeId is a separate route reference "
        "and version is configuration version.",
        "Native networkStatus/runStatus/processStatus are preserved without "
        "execution or availability guarantees.",
        "Settings only: dynamic effectiveness, success-rate and last-operation "
        "metrics, private text, owners and action payloads are excluded.",
        "Native configuration values, precision, unknown values, null, empty "
        "string and zero are preserved; missing units/timezone remain unknown.",
        "gmtCreate/gmtModified are source configuration times; fetched_at is "
        "capture time, neither guarantees business observation time.",
        "Source is the authorized Liquidity application; no tenant echo is "
        "inferred and no other network or detail inquiry is enabled.",
    ),
)


def validate_native_rows(rows: list[dict[str, Any]]) -> None:
    """Check native identity conflicts before stripping nonpublic fields."""
    seen: dict[str, str] = {}
    for row in rows:
        identity = row.get("id")
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_RESPONSE, "network id must be a nonempty native string"
            )
        content = canonical(row)
        if identity in seen and seen[identity] != content:
            raise CliError(
                INVALID_RESPONSE, "conflicting native network identity content"
            )
        seen[identity] = content


def project_network(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row[field] for field in FIELDS if field in row}
