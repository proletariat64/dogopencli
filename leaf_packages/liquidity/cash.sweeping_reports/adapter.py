"""Native cash pool operating reports through the host List SDK."""

from calendar import monthrange
from datetime import date, datetime
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

NAME = "liquidity.cash.sweeping_reports"
WIDTHS = (1000, 100)
POOL_TYPE = "Sweeping_Agreement"


def native_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    if parameters.get("timezone") != "GMT+08":
        raise CliError(INVALID_ARGUMENT, "unsupported source timezone", exit_code=2)
    dates = []
    for key in ("start_date", "end_date"):
        value = parameters.get(key)
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError
        except (ValueError, TypeError) as error:
            raise CliError(
                INVALID_ARGUMENT, "dates require valid YYYY-MM-DD", exit_code=2
            ) from error
        dates.append(parsed)
    start, end = dates
    year, month = (
        (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    )
    # The UI uses moment.diff(start, "months") >= 1, including month-end clipping.
    boundary = (
        date(year, month, min(start.day, monthrange(year, month)[1]))
        if year <= 9999
        else None
    )
    if end < start or (boundary is not None and end >= boundary):
        raise CliError(
            INVALID_ARGUMENT,
            "date range must be ordered and shorter than one calendar month",
            exit_code=2,
        )
    return {
        "tntInstId": "GUAPW3SG",
        "cashPoolType": POOL_TYPE,
        "valueDateStart": start.isoformat().replace("-", ""),
        "valueDateEnd": end.isoformat().replace("-", ""),
        "timezone": parameters["timezone"],
    }


class Inquiry:
    name = NAME + ".list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/cashPoolReportList.json",
            page_size=1000,
            allowed_page_sizes=WIDTHS,
            one_based=False,
            allowed_body_keys=frozenset({*values, "rowStart", "pageSize"}),
            fixed_body_values=tuple(values.items()),
            encoding="json",
        )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            scope != canonical(self.values)
            or type(page_size) is not int
            or page_size not in WIDTHS
            or type(row_start) is not int
            or row_start < 0
            or row_start % page_size
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified pool report List request")
        return {**self.values, "rowStart": row_start, "pageSize": page_size}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "response requires a boolean success flag")
        if not document["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected pool report inquiry"
            )
        data = document.get("data")
        if not isinstance(data, dict):
            raise CliError(INVALID_RESPONSE, "response data is not an object")
        rows, total = data.get("data"), data.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid pool report rows or native total")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not row["id"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE, "report id must be a nonempty native string"
                )
            if row.get("cashPoolType") not in ("", self.values["cashPoolType"]):
                raise CliError(
                    INVALID_RESPONSE, "report pool type contradicts requested scope"
                )
            value_date = row.get("valueDate")
            try:
                parsed_date = datetime.strptime(value_date, "%Y%m%d").date()
                if parsed_date.isoformat().replace("-", "") != value_date:
                    raise ValueError
            except (ValueError, TypeError) as error:
                raise CliError(
                    INVALID_RESPONSE, "invalid native report valueDate"
                ) from error
            if (
                not self.values["valueDateStart"]
                <= value_date
                <= self.values["valueDateEnd"]
            ):
                raise CliError(
                    INVALID_RESPONSE, "report valueDate contradicts requested range"
                )
        return rows, total

    def parse_metadata(self, body: bytes) -> dict[str, Any]:
        self.parse_rows(body)
        data = parse(body)["data"]
        return {"totalAmount": data["totalAmount"]} if "totalAmount" in data else {}


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry(native_scope(parameters))

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
