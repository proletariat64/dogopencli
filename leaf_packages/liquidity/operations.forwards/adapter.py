"""Native forward order history List without invented date partitions."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse

TENANT = "GUAPW3SG"
PAGE_SIZE = 10


def native_records(body: bytes) -> tuple[list[dict[str, Any]], int]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get("success")) is not bool:
        raise CliError(INVALID_RESPONSE, "invalid business success marker")
    if not document["success"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    node = document.get("data")
    if not isinstance(node, dict):
        raise CliError(INVALID_RESPONSE, "native data is not an object")
    if "success" in node:
        if type(node["success"]) is not bool:
            raise CliError(INVALID_RESPONSE, "invalid inner business success marker")
        if not node["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    rows, total = node.get("data"), node.get("totalCount")
    if not isinstance(rows, list) or type(total) is not int or total < 0:
        raise CliError(INVALID_RESPONSE, "invalid native records or total")
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("orderNo"), str)
            or not row["orderNo"].strip()
        ):
            raise CliError(INVALID_RESPONSE, "native orderNo must be a nonempty string")
        if "tntInstId" in row and row["tntInstId"] != TENANT:
            raise CliError(INVALID_RESPONSE, "native tenant contradicts query scope")
    return rows, total


class Inquiry:
    name = "liquidity.operations.forwards.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/forwardOrderList.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "rowStart", "pageSize"}),
        fixed_body_values=(("tntInstId", TENANT), ("pageSize", PAGE_SIZE)),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            scope
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified forward order request")
        return {"tntInstId": TENANT, "rowStart": row_start, "pageSize": page_size}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        return native_records(body)


CAPABILITY = Inquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return ""

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
