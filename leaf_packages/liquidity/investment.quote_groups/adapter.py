"""Native independent detail through the host Get SDK."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    CliError,
)
from dogopencli.jsonutil import parse

TENANT = "GUAPW3SG"


class DetailInquiry:
    name = "liquidity.investment.quote_groups.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/queryQuotationDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"quotationGroupId"}),
        encoding="form",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT, "detail lookup must be nonempty", exit_code=2
            )
        value = identity
        return {"quotationGroupId": value}

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
        if not isinstance(detail.get("id"), str) or detail["id"] != identity:
            raise CliError(
                INVALID_RESPONSE, "detail identity differs from the requested lookup"
            )
        tenant = detail.get("tntInstId")
        if tenant not in (None, "", TENANT):
            raise CliError(
                INVALID_RESPONSE, "detail tenant contradicts requested scope"
            )
        if (
            not isinstance(detail.get("quotationGroupId"), str)
            or not detail["quotationGroupId"].strip()
            or type(detail.get("version")) is not int
            or detail.get("tntInstId") != TENANT
        ):
            raise CliError(
                INVALID_RESPONSE, "quotation group native version identity is invalid"
            )
        return detail


DETAIL = DetailInquiry()


class Adapter:
    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL


adapter = Adapter()
