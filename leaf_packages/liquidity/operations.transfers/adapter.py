"""Native transfer-order List through the host collection SDK."""

import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    EXIT_USAGE,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse
from dogopencli.temporal import normalize_local_datetime, parse_date_or_instant

TENANT = "GUAPW3SG"
PAGE_SIZE = 1000
BEIJING = timezone(timedelta(hours=8))
PACIFIC = ZoneInfo("America/Los_Angeles")
ORDER = "__dogopencli_transfer_order"
STRING_FIELDS = (
    "orderNo",
    "orderId",
    "reportId",
    "tntInstId",
    "gmtCreate",
    "gmtModified",
    "debitValueDate",
    "creditValueDate",
    "debitEntity",
    "creditEntity",
    "debitBankId",
    "creditBankId",
    "debitCurrency",
    "creditCurrency",
    "debitAmount",
    "creditAmount",
    "orderStatus",
    "receiptStatus",
    "executeResult",
    "scene",
    "businessType",
    "orderType",
    "orderSource",
    "decisionMode",
)


def business_dates(parameters: dict[str, Any]) -> list[date]:
    dates = []
    try:
        for field in ("from_date", "to_date"):
            value = parameters.get(field)
            day = parse_date_or_instant(value)
            if type(day) is not date:
                raise ValueError
            dates.append(day)
        if dates[0] > dates[1]:
            raise ValueError
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT,
            "transfers requires an ordered --from-date/--to-date YYYY-MM-DD pair",
            exit_code=EXIT_USAGE,
        ) from error
    return dates


def native_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    start, end = business_dates(parameters)
    try:
        lower = datetime.combine(start, time.min, BEIJING).astimezone(PACIFIC)
        upper = datetime.combine(end, time(23, 59, 59), BEIJING).astimezone(PACIFIC)
    except OverflowError as error:
        raise CliError(
            INVALID_ARGUMENT,
            "transfer dates exceed the supported query clock",
            exit_code=EXIT_USAGE,
        ) from error
    return {
        "tntInstId": TENANT,
        "debitEntity": [],
        "creditEntity": [],
        "transactionStartDate": lower.strftime("%Y-%m-%d %H:%M:%S"),
        "transactionEndDate": upper.strftime("%Y-%m-%d %H:%M:%S"),
        "debitStartDate": "",
        "debitEndDate": "",
        "creditStartDate": "",
        "creditEndDate": "",
    }


def validate_record(row: Any) -> None:
    if not isinstance(row, dict):
        raise CliError(INVALID_RESPONSE, "transfer record is not an object")
    if not isinstance(row.get("orderNo"), str) or not row["orderNo"].strip():
        raise CliError(
            INVALID_RESPONSE, "transfer orderNo must be a nonempty native string"
        )
    if row.get("tntInstId") != TENANT:
        raise CliError(INVALID_RESPONSE, "transfer tenant contradicts query scope")
    for field in STRING_FIELDS:
        value = row.get(field)
        if value is not None and not isinstance(value, str):
            raise CliError(
                INVALID_RESPONSE, f"transfer {field} must be a native string or null"
            )
    for field in ("debitAmount", "creditAmount"):
        value = row.get(field)
        if value is None or value == "":
            continue
        try:
            if not Decimal(value).is_finite():
                raise InvalidOperation
        except InvalidOperation as error:
            raise CliError(
                INVALID_RESPONSE, f"transfer {field} is not a finite monetary string"
            ) from error
    value = row.get("gmtReturnFinnet")
    if value is not None and type(value) is not int:
        raise CliError(
            INVALID_RESPONSE, "transfer gmtReturnFinnet must be an integer or null"
        )


class Inquiry:
    name = "liquidity.operations.transfers.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/transferOrderQuery.json",
            encoding="form",
            page_size=PAGE_SIZE,
            one_based=False,
            internal_fields=(ORDER,),
            allowed_body_keys=frozenset({"tntInstId", "transferOrderQueryRequestVO"}),
            fixed_body_values=(("tntInstId", TENANT),),
            json_body_contracts=(
                (
                    "transferOrderQueryRequestVO",
                    frozenset({*values, "rowStart", "pageSize"}),
                    tuple(values.items()) + (("pageSize", PAGE_SIZE),),
                    frozenset({PAGE_SIZE}),
                ),
            ),
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
            raise CliError(REQUEST_NOT_ALLOWED, "unverified transfer List request")
        return {
            "tntInstId": TENANT,
            "transferOrderQueryRequestVO": json.dumps(
                {**self.values, "rowStart": row_start, "pageSize": PAGE_SIZE}
            ),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "transfer response is not JSON") from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            raise CliError(INVALID_RESPONSE, "invalid transfer business marker")
        if not document["resultFlag"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        node = document.get("result")
        if not isinstance(node, dict) or type(node.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "invalid transfer inner business marker")
        if not node["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        rows, total, inner_total = (
            node.get("data"),
            document.get("count"),
            node.get("count"),
        )
        if (
            not isinstance(rows, list)
            or type(total) is not int
            or total < 0
            or type(inner_total) is not int
            or inner_total != total
        ):
            raise CliError(
                INVALID_RESPONSE, "invalid transfer rows or disagreeing native counts"
            )
        selected = []
        for row in rows:
            validate_record(row)
            if ORDER in row:
                raise CliError(INVALID_RESPONSE, "transfer reserved field collision")
            timestamp = row.get("gmtModified")
            try:
                if not isinstance(timestamp, str) or not timestamp.endswith(
                    "（GMT+08）"
                ):
                    raise ValueError
                local = timestamp.removesuffix("（GMT+08）")
                normalized = normalize_local_datetime(local)
                if normalized != local:
                    raise ValueError
                ordering = int(
                    normalized.replace("-", "").replace(" ", "").replace(":", "")
                )
            except ValueError as error:
                raise CliError(
                    INVALID_RESPONSE, "invalid transfer native gmtModified GMT+08 clock"
                ) from error
            selected.append({**row, ORDER: ordering})
        return selected, total


class DetailInquiry:
    name = "liquidity.operations.transfers.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/transferOrderQueryDetail.json",
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
        document = document.get("baseResult")
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "detail baseResult is not an object")
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
    def history_bounds(self, parameters: dict[str, Any]) -> dict[str, str]:
        start, end = business_dates(parameters)
        return {"from": start.isoformat(), "to": end.isoformat()}

    def history_parameters(self, bounds: dict[str, str]) -> dict[str, str]:
        parameters = {"from_date": bounds["from"], "to_date": bounds["to"]}
        business_dates(parameters)
        return parameters

    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL

    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry(native_scope(parameters))

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in row.items() if key != ORDER}
            for row in records
        ]


adapter = Adapter()
