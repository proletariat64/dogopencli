"""Offline description for the collection VA capacity monitoring schema (#36)."""

from typing import Any

from ...annotations import schema_annotations
from ...helpspec import BizNode

_IDENTITY_STRINGS = {
    "ruleId": (
        "Stable row identity: the VA rule ID, unique and nonempty across the "
        "verified scope. Digit-only in every observation. --va-rule-id matches "
        "this field exactly."
    ),
    "bankAccountVaId": (
        "Bank-account VA rule identifier of the related bank-account rule; "
        "not unique across rows. --bank-va-rule-id matches this field exactly."
    ),
    "accountNo": "Account number; not unique across rows.",
    "id": (
        "Backend surrogate row ID; NOT unique across rows and never the row "
        "identity. Distinct from ruleId and bankAccountVaId."
    ),
}

_BUSINESS_STRINGS = {
    "bankAccountingEntityCode": (
        "Bank-account entity code (UI: Bank Account Entity Code)."
    ),
    "serviceAccountingEntityCode": "Legal entity code (UI: Legal entity code).",
    "financialInst": "Financial institution.",
    "currency": (
        "Currency code; server-side currency filtering was observed "
        "case-insensitive, but no CLI filter is exposed for it."
    ),
    "sceneCode": "Scene code.",
    "memo": "Free-text memo; may be empty.",
}

_COUNTERS = {
    "totalCount": (
        "Per-row total VA capacity counter. Shares its name with the response "
        "envelope's page total; the two are unrelated and stay distinct."
    ),
    "usedCount": "Used VA count.",
    "availableCount": (
        "Unused VA count; never derived by subtraction from other counters."
    ),
    "canAllocateCount": "Distributable VA count as reported; never derived.",
    "lastDayUseCount": (
        "Number of applications yesterday; day boundary and timezone unverified."
    ),
    "averageApplyCount": "Average applications; averaging period unverified.",
    "totalMaxUseCount": "Single-day peak applications; peak window unverified.",
    "warningCount": (
        "Number of warnings as reported; NOT the UI warning state and not a "
        "predicate for it."
    ),
    "warningDays": (
        "Warning days as reported; present and positive on rows of both "
        "warning states, so it does not reproduce the UI warning state."
    ),
    "canUseDays": (
        "Backend estimate of available days remaining; never recomputed or "
        "re-estimated locally."
    ),
}

_TIMESTAMPS = ("gmtCreate", "gmtModified")


def description(node: BizNode) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "ruleId": {
            "type": "string",
            "minLength": 1,
            "description": _IDENTITY_STRINGS["ruleId"],
        },
        **{
            name: {
                "x-observed-type": "string",
                "x-evidence": {"presence": "observed"},
                "description": text,
            }
            for name, text in _IDENTITY_STRINGS.items()
            if name != "ruleId"
        },
        **{
            name: {
                "x-observed-type": "string",
                "x-evidence": {"presence": "observed"},
                "description": text,
            }
            for name, text in _BUSINESS_STRINGS.items()
        },
        **{
            name: {
                "x-observed-type": "integer",
                "x-evidence": {"presence": "observed"},
                "description": text,
            }
            for name, text in _COUNTERS.items()
        },
        **{
            name: {
                "x-observed-type": "integer",
                "description": (
                    "Original business timestamp; epoch unit and timezone "
                    "remain unverified."
                ),
            }
            for name in _TIMESTAMPS
        },
    }
    record = {
        "type": "object",
        "required": ["ruleId"],
        "properties": properties,
        "additionalProperties": True,
    }
    return {
        "schema_version": 1,
        "data_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "x-annotation-vocabulary": schema_annotations(),
            "type": "array",
            "items": record,
        },
        "read_guide": {
            "scope": (
                "Collection VA capacity monitoring rows: one row per VA rule "
                "capacity/warning projection from the VA Capacity Monitoring "
                "menu. Not VA rules, bank-account VA rules, VA pools or "
                "individual VA accounts. Isolated "
                "collection.va.capacity.list:capacity:cdp cache; "
                "sources.collection_va_capacity kind=cdp."
            ),
            "filters": [
                "--bank-va-rule-id: local exact match on the bankAccountVaId "
                "row field; repeatable (OR), combines with other filters (AND).",
                "--va-rule-id: local exact match on the ruleId row identity; "
                "repeatable (OR), combines with other filters (AND).",
                "The UI warning state is deliberately not a filter: rows have "
                "no warning-state field and the server Y/N classification is "
                "volatile and not derivable from row counters.",
            ],
            "access_modes": {
                "cached": (
                    "Default reads only the local capacity snapshot; TTL "
                    "defaults to 72 hours. Stale remains readable unless "
                    "--require-fresh. Capacity counters are time-sensitive: "
                    "check meta.fetched_at and stale before acting on counts."
                ),
                "live": (
                    "Explicit read-only browser inquiry; never writes the "
                    "cache or falls back to it. Fetches the full unfiltered "
                    "scope before local filtering, sorting and windowing."
                ),
                "refresh": (
                    "refresh collection va capacity pages the verified "
                    "endpoint with pageSize=1000 until the first short page, "
                    "validates the final converged total against coverage and "
                    "unique ruleId identities, then atomically replaces only "
                    "the capacity namespace. Every failure — authentication, "
                    "refusal, malformed data, changing totals, duplicates, "
                    "lock or timeout — preserves the previous snapshot. Bare "
                    "refresh collection va still refreshes VA rules only."
                ),
            },
            "quality": [
                (
                    "Interim page totalCount is a backend running estimate "
                    "that only converges on the final page; mid-sweep totals "
                    "are never trusted. Beyond-end pages return a clean "
                    "zero-row success with the converged total."
                ),
                (
                    "Live counters can re-order rows between page queries; a "
                    "duplicate ruleId with changed content fails the "
                    "acquisition instead of merging."
                ),
                (
                    "A filtered query with no matching rows is a backend "
                    "failure envelope (success=false), not an empty success; "
                    "CLI filters are local over the acquired scope, so a "
                    "local nonmatch is simply an empty result."
                ),
                (
                    "complete is acquisition coverage, has_more is display "
                    "truncation, stale is cache age. Stable-ID sorting "
                    "precedes display windows: ASCII digit IDs numerically "
                    "with original-string tie-break, other IDs lexically "
                    "afterward."
                ),
            ],
            "evidence": (
                "docs/research/general/2026-09-26-collection-va-capacity-contract.md"
            ),
            "examples": [
                "dogopencli collection va capacity list --require-fresh",
                "dogopencli collection va capacity list --va-rule-id RULE_ID --limit 0",
                "dogopencli refresh collection va capacity",
            ],
        },
    }
