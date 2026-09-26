"""Offline schema and reading boundaries for network configuration lists."""

from typing import Any

from ...annotations import schema_annotations
from ...helpspec import BizNode
from .network_config import CAPABILITIES

COMMON = {
    "supportedCountry": "Creditor bank location, preserved as its raw string code.",
    "supportedCurrency": "Collection currency. A literal * is a value, not a wildcard.",
    "status": "Raw configuration lifecycle state; no closed enum. UI offers INIT, "
    "AUDITING, REJECT, VALID and INVALID; preserve future values unchanged.",
    "creator": "Original configuration creator.",
    "lastOperator": "Last configuration operator.",
}
CLEARING = {
    "clearingNetworkType": "Clearing-system type, not the clearing-system name.",
    "clearingNetworkId": "Clearing-system name/code (UI clearingSystemName). "
    "--system-name matches this field; this is not the unique row id.",
    "routeCodeType": "Identifier-code name/type shown by the configuration UI.",
    "costLevel": "String cost classification; not a fee amount or rate.",
    "efficiencyLevel": "String speed classification; not measured latency or SLA.",
}
CARD = {
    "supportedFinancialInst": "Collection bank/institution code.",
    "templateName": "Card-template name; --template-name matches this row field. "
    "The native server filter is named cardTemplateName instead.",
    "templateType": "Raw template type; semantic vocabulary remains unverified.",
    "remark": "Original free-text remark, which may be empty.",
}


def description(node: BizNode) -> dict[str, Any]:
    cap = next(cap for cap in CAPABILITIES if cap.slug == node.path[1])
    strings = COMMON | (CLEARING if cap.slug == "clearing-system" else CARD)
    properties: dict[str, Any] = {
        "id": {
            "type": "string",
            "minLength": 1,
            "description": "Nonempty unique row identity, preserved as a string; "
            "lexical sorting retains leading zeros.",
        },
        **{
            field: {
                "x-observed-type": "string",
                "x-evidence": {"presence": "observed"},
                "description": text,
            }
            for field, text in strings.items()
        },
        **{
            field: {
                "x-observed-type": "integer",
                "description": "Raw business timestamp; epoch unit and timezone "
                "unverified.",
            }
            for field in ("gmtCreate", "gmtModified")
        },
    }
    if cap.slug == "card-template":
        properties["cardTemplateItemList"] = {
            "x-observed-type": "array",
            "description": "Empty in every observed list row; nested element schema "
            "is unverified. Future nested values are preserved; this list does not "
            "establish template-detail completeness.",
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
            "scope": f"One {cap.title} record per string id. Independent "
            f"{cap.name}:all:cdp snapshot; sources.{cap.source_config_key} kind=cdp. "
            "Card templates describe collection-information configuration, not "
            "payment-card records. No cross-object joins are performed.",
            "filters": [
                f"--{flag}: local exact string match on {field}."
                for flag, field in cap.filters
            ]
            + [
                "Repeated values OR; different fields AND. Case-sensitive, * "
                "literal, empty/whitespace-only input invalid, no normalization. "
                "Missing/null never match. Raw values need not belong to a closed enum."
            ],
            "access_modes": {
                "cached": "Default is offline. Check meta.fetched_at and stale; "
                "TTL defaults to 72 hours. Stale reads require no override unless "
                "--require-fresh is requested.",
                "live": "Explicit read-only full-scope query; never publishes or "
                "falls back. Filter, lexical ID sort, window, then project.",
                "refresh": f"refresh collection {cap.slug}: one unfiltered page, "
                "pageNo=1/pageSize=1000, unique IDs and rows=totalCount required. "
                "Only complete acquisitions atomically replace the local snapshot; "
                "failures preserve it. No multi-page fallback.",
            },
            "quality": [
                "Out-of-range pages clamp to page 1. Small-page clearing-system "
                "sweeps produced duplicate IDs; a verified single-page acquisition "
                "avoids this instability. A scope over 1000 fails explicitly.",
                "Confirmed empty shape: success=true, totalCount=0, empty list, "
                "pageSize=1000, pageNo=0 or 1. Other echoes or failures reject. "
                "An empty unfiltered production scope has not been observed.",
                "RelatedCardTemplate and RelatedBankVaAccountRule are separate "
                "UI actions, not observed list fields. No related data is fetched. "
                "accountCheckingLength was absent from observed clearing rows.",
                "Missing/null/zero/empty and unknown fields are preserved. "
                "complete measures acquisition, has_more display truncation, "
                "and stale snapshot age. Counts in reports are not invariants.",
            ],
            "evidence": (
                f"docs/research/general/2026-09-27-collection-{cap.slug}-contract.md"
            ),
            "examples": [
                f"dogopencli collection {cap.slug} list --currency GBP --all",
                f"dogopencli refresh collection {cap.slug}",
            ],
        },
    }
