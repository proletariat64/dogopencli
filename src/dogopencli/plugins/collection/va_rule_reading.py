"""Offline description for the distinct collection VA rule schema."""

from typing import Any

from ...annotations import schema_annotations
from ...helpspec import BizNode
from .va_rule import DETAIL_FIELDS

ASSIGN_INFO_KEYS = (
    "assignCount",
    "assignFlows",
    "ruleVaTotal",
    "vaAssignAble",
    "vaAssigned",
    "vaImported",
    "vaRuleId",
    "vaUnused",
    "vaUsed",
)

_OBSERVED_STRINGS = (
    "assembleStrategy",
    "entity",
    "memo",
    "regionType",
    "ruleStatus",
)

_LIST_ONLY_STRINGS = (
    "aliasName",
    "bankAccountNo",
    "currency",
    "financialInst",
    "operator",
    "reconInst",
)


def _string_fields(names: tuple[str, ...]) -> dict[str, Any]:
    return {
        name: {"x-observed-type": "string", "x-evidence": {"presence": "observed"}}
        for name in names
    }


def description(node: BizNode) -> dict[str, Any]:
    is_detail = node.path[-1] == "get"
    shared: dict[str, Any] = {
        "vaRuleId": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Stable VA rule ID; never the numeric bankRuleId of the "
                "related bank-account VA rule."
            ),
        },
        "bankRuleId": {
            "x-observed-type": "number",
            "description": (
                "Numeric reference to a distinct bank-account VA rule "
                "object; not a VA rule ID and never accepted as one."
            ),
        },
        **_string_fields(_OBSERVED_STRINGS),
        "sceneCodes": {
            "x-observed-type": "array",
            "items": {"type": "string"},
            "x-evidence": {"presence": "observed"},
        },
    }
    list_only: dict[str, Any] = {
        **_string_fields(_LIST_ONLY_STRINGS),
        "countries": {
            "x-observed-type": "array",
            "items": {"type": "string"},
            "description": (
                "List-side country list; the detail uses the differently "
                "named creditAreas, never merged or renamed."
            ),
        },
        "supportMultiCurrency": {
            "x-observed-type": "boolean",
            "x-evidence": {"presence": "observed"},
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
    }
    detail_only: dict[str, Any] = {
        "clientEntity": {
            "x-observed-type": "string",
            "x-evidence": {"presence": "observed"},
        },
        "creditAreas": {
            "x-observed-type": "array",
            "items": {"type": "string"},
            "description": (
                "Detail-side area list; a different name from list "
                "countries, never merged or equated with it."
            ),
        },
        "assignInfo": {
            "x-observed-type": "object",
            "description": (
                "Observed VA assignment counters and flows; reading them "
                "never performs an assignment. Counters are raw display "
                "summaries, not inferred assignment state, and an empty "
                "assignFlows list does not prove assignment history is empty "
                "because flow history semantics are unverified."
            ),
            "properties": {
                name: {"x-evidence": {"presence": "observed", "meaning": "unknown"}}
                for name in ASSIGN_INFO_KEYS
            },
            "additionalProperties": True,
        },
        "vaWarningInfo": {
            "x-observed-type": "object",
            "description": (
                "Optional warning/notification object; absent from some "
                "observed details, so it is never required. Contents stay "
                "raw; contact details never enter fixtures or examples."
            ),
            "additionalProperties": True,
        },
    }
    record = {
        "type": "object",
        "required": list(DETAIL_FIELDS) if is_detail else ["vaRuleId"],
        "properties": {**shared, **(detail_only if is_detail else list_only)},
        "additionalProperties": True,
    }
    schema = record if is_detail else {"type": "array", "items": record}
    return {
        "schema_version": 1,
        "data_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "x-annotation-vocabulary": schema_annotations(),
            **schema,
        },
        "read_guide": {
            "scope": (
                "Collection VA rules, not bank-account VA rules, VA pools or "
                "assigned VA accounts. Isolated "
                "temporary-query:collection.va.rules slot; "
                "sources.collection_va kind=cdp."
            ),
            "filters": [],
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
                        "refresh collection va collects only the list, never details. "
                        "Valid nonempty results atomically replace this slot; "
                        "empty refresh, hard failures and strict rejection preserve it."
                    ),
                    "prune": "Delete this leaf's slot; idempotent offline.",
                }
            ),
            "quality": [
                (
                    "One pageNo=1/pageSize=1000 complete-scope request; "
                    "larger totals, duplicate IDs, invalid metadata or "
                    "truncation fail. No unverified pagination fallback."
                ),
                (
                    "List rows and true details stay distinct raw objects. "
                    "List-only fields: aliasName, bankAccountNo, "
                    "financialInst, reconInst, currency, operator, "
                    "countries, supportMultiCurrency, gmtCreate, "
                    "gmtModified. Detail-only fields: assignInfo, "
                    "clientEntity, creditAreas, vaWarningInfo. List "
                    "countries and detail creditAreas keep different names "
                    "and are never merged."
                ),
                (
                    "vaWarningInfo is optional; not every observed detail "
                    "carries enumerable warning keys, so notification "
                    "content is never required."
                ),
                (
                    "The related bank-account VA rule detail "
                    "(bankAccountVaRule/detail.json), observed as "
                    "resultObj=null, is out of scope and never queried or "
                    "merged into a VA rule detail."
                ),
                (
                    "Null or invalid detail is INVALID_RESPONSE; backend "
                    "not-found semantics stay native, independent of list cache."
                ),
                (
                    "Stable-ID sorting precedes display windows: ASCII "
                    "digit IDs numerically with original-string tie-break, "
                    "other IDs lexically afterward. complete is acquisition "
                    "coverage, has_more is display truncation, stale is "
                    "cache age."
                ),
            ],
            "evidence": (
                "docs/research/general/"
                "2026-09-26-collection-va-rule-contract-recheck.md"
            ),
            "examples": [
                "dogopencli collection va rules list --limit 0",
                (
                    "dogopencli collection va rules get --id VA_RULE_ID "
                    "--fields vaRuleId,assignInfo"
                ),
            ],
        },
    }
