"""Synthetic List and Get: owned contract/parsers, shared host mechanics.

The .invalid endpoint exists only in the offline handbook test harness.
No legacy business module or production endpoint is used by this example.
"""

from datetime import datetime
from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse


class SampleCapability:
    name = "collection.sample.calendar.list"
    page_url = "https://leaf-handbook.invalid/app"
    contract = EndpointContract(
        method="POST",
        host="leaf-handbook.invalid",
        path="/records/query",
        page_size=2,
        one_based=False,
        allowed_body_keys=frozenset({"fromDate", "toDate", "pageNo", "pageSize"}),
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if page_size != self.contract.page_size or page_num < 0:
            raise CliError(REQUEST_NOT_ALLOWED, "Unsupported sample request")
        return {**parse(scope), "pageNo": page_num, "pageSize": page_size}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            value = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "Sample response is not JSON") from error
        if not isinstance(value, dict) or type(value.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "Sample success flag is invalid")
        if not value["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "Sample inquiry was rejected")
        rows = value.get("rows")
        page, size, total = (
            value.get("pageNo"),
            value.get("pageSize"),
            value.get("total"),
        )
        if (
            any(type(number) is not int for number in (page, size, total))
            or page < 0
            or size != self.contract.page_size
            or total < 0
            or not isinstance(rows, list)
            or any(
                not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not row["id"].strip()
                for row in rows
            )
        ):
            raise CliError(INVALID_RESPONSE, "Sample records or pagination are invalid")
        return ParsedPage(rows, page, size, total, -(-total // size))


CAPABILITY = SampleCapability()


def compact(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y%m%d")
        if parsed.strftime("%Y%m%d") != value:
            raise ValueError
        return parsed.date().isoformat()
    except (ValueError, TypeError) as error:
        raise CliError(
            INVALID_ARGUMENT, "Sample dates require YYYYMMDD", exit_code=2
        ) from error


class Adapter:
    def history_bounds(self, parameters: dict) -> dict:
        return {
            "from": compact(parameters.get("from_date")),
            "to": compact(parameters.get("to_date")),
        }

    def history_parameters(self, bounds: dict) -> dict:
        return {
            "from_date": bounds["from"].replace("-", ""),
            "to_date": bounds["to"].replace("-", ""),
        }

    def capability(self, parameters: dict) -> SampleCapability:
        bounds = self.history_bounds(parameters)
        if bounds["from"] > bounds["to"]:
            raise CliError(
                INVALID_ARGUMENT, "Sample date range is reversed", exit_code=2
            )
        return CAPABILITY

    def scope(self, parameters: dict) -> str:
        self.capability(parameters)
        return canonical(
            {
                "fromDate": parameters["from_date"],
                "toDate": parameters["to_date"],
            }
        )

    def filter(self, records: list[dict], parameters: dict) -> list[dict]:
        return records


adapter = Adapter()
