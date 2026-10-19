"""Native account capability List with an unchanged integer row identity."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse

TENANT = "GUAPW3SG"
PAGE_SIZE = 10


class Inquiry:
    name = "liquidity.network.account_capabilities.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/serviceInfoQuery.json",
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
            raise CliError(REQUEST_NOT_ALLOWED, "unverified account capability request")
        return {"tntInstId": TENANT, "rowStart": row_start, "pageSize": page_size}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
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
        rows, total = node.get("data"), node.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid native records or total")
        for row in rows:
            if not isinstance(row, dict) or type(row.get("id")) is not int:
                raise CliError(
                    INVALID_RESPONSE,
                    "native account capability id must be an integer",
                )
            if "tntInstId" in row and row["tntInstId"] != TENANT:
                raise CliError(
                    INVALID_RESPONSE,
                    "native tenant contradicts query scope",
                )
        return rows, total


CAPABILITY = Inquiry()


class DetailInquiry:
    name = "liquidity.network.account_capabilities.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/serviceInfoDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"id"}),
        encoding="json",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT, "detail lookup must be nonempty", exit_code=2
            )
        try:
            value = int(identity)
        except ValueError as error:
            raise CliError(
                INVALID_ARGUMENT, "detail id must be an integer", exit_code=2
            ) from error
        return {"id": value}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "detail response is not JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "detail envelope is not an object")
        if type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "detail success marker is not boolean")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected the detail inquiry")
        detail = document.get("data")
        if not isinstance(detail, dict) or not detail:
            raise CliError(INVALID_RESPONSE, "detail root is not a nonempty object")
        if (
            type(detail.get("id")) is not int
            or detail["id"] != self.request_body(parameters, identity)["id"]
        ):
            raise CliError(
                INVALID_RESPONSE, "detail identity differs from the requested lookup"
            )
        tenant = detail.get("tntInstId")
        if tenant not in (None, "", TENANT):
            raise CliError(
                INVALID_RESPONSE, "detail tenant contradicts requested scope"
            )
        return detail


DETAIL = DetailInquiry()


class Adapter:
    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL

    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return ""

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
