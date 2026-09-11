"""Payment channel list capability.

Contract source: docs/research/payment/2026-09-08-channel-query-contract.md
POST https://ifundboss-api.alipay.com/payout/api/ability/search.json,
one-based pageNum, success envelope with resultObj.payoutAbilityVOList.
"""

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from ...errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from ...jsonutil import canonical, parse
from .. import EndpointContract, ParsedPage

DEFAULT_SCOPE = "EXTERNAL"
SCOPES = ("EXTERNAL", "LIQUIDITY", "MANUAL", "SETTLEMENT")
STATUSES = ("ENABLE", "DISABLE", "GRAY", "TEST", "INIT")
PAGE_SIZE = 100

CONTRACT = EndpointContract(
    method="POST",
    host="ifundboss-api.alipay.com",
    path="/payout/api/ability/search.json",
    page_size=PAGE_SIZE,
    one_based=True,
    allowed_body_keys=frozenset(
        {
            "payoutType",
            "financialInstId",
            "debitInstCountryCode",
            "status",
            "debitAccountNameList",
            "debitAccountNoList",
            "clearingSystemNameList",
            "debitCurrencyList",
            "creditCurrencyList",
            "pageNum",
            "pageSize",
        }
    ),
)

# Verified request field -> record field. financialInstId submits the bank
# suggest value, which records expose as financialInstCode.
FILTER_FIELDS = {
    "financialInstId": "financialInstCode",
    "debitInstCountryCode": "debitInstCountryCode",
    "status": "status",
    "debitAccountNameList": "debitAccountName",
    "debitAccountNoList": "debitAccountNo",
    "clearingSystemNameList": "clearingSystemName",
    "debitCurrencyList": "debitCurrency",
    "creditCurrencyList": "creditCurrency",
}

PAGINATION_KEYS = ("pageNum", "pageSize", "totalCount", "totalPages")


def _content_key(record: dict[str, Any]) -> tuple[str, str]:
    text = canonical(record)
    return (sha256(text.encode()).hexdigest(), text)


def assign_seqids(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Content-deterministic order, then seqid=1..N: dataset-local identity
    with the same semantics as the prepared snapshot set, never a
    cross-snapshot correlation key."""
    ordered = sorted(records, key=_content_key)
    return [{"seqid": index, **record} for index, record in enumerate(ordered, 1)]


def _invalid(message: str) -> CliError:
    return CliError(INVALID_RESPONSE, message)


@dataclass(frozen=True)
class ChannelCapability:
    name: str = "payment.channel.list"
    source_config_key: str = "payment_channel"
    default_scope: str = DEFAULT_SCOPE
    contract: EndpointContract = CONTRACT
    id_field: str = "abilityId"
    table_columns: tuple[str, ...] = (
        "seqid",
        "abilityId",
        "status",
        "financialInstCode",
        "debitAccountName",
        "debitAccountNo",
        "clearingSystemName",
        "debitCurrency",
        "creditCurrency",
        "debitInstCountryCode",
        "configVersion",
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        return {"payoutType": scope, "pageNum": page_num, "pageSize": page_size}

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
        """Deterministic local order: dataset seqid ascending."""
        return sorted(records, key=lambda record: record["seqid"])

    def identity_key(self, record: dict[str, Any]) -> Any:
        """abilityId is not a proven primary key: dedup by exact full content;
        different content or versions are always preserved."""
        return canonical(record)

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except ValueError as error:
            raise _invalid("response is not valid JSON") from error
        if not isinstance(document, dict):
            raise _invalid("response envelope is not an object")
        if document.get("success") is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend outer layer failed")
        if "status" in document and document["status"] is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend outer status failed")
        result = document.get("resultObj")
        if not isinstance(result, dict):
            raise _invalid("missing resultObj")
        if result.get("success") is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend inner layer failed")
        paging: dict[str, int] = {}
        for key in PAGINATION_KEYS:
            value = result.get(key)
            if isinstance(value, bool) or not isinstance(value, int):
                raise _invalid(f"invalid pagination field {key}")
            paging[key] = value
        rows = result.get("payoutAbilityVOList")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise _invalid("missing payoutAbilityVOList")
        if paging["totalCount"] == 0 and (rows or paging["totalPages"] != 0):
            raise _invalid("inconsistent empty result")
        return ParsedPage(
            records=list(rows),
            page_num=paging["pageNum"],
            page_size=paging["pageSize"],
            total_count=paging["totalCount"],
            total_pages=paging["totalPages"],
        )


CHANNEL_CAPABILITY = ChannelCapability()
