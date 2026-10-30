"""Intraday native statements with explicit account, currency and date scope."""

import re
from dataclasses import dataclass
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
TENANT = "GUAPW3SG"
IDENTITY = ("bankTransNo",)
SCOPE_KEYS = frozenset(
    {
        "instIds",
        "bankAccountAliasName",
        "currency",
        "timeZone",
        "queryDateBegin",
        "queryDateEnd",
    }
)


def compact_date(value: Any) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"(?:[0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2})", value) is None
    ):
        raise CliError(INVALID_ARGUMENT, "date must use YYYY-MM-DD or YYYYMMDD")
    try:
        return datetime.strptime(
            value, "%Y-%m-%d" if "-" in value else "%Y%m%d"
        ).strftime("%Y%m%d")
    except ValueError as error:
        raise CliError(INVALID_ARGUMENT, "date is not a calendar date") from error


def request_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for parameter, field, default in (
        ("inst_id", "instIds", "Z21"),
        ("account_alias", "bankAccountAliasName", None),
    ):
        value = parameters.get(parameter, default)
        if not isinstance(value, str) or not value.strip():
            raise CliError(INVALID_ARGUMENT, f"{parameter} requires a nonempty string")
        values[field] = [value]
    currency = parameters.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        raise CliError(INVALID_ARGUMENT, "currency requires an explicit nonempty value")
    if parameters.get("timezone", "GMT+08") != "GMT+08":
        raise CliError(INVALID_ARGUMENT, "only timezone GMT+08 is verified")
    values.update(
        currency=currency,
        timeZone="GMT+08",
        queryDateBegin=compact_date(parameters.get("from_date")),
        queryDateEnd=compact_date(parameters.get("to_date")),
    )
    if values["queryDateBegin"] > values["queryDateEnd"]:
        raise CliError(INVALID_ARGUMENT, "date window start is after its end")
    return values


@dataclass(frozen=True)
class StatementInquiry:
    name: str = "liquidity.cash.statements.intraday.list"
    page_url: str = LIQUIDITY_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/bankAccountDetailQuery.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=SCOPE_KEYS | {"tntInstId", "rowStart", "pageSize"},
        fixed_body_values=(
            ("tntInstId", TENANT),
            ("timeZone", "GMT+08"),
            ("pageSize", PAGE_SIZE),
        ),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        try:
            values = parse(scope)
        except ValueError as error:
            raise CliError(REQUEST_NOT_ALLOWED, "invalid statement scope") from error
        if (
            not isinstance(values, dict)
            or set(values) != SCOPE_KEYS
            or type(page_size) is not int
            or page_size != PAGE_SIZE
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified statement request")
        checked = request_scope(
            {
                "inst_id": values["instIds"][0]
                if len(values["instIds"]) == 1
                else None,
                "account_alias": values["bankAccountAliasName"][0]
                if len(values["bankAccountAliasName"]) == 1
                else None,
                "currency": values["currency"],
                "timezone": values["timeZone"],
                "from_date": values["queryDateBegin"],
                "to_date": values["queryDateEnd"],
            }
        )
        if checked != values:
            raise CliError(REQUEST_NOT_ALLOWED, "statement scope is not canonical")
        return {
            "tntInstId": TENANT,
            **values,
            "rowStart": row_start,
            "pageSize": PAGE_SIZE,
        }

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        values = parse(scope)
        for row in rows:
            if (
                ("instId" in row and row["instId"] not in values["instIds"])
                or (
                    "bankAccountAliasName" in row
                    and row["bankAccountAliasName"]
                    not in values["bankAccountAliasName"]
                )
                or row.get("currency") != values["currency"]
            ):
                raise CliError(
                    INVALID_RESPONSE,
                    "statement record is outside requested account/currency scope",
                )
            if "tntInstId" in row and row["tntInstId"] != TENANT:
                raise CliError(
                    INVALID_RESPONSE, "statement tenant is outside requested scope"
                )
            value = row.get("valueDate")
            if value is None:
                continue
            try:
                day = compact_date(value)
            except CliError as error:
                raise CliError(
                    INVALID_RESPONSE, "statement valueDate is not a valid date"
                ) from error
            if not values["queryDateBegin"] <= day <= values["queryDateEnd"]:
                raise CliError(
                    INVALID_RESPONSE, "statement valueDate is outside requested window"
                )

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "response envelope is not an object")
        if type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "success is not boolean")
        if document["success"] is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        data = document.get("data")
        if not isinstance(data, dict):
            raise CliError(INVALID_RESPONSE, "response data is not an object")
        rows, total = data.get("data"), data.get("totalCount")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(
                INVALID_RESPONSE, "record container is not a list of objects"
            )
        if type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE, "reported total is not a nonnegative integer"
            )
        for row in rows:
            values = [row.get(field) for field in IDENTITY]
            if any(
                type(value) not in (str, int)
                or (isinstance(value, str) and not value.strip())
                for value in values
            ):
                raise CliError(
                    INVALID_RESPONSE,
                    "statement is missing a typed composite identity field",
                )
        return rows, total


CAPABILITY = StatementInquiry()


class Adapter:
    def history_bounds(self, parameters: dict) -> dict:
        native = request_scope(parameters)
        return {
            "from": datetime.strptime(native["queryDateBegin"], "%Y%m%d")
            .date()
            .isoformat(),
            "to": datetime.strptime(native["queryDateEnd"], "%Y%m%d")
            .date()
            .isoformat(),
        }

    def history_parameters(self, bounds: dict) -> dict:
        return {
            "from_date": bounds["from"].replace("-", ""),
            "to_date": bounds["to"].replace("-", ""),
        }

    def capability(self, parameters: dict[str, Any]) -> Any:
        request_scope(parameters)
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(request_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        selected = parameters.get("fund_direction") or []
        return [
            row
            for row in records
            if not selected or row.get("fundDirection") in selected
        ]


adapter = Adapter()
