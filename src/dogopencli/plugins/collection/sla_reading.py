"""Offline description for the distinct collection SLA configuration schema."""

from typing import Any

from ...annotations import schema_annotations
from ...helpspec import BizNode
from .sla import DETAIL_FIELDS, FILTER_FIELDS


def description(node: BizNode) -> dict[str, Any]:
    is_detail = node.path[-1] == "get"
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
            **(
                {
                    "type": ["object", "null"],
                    "required": ["currencyCodes", "regionCodes"],
                }
                if is_detail
                else {}
            ),
            "properties": {
                name: {
                    "x-observed-type": "array",
                    **({"type": "array"} if is_detail else {}),
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
        "required": ["slaConfigId", *(DETAIL_FIELDS if is_detail else ())],
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
                "temporary-query:collection.sla.configs slot; "
                "sources.collection_sla kind=cdp."
            ),
            "filters": (
                [
                    {
                        "option": f"--{flag}",
                        "field": field,
                        "semantics": (
                            "Repeatable nonempty exact case-sensitive local match "
                            "for cache and live; same-field OR, cross-field AND. "
                            "Literal * is not a wildcard. Missing/null does not "
                            "match. Whitespace-only values are rejected; no "
                            "trimming or normalization."
                        ),
                    }
                    for flag, field in FILTER_FIELDS.items()
                ]
                if node.path[-1] == "list"
                else []
            ),
            "access_modes": (
                {"online": "Native detail inquiry; never reads or writes query cache."}
                if is_detail
                else {
                    "cached": (
                        "Default replays this leaf's last nonempty acquisition. "
                        "Explicit declared filters select saved rows only; no implicit "
                        "refresh. TTL defaults to 72 hours."
                    ),
                    "live": (
                        "Read-only online list inquiry; no cache writes or fallback. "
                        "Local display filtering follows full native acquisition."
                    ),
                    "refresh": (
                        "refresh collection sla collects only the list, never details. "
                        "Valid nonempty results atomically replace this slot; "
                        "empty refresh, hard failures and strict rejection preserve it."
                    ),
                    "prune": "Delete this leaf's slot; idempotent offline.",
                }
            ),
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
                    "details. Each online detail validates its genuine native payload; "
                    "this is not a backend transactional snapshot."
                ),
                (
                    "Unknown business fields, numeric values and time values "
                    "are preserved. Detail requires all four selection fields, "
                    "both SLA targets and holidayLimit to be present. Explicit "
                    "null business values remain raw; a nonnull holidayLimit "
                    "requires both complete string arrays. Other observed types "
                    "do not imply mandatory presence or non-null guarantees."
                ),
                (
                    "Local filtering precedes stable ID sorting and display windows. "
                    "Backend businessCategory filtering is not claimed. complete is "
                    "acquisition coverage, has_more is display truncation, "
                    "stale is cache age."
                ),
            ],
            "evidence": "docs/research/general/2026-09-23-collection-sla-query.md",
            "examples": [
                "dogopencli collection sla configs list --limit 0",
                (
                    "dogopencli collection sla configs get --id CONFIG_ID "
                    "--fields slaConfigId,holidayLimit"
                ),
            ],
        },
    }
