"""Native dated forecast records through the offset List SDK."""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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
VO = "bankCashForecastRecordQueryVo"
NULL_BOUNDS = {
    "expectInflowStart": None,
    "expectInflowEnd": None,
    "expectOutflowStart": None,
    "expectOutflowEnd": None,
    "expectMinBalance": None,
    "expectMaxBalance": None,
}
SCOPE_KEYS = {"valueStartDay", "valueEndDay", "recordStartTime", "recordEndTime"}
AMOUNTS = (
    "forecastBalance",
    "minimumBalance",
    "openBalance",
    "cashFlowTransIn",
    "cashFlowTransOut",
)
INTEGERS = ("forecastBatchNo", "gmtCreate", "gmtModified", "lastestFlag")


def normalize(value: Any, *, time: bool = False) -> str:
    pattern = (
        r"(?:[0-9]{6}|[0-9]{2}:[0-9]{2}:[0-9]{2})"
        if time
        else r"(?:[0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2})"
    )
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise CliError(INVALID_ARGUMENT, "invalid time or date format", exit_code=2)
    wire = value.replace(":" if time else "-", "")
    try:
        datetime.strptime(wire, "%H%M%S" if time else "%Y%m%d")
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT, "invalid calendar date or clock time", exit_code=2
        ) from error
    return wire


def selection(parameters: dict[str, Any], *, required: bool) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for parameter, field, is_time, default in (
        ("from_date", "valueStartDay", False, None),
        ("to_date", "valueEndDay", False, None),
        ("record_from_time", "recordStartTime", True, "000000"),
        ("record_to_time", "recordEndTime", True, "235959"),
    ):
        value = parameters.get(parameter)
        if value is None and required:
            value = default
        if value is not None:
            values[field] = normalize(value, time=is_time)
    if required and not SCOPE_KEYS <= values.keys():
        raise CliError(
            INVALID_ARGUMENT, "both inclusive date bounds are required", exit_code=2
        )
    for start, end in (
        ("valueStartDay", "valueEndDay"),
        ("recordStartTime", "recordEndTime"),
    ):
        if start in values and end in values and values[start] > values[end]:
            raise CliError(
                INVALID_ARGUMENT, "window start is after its end", exit_code=2
            )
    aliases = parameters.get("account_alias")
    if aliases is not None:
        if (
            not isinstance(aliases, (list, tuple))
            or not aliases
            or any(not isinstance(v, str) or not v.strip() for v in aliases)
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "account-alias requires nonempty exact values",
                exit_code=2,
            )
        values["aliasName"] = list(dict.fromkeys(aliases))
    return values


@dataclass(frozen=True)
class Inquiry:
    with_alias: bool = False

    name = "liquidity.forecast.results.list"
    page_url = LIQUIDITY_STARTUP_URL

    @property
    def contract(self) -> EndpointContract:
        return EndpointContract(
            method="GET",
            host="iliquidity.alipay.com",
            path="/bankCashForecastRecordQuery.json",
            page_size=PAGE_SIZE,
            one_based=False,
            encoding="query",
            allowed_body_keys=frozenset({"tntInstId", VO}),
            fixed_body_values=(("tntInstId", TENANT),),
            json_body_contracts=(
                (
                    VO,
                    frozenset(
                        {
                            "tntInstId",
                            *NULL_BOUNDS,
                            *SCOPE_KEYS,
                            *({"aliasName"} if self.with_alias else set()),
                            "rowStart",
                            "pageSize",
                        }
                    ),
                    (("tntInstId", TENANT), *tuple(NULL_BOUNDS.items())),
                    frozenset({PAGE_SIZE}),
                ),
            ),
        )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        try:
            values = parse(scope)
            if (
                not isinstance(values, dict)
                or not SCOPE_KEYS <= values.keys()
                or set(values) - SCOPE_KEYS - {"aliasName"}
            ):
                raise ValueError
            checked = selection(
                {
                    "from_date": values["valueStartDay"],
                    "to_date": values["valueEndDay"],
                    "record_from_time": values["recordStartTime"],
                    "record_to_time": values["recordEndTime"],
                    "account_alias": values.get("aliasName"),
                },
                required=True,
            )
            if values != checked:
                raise ValueError
        except (ValueError, UnicodeError, CliError) as error:
            raise CliError(REQUEST_NOT_ALLOWED, "unverified forecast scope") from error
        if (
            type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified forecast offset or width")
        inner = {
            "tntInstId": TENANT,
            **NULL_BOUNDS,
            **values,
            "rowStart": row_start,
            "pageSize": PAGE_SIZE,
        }
        return {"tntInstId": TENANT, VO: canonical(inner)}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            raise CliError(INVALID_RESPONSE, "forecast resultFlag must be boolean")
        if not document["resultFlag"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected forecast inquiry")
        data = document.get("result")
        if not isinstance(data, dict) or type(data.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "forecast inner success must be boolean")
        if not data["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected forecast inquiry")
        rows, total = data.get("dataValue"), data.get("count")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE,
                "forecast requires an array and nonnegative integer total",
            )
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not row["id"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE, "forecast requires native nonempty string id"
                )
            for field in AMOUNTS:
                value = row.get(field)
                valid = (
                    value is None
                    or type(value) is int
                    or isinstance(value, Decimal)
                    and value.is_finite()
                    or isinstance(value, str)
                    and (
                        not value.strip()
                        or re.fullmatch(
                            r"[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?",
                            value,
                        )
                        is not None
                    )
                )
                if not valid:
                    raise CliError(
                        INVALID_RESPONSE,
                        "forecast amount has an unverified type or value",
                    )
            if any(
                row.get(field) is not None and type(row[field]) is not int
                for field in INTEGERS
            ):
                raise CliError(
                    INVALID_RESPONSE, "forecast integer has an unverified type"
                )
            for field, time in (("valueDate", False), ("recordCreateTime", True)):
                try:
                    if normalize(row.get(field), time=time) != row[field]:
                        raise ValueError
                except (CliError, ValueError) as error:
                    raise CliError(
                        INVALID_RESPONSE, "forecast native date or time is invalid"
                    ) from error
        return rows, total

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        values = parse(scope)
        for row in rows:
            if (
                not values["valueStartDay"] <= row["valueDate"] <= values["valueEndDay"]
                or not values["recordStartTime"]
                <= row["recordCreateTime"]
                <= values["recordEndTime"]
                or (
                    "aliasName" in values
                    and row.get("bankAccountAliasName") not in values["aliasName"]
                )
                or (row.get("tntInstId") not in (None, "", TENANT))
            ):
                raise CliError(
                    INVALID_RESPONSE, "forecast record is outside requested scope"
                )


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        values = selection(parameters, required=True)
        return Inquiry(with_alias="aliasName" in values)

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(selection(parameters, required=True))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        values = selection(parameters, required=False)
        return [
            row
            for row in records
            if (
                "aliasName" not in values
                or row.get("bankAccountAliasName") in values["aliasName"]
            )
            and (
                "valueStartDay" not in values
                or row["valueDate"] >= values["valueStartDay"]
            )
            and (
                "valueEndDay" not in values or row["valueDate"] <= values["valueEndDay"]
            )
            and (
                "recordStartTime" not in values
                or row["recordCreateTime"] >= values["recordStartTime"]
            )
            and (
                "recordEndTime" not in values
                or row["recordCreateTime"] <= values["recordEndTime"]
            )
        ]


adapter = Adapter()
