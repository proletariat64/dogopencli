"""Collection VA rules: verified inquiry contracts, never bank-account rules."""

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
    BizNode,
    opt,
)
from .. import EndpointContract, ParsedPage
from ..envelope import success_document

PAGE_SIZE = 1000
LIST_CONTRACT = EndpointContract(
    method="POST",
    host="ifundboss-api.alipay.com",
    path="/ivostro/api/virtualAccountRule/list.json",
    page_size=PAGE_SIZE,
    one_based=True,
    allowed_body_keys=frozenset({"pageNo", "pageSize"}),
    fixed_body_values=(("pageNo", 1), ("pageSize", PAGE_SIZE)),
)
DETAIL_CONTRACT = EndpointContract(
    method="GET",
    host="ifundboss-api.alipay.com",
    path="/ivostro/api/virtualAccountRule/detail.json",
    page_size=0,
    one_based=False,
    allowed_body_keys=frozenset({"vaRuleId"}),
)

# Business fields proven identical between a list row and its true detail;
# the differently named list countries and detail creditAreas are never
# merged, renamed or equated.
SHARED_FIELDS = (
    "assembleStrategy",
    "bankRuleId",
    "entity",
    "memo",
    "regionType",
    "ruleStatus",
    "sceneCodes",
    "vaRuleId",
)

# vaWarningInfo is optional: not every observed detail carries one.
DETAIL_FIELDS = (
    "assembleStrategy",
    "assignInfo",
    "bankRuleId",
    "clientEntity",
    "creditAreas",
    "entity",
    "memo",
    "regionType",
    "ruleStatus",
    "sceneCodes",
    "vaRuleId",
)


def _validate_row(row: Any) -> None:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("vaRuleId"), str)
        or not row["vaRuleId"].strip()
    ):
        raise CliError(
            INVALID_RESPONSE, "VA rule row requires nonempty string vaRuleId"
        )


def _validate_detail(detail: Any) -> None:
    _validate_row(detail)
    if any(field not in detail for field in DETAIL_FIELDS):
        raise CliError(
            INVALID_RESPONSE, "VA rule detail is missing required business fields"
        )


def parse_detail(body: bytes, identity: str) -> dict[str, Any]:
    detail = success_document(body).get("resultObj")
    _validate_detail(detail)
    if detail["vaRuleId"] != identity:
        raise CliError(INVALID_RESPONSE, "detail vaRuleId does not match request")
    return detail


def validate_pair(row: Any, detail: Any) -> None:
    """Keep true detail separate; reject drift in any shared business field."""
    _validate_row(row)
    _validate_detail(detail)
    if any(field not in row or row[field] != detail[field] for field in SHARED_FIELDS):
        raise CliError(INVALID_RESPONSE, "VA rule list and detail shared fields differ")


def validate_stored_pair(pair: Any) -> None:
    """Accept a detail or the null detail ADR 0010 stores for a backend refusal."""
    if not isinstance(pair, dict) or "rule" not in pair or "detail" not in pair:
        raise CliError(INVALID_RESPONSE, "invalid cached VA rule pair")
    _validate_row(pair["rule"])
    if pair["detail"] is not None:
        validate_pair(pair["rule"], pair["detail"])


def _identity_order(record: dict[str, Any]) -> tuple[Any, ...]:
    identity = record["vaRuleId"]
    return (
        (0, int(identity), identity)
        if identity.isascii() and identity.isdigit()
        else (1, identity)
    )


@dataclass(frozen=True)
class CollectionVaRuleDetailCapability:
    name: str = "collection.va.rules.get"
    contract: EndpointContract = DETAIL_CONTRACT


