"""Native investment inquiry; no business storage or authentication side effects."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from dogopencli.contracts import EndpointContract
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


def business_data(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get("success")) is not bool:
        raise CliError(INVALID_RESPONSE, "response requires a boolean success flag")
    if not document["success"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    data = document.get("data")
    if not isinstance(data, dict):
        raise CliError(INVALID_RESPONSE, "response data is not an object")
    if data.get("success") is False:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return data


def native_identity(record: dict[str, Any], fields: tuple[str, ...]) -> str:
    values = [record.get(field) for field in fields]
    if any(
        type(value) not in (str, int) or (isinstance(value, str) and not value.strip())
        for value in values
    ):
        raise CliError(INVALID_RESPONSE, "record is missing a valid native identity")
    return canonical(values)


def compact_day(value: Any) -> str:
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT, "date requires YYYY-MM-DD", exit_code=2
        ) from error
    return value.replace("-", "")


@dataclass(frozen=True)
class Inquiry:
    name: str
    contract: EndpointContract
    identity: tuple[str, ...]
    page_url: str = LIQUIDITY_STARTUP_URL

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        values = parse(scope)
        if (
            type(page_size) is not int
            or page_size != self.contract.page_size
            or type(row_start) is not int
            or row_start < 0
            or row_start % self.contract.page_size
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified investment offset")
        return {**values, "rowStart": row_start, "pageSize": page_size}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        result = business_data(body)
        rows, total = result.get("data"), result.get("totalCount")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(INVALID_RESPONSE, "records are not an object array")
        if type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "total is not a nonnegative integer")
        for row in rows:
            native_identity(row, self.identity)
        return rows, total


def inquiry(
    values: dict[str, Any], path: str, size: int, identity: tuple[str, ...]
) -> Inquiry:
    return Inquiry(
        name=NAME + ".list",
        contract=EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path=path,
            page_size=size,
            one_based=False,
            allowed_body_keys=frozenset((*values, "rowStart", "pageSize")),
            fixed_body_values=tuple(values.items()) + (("pageSize", size),),
        ),
        identity=identity,
    )


NAME = "liquidity.investment.holdings"


class DetailInquiry:
    name = "liquidity.investment.holdings.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/queryIncrementOrderDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"orderId"}),
        fixed_body_values=(),
        encoding="form",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        return {"orderId": identity}

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
        value = detail.get("orderId")
        if not isinstance(value, str) or not value.strip() or value != identity:
            raise CliError(INVALID_RESPONSE, "detail identity does not match request")
        if "tntInstId" in detail and detail["tntInstId"] != TENANT:
            raise CliError(
                INVALID_RESPONSE, "detail tenant contradicts requested scope"
            )
        return detail


DETAIL = DetailInquiry()


class Adapter:
    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL

    def scope(self, parameters: dict[str, Any]) -> str:
        values = {"tntInstId": TENANT}
        values.update(
            status=["ACTIVE", "INACTIVE"], date=compact_day(parameters.get("date"))
        )
        return canonical(values)

    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        values = parse(self.scope(parameters))
        return inquiry(values, "/portfolioQueryList.json", 500, ("investmentNo",))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        selected = records
        for parameter, field in (
            ("currency", "currency"),
            ("product_code", "productCode"),
        ):
            values = parameters.get(parameter)
            if values:
                selected = [row for row in selected if row.get(field) in values]
        return selected


adapter = Adapter()
