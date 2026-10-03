"""Verified account-isolation configuration inquiry (issue #51)."""

from ...errors import INVALID_RESPONSE, CliError
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
from .. import EndpointContract, ParsedPage
from ..envelope import success_document
from .configuration import ERRORS, ConfigurationListCapability, validate_row


class AccountIsolationCapability(ConfigurationListCapability):
    request_filter_error = "backend isolation filters disabled"
    name = "collection.account_isolation.list"
    slug = "account-isolation"
    title = "collection account-isolation configuration"
    source_config_key = "collection_account_isolation"
    default_scope = "all"
    id_field = "id"
    filters = (
        ("opening-rule-id", "id"),
        ("business-line", "businessCategory"),
        ("business-region", "businessRegionScope"),
        ("customer-group", "customerTags"),
        ("scene-code", "sceneCode"),
        ("collection-region", "creditArea"),
        ("currency", "currency"),
        ("transaction-type", "regionType"),
    )
    table_columns = tuple(field for _, field in filters)
    contract = EndpointContract(
        method="POST",
        host="ifundcontrolprodops.alipay.com",
        path="/api/virtualAccountRuleConfig/search",
        page_size=1000,
        one_based=False,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
        fixed_body_values=(("pageNo", 0), ("pageSize", 1000)),
        single_page=True,
    )

    def parse_page(self, body: bytes) -> ParsedPage:
        document = success_document(body)
        data = document.get("data")
        if not isinstance(data, dict):
            raise CliError(INVALID_RESPONSE, "missing isolation page data")
        for key in ("pageNo", "pageSize", "totalCount", "totalPageNo"):
            if type(data.get(key)) is not int or data[key] < 0:
                raise CliError(INVALID_RESPONSE, f"invalid isolation pagination {key}")
        rows = data.get("businessDataList")
        number, size, total = data["pageNo"], data["pageSize"], data["totalCount"]
        if not isinstance(rows, list) or number != 0 or size != 1000:
            raise CliError(
                INVALID_RESPONSE, "invalid isolation list or pagination echo"
            )
        for row in rows:
            validate_row(row)
        # The observed totalPageNo remains zero even for nonempty scopes.
        # Coverage is established by row count and identity, not that field.
        return ParsedPage(rows, 0, 1000, total, 1 if rows else 0)


ACCOUNT_ISOLATION = AccountIsolationCapability()
ACQUISITION = (
    "Acquire one unfiltered pageNo=0/pageSize=1000, validate string IDs and "
    "deduplicate identical rows, then filter, lexical ID sort, window and project. "
    "Safe incomplete coverage warns; --require-complete rejects. No paging "
    "fallback; totalPageNo is not trusted."
)
MATCHING = (
    "Local exact case-sensitive whole-string filters: same-field OR, cross-field "
    "AND, * literal, missing/null never match. Comma-separated customerTags and "
    "currency are not split. Reject empty/whitespace-only input; never normalize."
)
LIST_NODE = BizNode(
    ("collection", "account-isolation", "list"),
    "List account-isolation configurations from cache or explicitly with --live.",
    options=(
        *(
            opt(
                flag.replace("-", "_"),
                f"Exact whole-string match on {field}.",
                "append",
            )
            for flag, field in ACCOUNT_ISOLATION.filters
        ),
        LIMIT,
        OFFSET,
        ALL,
        LIVE,
        *CACHE_FLAGS,
        FORMAT_TABLE,
        FIELDS,
    ),
    constraints=(CACHE_SEMANTICS, DISPLAY_WINDOW, ACQUISITION, MATCHING),
    effects_variants=QUERY_EFFECTS_VARIANTS,
    output=QUERY_OUTPUT,
    errors=ERRORS,
    examples=("dogopencli collection account-isolation list --all",),
    next=("dogopencli help refresh collection account-isolation",),
    handler="cmd_collection_account_isolation_list",
)
REFRESH_NODE = BizNode(
    ("refresh", "collection", "account-isolation"),
    "Atomically refresh the isolated account-isolation snapshot.",
    constraints=(
        ACQUISITION,
        "Requires authenticated CDP; only the local cache changes. No selectors. "
        "Safe incomplete results publish with a warning; strict mode and hard "
        "failures preserve the prior snapshot. Progress goes to stderr.",
    ),
    effects=dict(REFRESH_CDP_EFFECTS),
    output=REFRESH_OUTPUT,
    errors=ERRORS,
    examples=("dogopencli refresh collection account-isolation",),
    next=("dogopencli help collection account-isolation list",),
    handler="cmd_refresh_collection_account_isolation",
)
GROUP_NODE = BizNode(
    ("collection", "account-isolation"),
    "Account-isolation configuration inquiries.",
    next=("dogopencli help collection account-isolation list",),
)
