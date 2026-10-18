"""Native inquiry-only rules.transfer contract; no legacy runtime dependencies."""

import json
from typing import Any

from dogopencli import collect
from dogopencli.collect import CollectedScope
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


def result(body: bytes, marker: str = "resultFlag") -> dict[str, Any]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get(marker)) is not bool:
        raise CliError(INVALID_RESPONSE, "invalid business success marker")
    if not document[marker]:
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


class DetailInquiry:
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, leaf: str, path: str, field: str):
        self.name = "liquidity." + leaf + ".get"
        self.contract = EndpointContract(
            method="GET",
            host="iliquidity.alipay.com",
            path=path,
            page_size=0,
            one_based=False,
            allowed_body_keys=frozenset({"tntInstId", field}),
            fixed_body_values=(("tntInstId", TENANT),),
            encoding="query",
        )


DETAIL = DetailInquiry("rules.transfer", "/queryTransferRuleDetail.json", "ruleId")

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
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "transfer has one fixed inquiry")
        return {"tntInstId": TENANT, "transferRuleQueryRequest": VO}

    def identity_key(self, row: dict[str, Any]) -> str:
        validate_row(row, "ruleId")
        return row["ruleId"]

    def parse_page(self, body: bytes):
        from dogopencli.contracts import ParsedPage

        node = result(body)
        if node.get("success") is not True:
            raise CliError(INVALID_RESPONSE, "transfer list requires inner success")
        rows, total = node.get("transferRuleVOS"), node.get("ruleCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid transfer records or ruleCount")
        for row in rows:
            self.identity_key(row)
        return ParsedPage(rows, 0, PAGE_SIZE, total, -(-total // PAGE_SIZE))


CAPABILITY = Inquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return ""

    def collector(
        self, capability: Any, transport: Any, scope: str, *, progress: Any = None
    ) -> CollectedScope:
        return collect.collect_scope(capability, transport, scope, progress=progress)

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records

    def get(self, session: Any, parameters: dict[str, Any], identity: str) -> Any:
        response = collect.execute_bounded(
            DETAIL,
            session.transport(DETAIL),
            {"ruleId": identity, "tntInstId": TENANT},
        )
        detail = result(response.body, "success").get("transferRuleVO")
        validate_row(detail, "ruleId")
        if detail["ruleId"] != identity:
            raise CliError(INVALID_RESPONSE, "detail identity does not match request")
        return detail


adapter = Adapter()
