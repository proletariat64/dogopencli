"""Independent native return sources and reviewed pure parent assembly."""

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
SOURCES = ("accrual", "cash")


def date_pair(parameters: dict[str, Any], prefix: str) -> tuple[str, str]:
    bounds = []
    for suffix in ("from_date", "to_date"):
        value = parameters.get(prefix + "_" + suffix)
        try:
            if (
                not isinstance(value, str)
                or len(value) != 8
                or not value.isascii()
                or not value.isdigit()
            ):
                raise ValueError
            if datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d") != value:
                raise ValueError
        except ValueError as error:
            raise CliError(
                INVALID_ARGUMENT, prefix + " date bounds require YYYYMMDD", exit_code=2
            ) from error
        bounds.append(value)
    if bounds[0] > bounds[1]:
        raise CliError(INVALID_ARGUMENT, prefix + " start is after end", exit_code=2)
    return bounds[0], bounds[1]


def source_values(name: str, parameters: dict[str, Any]) -> dict[str, Any]:
    if name not in SOURCES:
        raise CliError(INVALID_ARGUMENT, "unknown returns source", exit_code=2)
    values = {"tntInstId": TENANT, "timeZone": "GMT+08"}
    if name == "accrual":
        start, end = date_pair(parameters, "accrual")
        selected = parameters.get("accrual_investment_no") or []
        if not isinstance(selected, list) or any(
            not isinstance(value, str) or not value.strip() for value in selected
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "accrual investment references must be nonempty strings",
                exit_code=2,
            )
        values.update(
            queryBeginTime=start, queryEndTime=end, transactionId=list(selected)
        )
    else:
        start, end = date_pair(parameters, "settlement")
        values.update(
            settlementDateBegin=start,
            settlementDateEnd=end,
            postingDateBegin="",
            postingDateEnd="",
        )
    return values


def native_string(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CliError(
            INVALID_RESPONSE,
            "native return field " + field + " must be a nonempty string",
        )
    return value


def child_identity(name: str, row: Any) -> tuple[str, ...]:
    if not isinstance(row, dict):
        raise CliError(INVALID_RESPONSE, "native return child is not an object")
    if "tntInstId" in row and row["tntInstId"] != TENANT:
        raise CliError(INVALID_RESPONSE, "return child tenant contradicts scope")
    if name == "accrual":
        return native_string(row, "investmentNo"), native_string(row, "transactionDate")
    if name == "cash":
        native_string(row, "transactionId")
        native_string(row, "settlementDate")
        return (native_string(row, "id"),)
    raise CliError(INVALID_RESPONSE, "unknown return source")


class SourceInquiry:
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, source: str, values: dict[str, Any]) -> None:
        self.source = source
        self.values = values
        self.name = "liquidity.investment.returns.list." + source
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/accrualBaseList.json"
            if source == "accrual"
            else "/cashBaseList.json",
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
            raise CliError(
                REQUEST_NOT_ALLOWED, "unqualified return source scope or offset"
            )
        return {**self.values, "rowStart": row_start, "pageSize": PAGE_SIZE}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            value = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                INVALID_RESPONSE, "return response is not valid JSON"
            ) from error
        if not isinstance(value, dict) or type(value.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "return success marker is not boolean")
        if not value["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        node = value.get("data")
        if not isinstance(node, dict):
            raise CliError(INVALID_RESPONSE, "return source data is not an object")
        rows, total = node.get("data"), node.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid return records or native total")
        for row in rows:
            child_identity(self.source, row)
            if self.source == "accrual":
                if (
                    not self.values["queryBeginTime"]
                    <= row["transactionDate"]
                    <= self.values["queryEndTime"]
                ):
                    raise CliError(
                        INVALID_RESPONSE,
                        "accrual transactionDate contradicts source scope",
                    )
                selected = self.values["transactionId"]
                if selected and row["investmentNo"] not in selected:
                    raise CliError(
                        INVALID_RESPONSE,
                        "accrual parent contradicts requested references",
                    )
            elif (
                not self.values["settlementDateBegin"]
                <= row["settlementDate"]
                <= self.values["settlementDateEnd"]
            ):
                raise CliError(
                    INVALID_RESPONSE, "cash settlementDate contradicts source scope"
                )
        return rows, total


class Adapter:
    def source_scope(self, name: str, parameters: dict[str, Any]) -> str:
        return canonical(source_values(name, parameters))

    def source_capability(self, name: str, parameters: dict[str, Any]) -> SourceInquiry:
        return SourceInquiry(name, source_values(name, parameters))

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical({name: source_values(name, parameters) for name in SOURCES})

    def assemble(
        self,
        records_by_source: dict[str, list[dict[str, Any]]],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if set(records_by_source) != set(SOURCES):
            raise CliError(
                INVALID_RESPONSE, "both complete return sources are required"
            )
        roots = {}
        for source in SOURCES:
            children = records_by_source[source]
            if not isinstance(children, list):
                raise CliError(
                    INVALID_RESPONSE, "return source records are not an array"
                )
            seen = set()
            for child in children:
                identity = child_identity(source, child)
                if identity in seen:
                    raise CliError(
                        INVALID_RESPONSE, "ambiguous native return child identity"
                    )
                seen.add(identity)
                parent = child[
                    "investmentNo" if source == "accrual" else "transactionId"
                ]
                if parent not in roots:
                    roots[parent] = {"investmentNo": parent, "accrual": [], "cash": []}
                roots[parent][source].append(child)
        return list(roots.values())

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
