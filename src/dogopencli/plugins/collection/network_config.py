"""Verified collection network configuration snapshots (issues #41/#45)."""

from dataclasses import dataclass, field
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
    REFRESH_OUTPUT,
    BizNode,
    opt,
)
from .. import EndpointContract, ParsedPage
from ..envelope import success_document

PAGE_SIZE = 1000


def validate_row(row: Any) -> None:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("id"), str)
        or not row["id"].strip()
    ):
        raise CliError(
            INVALID_RESPONSE, "configuration row requires nonempty string id"
        )


@dataclass
class NetworkConfigCapability:
    slug: str
    title: str
    endpoint: str
    filters: tuple[tuple[str, str], ...]
    table_columns: tuple[str, ...]
    id_field: str = "id"
    default_scope: str = "all"

    name: str = field(init=False)
    source_config_key: str = field(init=False)
    contract: EndpointContract = field(init=False)

    def __post_init__(self) -> None:
        self.name = f"collection.{self.slug.replace('-', '_')}.list"
        self.source_config_key = f"collection_{self.slug.replace('-', '_')}"
        self.contract = EndpointContract(
            method="POST",
            host="ifundboss-api.alipay.com",
            path=f"/ivostro/api/{self.endpoint}/pageList.json",
            page_size=PAGE_SIZE,
            one_based=True,
            allowed_body_keys=frozenset({"pageNo", "pageSize"}),
            fixed_body_values=(("pageNo", 1), ("pageSize", PAGE_SIZE)),
        )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if scope != self.default_scope or page_num != 1 or page_size != PAGE_SIZE:
            raise CliError(
                REQUEST_NOT_ALLOWED, "only the verified first page is allowed"
            )
        return {"pageNo": 1, "pageSize": PAGE_SIZE}

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        if body != {"pageNo": 1, "pageSize": PAGE_SIZE}:
            raise CliError(
                REQUEST_NOT_ALLOWED, "backend configuration filters disabled"
            )
        return {}

    def filter_records(
        self, records: list[dict[str, Any]], filters: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in records
            if all(row.get(field) in values for field, values in filters.items())
        ]

    def sort_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(records, key=lambda row: row["id"])

    def identity_key(self, record: dict[str, Any]) -> str:
        return record["id"]

    def parse_page(self, body: bytes) -> ParsedPage:
        document = success_document(body)
        for key in ("pageNo", "pageSize", "totalCount"):
            if type(document.get(key)) is not int:
                raise CliError(INVALID_RESPONSE, f"invalid pagination field {key}")
        number, size, total = (
            document["pageNo"],
            document["pageSize"],
            document["totalCount"],
        )
        rows = document.get("resultDataList")
        if not isinstance(rows, list) or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid configuration scope")
        empty = total == 0 and not rows
        if size != PAGE_SIZE or (number != 1 and not (empty and number == 0)):
            raise CliError(INVALID_RESPONSE, "configuration pagination echo mismatch")
        for row in rows:
            validate_row(row)
        if total != len(rows) or total > PAGE_SIZE:
            raise CliError(
                INCOMPLETE_RESULT,
                "configuration exceeds verified single-page coverage; "
                "reverify the contract before expanding acquisition",
            )
        if len({row["id"] for row in rows}) != len(rows):
            raise CliError(INCOMPLETE_RESULT, "duplicate configuration identities")
        return ParsedPage(rows, number, size, total, 0 if empty else 1)


CLEARING_SYSTEM = NetworkConfigCapability(
    slug="clearing-system",
    title="collection clearing-system configuration",
    endpoint="clearingNetworkInfo",
    filters=(
        ("bank-location", "supportedCountry"),
        ("currency", "supportedCurrency"),
        ("system-type", "clearingNetworkType"),
        ("system-name", "clearingNetworkId"),
        ("status", "status"),
    ),
    table_columns=(
        "id",
        "supportedCountry",
        "supportedCurrency",
        "clearingNetworkType",
        "clearingNetworkId",
        "status",
        "costLevel",
        "efficiencyLevel",
    ),
)
CARD_TEMPLATE = NetworkConfigCapability(
    slug="card-template",
    title="collection card-template configuration",
    endpoint="cardTemplate",
    filters=(
        ("bank-location", "supportedCountry"),
        ("currency", "supportedCurrency"),
        ("bank", "supportedFinancialInst"),
        ("template-name", "templateName"),
        ("template-id", "id"),
        ("status", "status"),
    ),
    table_columns=(
        "id",
        "supportedCountry",
        "supportedCurrency",
        "supportedFinancialInst",
        "templateName",
        "status",
    ),
)
CAPABILITIES = (CLEARING_SYSTEM, CARD_TEMPLATE)

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


def list_node(cap: NetworkConfigCapability) -> BizNode:
    return BizNode(
        ("collection", cap.slug, "list"),
        f"List {cap.title} from cache or explicitly with --live.",
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
            "Local filters use exact case-sensitive strings, same-field OR and "
            "cross-field AND; * is literal, missing/null never match. Empty or "
            "whitespace-only values reject; valid values are never normalized.",
            "Acquire one unfiltered page (pageNo=1, pageSize=1000), require rows "
            "equal totalCount and unique nonempty string IDs, then filter, sort "
            "IDs lexically and apply display windows. Incomplete coverage fails; "
            "no multi-page fallback. Out-of-range backend pages clamp to page 1.",
            "Only list configuration data is covered. No detail or relationship "
            "queries; absent relationship fields are not fabricated. Unknown "
            "fields and nested values remain raw. Timestamp units are unverified.",
            "Check meta.fetched_at and stale: configuration snapshots age until "
            "explicit refresh; the configured TTL defaults to 72 hours.",
        ),
        effects_variants=QUERY_EFFECTS_VARIANTS,
        output=QUERY_OUTPUT,
        errors=ERRORS,
        examples=(f"dogopencli collection {cap.slug} list --all",),
        next=(f"dogopencli help refresh collection {cap.slug}",),
        handler=f"cmd_collection_{cap.slug.replace('-', '_')}_list",
    )


def refresh_node(cap: NetworkConfigCapability) -> BizNode:
    return BizNode(
        ("refresh", "collection", cap.slug),
        f"Atomically refresh the isolated {cap.title} snapshot.",
        constraints=(
            "Requires an existing authenticated CDP session. Only the local cache "
            "changes; production remains inquiry-only. Accepts no selectors.",
            "One unfiltered page at size 1000 must cover totalCount with unique "
            "IDs. Any failure or incomplete coverage preserves the prior snapshot. "
            "No multi-page fallback; exact full pages require totalCount=1000.",
            "Progress goes to stderr, the result envelope to stdout.",
        ),
        effects={
            "mutates": True,
            "network": True,
            "browser_required": True,
            "destructive": False,
        },
        output=REFRESH_OUTPUT,
        errors=ERRORS,
        examples=(f"dogopencli refresh collection {cap.slug}",),
        next=(f"dogopencli help collection {cap.slug} list",),
        handler=f"cmd_refresh_collection_{cap.slug.replace('-', '_')}",
    )
