"""Single-account native T3 forecasts through the offset List SDK."""

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

PAGE_SIZE = 1000
IDENTITY = (
    "aliasName",
    "currency",
    "entity",
    "bankId",
    "forecastDate",
    "expectValueDate",
    "fundActionType",
    "dateFlag",
)


def valid_day(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or len(value) != 8
        or any(c not in "0123456789" for c in value)
    ):
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return False
    return True


def validate_scope(values: Any) -> None:
    if not isinstance(values, dict) or set(values) != {
        "aliasName",
        "startDate",
        "endDate",
    }:
        raise CliError(
            INVALID_ARGUMENT,
            "T3 requires one account alias and both date bounds",
            exit_code=2,
        )
    alias = values["aliasName"]
    if (
        not isinstance(alias, str)
        or not alias.strip()
        or "," in alias
        or alias == "ANY"
    ):
        raise CliError(
            INVALID_ARGUMENT, "account-alias requires one nonempty alias", exit_code=2
        )
    if (
        not valid_day(values["startDate"])
        or not valid_day(values["endDate"])
        or values["startDate"] > values["endDate"]
    ):
        raise CliError(
            INVALID_ARGUMENT,
            "ordered inclusive YYYYMMDD date bounds are required",
            exit_code=2,
        )


def native_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    values = {
        "aliasName": parameters.get("account_alias"),
        "startDate": parameters.get("from_date"),
        "endDate": parameters.get("to_date"),
    }
    validate_scope(values)
    return values


class Inquiry:
    name = "liquidity.forecast.account_t3.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/t3ForecastDemandList.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset(
            {"aliasName", "startDate", "endDate", "rowStart", "pageSize"}
        ),
        fixed_body_values=(("pageSize", PAGE_SIZE),),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified T3 offset or width")
        try:
            values = parse(scope)
            validate_scope(values)
        except (ValueError, UnicodeError, CliError) as error:
            raise CliError(REQUEST_NOT_ALLOWED, "unverified T3 scope") from error
        return {**values, "rowStart": row_start, "pageSize": PAGE_SIZE}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "T3 success marker must be boolean")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected T3 inquiry")
        data = document.get("data")
        if (
            not isinstance(data, dict)
            or type(data.get("totalCount")) is not int
            or data["totalCount"] < 0
        ):
            raise CliError(
                INVALID_RESPONSE, "T3 requires an object and nonnegative integer total"
            )
        if "pageSize" in data and (
            type(data["pageSize"]) is not int or data["pageSize"] != PAGE_SIZE
        ):
            raise CliError(INVALID_RESPONSE, "invalid T3 page size echo")
        if "rowStart" in data and (
            type(data["rowStart"]) is not int
            or data["rowStart"] < 0
            or data["rowStart"] % PAGE_SIZE
        ):
            raise CliError(INVALID_RESPONSE, "invalid T3 offset echo")
        rows = data.get("data")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "T3 records must be an array")
        for row in rows:
            if not isinstance(row, dict) or any(
                not isinstance(row.get(field), str) or not row[field].strip()
                for field in IDENTITY
            ):
                raise CliError(INVALID_RESPONSE, "invalid native T3 identity")
            if not valid_day(row["forecastDate"]) or not valid_day(
                row["expectValueDate"]
            ):
                raise CliError(INVALID_RESPONSE, "invalid native T3 calendar date")
        return rows, data["totalCount"]

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        values = parse(scope)
        validate_scope(values)
        if any(
            row["aliasName"] != values["aliasName"]
            or not values["startDate"] <= row["forecastDate"] <= values["endDate"]
            for row in rows
        ):
            raise CliError(
                INVALID_RESPONSE,
                "T3 row is outside the requested account or forecast-date window",
            )


CAPABILITY = Inquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        native_scope(parameters)
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        alias = parameters.get("account_alias")
        start = parameters.get("from_date")
        end = parameters.get("to_date")
        if alias is not None and (
            not isinstance(alias, str)
            or not alias.strip()
            or "," in alias
            or alias == "ANY"
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "account-alias requires one nonempty alias",
                exit_code=2,
            )
        if (
            (start is not None and not valid_day(start))
            or (end is not None and not valid_day(end))
            or (start is not None and end is not None and start > end)
        ):
            raise CliError(
                INVALID_ARGUMENT, "invalid YYYYMMDD date window", exit_code=2
            )
        return [
            row
            for row in records
            if (alias is None or row["aliasName"] == alias)
            and (start is None or row["forecastDate"] >= start)
            and (end is None or row["forecastDate"] <= end)
        ]


adapter = Adapter()
