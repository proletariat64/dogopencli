"""Native bounded TARGET_RFQ List through the host collection SDK."""

from datetime import date
from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    EXIT_USAGE,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse

TENANT = "GUAPW3SG"
PAGE_SIZE = 5000
INQUIRY_TYPE = "TARGET_RFQ"


def native_scope(parameters: dict[str, Any]) -> dict[str, str]:
    values = {}
    try:
        for parameter, field in (
            ("from_date", "inquiryStartDate"),
            ("to_date", "inquiryEndDate"),
        ):
            value = parameters.get(parameter)
            if not isinstance(value, str) or not value.isascii() or len(value) != 10:
                raise ValueError
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError
            values[field] = value.replace("-", "")
        if values["inquiryStartDate"] > values["inquiryEndDate"]:
            raise ValueError
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT,
            "RFQs require ordered --from-date/--to-date YYYY-MM-DD bounds",
            exit_code=EXIT_USAGE,
        ) from error
    return {"inquiryType": INQUIRY_TYPE, **values}


class Inquiry:
    name = "liquidity.investment.rfqs.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/rfq/subInquiryTask/querySubInquiryTask.json",
            page_size=PAGE_SIZE,
            one_based=False,
            single_page=True,
            allowed_body_keys=frozenset({*values, "rowStart", "pageSize"}),
            fixed_body_values=tuple(values.items())
            + (("rowStart", 0), ("pageSize", PAGE_SIZE)),
        )

    def page_body(self, scope: str, position: int, page_size: int) -> dict[str, Any]:
        if (
            scope != canonical(self.values)
            or type(position) is not int
            or position != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "RFQs have one fixed bounded inquiry")
        return {**self.values, "rowStart": 0, "pageSize": PAGE_SIZE}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "RFQ response is not JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "invalid RFQ business marker")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        node = document.get("data")
        if not isinstance(node, dict):
            raise CliError(INVALID_RESPONSE, "RFQ data is not an object")
        rows, total = node.get("data"), node.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid RFQ records or native totalCount")
        if total > PAGE_SIZE or len(rows) > PAGE_SIZE:
            raise CliError(
                INVALID_RESPONSE, "RFQ scope exceeds the single 5000 response"
            )
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("inquirySubTaskId"), str)
                or not row["inquirySubTaskId"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE, "RFQ subtask identity must be a nonempty string"
                )
            if row.get("inquiryType") != INQUIRY_TYPE:
                raise CliError(INVALID_RESPONSE, "RFQ inquiryType contradicts scope")
            if "tntInstId" in row and row["tntInstId"] != TENANT:
                raise CliError(INVALID_RESPONSE, "RFQ tenant contradicts application")
        return ParsedPage(rows, 0, PAGE_SIZE, total, -(-total // PAGE_SIZE))


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry(native_scope(parameters))

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
