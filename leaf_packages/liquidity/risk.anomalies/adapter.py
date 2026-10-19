"""Native inquiry-only detail through the host Get SDK."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import BUSINESS_QUERY_FAILED, INVALID_RESPONSE, CliError
from dogopencli.jsonutil import parse

TENANT = "GUAPW3SG"


class DetailInquiry:
    name = "liquidity.risk.anomalies.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/api/risk/event/detail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"riskEventId"}),
        fixed_body_values=(),
        encoding="form",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        return {"riskEventId": identity}

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
        value = detail.get("id")
        if not isinstance(value, str) or not value.strip() or value != identity:
            raise CliError(INVALID_RESPONSE, "detail identity does not match request")
        if detail.get("riskMode") != "RISK_ALERT":
            raise CliError(INVALID_RESPONSE, "detail mode contradicts requested scope")
        if "tntInstId" in detail and detail["tntInstId"] != TENANT:
            raise CliError(
                INVALID_RESPONSE, "detail tenant contradicts requested scope"
            )
        return detail


DETAIL = DetailInquiry()


class Adapter:
    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL


adapter = Adapter()
