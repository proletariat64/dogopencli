"""Offline contracts for verified PTR outflow inquiries."""

from typing import Any

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
from .ptr import CASES

MATCHING = (
    "Local exact case-sensitive whole-string matching. Same-field OR, cross-field "
    "AND; missing/null never match. No trimming, wildcard or comma expansion. "
    "Debtor account means alias. Baseline capabilities are not case input flags."
)
COVERAGE = (
    "Two complete pageNo=0/pageSize=5000 reads must have unique IDs, count=total "
    "and identical retained content. Reject overflow, drift and partial results. "
    "No paging fallback. Scope is current outflow case library, not all history."
)
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

LIST_NODE = BizNode(
    ("payment", "ptr", "cases", "list"),
    "List existing outflow PTR cases and last-verification summaries.",
    options=(
        *(
            opt(flag.replace("-", "_"), f"Exact local match on {field}.", "append")
            for flag, field in CASES.filters
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
        COVERAGE,
        "Only allowlisted fields are retained; personal data and unknown "
        "fields are omitted. No get, joins, test launch or result changes.",
    ),
    effects_variants=QUERY_EFFECTS_VARIANTS,
    output=QUERY_OUTPUT,
    errors=ERRORS,
    examples=("dogopencli payment ptr cases list --case-type NEGATIVE --all",),
    next=("dogopencli help refresh payment ptr cases",),
    handler="cmd_payment_ptr_cases_list",
)

REFRESH_NODE = BizNode(
    ("refresh", "payment", "ptr", "cases"),
    "Atomically refresh the complete current outflow PTR case library.",
    constraints=(
        COVERAGE,
        "Every failure retains the prior snapshot. "
        "No test execution, mutations or detail acquisition.",
    ),
    effects=dict(REFRESH_CDP_EFFECTS),
    output=REFRESH_OUTPUT,
    errors=ERRORS,
    examples=("dogopencli refresh payment ptr cases",),
    next=("dogopencli help payment ptr cases list",),
    handler="cmd_refresh_payment_ptr_cases",
)

GROUPS = (
    BizNode(("payment", "ptr"), "Query existing outflow production trial run data."),
    BizNode(("payment", "ptr", "cases"), "Outflow PTR case-library inquiries."),
    BizNode(("refresh", "payment", "ptr"), "Refresh a verified PTR query scope."),
)


def description(node: BizNode) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "data_schema": CASES.data_schema,
        "read_guide": {
            "scope": "Current endpoint-visible outflow-library; "
            "payment.ptr.cases.list:outflow-library:cdp. "
            "Configure sources.payment_ptr_cases kind=cdp. "
            "No deleted-record or version-history guarantee; list is not detail.",
            "filters": [MATCHING, *[f"--{f}: {k}" for f, k in CASES.filters]],
            "access_modes": {
                "cached": "Offline. Shared TTL defaults to 72h, a cache policy "
                "rather than a guarantee that verification summaries remain current.",
                "live": "Two complete reads; never publishes or falls back to cache.",
                "refresh": "Two complete reads; atomic publication, retaining the "
                "prior snapshot on any failure. Use refresh or live for current state.",
            },
            "quality": [
                COVERAGE,
                "Only the documented field projection is retained. Personal "
                "names, addresses, user IDs, IBAN/BIC, operators, free text and "
                "unknown properties are omitted, including nested properties.",
                "verifyResult is a test-verification summary, not payment success. "
                "Expected rejection can pass. OBO/FVT inputs and baseline support "
                "are separate raw strings. No closed enum or local adjudication.",
                "Full empty libraries, refusals and authentication expiry are "
                "synthetic coverage; not observed production outcomes.",
            ],
            "evidence": (
                "docs/research/payment/"
                "2026-09-27-payment-ptr-cases-accounts-contract.md"
            ),
            "examples": ["dogopencli payment ptr cases list --all"],
        },
    }
