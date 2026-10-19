"""Bounded decision-report List projection and independent native-root Get."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
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
from dogopencli.temporal import normalize_local_datetime

TENANT = "GUAPW3SG"
PAGE_SIZE = 1000
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
BOUNDS = (
    ("start_from", "startTime"),
    ("start_to", "endTime"),
    ("created_from", "createStartTime"),
    ("created_to", "createEndTime"),
)
STRING_FIELDS = (
    "reportId",
    "groupId",
    "orderNo",
    "reportStatus",
    "operationStatus",
    "status",
    "operationType",
    "decisionMode",
    "executionTimeStart",
    "executionTimeEnd",
    "gmtCreate",
    "gmtModified",
    "decisionCurrency",
    "decisionAmount",
    "debitEntity",
    "creditEntity",
    "debitBankId",
    "creditBankId",
    "debitCurrency",
    "creditCurrency",
    "debitAmount",
    "creditAmount",
    "debitValueDate",
    "creditValueDate",
    "strategyType",
    "needReview",
    "linkType",
    "assetTransactionType",
)
INTEGER_FIELDS = ("version", "genOrder", "timeliness")
FIELDS = ("id", "tntInstId", *STRING_FIELDS, *INTEGER_FIELDS)


def native_time(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value
    ):
        raise ValueError
    if datetime.strptime(value, TIME_FORMAT).strftime(TIME_FORMAT) != value:
        raise ValueError
    return value


def selection(parameters: dict[str, Any]) -> dict[str, str]:
    result = {}
    try:
        for name, field in BOUNDS:
            value = parameters.get(name)
            if not isinstance(value, str) or len(value) != 19 or value[10] != "T":
                raise ValueError
            result[field] = native_time(normalize_local_datetime(value))
        if (
            result["startTime"] > result["endTime"]
            or result["createStartTime"] > result["createEndTime"]
        ):
            raise ValueError
    except (ValueError, OverflowError) as error:
        raise CliError(
            INVALID_ARGUMENT,
            "both inclusive ranges require ordered offset-free YYYY-MM-DDTHH:mm:ss; "
            "source timezone unknown",
            exit_code=2,
        ) from error
    return result


def checked_scope(scope: str) -> dict[str, str]:
    try:
        values = parse(scope)
        if not isinstance(values, dict) or set(values) != {
            field for _, field in BOUNDS
        }:
            raise ValueError
        for value in values.values():
            native_time(value)
        if (
            values["startTime"] > values["endTime"]
            or values["createStartTime"] > values["createEndTime"]
        ):
            raise ValueError
        return values
    except (ValueError, UnicodeError, OverflowError) as error:
        raise CliError(
            REQUEST_NOT_ALLOWED, "unverified decision-report scope"
        ) from error


def business_root(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except (ValueError, UnicodeError) as error:
        raise CliError(INVALID_RESPONSE, "decision response is not JSON") from error
    if not isinstance(document, dict) or type(document.get("success")) is not bool:
        raise CliError(INVALID_RESPONSE, "decision success marker must be boolean")
    if not document["success"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend rejected decision inquiry")
    result = document.get("data")
    if not isinstance(result, dict):
        raise CliError(INVALID_RESPONSE, "decision data must be an object")
    return result


def project(row: Any) -> dict[str, Any]:
    if (
        not isinstance(row, dict)
        or type(row.get("id")) is not int
        or row.get("tntInstId") != TENANT
    ):
        raise CliError(
            INVALID_RESPONSE, "decision requires native integer id and exact tenant"
        )
    if any(
        field in row and not isinstance(row[field], str) for field in STRING_FIELDS
    ) or any(field in row and type(row[field]) is not int for field in INTEGER_FIELDS):
        raise CliError(INVALID_RESPONSE, "decision fields have invalid native types")
    try:
        for field in ("decisionAmount", "debitAmount", "creditAmount"):
            if (
                field in row
                and row[field] != ""
                and not Decimal(row[field]).is_finite()
            ):
                raise ValueError
        native_time(row.get("executionTimeStart"))
        native_time(row.get("gmtCreate"))
    except (ValueError, InvalidOperation, OverflowError) as error:
        raise CliError(
            INVALID_RESPONSE, "decision amount or native timestamp is invalid"
        ) from error
    return {field: row[field] for field in FIELDS if field in row}


class Inquiry:
    name = "liquidity.operations.decisions.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/api/ai/decision/report/getAllNew.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset(
            {
                "tntInstId",
                "startTime",
                "endTime",
                "createStartTime",
                "createEndTime",
                "rowStart",
                "pageSize",
            }
        ),
        fixed_body_values=(("tntInstId", TENANT),),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        values = checked_scope(scope)
        if (
            type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified decision paging")
        return {
            "tntInstId": TENANT,
            **values,
            "rowStart": row_start,
            "pageSize": page_size,
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        result = business_root(body)
        rows, total = result.get("data"), result.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE, "decision List needs native rows and integer total"
            )
        return [project(row) for row in rows], total

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        values = checked_scope(scope)
        for row in rows:
            for field, lower, upper in (
                ("executionTimeStart", "startTime", "endTime"),
                ("gmtCreate", "createStartTime", "createEndTime"),
            ):
                if not values[lower] <= row[field] <= values[upper]:
                    raise CliError(
                        INVALID_RESPONSE,
                        "decision timestamp is outside requested range",
                    )


def lookup(identity: str) -> int:
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9]+", identity):
        raise CliError(
            INVALID_ARGUMENT,
            "lookup requires an ASCII decimal native decision id",
            exit_code=2,
        )
    try:
        return int(identity)
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT, "decision id cannot be represented", exit_code=2
        ) from error


class DetailInquiry:
    name = "liquidity.operations.decisions.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/api/ai/decision/report/getDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"id"}),
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        return {"id": lookup(identity)}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        result = business_root(body)
        if type(result.get("id")) is not int or result["id"] != lookup(identity):
            raise CliError(
                INVALID_RESPONSE, "decision native integer id does not match lookup"
            )
        return result


LIST = Inquiry()
DETAIL = DetailInquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        selection(parameters)
        return LIST

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(selection(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records

    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL


adapter = Adapter()
