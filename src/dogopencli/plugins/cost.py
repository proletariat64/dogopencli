"""Shared cost envelope and record conventions for product plugins."""

from typing import Any

from ..errors import BUSINESS_QUERY_FAILED, INVALID_RESPONSE, CliError
from ..jsonutil import parse
from . import ParsedPage

TABLE_COLUMNS = (
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

PAGINATION_KEYS = ("pageNo", "pageSize", "totalCount")


def _invalid(message: str) -> CliError:
    return CliError(INVALID_RESPONSE, message)


def _record_key(record: dict[str, Any]) -> tuple[int, Any]:
    item_id = record.get("itemId")
    if isinstance(item_id, str) and item_id.isdigit():
        return (0, int(item_id))
    return (1, str(item_id))


def sort_cost_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order original item IDs numerically when possible, then lexically."""
    return sorted(records, key=_record_key)


def parse_cost_page(
    body: bytes, cost_type: str, *, allow_omitted_empty: bool = False
) -> ParsedPage:
    """Parse the shared cost envelope while preserving exact values and extensions."""
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
    if (
        allow_omitted_empty
        and paging["totalCount"] == 0
        and "resultDataList" not in document
    ):
        rows = []
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise _invalid("missing resultDataList")
    if paging["totalCount"] == 0 and rows:
        raise _invalid("inconsistent empty result")
    if len(rows) > paging["pageSize"]:
        raise _invalid("page returned more rows than pageSize")
    for row in rows:
        if row.get("itemType") != cost_type:
            raise _invalid("row itemType is outside the fixed cost type")
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
