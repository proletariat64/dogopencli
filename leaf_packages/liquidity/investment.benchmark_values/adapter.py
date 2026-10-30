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

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        bounds = parse(scope)
        for row in rows:
            day = row.get("effectiveDate")
            try:
                if type(day) is not str or len(day) != 8:
                    raise ValueError
                date.fromisoformat(day[:4] + "-" + day[4:6] + "-" + day[6:])
            except ValueError as error:
                raise CliError(
                    INVALID_RESPONSE, "invalid native effective date"
                ) from error
            if not bounds["valueDateStart"] <= day <= bounds["valueDateEnd"]:
                raise CliError(
                    INVALID_RESPONSE, "effective date is outside requested scope"
                )


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


NAME = "liquidity.investment.benchmark_values"


class Adapter:
    def history_bounds(self, parameters: dict) -> dict:
        native = parse(self.scope(parameters))
        return {
            "from": date.fromisoformat(native["valueDateStart"]).isoformat(),
            "to": date.fromisoformat(native["valueDateEnd"]).isoformat(),
        }

    def history_parameters(self, bounds: dict) -> dict:
        return {
            "from_date": bounds["from"],
            "to_date": bounds["to"],
        }

    def scope(self, parameters: dict[str, Any]) -> str:
        values = {"tntInstId": TENANT}
        start = compact_day(parameters.get("from_date"))
        end = compact_day(parameters.get("to_date"))
        if start > end:
            raise CliError(
                INVALID_ARGUMENT, "start date is after end date", exit_code=2
            )
        values["timeZone"] = "GMT+08"
        values.update(valueDateStart=start, valueDateEnd=end)
        return canonical(values)

    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        values = parse(self.scope(parameters))
        return inquiry(
            values,
            "/queryStrategyBenchmarkList.json",
            5000,
            ("effectiveDate", "strategyBenchmarkType", "currency", "colorType"),
        )

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
