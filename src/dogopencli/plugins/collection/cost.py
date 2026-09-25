"""Verified collection transaction-cost inquiry (issue #21).

One complete page at the observed capacity; no speculative pagination,
filters, VA fees or cost calculations.
"""

from dataclasses import dataclass
from typing import Any

from ...errors import INCOMPLETE_RESULT, INVALID_RESPONSE, REQUEST_NOT_ALLOWED, CliError
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
        identities = {row["itemId"] for row in page.records}
        if (
            page.total_count > PAGE_SIZE
            or len(page.records) != page.total_count
            or len(identities) != len(page.records)
        ):
            raise CliError(
                INCOMPLETE_RESULT,
                "collection cost response does not prove complete unique coverage; "
                "no pagination fallback is verified",
            )
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
        "Live results must prove complete unique coverage in one 1000-row request; "
        "otherwise fail without a fallback or cache update.",
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
