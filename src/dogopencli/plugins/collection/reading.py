"""Offline collection-cost evidence, independent of payment filter semantics."""

from typing import Any

from ...annotations import schema_annotations
from ...helpspec import BizNode
from .cost import COST_TYPE


def description(node: BizNode) -> dict[str, Any]:
    observed = {
        name: {
            "description": "Observed collection field; business "
            "interpretation remains unverified.",
            "x-evidence": {"presence": "observed", "meaning": "unknown"},
        }
        for name in (
            "bankAccountAliasName",
            "chargeBearer",
            "clearingNetworkName",
            "costCurrencyCode",
            "financialInst",
            "gmtCreate",
            "gmtModified",
            "isExistFvtAbility",
            "isFvt",
            "lastOperator",
            "legalEntity",
            "mappingCode",
            "status",
            "transCurrencyCode",
            "validStartTime",
            "validEndTime",
        )
    }
    observed["costRateConfigList"] = {
        "description": "Observed nested rate configurations. Preserve all "
        "original values, "
        "units and extensions; no fee computation or ratio conversion is verified.",
        "x-observed-type": "array",
        "items": {
            "properties": {
                "costRateVO": {
                    "x-observed-type": "object",
                    "properties": {
                        name: {
                            "x-evidence": {"presence": "observed", "meaning": "unknown"}
                        }
                        for name in (
                            "bottomAmount",
                            "topAmount",
                            "fixedAmount",
                            "feeRateRatioValue",
                            "costRateRangeList",
                        )
                    },
                    "additionalProperties": True,
                }
            },
            "additionalProperties": True,
        },
        "x-evidence": {"type": "observed", "presence": "observed", "unit": "unknown"},
    }
    return {
        "schema_version": 1,
        "data_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "array",
            "x-annotation-vocabulary": schema_annotations(),
            "items": {
                "type": "object",
                "required": ["itemId", "itemType"],
                "properties": {
                    **observed,
                    "itemId": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Configuration identifier; not a channel or "
                        "transaction ID.",
                    },
                    "itemType": {"const": COST_TYPE},
                },
                "additionalProperties": True,
            },
        },
        "read_guide": {
            "filters": [],
            "scope": "Fixed costTypeCode=" + COST_TYPE + "; no domain filters.",
            "access_modes": {
                "cached": "Default reads only the isolated collection cost cache.",
                "live": "--live uses the authenticated browser without "
                "cache writes or fallback.",
                "refresh": "dogopencli refresh collection cost atomically "
                "replaces only the local "
                "collection snapshot after complete validation; no "
                "production mutation.",
            },
            "quality": [
                "Acquisition is pageNo=0/pageSize=1000. This is an observed capacity, "
                "not a guaranteed backend maximum. Larger totals, "
                "duplicates, truncation "
                "or inconsistent metadata fail; no smaller-page fallback.",
                "complete describes backend coverage; has_more "
                "describes the display window. "
                "stale describes cache age. --require-fresh and "
                "--require-complete enforce "
                "these independent cache properties.",
                "Only success with totalCount=0 may omit "
                "resultDataList; null is invalid.",
            ],
            "interpretation": [
                "These are collection transaction-cost "
                "configurations, not actual charges.",
                "Preserve exact decimals, business timestamps, "
                "nested rates and unknown "
                "extensions. Observed fields are not mandatory or non-null guarantees. "
                "Unknown amount units, ratio scaling and enum meanings remain unknown.",
                "VA fees, VA pools/accounts, rules, SLA, signing "
                "and orders are excluded.",
                "Records sort by the existing numeric-string "
                "itemId convention. Different "
                "records and versions are never merged by "
                "institution, account or name.",
            ],
            "evidence": "docs/research/general/2026-09-23-collection-discovery.md",
            "examples": [
                "dogopencli collection cost list --all",
                "dogopencli collection cost list --live --fields itemId,itemType",
            ],
        },
    }
