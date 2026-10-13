"""Offline account-isolation schema and evidence-aware reading guide."""

from typing import Any

from ...annotations import schema_annotations
from ...helpspec import BizNode
from .account_isolation import ACCOUNT_ISOLATION, ACQUISITION, MATCHING


def description(node: BizNode) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "id": {
            "type": "string",
            "minLength": 1,
            "description": "Opening-rule identity; unique nonempty string. "
            "Preserve long digit strings/leading zeros and sort lexically.",
        },
        **{
            field: {
                "x-observed-type": "string or null"
                if field == "businessCategory"
                else "string",
                "description": text,
            }
            for field, text in {
                "businessCategory": "Business line; observed null never matches.",
                "businessRegionScope": "Business region, not the collection region.",
                "customerTags": "Raw customer tags; comma-containing strings are "
                "matched as a whole, not split into groups.",
                "sceneCode": "Raw scene code.",
                "creditArea": "Collection region, distinct from business region.",
                "currency": "Raw collection currency string; comma lists and literal "
                "* are preserved. Exact whole-string matching, not membership.",
                "regionType": "Raw transaction type; no closed enum or normalization.",
                "businessEntity": "Raw business entity code.",
                "finInstCode": "Raw financial institution code.",
                "lastOperator": "Last configuration operator.",
            }.items()
        },
        **{
            field: {
                "x-observed-type": "integer",
                "description": "Raw business timestamp; units and timezone unverified.",
            }
            for field in ("gmtCreate", "gmtModified")
        },
    }
    return {
        "schema_version": 1,
        "data_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "x-annotation-vocabulary": schema_annotations(),
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id"],
                "properties": properties,
                "additionalProperties": True,
            },
        },
        "read_guide": {
            "scope": "One account-isolation opening-rule configuration per string id. "
            "Not a bank-account VA rule, VA account, inventory or balance. "
            "No detail, joins or relationship queries.",
            "filters": [MATCHING]
            + [
                f"--{flag}: exact whole-string match on {field}."
                for flag, field in ACCOUNT_ISOLATION.filters
            ],
            "access_modes": {
                "cached": "Offline isolated collection.account_isolation.list:all:cdp "
                "snapshot. Check fetched_at/stale; TTL defaults to 72h. "
                "Configure sources.collection_account_isolation kind=cdp.",
                "live": "Full verified acquisition, no cache writes or fallback. "
                "Filter, lexical ID sort, display window, then project.",
                "refresh": ACQUISITION + " Atomic complete publication only; "
                "any failure preserves the old snapshot. No selectors.",
            },
            "quality": [
                "Nonempty schema and complete scope were verified. totalPageNo "
                "was always zero; it is not a reliable page count.",
                "Confirmed filtered empty shape: success=true, data has null "
                "businessDataList and all four pagination fields zero. "
                "This filtered-only shape is rejected during unfiltered acquisition; "
                "a correctly echoed empty array is accepted synthetically.",
                "Backend customerTags/currency queries returned broader matches; "
                "CLI deliberately uses local whole-string equality, including commas.",
                "Unknown fields/nesting and missing/null/zero/empty remain raw. "
                "Acquisition completeness differs from display truncation and age.",
            ],
            "evidence": "docs/research/general/"
            "2026-09-27-collection-account-isolation-contract.md",
            "examples": [
                "dogopencli refresh collection account-isolation",
                "dogopencli collection account-isolation list --limit 0",
            ],
        },
    }
