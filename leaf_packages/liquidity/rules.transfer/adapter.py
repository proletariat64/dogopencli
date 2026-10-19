"""Native inquiry-only rules.transfer contract; no legacy runtime dependencies."""

import json
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


def result(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get("resultFlag")) is not bool:
        raise CliError(INVALID_RESPONSE, "invalid business success marker")
    if not document["resultFlag"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    node = document.get("result")
    if not isinstance(node, dict):
        raise CliError(INVALID_RESPONSE, "result is not an object")
    if "success" in node:
        if type(node["success"]) is not bool:
            raise CliError(INVALID_RESPONSE, "inner success is not boolean")
        if not node["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return node


def validate_row(row: Any, field: str) -> None:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get(field), str)
        or not row[field].strip()
    ):
        raise CliError(INVALID_RESPONSE, "native identity must be a nonempty string")
    if "tntInstId" in row and row["tntInstId"] != TENANT:
        raise CliError(INVALID_RESPONSE, "record tenant contradicts query scope")


PAGE_SIZE = 5000
VO = json.dumps(
    {
        "tntInstId": TENANT,
        "debitEntity": [],
        "creditEntity": [],
        "rowStart": 0,
        "pageSize": PAGE_SIZE,
    }
)


class Inquiry:
    name = "liquidity.rules.transfer.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/transferRuleQuery.json",
        page_size=PAGE_SIZE,
        one_based=False,
        single_page=True,
        allowed_body_keys=frozenset({"tntInstId", "transferRuleQueryRequest"}),
        fixed_body_values=(("tntInstId", TENANT), ("transferRuleQueryRequest", VO)),
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope
            or type(page_num) is not int
            or page_num != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "transfer has one fixed inquiry")
        return {"tntInstId": TENANT, "transferRuleQueryRequest": VO}

    def parse_page(self, body: bytes) -> ParsedPage:
        node = result(body)
        if node.get("success") is not True:
            raise CliError(INVALID_RESPONSE, "transfer list requires inner success")
        rows, total = node.get("transferRuleVOS"), node.get("ruleCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid transfer records or ruleCount")
        for row in rows:
            validate_row(row, "ruleId")
        return ParsedPage(rows, 0, PAGE_SIZE, total, -(-total // PAGE_SIZE))


CAPABILITY = Inquiry()


class DetailInquiry:
    name = "liquidity.rules.transfer.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/queryTransferRuleDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "ruleId"}),
        fixed_body_values=(("tntInstId", "GUAPW3SG"),),
        encoding="query",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT,
                "detail identity must be a nonempty string",
                exit_code=2,
            )
        return {"ruleId": identity, "tntInstId": "GUAPW3SG"}

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
        detail = detail.get("result")
        if not isinstance(detail, dict):
            raise CliError(INVALID_RESPONSE, "detail container is not an object")
        if "success" in detail:
            if type(detail["success"]) is not bool:
                raise CliError(INVALID_RESPONSE, "inner success is not boolean")
            if not detail["success"]:
                raise CliError(
                    BUSINESS_QUERY_FAILED, "backend reported a business failure"
                )
        detail = detail.get("transferRuleVO")
        if not isinstance(detail, dict):
            raise CliError(INVALID_RESPONSE, "detail container is not an object")
        value = detail.get("ruleId")
        if not isinstance(value, str) or not value.strip() or value != identity:
            raise CliError(INVALID_RESPONSE, "detail identity does not match request")
        if "tntInstId" in detail and detail["tntInstId"] != TENANT:
            raise CliError(
                INVALID_RESPONSE, "detail tenant contradicts requested scope"
            )
        return detail


DETAIL = DetailInquiry()


class Adapter:
    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL

    def capability(self, parameters: dict[str, Any]) -> Any:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return ""

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
