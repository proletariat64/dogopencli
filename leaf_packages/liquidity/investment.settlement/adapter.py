"""Native Cash Base Yield as an independent standard List."""

from datetime import datetime
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
PAGE_SIZE = 5000


def native_day(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 8
        or not value.isascii()
        or not value.isdigit()
    ):
        raise ValueError
    if datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d") != value:
        raise ValueError
    return value


def native_scope(parameters: dict) -> dict:
    try:
        start, end = (
            native_day(parameters.get(key)) for key in ("from_date", "to_date")
        )
        if start > end:
            raise ValueError
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT, "ordered inclusive YYYYMMDD dates required", exit_code=2
        ) from error
    native = {
        "tntInstId": TENANT,
        "timeZone": "GMT+08",
        "settlementDateBegin": start,
        "settlementDateEnd": end,
    }
    native.update(postingDateBegin="", postingDateEnd="")
    return native


class Inquiry:
    name = "liquidity.investment.settlement.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/cashBaseList.json",
            page_size=PAGE_SIZE,
            one_based=False,
            allowed_body_keys=frozenset({*values, "rowStart", "pageSize"}),
            fixed_body_values=tuple(values.items()) + (("pageSize", PAGE_SIZE),),
        )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict:
        if (
            scope != canonical(self.values)
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unqualified yield scope or offset")
        return {**self.values, "rowStart": row_start, "pageSize": PAGE_SIZE}

    def parse_rows(self, body: bytes) -> tuple[list[dict], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                INVALID_RESPONSE, "yield response is not valid JSON"
            ) from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "yield success must be boolean")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected yield inquiry")
        data = document.get("data")
        if not isinstance(data, dict):
            raise CliError(INVALID_RESPONSE, "yield data must be an object")
        rows, total = data.get("data"), data.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid yield records or native total")
        for row in rows:
            if not isinstance(row, dict) or any(
                not isinstance(row.get(key), str) or not row[key].strip()
                for key in ("id", "transactionId", "settlementDate")
            ):
                raise CliError(
                    INVALID_RESPONSE, "yield native identity or date is missing"
                )
            if "tntInstId" in row and row["tntInstId"] != TENANT:
                raise CliError(INVALID_RESPONSE, "yield tenant contradicts scope")
            try:
                day = native_day(row["settlementDate"])
            except ValueError as error:
                raise CliError(INVALID_RESPONSE, "invalid native yield date") from error
            if (
                not self.values["settlementDateBegin"]
                <= day
                <= self.values["settlementDateEnd"]
            ):
                raise CliError(INVALID_RESPONSE, "native yield date contradicts scope")
        return rows, total


class Adapter:
    def history_bounds(self, parameters: dict) -> dict:
        native = native_scope(parameters)
        return {
            "from": datetime.strptime(native["settlementDateBegin"], "%Y%m%d")
            .date()
            .isoformat(),
            "to": datetime.strptime(native["settlementDateEnd"], "%Y%m%d")
            .date()
            .isoformat(),
        }

    def history_parameters(self, bounds: dict) -> dict:
        return {
            "from_date": bounds["from"].replace("-", ""),
            "to_date": bounds["to"].replace("-", ""),
        }

    def capability(self, parameters: dict) -> Inquiry:
        return Inquiry(native_scope(parameters))

    def scope(self, parameters: dict) -> str:
        return canonical(native_scope(parameters))

    def filter(self, records: list[dict], parameters: dict) -> list[dict]:
        return records


adapter = Adapter()
