"""Native route quota aggregate, identified by its explicit request context."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse
from dogopencli.leaves.query import CustomGetResult
from dogopencli.result_policy import AcquisitionEvidence

TENANT = "GUAPW3SG"


def validate_context(parameters: dict[str, Any], *, route: bool = True) -> None:
    fields = ("routeId", "account_alias") if route else ("account_alias",)
    if (
        any(
            not isinstance(parameters.get(field), str)
            or not parameters[field].strip()
            or parameters[field].strip().upper() == "ANY"
            for field in fields
        )
        or parameters.get("tenant", TENANT) != TENANT
    ):
        raise CliError(
            INVALID_ARGUMENT,
            "route quota requires exact route and account context in GUAPW3SG",
            exit_code=2,
        )


class Inquiry:
    name = "liquidity.network.route_quotas.get"
    page_url = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/queryWhaleRouteDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"routeId", "aliasName", "tntInstId"}),
        fixed_body_values=(("tntInstId", TENANT),),
    )

    def request_body(self, parameters: dict[str, Any]) -> dict[str, Any]:
        validate_context(parameters)
        return {
            "routeId": parameters["routeId"],
            "aliasName": parameters["account_alias"],
            "tntInstId": TENANT,
        }

    def parse_inquiry(self, body: bytes, parameters: dict[str, Any]) -> dict[str, Any]:
        expected = self.request_body(parameters)
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "quota response is not JSON") from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            raise CliError(
                INVALID_RESPONSE, "quota response requires boolean resultFlag"
            )
        if not document["resultFlag"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        result = document.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "quota result requires boolean success")
        if not result["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        data = result.get("data")
        if not isinstance(data, dict):
            raise CliError(INVALID_RESPONSE, "quota aggregate is not an object")
        for field, value in expected.items():
            if field in data and data[field] not in (None, ""):
                if type(data[field]) is not str or data[field] != value:
                    raise CliError(
                        INVALID_RESPONSE, "quota context contradicts request"
                    )
        for section in ("dynamicQuotas", "staticQuotas"):
            items = data.get(section)
            if not isinstance(items, list) or any(
                not isinstance(item, dict) for item in items
            ):
                raise CliError(
                    INVALID_RESPONSE, "quota aggregate requires both arrays of objects"
                )
        return data


class Adapter:
    def query_capability(
        self, operation: str, name: str, parameters: dict[str, Any]
    ) -> Inquiry:
        if operation != "get" or name != "quotas":
            raise CliError(REQUEST_NOT_ALLOWED, "undeclared route quota inquiry")
        validate_context(parameters, route=False)
        return Inquiry()

    def query_get(
        self, parameters: dict[str, Any], identity: str, tools: Any
    ) -> CustomGetResult:
        context = {**parameters, "routeId": identity}
        validate_context(context)
        data = tools.inquire("quotas", context)
        return CustomGetResult(
            data,
            AcquisitionEvidence.for_collection(
                complete=True,
                reported_total=None,
                collected_total=1,
                arrivals=1,
                total_semantics="unknown",
                coverage_basis="qualified_single_response",
                attempts=(
                    {
                        "component": "native_quotas",
                        "status": "succeeded",
                        "complete": True,
                        "member_counts": {
                            name: len(data[name])
                            for name in ("dynamicQuotas", "staticQuotas")
                        },
                        "reported_count_unit": "unknown",
                    },
                ),
            ),
        )


adapter = Adapter()
