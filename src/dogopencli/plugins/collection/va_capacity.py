"""Collection VA capacity monitoring: verified inquiry contract (#36/#37).

One row is one VA rule's capacity/warning projection. The verified endpoint
reports a running-estimate totalCount on interim pages; only the final
converged total validates completeness, and duplicate or drifting ruleId
identities fail the acquisition instead of publishing a partial scope.
"""

from dataclasses import dataclass
from typing import Any

from ...errors import (
    INCOMPLETE_RESULT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
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
    opt,
)
from .. import EndpointContract, ParsedPage
from ..envelope import success_document

PAGE_SIZE = 1000
LIST_CONTRACT = EndpointContract(
    method="POST",
    host="ifundboss-api.alipay.com",
    path="/ivostro/api/warningUseCount/pageList.json",
    page_size=PAGE_SIZE,
    one_based=True,
    allowed_body_keys=frozenset({"pageNo", "pageSize"}),
    # pageNo varies across the verified multi-page sweep; pageSize is fixed.
    fixed_body_values=(("pageSize", PAGE_SIZE),),
    # Interim totalCount is a running estimate; only the final converged
    # total on the first short page validates completeness (#37).
    running_total=True,
)

# Accepted local filters: CLI flag -> raw row field (frozen in #36).
FILTER_FIELDS = {
    "bank-va-rule-id": "bankAccountVaId",
    "va-rule-id": "ruleId",
}


def _validate_row(row: Any) -> None:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("ruleId"), str)
        or not row["ruleId"].strip()
    ):
        raise CliError(
            INVALID_RESPONSE, "VA capacity row requires nonempty string ruleId"
        )


def validate_row(row: Any) -> None:
    """Public read-side re-validation of a cached capacity row."""
    _validate_row(row)


def _identity_order(record: dict[str, Any]) -> tuple[Any, ...]:
    identity = record["ruleId"]
    return (
        (0, int(identity), identity)
        if identity.isascii() and identity.isdigit()
        else (1, identity)
    )


