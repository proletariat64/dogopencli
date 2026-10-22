"""Native product history array, scoped by business product code."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse

TENANT = "GUAPW3SG"


def product_code(parameters: dict[str, Any], *, required: bool = True) -> str | None:
    code = parameters.get("product_code")
    if code is None and not required:
        return None
    if not isinstance(code, str) or not code.strip():
        raise CliError(
            "INVALID_ARGUMENT", "product-code requires one nonblank code", exit_code=2
        )
    return code


class Inquiry:
    name = "liquidity.investment.products.history.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/incrementProductHistoryQuery.json",
        encoding="form",
        page_size=0,
        one_based=False,
        total_semantics="unknown",
        allowed_body_keys=frozenset({"tntInstId", "incrementProductCode"}),
        fixed_body_values=(("tntInstId", TENANT),),
    )

    def page_body(self, scope: str, position: int, page_size: int) -> dict[str, Any]:
        if (
            type(position) is not int
            or position != 0
            or type(page_size) is not int
            or page_size != 0
        ):
            raise CliError("REQUEST_NOT_ALLOWED", "product history is unpaged")
        context = parse(scope)
        if (
            not isinstance(context, dict)
            or set(context) != {"tntInstId", "incrementProductCode"}
            or context["tntInstId"] != TENANT
            or not isinstance(context["incrementProductCode"], str)
            or not context["incrementProductCode"].strip()
        ):
            raise CliError("REQUEST_NOT_ALLOWED", "invalid product history scope")
        return context

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], None]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                "INVALID_RESPONSE", "history response is not JSON"
            ) from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError("INVALID_RESPONSE", "history success marker must be boolean")
        if not document["success"]:
            raise CliError("BUSINESS_QUERY_FAILED", "product history inquiry failed")
        rows = document.get("data")
        if not isinstance(rows, list):
            raise CliError("INVALID_RESPONSE", "history data must be a native array")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("incrementProductId"), str)
                or not row["incrementProductId"].strip()
            ):
                raise CliError("INVALID_RESPONSE", "history physical ID is missing")
            tenant = row.get("tntInstId")
            if tenant is not None and (
                not isinstance(tenant, str) or (tenant.strip() and tenant != TENANT)
            ):
                raise CliError("INVALID_RESPONSE", "history tenant differs from scope")
        return rows, None

    def validate_rows_scope(self, rows: list[dict], scope: str) -> None:
        code = parse(scope)["incrementProductCode"]
        if any(row.get("incrementProductCode") != code for row in rows):
            raise CliError(
                "INVALID_RESPONSE", "history product code differs from scope"
            )


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        product_code(parameters)
        return Inquiry()

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(
            {"tntInstId": TENANT, "incrementProductCode": product_code(parameters)}
        )

    def filter(self, records: list[dict], parameters: dict[str, Any]) -> list[dict]:
        code = product_code(parameters, required=False)
        return [
            row
            for row in records
            if code is None or row["incrementProductCode"] == code
        ]


adapter = Adapter()
