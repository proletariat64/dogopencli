"""Native asset trade List; trading dates remain distinct from source timestamps."""

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
PAGE_SIZE = 1000


def native_records(body: bytes) -> tuple[list[dict[str, Any]], int]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get("success")) is not bool:
        raise CliError(INVALID_RESPONSE, "invalid business success marker")
    if not document["success"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    node = document.get("data")
    if not isinstance(node, dict):
        raise CliError(INVALID_RESPONSE, "native data is not an object")
    if "success" in node:
        if type(node["success"]) is not bool:
            raise CliError(INVALID_RESPONSE, "invalid inner business success marker")
        if not node["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    rows, total = node.get("data"), node.get("totalCount")
    if not isinstance(rows, list) or type(total) is not int or total < 0:
        raise CliError(INVALID_RESPONSE, "invalid native records or total")
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("orderNo"), str)
            or not row["orderNo"].strip()
        ):
            raise CliError(INVALID_RESPONSE, "native orderNo must be a nonempty string")
        if "tntInstId" in row and row["tntInstId"] != TENANT:
            raise CliError(INVALID_RESPONSE, "native tenant contradicts query scope")
    return rows, total


def compact_day(value: Any) -> str:
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError
        day = date.fromisoformat(value)
        if day.isoformat() != value:
            raise ValueError
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT, "trading date requires YYYY-MM-DD", exit_code=2
        ) from error
    return value.replace("-", "")


def native_scope(parameters: dict[str, Any]) -> dict[str, str]:
    timezone = parameters.get("timezone", "GMT+08")
    if timezone != "GMT+08":
        raise CliError(
            INVALID_ARGUMENT, "asset trade timezone must be GMT+08", exit_code=2
        )
    start, end = (
        compact_day(parameters.get("from_date")),
        compact_day(parameters.get("to_date")),
    )
    if start > end:
        raise CliError(
            INVALID_ARGUMENT, "trading date start is after its end", exit_code=2
        )
    return {
        "tntInstId": TENANT,
        "timeZone": timezone,
        "tradingDateBegin": start,
        "tradingDateEnd": end,
    }


class Inquiry:
    name = "liquidity.operations.asset_trades.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/assetTransferOrderListQuery.json",
            page_size=PAGE_SIZE,
            one_based=False,
            allowed_body_keys=frozenset({*values, "rowStart", "pageSize"}),
            fixed_body_values=tuple(values.items()) + (("pageSize", PAGE_SIZE),),
        )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            scope != canonical(self.values)
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified asset trade request")
        return {**self.values, "rowStart": row_start, "pageSize": page_size}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        return native_records(body)


class DetailInquiry:
    name = "liquidity.operations.asset_trades.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/assetTransferOrderDetailQuery.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"orderNo"}),
        encoding="form",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT, "detail lookup must be nonempty", exit_code=2
            )
        value = identity
        return {"orderNo": value}

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
        if not isinstance(detail.get("orderNo"), str) or detail["orderNo"] != identity:
            raise CliError(
                INVALID_RESPONSE, "detail identity differs from the requested lookup"
            )
        tenant = detail.get("tntInstId")
        if tenant not in (None, "", TENANT):
            raise CliError(
                INVALID_RESPONSE, "detail tenant contradicts requested scope"
            )
        return detail


DETAIL = DetailInquiry()


class Adapter:
    def history_bounds(self, parameters: dict) -> dict:
        native = native_scope(parameters)
        return {
            "from": date.fromisoformat(native["tradingDateBegin"]).isoformat(),
            "to": date.fromisoformat(native["tradingDateEnd"]).isoformat(),
        }

    def history_parameters(self, bounds: dict) -> dict:
        return {
            "from_date": bounds["from"],
            "to_date": bounds["to"],
        }

    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL

    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry(native_scope(parameters))

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
