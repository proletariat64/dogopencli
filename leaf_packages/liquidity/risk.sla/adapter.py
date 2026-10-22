"""Native risk SLA configuration List through the host collection SDK."""

from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
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
PAGE_SIZE = 5000


class Inquiry:
    name = "liquidity.risk.sla.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/api/risk/sla/slaConfigPageQuery.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"rowStart", "pageSize"}),
        fixed_body_values=(("rowStart", 0), ("pageSize", PAGE_SIZE)),
    )

    def page_body(self, scope: str, position: int, page_size: int) -> dict[str, Any]:
        if (
            scope
            or type(position) is not int
            or position != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "risk SLA has one fixed inquiry")
        return {"rowStart": 0, "pageSize": PAGE_SIZE}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(
                INVALID_RESPONSE, "SLA response is not valid JSON"
            ) from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "invalid SLA business success marker")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        node = document.get("data")
        if not isinstance(node, dict):
            raise CliError(INVALID_RESPONSE, "SLA data is not an object")
        rows, total = node.get("data"), node.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid SLA records or native total")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("slaConfigId"), str)
                or not row["slaConfigId"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE, "SLA slaConfigId must be a nonempty string"
                )
            if "tntInstId" in row and row["tntInstId"] != TENANT:
                raise CliError(
                    INVALID_RESPONSE, "SLA tenant contradicts application scope"
                )
            if row.get("version") is not None and not isinstance(row["version"], str):
                raise CliError(INVALID_RESPONSE, "SLA version must be a native string")
        return ParsedPage(rows, 0, PAGE_SIZE, total, -(-total // PAGE_SIZE))


CAPABILITY = Inquiry()


class DetailInquiry:
    name = "liquidity.risk.sla.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/api/risk/sla/slaConfigDetailQuery.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"slaConfigId"}),
        fixed_body_values=(),
        encoding="form",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT,
                "detail identity must be a nonempty string",
                exit_code=2,
            )
        return {"slaConfigId": identity}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "detail success marker is not boolean")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        detail = document
        detail = detail.get("data")
        if not isinstance(detail, dict):
            raise CliError(INVALID_RESPONSE, "detail container is not an object")
        value = detail.get("slaConfigId")
        if not isinstance(value, str) or not value.strip() or value != identity:
            raise CliError(INVALID_RESPONSE, "detail identity does not match request")
        if detail.get("version") is not None and not isinstance(detail["version"], str):
            raise CliError(INVALID_RESPONSE, "detail version must be a native string")
        if "tntInstId" in detail and detail["tntInstId"] != TENANT:
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
