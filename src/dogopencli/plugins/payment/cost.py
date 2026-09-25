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
from .. import EndpointContract, ParsedPage
from ..cost import TABLE_COLUMNS, parse_cost_page, sort_cost_records

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


@dataclass(frozen=True)
class CostCapability:
    name: str = "payment.cost.list"
    source_config_key: str = "payment_cost"
    default_scope: str = COST_TYPE
    contract: EndpointContract = CONTRACT
    id_field: str = "itemId"
    table_columns: tuple[str, ...] = TABLE_COLUMNS

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
        return sort_cost_records(records)

    def identity_key(self, record: dict[str, Any]) -> Any:
        return record.get(self.id_field)

    def parse_page(self, body: bytes) -> ParsedPage:
        return parse_cost_page(body, self.default_scope)


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
    handler="cmd_cost_list",
)
