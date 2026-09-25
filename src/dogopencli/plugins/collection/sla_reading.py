"""Offline description for the distinct collection SLA configuration schema."""

from typing import Any

from ...annotations import schema_annotations
from ...helpspec import BizNode


def description(node: BizNode) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "slaConfigId": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Stable collection configuration ID; not payment slaBaselineId."
            ),
        },
        **{
            name: {"x-observed-type": "string", "x-evidence": {"presence": "observed"}}
            for name in (
                "businessCategory",
                "legalEntityCode",
                "creditorCurrency",
                "creditorRegion",
                "slaConfigStatus",
                "creator",
                "lastOperator",
            )
        },
        **{
            name: {
                "x-observed-type": "number",
                "description": (
                    "Raw SLA target in seconds; no zero substitution or "
                    "arrival-time calculation."
                ),
            }
            for name in ("endToEndSla", "ipayInnerSla")
        },
        **{
            name: {
                "x-observed-type": "number",
                "description": (
                    "Original business timestamp; epoch unit and timezone "
                    "remain unverified."
                ),
            }
            for name in ("gmtCreate", "gmtModified")
        },
        "holidayLimit": {
            "x-observed-type": "object",
            "properties": {
                name: {
                    "x-observed-type": "array",
                    "items": {"type": "string"},
                    "description": "Full array; calendar precedence is unknown.",
                }
                for name in ("currencyCodes", "regionCodes")
            },
            "additionalProperties": True,
        },
    }
    record = {
        "type": "object",
        "required": ["slaConfigId"],
        "properties": properties,
        "additionalProperties": True,
    }
    schema = record if node.path[-1] == "get" else {"type": "array", "items": record}
    return {
        "schema_version": 1,
        "data_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "x-annotation-vocabulary": schema_annotations(),
            **schema,
        },
        "read_guide": {
            "scope": (
                "Collection SLA configuration targets, not payment "
                "baselines or actual order performance. Isolated "
                "collection.sla.configs.list:configs:cdp cache; "
                "sources.collection_sla kind=cdp."
            ),
            "filters": [],
            "access_modes": {
                "cached": (
                    "Default reads only the local list/detail snapshot; TTL "
                    "defaults to 72 hours. Stale remains readable unless "
                    "--require-fresh."
                ),
                "live": (
                    "Explicit read-only browser inquiries never write cache "
                    "or fall back. Live get completeness covers the requested"
                    " detail only."
                ),
                "refresh": (
                    "refresh collection sla collects the full list and every "
                    "true detail, validates IDs/shared fields, then "
                    "atomically publishes. Any failure preserves the old "
                    "snapshot."
                ),
            },
            "quality": [
                (
                    "One pageNo=0/pageSize=1000 complete-scope request; "
                    "larger totals, duplicate IDs, invalid metadata or "
                    "truncation fail. No unverified pagination fallback."
                ),
                (
                    "Only explicit successful zero-total list is empty. "
                    "Invalid/null detail is INVALID_RESPONSE; backend not-"
                    "found semantics are unverified. A confirmed absent ID in"
                    " a complete local snapshot is NOT_FOUND."
                ),
                (
                    "List and detail remain distinct raw objects; list-only "
                    "viewProcessInstanceRequired was absent from observed "
                    "details. Shared-field mismatch rejects refresh; this is "
                    "not a backend transactional snapshot."
                ),
                (
                    "Unknown business fields, numeric values and time values "
                    "are preserved. Observed types do not imply mandatory "
                    "presence or non-null guarantees."
                ),
                (
                    "Stable ID sorting precedes display windows. complete is "
                    "acquisition coverage, has_more is display truncation, "
                    "stale is cache age."
                ),
            ],
            "evidence": "docs/research/general/2026-09-23-collection-sla-query.md",
            "examples": [
                "dogopencli collection sla configs list --all",
                (
                    "dogopencli collection sla configs get --id CONFIG_ID "
                    "--fields slaConfigId,holidayLimit"
                ),
            ],
        },
    }