@dataclass(frozen=True)
class CollectionVaCapacityCapability:
    name: str = "collection.va.capacity.list"
    source_config_key: str = "collection_va_capacity"
    default_scope: str = "capacity"
    contract: EndpointContract = LIST_CONTRACT
    id_field: str = "ruleId"
    table_columns: tuple[str, ...] = (
        "ruleId",
        "bankAccountVaId",
        "accountNo",
        "currency",
        "sceneCode",
        "totalCount",
        "usedCount",
        "availableCount",
        "canUseDays",
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if scope != self.default_scope or page_size != PAGE_SIZE or page_num < 1:
            raise CliError(REQUEST_NOT_ALLOWED, "unverified VA capacity request")
        return {"pageNo": page_num, "pageSize": page_size}

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        if set(body) - LIST_CONTRACT.allowed_body_keys:
            raise CliError(
                REQUEST_NOT_ALLOWED, "VA capacity backend filters are not exposed"
            )
        return {}

    def filter_records(
        self, records: list[dict[str, Any]], filters: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        return [
            record
            for record in records
            if all(record.get(field) in values for field, values in filters.items())
        ]

    def sort_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(records, key=_identity_order)

    def identity_key(self, record: dict[str, Any]) -> Any:
        return record[self.id_field]

    def parse_page(self, body: bytes) -> ParsedPage:
        document = success_document(body)
        for key in ("pageNo", "pageSize", "totalCount"):
            if type(document.get(key)) is not int:
                raise CliError(INVALID_RESPONSE, f"invalid pagination field {key}")
        total = document["totalCount"]
        if total < 0 or document["pageNo"] < 1:
            raise CliError(INVALID_RESPONSE, "invalid VA capacity pagination")
        rows = document.get("resultDataList")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "invalid resultDataList")
        for row in rows:
            _validate_row(row)
        if total == 0 and rows:
            raise CliError(INVALID_RESPONSE, "inconsistent empty result")
        # A full page may have more rows behind it; only a short page ends the
        # scope. The shared collector checks the final total against coverage.
        total_pages = -(-total // PAGE_SIZE)
        # Interim totals are estimates, so a page is never rejected for
        # exceeding the current estimate; the collector's converged-total
        # check is the only coverage validation. A page larger than the
        # requested size remains invalid under any total semantics.
        if len(rows) > PAGE_SIZE:
            raise CliError(
                INCOMPLETE_RESULT, "VA capacity page exceeds its declared scope"
            )
        if len({row[self.id_field] for row in rows}) != len(rows):
            raise CliError(
                INCOMPLETE_RESULT, "duplicate ruleId within one VA capacity page"
            )
        return ParsedPage(
            rows, document["pageNo"], document["pageSize"], total, total_pages
        )


COLLECTION_VA_CAPACITY = CollectionVaCapacityCapability()
_ERRORS = (
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
COLLECTION_VA_CAPACITY_LIST_NODE = BizNode(
    ("collection", "va", "capacity", "list"),
    "List collection VA capacity and warning counters from cache or"
    " explicitly with --live.",
    options=(
        *(
            opt(
                flag.replace("-", "_"),
                f"Nonempty exact local match on {field}.",
                "append",
            )
            for flag, field in FILTER_FIELDS.items()
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
        (
            "Filters are local for cache and live: exact case-sensitive literal "
            "values, same-field OR and cross-field AND. Whitespace-only values "
            "are invalid; values are never trimmed or normalized. A literal * "
            "is not a wildcard. Missing/null fields do not match."
        ),
        (
            "ruleId is the row identity and is unique in the verified scope; "
            "id, bankAccountVaId and accountNo are not unique and are never "
            "accepted as the row identity. --bank-va-rule-id matches the "
            "bankAccountVaId row field, not the id field."
        ),
        (
            "Live fetches the complete unfiltered scope before local "
            "filtering, stable-ID sorting and display windowing. Acquisition "
            "pages with pageSize=1000 from page 1 until the first short page; "
            "interim totalCount is a backend running estimate and only the "
            "final converged total validates completeness. Duplicate or "
            "drifting ruleId identities fail instead of publishing or "
            "returning a partial scope. Refresh is unfiltered."
        ),
        (
            "Capacity and warning counters are live backend values; the "
            "snapshot ages between refreshes. canUseDays is the backend's "
            "remaining-days estimate and is never recomputed; no counter is "
            "derived from another. gmtCreate/gmtModified units and the "
            "average/peak aggregation periods are unverified."
        ),
        (
            "The UI warning state is not exposed: rows carry no warning-state "
            "field and the server classification is volatile and not "
            "derivable from row counters."
        ),
    ),
    effects_variants=QUERY_EFFECTS_VARIANTS,
    output=QUERY_OUTPUT,
    errors=_ERRORS,
    examples=(
        "dogopencli collection va capacity list",
        "dogopencli collection va capacity list --va-rule-id RULE_ID",
        "dogopencli collection va capacity list --bank-va-rule-id BANK_RULE_ID --all",
    ),
    next=("dogopencli help refresh collection va capacity",),
    handler="cmd_collection_va_capacity_list",
)


REFRESH_NODE = BizNode(
    ("refresh", "collection", "va", "capacity"),
    "Rebuild the collection VA capacity cache through the existing CDP session.",
    constraints=(
        *REFRESH_CDP_CONSTRAINTS,
        (
            "Only the local capacity cache changes; production business state "
            "remains read-only. Bare refresh collection va still refreshes VA "
            "rules; this child refreshes only the capacity snapshot."
        ),
        (
            "Pages the verified endpoint with pageSize=1000 until the first "
            "short page; only the final converged totalCount validates "
            "completeness. Any failure — authentication, refusal, malformed "
            "data, changing totals, duplicate identities, lock or timeout — "
            "preserves the previous snapshot."
        ),
    ),
    effects=dict(REFRESH_CDP_EFFECTS),
    output=dict(REFRESH_OUTPUT),
    # Keep the established help order: capacity reports incomplete coverage
    # immediately after invalid responses, before authentication/runtime errors.
    errors=(
        *REFRESH_CDP_ERRORS[:3],
        "INCOMPLETE_RESULT",
        *REFRESH_CDP_ERRORS[3:],
    ),
    examples=("dogopencli refresh collection va capacity",),
    next=("dogopencli help collection va capacity list",),
    handler="cmd_refresh_collection_va_capacity",
)
