"""Offline help and schemas for bounded outflow PTR order inquiries."""

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
    filter_opt,
    scope_opt,
)
from .ptr_orders import ORDERS

WINDOW = (
    "Required --updated-from and --updated-to use YYYY-MM-DDTHH:MM:SS with an "
    "explicit numeric offset; +08:00 (UTC+08:00 Shanghai wall time) is "
    "preferred and other valid numeric offsets are accepted as equivalent "
    "instants, normalized to +08:00 before scope binding. "
    "No date-only values, Z, -00:00, fractional seconds or missing offsets. "
    "Require from < to, a span of at most 31 days, and to <= current time. "
    "The public interval is half-open: from <= gmtModified < to. "
    "gmtModified is integer epoch milliseconds; no default dates or all-history scope."
)
WINDOW_OPTIONS = (
    scope_opt(
        "updated_from",
        "Inclusive modification-time start, YYYY-MM-DDTHH:MM:SS with an explicit"
        " numeric offset (preferred +08:00).",
        value_type="datetime",
        preferred_format="YYYY-MM-DDTHH:mm:ss+08:00",
        accepted_formats=("YYYY-MM-DDTHH:mm:ss±hh:mm",),
        timezone="+08:00",
        constraints=(
            {"kind": "ordered-pair", "role": "lower"},
            {"kind": "max-elapsed-days", "days": 31},
            {"kind": "not-future"},
            {"kind": "half-open", "role": "inclusive"},
        ),
        required=True,
    ),
    scope_opt(
        "updated_to",
        "Exclusive modification-time end, YYYY-MM-DDTHH:MM:SS with an explicit"
        " numeric offset (preferred +08:00).",
        value_type="datetime",
        preferred_format="YYYY-MM-DDTHH:mm:ss+08:00",
        accepted_formats=("YYYY-MM-DDTHH:mm:ss±hh:mm",),
        timezone="+08:00",
        constraints=(
            {"kind": "ordered-pair", "role": "upper"},
            {"kind": "max-elapsed-days", "days": 31},
            {"kind": "not-future"},
            {"kind": "half-open", "role": "exclusive"},
        ),
        required=True,
    ),
)
MATCHING = (
    "Business filters are local exact case-sensitive whole-string matches after "
    "complete interval capture. Same-field OR, cross-field AND; missing/null "
    "never match. Blank arguments are rejected; no trimming, wildcard or comma "
    "expansion. Debtor account means alias, and payment currency is "
    "debtorAmount.currencyCode."
)
COVERAGE = (
    "Query native bounds padded by one second before from and after to, twice "
    "with pageNo=0/pageSize=500. Each padded response must be complete, echo "
    "the requested pagination, have count=total<=500, unique ptrOrderId values "
    "and an outflow baseline per row. Retained content must agree by ID across "
    "both reads. Only then apply the exact half-open interval locally, followed "
    "by business filters and output windows. Reject overflow, truncation and "
    "drift; no paging fallback or merging partial results."
)
RETENTION = (
    "Only the documented allowlisted projection is retained. Names, addresses, "
    "user IDs, actual account numbers, IBAN/BIC, creator/verifier identities, "
    "remarks and unknown properties are omitted, including nested properties. "
    "The retained failureReason is raw operational text and is not guaranteed "
    "PII-free."
)
STATE_GUIDE = (
    "orderStatus, verifyStatus and ptrFinalResult are distinct raw state "
    "dimensions. Expected payment rejection may pass verification. "
    "Per-capability verification results remain separate; no derived verdict "
    "or closed enum. ptrOrderId, caseId, allocateOrderId, finNetId and "
    "bizRequestId identify different objects. Baseline support flags are not "
    "OBO/FVT test inputs. spentTime and spentTimeInfoSource remain opaque "
    "native values without inferred units."
)
DEFERRED = (
    "No get: list rows are summaries, not verified independent details. "
    "Entity and batch-association filters are deferred because their returned "
    "fields are unverified. No joins, PTR launch, verification, approval, "
    "retry, result changes or export jobs."
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
EXAMPLE_WINDOW = (
    "--updated-from 2026-09-01T00:00:00+08:00 --updated-to 2026-09-02T00:00:00+08:00"
)

LIST_NODE = BizNode(
    ("payment", "ptr", "orders", "list"),
    "List existing outflow PTR orders in an explicit modification-time interval.",
    options=(
        *WINDOW_OPTIONS,
        *(
            filter_opt(
                flag.replace("-", "_"), f"Exact local match on {field}.", "append"
            )
            for flag, field in ORDERS.filters
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
        WINDOW,
        MATCHING,
        COVERAGE,
        RETENTION,
        STATE_GUIDE,
        DEFERRED,
    ),
    effects_variants=QUERY_EFFECTS_VARIANTS,
    output=QUERY_OUTPUT,
    errors=ERRORS,
    examples=(f"dogopencli payment ptr orders list {EXAMPLE_WINDOW} --all",),
    next=("dogopencli help refresh payment ptr orders",),
    handler="cmd_payment_ptr_orders_list",
)

REFRESH_NODE = BizNode(
    ("refresh", "payment", "ptr", "orders"),
    "Atomically refresh one explicit outflow PTR modification-time interval.",
    options=WINDOW_OPTIONS,
    constraints=(
        WINDOW,
        COVERAGE,
        RETENTION,
        "Each exact interval keeps its own latest successful snapshot. "
        "No automatic historical-window pruning. Every failure retains the "
        "previous snapshot for that same interval.",
        DEFERRED,
    ),
    effects=dict(REFRESH_CDP_EFFECTS),
    output=REFRESH_OUTPUT,
    errors=ERRORS,
    examples=(f"dogopencli refresh payment ptr orders {EXAMPLE_WINDOW}",),
    next=("dogopencli help payment ptr orders list",),
    handler="cmd_refresh_payment_ptr_orders",
)

GROUPS = (
    BizNode(
        ("payment", "ptr", "orders"),
        "Outflow PTR order inquiries with explicit modification-time bounds.",
    ),
)


def description(node: BizNode) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "data_schema": ORDERS.data_schema,
        "read_guide": {
            "scope": WINDOW,
            "namespace": (
                "payment.ptr.orders.list:updated:<from-ISO8601>:<to-ISO8601>:cdp. "
                "Equivalent instants normalize so both exact bounds retain "
                "literal +08:00. Configure "
                "sources.payment_ptr_orders kind=cdp. Different intervals never "
                "share a snapshot; --all expands only the requested interval."
            ),
            "filters": [MATCHING, *[f"--{f}: {k}" for f, k in ORDERS.filters]],
            "access_modes": {
                "cached": (
                    "Offline, using the latest successful snapshot for the exact "
                    "requested interval. Shared TTL defaults to 72h; this is a "
                    "cache policy, not a guarantee that dynamic orders stay current."
                ),
                "live": (
                    "Two complete padded reads, then exact local interval "
                    "selection; never publishes or falls back to cache."
                ),
                "refresh": (
                    "Two complete padded reads and atomic interval publication. "
                    "Failure retains the previous snapshot of the same interval. "
                    "No automatic historical-window pruning. Use live or refresh "
                    "for current state."
                ),
            },
            "quality": [
                COVERAGE,
                RETENTION,
                STATE_GUIDE,
                DEFERRED,
                "Native filtered empty intervals were observed; an entirely "
                "empty production resource was not. Business refusals, permission "
                "failures and authentication expiry use synthetic/shared "
                "transport coverage, not induced production outcomes.",
            ],
            "evidence": (
                "docs/research/payment/2026-09-27-payment-ptr-orders-contract.md"
            ),
            "examples": [f"dogopencli payment ptr orders list {EXAMPLE_WINDOW} --all"],
        },
    }
