"""Payment channel cost configuration capability.

Contract source: docs/research/payment/2026-09-08-cost-query-contract.md
POST https://iglobalfundcontrol.alipay.com/api/fundCost/query.json,
zero-based pageNo, success envelope with resultDataList/totalCount.
The payment scope is fixed to costTypeCode=FUND_OUT_CHANNEL_TRANS_FEE;
actual fees are never computed from the nested rate configuration.
"""

from dataclasses import dataclass
from typing import Any

from ...errors import (
    BUSINESS_QUERY_FAILED,
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
    FILTER_OR_AND,
    FORMAT_TABLE,
    LIMIT,
    LIVE,
    LIVE_SINGLE_VALUE,
    OFFSET,
    QUERY_EFFECTS_VARIANTS,
    QUERY_OUTPUT,
    SEQID_UNSTABLE,
    BizNode,
    opt,
)
from ...jsonutil import parse
from .. import EndpointContract, ParsedPage

COST_TYPE = "FUND_OUT_CHANNEL_TRANS_FEE"
PAGE_SIZE = 5000

CONTRACT = EndpointContract(
    method="POST",
    host="iglobalfundcontrol.alipay.com",
    path="/api/fundCost/query.json",
    page_size=PAGE_SIZE,
    one_based=False,
    allowed_body_keys=frozenset(
        {
            "costTypeCode",
            "legalEntityCode",
            "financialInstCode",
            "bankAccount",
            "transCurrencyCode",
            "chargeBearer",
            "clearingNetworkName",
            "pageNo",
            "pageSize",
        }
    ),
    rebuild_page_size=10000,
)

# Verified request field -> record field. bankAccount submits the bank
# deposit alias, never the full account number.
FILTER_FIELDS = {
    "legalEntityCode": "legalEntity",
    "financialInstCode": "financialInst",
    "bankAccount": "bankAccountAliasName",
    "transCurrencyCode": "transCurrencyCode",
    "chargeBearer": "chargeBearer",
    "clearingNetworkName": "clearingNetworkName",
}

PAGINATION_KEYS = ("pageNo", "pageSize", "totalCount")


def _invalid(message: str) -> CliError:
    return CliError(INVALID_RESPONSE, message)


def _record_key(record: dict[str, Any]) -> tuple[int, Any]:
    item_id = record.get("itemId")
    if isinstance(item_id, str) and item_id.isdigit():
        return (0, int(item_id))
    return (1, str(item_id))


@dataclass(frozen=True)
class CostCapability:
    name: str = "payment.cost.list"
    source_config_key: str = "payment_cost"
    default_scope: str = COST_TYPE
    contract: EndpointContract = CONTRACT
    id_field: str = "itemId"
    table_columns: tuple[str, ...] = (
        "itemId",
        "status",
        "legalEntity",
        "financialInst",
        "bankAccountAliasName",
        "transCurrencyCode",
        "costCurrencyCode",
        "chargeBearer",
        "clearingNetworkName",
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        return {"costTypeCode": scope, "pageNo": page_num, "pageSize": page_size}

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        filters: dict[str, list[str]] = {}
        for key in FILTER_FIELDS:
            if key not in body:
                continue
            value = body[key]
            values = value if isinstance(value, list) else [value]
            if not values or not all(isinstance(item, str) for item in values):
                raise CliError(REQUEST_NOT_ALLOWED, f"invalid filter value for {key}")
            filters[key] = list(values)
        return filters

    def filter_records(
        self, records: list[dict[str, Any]], filters: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        return [
            record
            for record in records
            if all(
                record.get(FILTER_FIELDS[key]) in values
                for key, values in filters.items()
            )
        ]

    def sort_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deterministic local order: original itemId ascending."""
        return sorted(records, key=_record_key)

    def identity_key(self, record: dict[str, Any]) -> Any:
        return record.get(self.id_field)

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except ValueError as error:
            raise _invalid("response is not valid JSON") from error
        if not isinstance(document, dict):
            raise _invalid("response envelope is not an object")
        # A success envelope also carries errorContext with errorName=SUCCESS;
        # only the success flag itself decides the business outcome.
        if document.get("success") is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        paging: dict[str, int] = {}
        for key in PAGINATION_KEYS:
            value = document.get(key)
            if isinstance(value, bool) or not isinstance(value, int):
                raise _invalid(f"invalid pagination field {key}")
            paging[key] = value
        if paging["pageSize"] <= 0:
            raise _invalid("invalid pagination field pageSize")
        rows = document.get("resultDataList")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise _invalid("missing resultDataList")
        if paging["totalCount"] == 0 and rows:
            raise _invalid("inconsistent empty result")
        if len(rows) > paging["pageSize"]:
            raise _invalid("page returned more rows than pageSize")
        for row in rows:
            if row.get("itemType") != COST_TYPE:
                raise _invalid("row itemType is outside the fixed payment cost type")
            item_id = row.get("itemId")
            if not isinstance(item_id, str) or not item_id:
                raise _invalid("row is missing itemId")
        total_pages = -(-paging["totalCount"] // paging["pageSize"])
        return ParsedPage(
            records=list(rows),
            page_num=paging["pageNo"],
            page_size=paging["pageSize"],
            total_count=paging["totalCount"],
            total_pages=total_pages,
        )


COST_CAPABILITY = CostCapability()

COST_LIST_NODE = BizNode(
    ("payment", "cost", "list"),
    "List payment channel cost configurations from the local cache (default)"
    " or the backend with --live.",
    options=(
        opt("legal_entity_code", "Filter by legal entity code.", "append"),
        opt("financial_inst_code", "Filter by financial institution code.", "append"),
        opt("bank_account", "Filter by bank account.", "append"),
        opt("trans_currency_code", "Filter by transaction currency.", "append"),
        opt("charge_bearer", "Filter by charge bearer.", "append"),
        opt("clearing_network_name", "Filter by clearing network name.", "append"),
        LIMIT,
        OFFSET,
        ALL,
        LIVE,
        *CACHE_FLAGS,
        FORMAT_TABLE,
        FIELDS,
    ),
    constraints=(
        "The scope is fixed to costTypeCode=FUND_OUT_CHANNEL_TRANS_FEE; there"
        " is no scope option.",
        FILTER_OR_AND,
        CACHE_SEMANTICS,
        DISPLAY_WINDOW,
        SEQID_UNSTABLE,
        LIVE_SINGLE_VALUE,
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
        "dogopencli payment cost list",
        "dogopencli payment cost list --legal-entity-code LE01",
        "dogopencli payment cost list --live",
    ),
    next=("dogopencli help refresh payment cost",),
    handler=True,
)
