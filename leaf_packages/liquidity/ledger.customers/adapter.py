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
    name = "liquidity.ledger.customers.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/bookCustomer/detail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"version", "tntInstId", "customerNo"}),
        encoding="query",
        fixed_body_values=(("tntInstId", TENANT),),
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT, "detail lookup must be nonempty", exit_code=2
            )
        value = identity
        version = parameters.get("customer_version")
        if not isinstance(version, str) or not version.strip():
            raise CliError(
                INVALID_ARGUMENT,
                "customer detail requires --customer-version",
                exit_code=2,
            )
        return {"customerNo": value, "tntInstId": TENANT, "version": version}

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
            not isinstance(detail.get("customerNo"), str)
            or detail["customerNo"] != identity
        ):
            raise CliError(
                INVALID_RESPONSE, "detail identity differs from the requested lookup"
            )
        tenant = detail.get("tntInstId")
        if tenant not in (None, "", TENANT):
            raise CliError(
                INVALID_RESPONSE, "detail tenant contradicts requested scope"
            )
        if "version" in detail and detail["version"] is not None:
            version = detail["version"]
            if (
                isinstance(version, bool)
                or not isinstance(version, (str, int))
                or str(version) != parameters["customer_version"]
            ):
                raise CliError(
                    INVALID_RESPONSE, "customer detail version contradicts request"
                )
        return detail


DETAIL = DetailInquiry()


class Adapter:
    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL


adapter = Adapter()