@dataclass(frozen=True)
class CollectionVaRuleCapability:
    name: str = "collection.va.rules.list"
    source_config_key: str = "collection_va"
    default_scope: str = "rules"
    contract: EndpointContract = LIST_CONTRACT
    id_field: str = "vaRuleId"
    table_columns: tuple[str, ...] = (
        "vaRuleId",
        "aliasName",
        "bankAccountNo",
        "financialInst",
        "entity",
        "currency",
        "ruleStatus",
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if scope != self.default_scope or page_num != 1 or page_size != PAGE_SIZE:
            raise CliError(REQUEST_NOT_ALLOWED, "unverified VA rule request")
        return dict(LIST_CONTRACT.fixed_body_values)

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        if set(body) - LIST_CONTRACT.allowed_body_keys:
            raise CliError(
                REQUEST_NOT_ALLOWED, "VA rule backend filters are not exposed"
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
        if document["pageNo"] != 1 or document["pageSize"] != PAGE_SIZE or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid VA rule pagination")
        rows = document.get("resultDataList")
        if total == 0 and "resultDataList" not in document:
            rows = []
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "invalid resultDataList")
        for row in rows:
            _validate_row(row)
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
                    "VA rule response does not prove complete unique coverage; "
                    "no pagination fallback is verified"
                ),
            )
        return ParsedPage(rows, 1, PAGE_SIZE, total, 1 if total else 0)


COLLECTION_VA_RULES = CollectionVaRuleCapability()
COLLECTION_VA_RULES_DETAIL = CollectionVaRuleDetailCapability()
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
COLLECTION_VA_RULE_LIST_NODE = BizNode(
    ("collection", "va", "rules", "list"),
    "List collection VA rules from cache or explicitly with --live.",
    options=(LIMIT, OFFSET, ALL, LIVE, *CACHE_FLAGS, FORMAT_TABLE, FIELDS),
    constraints=(
        CACHE_SEMANTICS,
        DISPLAY_WINDOW,
        (
            "Live fetches the complete unfiltered scope before local "
            "stable-ID sorting and display windowing. ASCII digit IDs sort "
            "numerically, with original string as the tie-breaker; other IDs "
            "sort lexically afterward. Original string IDs remain unchanged. "
            "Refresh is unfiltered; get accepts only ID selection."
        ),
        (
            "vaRuleId is the VA rule identity. bankRuleId references a "
            "distinct bank-account VA rule object and is never accepted as a "
            "VA rule ID; bank-account rule details (bankAccountVaRule) are out"
            " of scope and never merged into VA rule records."
        ),
        (
            "List rows and details remain distinct raw objects; list "
            "countries and detail creditAreas keep their original names and "
            "are never merged or equated."
        ),
        (
            "Live acquisition validates one complete "
            "pageNo=1/pageSize=1000 response; no speculative paging "
            "or implicit refresh."
        ),
        (
            "A detail the backend refuses (success=false) still publishes its "
            "list row with a null detail: backend_complete stays true, "
            "dataset_complete becomes false, and --require-complete rejects "
            "such a snapshot."
        ),
    ),
    effects_variants=QUERY_EFFECTS_VARIANTS,
    output=QUERY_OUTPUT,
    errors=_ERRORS,
    examples=(
        "dogopencli collection va rules list",
        "dogopencli collection va rules list --all",
        "dogopencli collection va rules list --live --fields vaRuleId,ruleStatus",
    ),
    next=(
        "dogopencli help collection va rules get",
        "dogopencli help refresh collection va",
    ),
    handler="cmd_collection_va_rules_list",
)
COLLECTION_VA_RULE_GET_NODE = BizNode(
    ("collection", "va", "rules", "get"),
    "Retrieve a true collection VA rule detail by vaRuleId.",
    options=(
        opt("id", "Nonempty string vaRuleId from the list.", "str", required=True),
        LIVE,
        *CACHE_FLAGS,
        FORMAT_TABLE,
        FIELDS,
    ),
    constraints=(
        CACHE_SEMANTICS,
        (
            "Never substitutes a list row for detail. Core business fields "
            "must be present; explicit null values remain raw. Null or invalid"
            " live detail fails; backend not-found semantics are "
            "unverified."
        ),
        (
            "A cached rule whose detail the backend refused is "
            "INCOMPLETE_RESULT, not NOT_FOUND, and never its list row; an "
            "explicit live get reports the business failure instead."
        ),
        (
            "The related bank-account rule lookup (bankAccountVaRule) is not "
            "part of this detail and is never queried."
        ),
        "Live complete describes only the requested detail, not all rules.",
    ),
    effects_variants=QUERY_EFFECTS_VARIANTS,
    output=QUERY_OUTPUT,
    errors=(*_ERRORS, "NOT_FOUND"),
    examples=("dogopencli collection va rules get --id VA_RULE_ID",),
    next=("dogopencli help collection va rules list",),
    handler="cmd_collection_va_rules_get",
)
