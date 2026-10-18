"""Native inquiry-only rules.notification contract; no legacy runtime dependencies."""

from typing import Any

from dogopencli import collect
from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
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


DETAIL = DetailInquiry("rules.notification", "/messageNoticeConfigDetail.json", "id")


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return DETAIL

    def get(self, session: Any, parameters: dict[str, Any], identity: str) -> Any:
        response = collect.execute_bounded(
            DETAIL,
            session.transport(DETAIL),
            {"id": identity, "tntInstId": TENANT},
        )
        detail = result(response.body, "resultFlag").get("data")
        validate_row(detail, "id")
        if detail["id"] != identity:
            raise CliError(INVALID_RESPONSE, "detail identity does not match request")
        return detail


adapter = Adapter()
