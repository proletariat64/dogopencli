"""Offline payment-rule command contracts and field reading guides."""

from typing import Any

from ...annotations import schema_annotations
from ...helpspec import (
    ALL,
    CACHE_FLAGS,
    CACHE_SEMANTICS,
    DISPLAY_WINDOW,
    FIELDS,
    FORMAT_TABLE,
    LIMIT,
    LIVE,
    OFFSET,
    QUERY_EFFECTS_VARIANTS,
    QUERY_OUTPUT,
    REFRESH_CDP_EFFECTS,
    REFRESH_OUTPUT,
    BizNode,
    opt,
)
from .rules import CAPABILITIES, RuleListCapability

ERRORS = (
    "INVALID_ARGUMENT",
    "CONFIG_ERROR",
    "CACHE_MISS",
    "CACHE_STALE",
    "INCOMPLETE_RESULT",
    "AUTH_REQUIRED",
    "BROWSER_UNAVAILABLE",
    "LOCKED",
    "TIMEOUT",
    "BUSINESS_QUERY_FAILED",
    "INVALID_RESPONSE",
)
MATCHING = (
    "Local exact case-sensitive matching; same-field OR, cross-field AND, * literal. "
    "Declared string arrays match exact members. Missing/null never match; reject "
    "empty/whitespace input, do not normalize or split comma strings. "
    "Filter, identity sort, window, then project. Preserve all returned states."
)

BANK_MATCHING = (
    "Bank-switch filters select source nodes. Nested predicates must match the "
    "same requirement and same rule; target account/network must match the same target "
    "within that rule. Return the entire source node, including other child versions. "
    "Do not flatten or trim child arrays. Without nested filters empty nodes remain."
)


def observed(kind: str, text: str) -> dict[str, Any]:
    return {
        "x-observed-type": kind,
        "x-evidence": {"presence": "observed"},
        "description": text,
    }


def bank_schema() -> dict[str, Any]:
    target = {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "targetNodeCode": observed(
                "string", "Target account/node code; --target-account."
            ),
            "clearingNetworkList": {
                **observed(
                    "array", "Target networks; exact member for --target-network."
                ),
                "items": {"type": "string"},
            },
            "nodeInfoId": observed("string", "Raw target-node entry identity."),
            "restrictClearingNetwork": observed(
                "string", "Raw restriction marker; no boolean conversion."
            ),
        },
    }
    rule = {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            **{
                k: observed("string", text)
                for k, text in {
                    "ruleId": "Nested rule identity; not the source-row key.",
                    "version": "Raw rule version, retained without merging.",
                    "status": "Configuration state; --status, separate from audit.",
                    "currentSwitchPeriodCode": "Current switch phase; may be null.",
                    "switchStrategy": "Raw switch strategy.",
                    "switchRatio": "Raw ratio string; scale unverified.",
                }.items()
            },
            "ratioList": {
                "type": ["array", "null"],
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "targetNodeInfoList": {
                            "type": ["array", "null"],
                            "items": target,
                        }
                    },
                },
            },
        },
    }
    return {
        **observed(
            "array",
            "Requirements under one source node; entire nested records retained.",
        ),
        "type": ["array", "null"],
        "items": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "requirementId": observed("string", "Requirement identity."),
                "switchBankAccount": observed(
                    "string", "Source account, observed equal to parent switchNodeCode."
                ),
                "switchClearingNetwork": observed(
                    "string", "Source network; --source-network."
                ),
                "switchRuleVOList": {"type": ["array", "null"], "items": rule},
            },
        },
    }


def list_node(cap: RuleListCapability) -> BizNode:
    return BizNode(
        ("payment", "rules", cap.slug, "list"),
        f"List payment {cap.slug} configurations from cache or explicitly live.",
        options=(
            *(
                opt(flag.replace("-", "_"), f"Exact local match on {field}.", "append")
                for flag, field in cap.filters
            ),
            LIMIT,
            OFFSET,
            ALL,
            LIVE,
            *CACHE_FLAGS,
            FORMAT_TABLE,
            FIELDS,
        ),
        constraints=(
            CACHE_SEMANTICS,
            DISPLAY_WINDOW,
            MATCHING,
            *([BANK_MATCHING] if cap.slug == "bank-switch" else []),
            "One verified first page at size 1000 must cover totalCount "
            "with unique IDs. No fallback, detail, joins or mutations.",
        ),
        effects_variants=QUERY_EFFECTS_VARIANTS,
        output=QUERY_OUTPUT,
        errors=ERRORS,
        examples=(f"dogopencli {cap.command_path} list --all",),
        next=(f"dogopencli help refresh {cap.command_path}",),
        handler=f"cmd_payment_rules_{cap.slug.replace('-', '_')}_list",
    )


