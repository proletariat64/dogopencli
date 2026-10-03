"""Verified collection transaction-cost inquiry (issue #21).

One validated page at the observed capacity; no speculative pagination,
filters, VA fees or cost calculations.
"""

from dataclasses import dataclass
from typing import Any

from ...errors import INVALID_RESPONSE, REQUEST_NOT_ALLOWED, CliError
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
    REFRESH_CDP_CONSTRAINTS,
    REFRESH_CDP_EFFECTS,
    REFRESH_CDP_ERRORS,
    REFRESH_OUTPUT,
    BizNode,
)
from .. import EndpointContract, ParsedPage
from ..cost import TABLE_COLUMNS, parse_cost_page, sort_cost_records

COST_TYPE = "FUND_IN_CHANNEL_TRANS_FEE"
PAGE_SIZE = 1000
CONTRACT = EndpointContract(
    method="POST",
    host="iglobalfundcontrol.alipay.com",
    path="/api/fundCost/query.json",
    page_size=PAGE_SIZE,
    one_based=False,
    allowed_body_keys=frozenset({"costTypeCode", "pageNo", "pageSize"}),
    scope_field="itemType",
    single_page=True,
    fixed_body_values=(
        ("costTypeCode", COST_TYPE),
        ("pageNo", 0),
        ("pageSize", PAGE_SIZE),
    ),
)


@dataclass(frozen=True)
class CollectionCostCapability:
    name: str = "collection.cost.list"
    source_config_key: str = "collection_cost"
    default_scope: str = COST_TYPE
    contract: EndpointContract = CONTRACT
    id_field: str = "itemId"
    table_columns: tuple[str, ...] = TABLE_COLUMNS

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if scope != COST_TYPE or page_num != 0 or page_size != PAGE_SIZE:
            raise CliError(REQUEST_NOT_ALLOWED, "unverified collection cost request")
        return dict(CONTRACT.fixed_body_values)

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        if set(body) - CONTRACT.allowed_body_keys:
            raise CliError(
                REQUEST_NOT_ALLOWED, "collection cost filters are unverified"
            )
        return {}

    def filter_records(
        self, records: list[dict[str, Any]], filters: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        if filters:
            raise CliError(
                REQUEST_NOT_ALLOWED, "collection cost filters are unverified"
            )
        return records

    def sort_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sort_cost_records(records)

    def identity_key(self, record: dict[str, Any]) -> Any:
        return record.get(self.id_field)

    def parse_page(self, body: bytes) -> ParsedPage:
        page = parse_cost_page(body, COST_TYPE, allow_omitted_empty=True)
        if page.page_num != 0 or page.page_size != PAGE_SIZE or page.total_count < 0:
            raise CliError(INVALID_RESPONSE, "invalid collection cost pagination")
        return page


COLLECTION_COST_CAPABILITY = CollectionCostCapability()
COLLECTION_COST_LIST_NODE = BizNode(
    ("collection", "cost", "list"),
    "List collection transaction-cost configurations from cache or with --live.",
    options=(LIMIT, OFFSET, ALL, LIVE, *CACHE_FLAGS, FORMAT_TABLE, FIELDS),
    constraints=(
        "Fixed costTypeCode=FUND_IN_CHANNEL_TRANS_FEE; no "
        "domain filters or scope option.",
        "Cost configurations are not actual transaction charges or calculated fees.",
        "Live uses one verified 1000-row request. Safe incomplete coverage returns "
        "with a warning; --require-complete rejects. No pagination fallback.",
        CACHE_SEMANTICS,
        DISPLAY_WINDOW,
    ),
    effects_variants=QUERY_EFFECTS_VARIANTS,
    output=QUERY_OUTPUT,
    errors=(
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
    ),
    examples=(
        "dogopencli collection cost list",
        "dogopencli collection cost list --live",
    ),
    next=("dogopencli help refresh collection cost",),
    handler="cmd_collection_cost_list",
)


REFRESH_NODE = BizNode(
    effects=dict(REFRESH_CDP_EFFECTS),
    output=dict(REFRESH_OUTPUT),
    path=("refresh", "collection", "cost"),
    summary="Rebuild the collection transaction-cost cache "
    "through the existing CDP session.",
    constraints=(
        *REFRESH_CDP_CONSTRAINTS,
        "Fixed transaction-cost type; safe partial results publish with a warning; "
        "--require-complete rejects before publishing.",
        "Only the local cache changes; production business state remains read-only.",
    ),
    errors=(*REFRESH_CDP_ERRORS, "INCOMPLETE_RESULT"),
    examples=("dogopencli refresh collection cost",),
    next=("dogopencli help collection cost list",),
    handler="cmd_refresh_collection_cost",
)
