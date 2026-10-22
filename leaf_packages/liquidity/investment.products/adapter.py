"""Native product definitions and independent physical-ID detail inquiries."""

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
from dogopencli.jsonutil import canonical, parse

TENANT = "GUAPW3SG"
PAGE_SIZE = 5000
FILTERS = (("currency", "currency"), ("bank", "bankId"), ("status", "status"))


def validate_filters(parameters: dict[str, Any]) -> None:
    for name, _ in FILTERS:
        values = parameters.get(name)
        if values is not None and (
            not isinstance(values, list)
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "filters require nonblank repeated strings",
                exit_code=2,
            )


def business_root(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except (ValueError, UnicodeError) as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get("success")) is not bool:
        raise CliError(INVALID_RESPONSE, "product success marker must be boolean")
    if not document["success"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend rejected product inquiry")
    result = document.get("data")
    if not isinstance(result, dict):
        raise CliError(INVALID_RESPONSE, "product data must be an object")
    return result


def validate_identity(row: Any) -> None:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("incrementProductId"), str)
        or not row["incrementProductId"].strip()
    ):
        raise CliError(
            INVALID_RESPONSE, "product requires a nonblank native physical ID"
        )
    tenant = row.get("tntInstId")
    if tenant is not None and tenant != "" and tenant != TENANT:
        raise CliError(INVALID_RESPONSE, "product tenant contradicts requested scope")


class Inquiry:
    name = "liquidity.investment.products.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/incrementProductsPage.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "rowStart", "pageSize"}),
        fixed_body_values=(
            ("tntInstId", TENANT),
            ("rowStart", 0),
            ("pageSize", PAGE_SIZE),
        ),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            scope != canonical({"tntInstId": TENANT})
            or type(row_start) is not int
            or row_start != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "unverified product inquiry scope or paging"
            )
        return {"tntInstId": TENANT, "rowStart": 0, "pageSize": PAGE_SIZE}

    def parse_page(self, body: bytes) -> ParsedPage:
        result = business_root(body)
        rows = result.get("data")
        total = result.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE,
                "product List requires native array and nonnegative integer total",
            )
        for name, expected in (("rowStart", 0), ("pageSize", PAGE_SIZE)):
            if name in result and (
                type(result[name]) is not int or result[name] != expected
            ):
                raise CliError(INVALID_RESPONSE, "invalid product paging echo")
        for row in rows:
            validate_identity(row)
        return ParsedPage(rows, 0, PAGE_SIZE, total, -(-total // PAGE_SIZE))


class DetailInquiry:
    name = "liquidity.investment.products.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/incrementProductDetail.json",
        page_size=0,
        one_based=False,
        encoding="form",
        allowed_body_keys=frozenset({"tntInstId", "incrementProductId"}),
        fixed_body_values=(("tntInstId", TENANT),),
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT,
                "lookup requires one nonblank physical product ID",
                exit_code=2,
            )
        return {"tntInstId": TENANT, "incrementProductId": identity}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        result = business_root(body)
        validate_identity(result)
        if result["incrementProductId"] != identity:
            raise CliError(
                INVALID_RESPONSE, "product physical ID does not match lookup"
            )
        return result


LIST = Inquiry()
DETAIL = DetailInquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        validate_filters(parameters)
        return LIST

    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL

    def scope(self, parameters: dict[str, Any]) -> str:
        validate_filters(parameters)
        return canonical({"tntInstId": TENANT})

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        validate_filters(parameters)
        return [
            row
            for row in records
            if all(
                not parameters.get(name) or row.get(field) in parameters[name]
                for name, field in FILTERS
            )
        ]


adapter = Adapter()
