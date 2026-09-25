"""Collection SLA configs: verified inquiry contracts, never payment baselines."""

from dataclasses import dataclass
from typing import Any

from ...errors import (
    BUSINESS_QUERY_FAILED,
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
    BizNode,
    opt,
)
from ...jsonutil import parse
from .. import EndpointContract, ParsedPage

PAGE_SIZE = 1000
LIST_CONTRACT = EndpointContract(
    method="POST",
    host="iglobalfundcontrol.alipay.com",
    path="/api/fundInSlaConfig/search.json",
    page_size=PAGE_SIZE,
    one_based=False,
    allowed_body_keys=frozenset({"pageNo", "pageSize"}),
    fixed_body_values=(("pageNo", 0), ("pageSize", PAGE_SIZE)),
)
DETAIL_CONTRACT = EndpointContract(
    method="GET",
    host="iglobalfundcontrol.alipay.com",
    path="/api/fundInSlaConfig/getDetailBySlaConfigId.json",
    page_size=0,
    one_based=False,
    allowed_body_keys=frozenset({"slaConfigId"}),
)


def _document(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict):
        raise CliError(INVALID_RESPONSE, "response envelope is not an object")
    if document.get("success") is not True:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return document


def _validate_record(record: Any) -> None:
    if (
        not isinstance(record, dict)
        or not isinstance(record.get("slaConfigId"), str)
        or not record["slaConfigId"].strip()
    ):
        raise CliError(
            INVALID_RESPONSE, "SLA configuration requires nonempty string slaConfigId"
        )


def parse_detail(body: bytes, identity: str) -> dict[str, Any]:
    detail = _document(body).get("resultData")
    _validate_record(detail)
    if detail["slaConfigId"] != identity:
        raise CliError(INVALID_RESPONSE, "detail slaConfigId does not match request")
    return detail


def validate_pair(record: Any, detail: Any) -> None:
    """Keep true detail separate; reject changes in any shared business field."""
    _validate_record(record)
    _validate_record(detail)
    if any(record[key] != detail[key] for key in record.keys() & detail.keys()):
        raise CliError(INVALID_RESPONSE, "SLA list and detail shared fields differ")


def _identity_order(record: dict[str, Any]) -> tuple[Any, ...]:
    identity = record["slaConfigId"]
    return (
        (0, int(identity), identity)
        if identity.isascii() and identity.isdigit()
        else (1, identity)
    )


@dataclass(frozen=True)
class CollectionSlaDetailCapability:
    name: str = "collection.sla.configs.get"
    contract: EndpointContract = DETAIL_CONTRACT


@dataclass(frozen=True)
class CollectionSlaCapability:
    name: str = "collection.sla.configs.list"
    source_config_key: str = "collection_sla"
    default_scope: str = "configs"
    contract: EndpointContract = LIST_CONTRACT
    id_field: str = "slaConfigId"
    table_columns: tuple[str, ...] = (
        "slaConfigId",
        "businessCategory",
        "legalEntityCode",
        "creditorCurrency",
        "creditorRegion",
        "endToEndSla",
        "ipayInnerSla",
        "holidayLimit",
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if scope != self.default_scope or page_num != 0 or page_size != PAGE_SIZE:
            raise CliError(REQUEST_NOT_ALLOWED, "unverified collection SLA request")
        return dict(LIST_CONTRACT.fixed_body_values)

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        if set(body) - LIST_CONTRACT.allowed_body_keys:
            raise CliError(
                REQUEST_NOT_ALLOWED, "collection SLA backend filters are not exposed"
            )
        return {}

    def filter_records(
        self, records: list[dict[str, Any]], filters: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        if filters:
            raise CliError(
                REQUEST_NOT_ALLOWED, "collection SLA filters are not exposed"
            )
        return records

    def sort_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(records, key=_identity_order)

    def identity_key(self, record: dict[str, Any]) -> Any:
        return record[self.id_field]

    def parse_page(self, body: bytes) -> ParsedPage:
        document = _document(body)
        for key in ("pageNo", "pageSize", "totalCount"):
            if type(document.get(key)) is not int:
                raise CliError(INVALID_RESPONSE, f"invalid pagination field {key}")
        total = document["totalCount"]
        if document["pageNo"] != 0 or document["pageSize"] != PAGE_SIZE or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid collection SLA pagination")
        rows = document.get("resultDataList")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "invalid resultDataList")
        for row in rows:
            _validate_record(row)
        if total == 0 and rows:
            raise CliError(INVALID_RESPONSE, "inconsistent empty result")
        if (
            total > PAGE_SIZE
            or len(rows) != total
            or len({row[self.id_field] for row in rows}) != len(rows)
        ):
            raise CliError(
                INCOMPLETE_RESULT,
                (
                    "collection SLA response does not prove complete unique "
                    "coverage; no pagination fallback is verified"
                ),
            )
        return ParsedPage(rows, 0, PAGE_SIZE, total, 1 if total else 0)


COLLECTION_SLA = CollectionSlaCapability()
COLLECTION_SLA_DETAIL = CollectionSlaDetailCapability()
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
COLLECTION_SLA_LIST_NODE = BizNode(
    ("collection", "sla", "configs", "list"),
    "List collection SLA configurations from cache or explicitly with --live.",
    options=(LIMIT, OFFSET, ALL, LIVE, *CACHE_FLAGS, FORMAT_TABLE, FIELDS),
    constraints=(
        CACHE_SEMANTICS,
        DISPLAY_WINDOW,
        (
            "Configuration targets, not actual order timing. "
            "endToEndSla and ipayInnerSla remain raw seconds; "
            "holidayLimit arrays remain complete."
        ),
        (
            "Live acquisition validates one complete "
            "pageNo=0/pageSize=1000 response; no speculative paging "
            "or implicit refresh."
        ),
    ),
    effects_variants=QUERY_EFFECTS_VARIANTS,
    output=QUERY_OUTPUT,
    errors=_ERRORS,
    examples=("dogopencli collection sla configs list",),
    next=(
        "dogopencli help collection sla configs get",
        "dogopencli help refresh collection sla",
    ),
    handler="cmd_collection_sla_list",
)
COLLECTION_SLA_GET_NODE = BizNode(
    ("collection", "sla", "configs", "get"),
    "Retrieve a true collection SLA configuration detail by slaConfigId.",
    options=(
        opt("id", "Nonempty string slaConfigId from the list.", "str", required=True),
        LIVE,
        *CACHE_FLAGS,
        FORMAT_TABLE,
        FIELDS,
    ),
    constraints=(
        CACHE_SEMANTICS,
        (
            "Never substitutes a list row for detail. Null or invalid"
            " live detail fails; backend not-found semantics are "
            "unverified."
        ),
        "Live complete describes only the requested detail, not all configurations.",
    ),
    effects_variants=QUERY_EFFECTS_VARIANTS,
    output=QUERY_OUTPUT,
    errors=(*_ERRORS, "NOT_FOUND"),
    examples=("dogopencli collection sla configs get --id CONFIG_ID",),
    next=("dogopencli help collection sla configs list",),
    handler="cmd_collection_sla_get",
)
