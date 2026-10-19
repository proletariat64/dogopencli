"""Native investment strategy settings detail through the host Get SDK."""

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


class DetailCapability:
    name = "liquidity.investment.strategies.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/queryIncrementStrategyRuleDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"strategyRuleCode"}),
        encoding="form",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT, "strategy rule code must be nonempty", exit_code=2
            )
        return {"strategyRuleCode": identity}

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
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected strategy inquiry")
        detail = document.get("data")
        if not isinstance(detail, dict):
            raise CliError(INVALID_RESPONSE, "strategy detail is not an object")
        code = detail.get("strategyRuleCode")
        if not isinstance(code, str) or not code.strip() or code != identity:
            raise CliError(INVALID_RESPONSE, "strategy rule code differs from request")
        return detail


class Adapter:
    def detail_capability(self, parameters: dict[str, Any]) -> DetailCapability:
        return DetailCapability()


adapter = Adapter()
