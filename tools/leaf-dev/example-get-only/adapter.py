"""Synthetic Get-only leaf; run only through the offline handbook harness."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.errors import BUSINESS_QUERY_FAILED, INVALID_RESPONSE, CliError
from dogopencli.jsonutil import parse


class DetailCapability:
    name = "collection.sample.detail.get"
    page_url = "https://leaf-handbook.invalid/app"
    contract = EndpointContract(
        method="GET",
        host="leaf-handbook.invalid",
        path="/detail/by-reference",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"businessReference", "account"}),
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        return {"businessReference": identity, "account": parameters["account"]}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        try:
            value = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "Sample response is not JSON") from error
        if not isinstance(value, dict) or type(value.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "Sample success flag is invalid")
        if not value["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "Sample detail inquiry was rejected")
        detail = value.get("detail")
        if (
            not isinstance(detail, dict)
            or type(detail.get("nativeId")) is not int
            or detail.get("reference") != identity
            or detail.get("account") != parameters["account"]
        ):
            raise CliError(INVALID_RESPONSE, "Sample detail identity or scope differs")
        return detail


class Adapter:
    def detail_capability(self, parameters: dict[str, Any]) -> DetailCapability:
        return DetailCapability()


adapter = Adapter()