def refresh_node(cap: RuleListCapability) -> BizNode:
    return BizNode(
        ("refresh", "payment", "rules", cap.slug),
        f"Atomically refresh payment {cap.slug} configurations.",
        constraints=(
            "One unfiltered verified first page at size 1000; no selectors. "
            "Require rows=totalCount and unique IDs. Every failure preserves "
            "the prior snapshot. No partial publication or paging fallback.",
        ),
        effects=dict(REFRESH_CDP_EFFECTS),
        output=REFRESH_OUTPUT,
        errors=ERRORS,
        examples=(f"dogopencli refresh {cap.command_path}",),
        next=(f"dogopencli help {cap.command_path} list",),
        handler=f"cmd_refresh_payment_rules_{cap.slug.replace('-', '_')}",
    )


def groups(cap: RuleListCapability) -> tuple[BizNode, ...]:
    nodes = (BizNode(("payment", "rules", cap.slug), f"Payment {cap.slug} inquiries."),)
    if cap.slug == "same-bank-transfer":
        nodes += (
            BizNode(("payment", "rules"), "Read-only payment rule configurations."),
            BizNode(
                ("refresh", "payment", "rules"), "Refresh one payment rule capability."
            ),
        )
    return nodes


def description(node: BizNode) -> dict[str, Any]:
    cap = next(cap for cap in CAPABILITIES if cap.slug == node.path[2])
    properties: dict[str, Any] = {
        field: observed(
            "array" if field in cap.array_fields else "string",
            f"Raw configuration field; --{flag} matches "
            + (
                "an exact string-array member."
                if field in cap.array_fields
                else "the whole string locally."
            ),
        )
        for flag, field in cap.filters
    }
    for field in cap.array_fields:
        properties[field]["items"] = {"type": "string"}
    if cap.slug == "bank-switch":
        properties = {"fundNavigationNodeSwitchRequirementVOList": bank_schema()}
    elif cap.is_same_bank_transfer:
        properties.update(
            {
                "priority": observed(
                    "integer", "Raw evaluation priority; do not execute matching."
                ),
                "ruleTypeCode": observed("string", "Raw rule judgment type."),
                "debitClearingSystemMemberId": observed(
                    "string", "Payment-bank clearing member ID."
                ),
                "creditClearingSystemMemberIdPatterns": observed(
                    "array", "Receiving-bank match patterns; not executed by CLI."
                ),
            }
        )
    elif cap.slug == "cost-reduction":
        properties.update(
            {
                k: observed(
                    "integer",
                    "Raw allocation value; scaling and actual savings unverified.",
                )
                for k in ("ratio", "ratioBase")
            }
        )
    else:
        properties.update(
            {
                k: observed("string", "Raw retry configuration, never executed by CLI.")
                for k in ("exceptionRetryType", "autoRetryRule", "retryHoldTime")
            }
        )
    if cap.slug != "bank-switch":
        properties["auditStatus"] = {
            "description": "Approval state where present; "
            "distinct from configuration status."
        }
        for key in ("gmtCreate", "gmtModified"):
            properties[key] = observed(
                "integer", "Raw timestamp if present; unit/timezone unverified."
            )
    properties[cap.id_field] = {
        "type": "integer" if cap.is_same_bank_transfer else "string",
        "description": "Unique raw row identity. Numeric order for same-bank; "
        "lexical order for string identities. No version merging.",
    }
    return {
        "schema_version": 1,
        "data_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "x-annotation-vocabulary": schema_annotations(),
            "type": "array",
            "items": {
                "type": "object",
                "required": [cap.id_field],
                "properties": properties,
                "additionalProperties": True,
            },
        },
        "read_guide": {
            "scope": f"Independent {cap.name}:all:cdp snapshot; "
            f"sources.{cap.source_config_key} kind=cdp. List only, no detail or joins."
            + (
                " Group summaries, not verified complete historical rule versions."
                if cap.slug == "cost-reduction"
                else ""
            ),
            "filters": [MATCHING]
            + ([BANK_MATCHING] if cap.slug == "bank-switch" else [])
            + [f"--{f}: {k}" for f, k in cap.filters],
            "access_modes": {
                "cached": "Offline; TTL defaults to 72h. Inspect fetched_at/stale.",
                "live": "Complete acquisition; never writes cache or falls back.",
                "refresh": f"refresh {cap.command_path}; "
                f"{cap.page_key}={cap.first_page}/pageSize=1000 only. "
                "Atomic complete publication; every failure retains old data.",
            },
            "quality": [
                "Coverage must equal totalCount with unique identities, at most 1000. "
                "Null/missing lists and wrong echoes reject. A correctly echoed "
                "empty array is synthetic-only; no unfiltered empty production "
                "scope observed.",
                "Unknown fields, nested values and missing/null/zero distinctions "
                "remain raw. "
                "Closed enums, timestamp units/timezones and ratio scaling "
                "are unverified. "
                "Configurations do not prove actual execution or savings.",
            ],
            "evidence": "docs/research/payment/2026-09-27-payment-rules-contract.md",
            "examples": [f"dogopencli {cap.command_path} list --all"],
        },
    }
