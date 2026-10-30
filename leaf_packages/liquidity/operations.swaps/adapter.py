"""Native swap-order List through the host collection SDK."""

import json
import re
from datetime import datetime
from typing import Any

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

TENANT = "GUAPW3SG"
PAGE_SIZE = 1000
AMOUNT_FIELDS = (
    "nearLegCreditAmount",
    "nearLegDebitAmount",
    "farLegCreditAmount",
    "farLegDebitAmount",
    "nearLegFxRate",
    "farLegFxRate",
    "expectNearLegFxRate",
    "expectFarLegFxRate",
)
AMOUNT_TEXT = re.compile(r"[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?")


def business_date(value: Any, format_string: str) -> str:
    if not isinstance(value, str) or not value.isascii():
        raise ValueError
    day = datetime.strptime(value, format_string)
    if day.strftime(format_string) != value:
        raise ValueError
    return day.strftime("%Y%m%d")


def native_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    try:
        start = business_date(parameters.get("from_date"), "%Y-%m-%d")
        end = business_date(parameters.get("to_date"), "%Y-%m-%d")
        if start > end:
            raise ValueError
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT,
            "swaps requires an ordered --from-date/--to-date YYYY-MM-DD pair",
            exit_code=EXIT_USAGE,
        ) from error
    return {
        "tntInstId": TENANT,
        "nearLegDebitEntity": [],
        "nearLegCreditEntity": [],
        "tradeStartDate": start,
        "tradeEndDate": end,
        "nearLegStartDate": "",
        "nearLegEndDate": "",
        "farLegStartDate": "",
        "farLegEndDate": "",
    }


def validate_record(row: Any) -> None:
    if not isinstance(row, dict):
        raise CliError(INVALID_RESPONSE, "swap record is not an object")
    if not isinstance(row.get("dealId"), str) or not row["dealId"].strip():
        raise CliError(INVALID_RESPONSE, "swap dealId must be a nonempty native string")
    if row.get("tntInstId") != TENANT:
        raise CliError(INVALID_RESPONSE, "swap tenant contradicts query scope")
    for field in AMOUNT_FIELDS:
        value = row.get(field)
        if value is not None and (
            not isinstance(value, str)
            or (value.strip() and not AMOUNT_TEXT.fullmatch(value))
        ):
            raise CliError(
                INVALID_RESPONSE,
                f"swap {field} must be a native decimal string or null",
            )
    for field in ("tradeDate", "nearLegValueDate", "farLegValueDate"):
        value = row.get(field)
        if field != "tradeDate" and (value is None or value == ""):
            continue
        try:
            business_date(value, "%Y%m%d")
        except ValueError as error:
            raise CliError(
                INVALID_RESPONSE, f"swap {field} must be valid native YYYYMMDD"
            ) from error
    for field in ("gmtCreate", "gmtModified", "gmtSend", "gmtReturn", "nodeNum"):
        if row.get(field) is not None and type(row[field]) is not int:
            raise CliError(
                INVALID_RESPONSE, f"swap {field} must be a native integer or null"
            )
    if row.get("needReview") is not None and type(row["needReview"]) is not bool:
        raise CliError(
            INVALID_RESPONSE, "swap needReview must be a native boolean or null"
        )


class Inquiry:
    name = "liquidity.operations.swaps.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/swapOrderQuery.json",
            encoding="form",
            page_size=PAGE_SIZE,
            one_based=False,
            allowed_body_keys=frozenset({"tntInstId", "swapOrderQueryVO"}),
            fixed_body_values=(("tntInstId", TENANT),),
            json_body_contracts=(
                (
                    "swapOrderQueryVO",
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
            raise CliError(REQUEST_NOT_ALLOWED, "unverified swap List request")
        return {
            "tntInstId": TENANT,
            "swapOrderQueryVO": json.dumps(
                {**self.values, "rowStart": row_start, "pageSize": PAGE_SIZE}
            ),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "swap response is not JSON") from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            raise CliError(INVALID_RESPONSE, "invalid swap business marker")
        if not document["resultFlag"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        node = document.get("result")
        if not isinstance(node, dict) or type(node.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "invalid swap inner business marker")
        if not node["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        rows, total = node.get("swapOrderVOList"), node.get("count")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid swap rows or native count")
        for row in rows:
            validate_record(row)
        return rows, total

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        if scope != canonical(self.values):
            raise CliError(INVALID_RESPONSE, "swap acquisition scope is inconsistent")
        for row in rows:
            if (
                not self.values["tradeStartDate"]
                <= row["tradeDate"]
                <= self.values["tradeEndDate"]
            ):
                raise CliError(
                    INVALID_RESPONSE, "swap tradeDate is outside query scope"
                )


class Adapter:
    def history_bounds(self, parameters: dict) -> dict:
        native = native_scope(parameters)
        return {
            "from": datetime.strptime(native["tradeStartDate"], "%Y%m%d")
            .date()
            .isoformat(),
            "to": datetime.strptime(native["tradeEndDate"], "%Y%m%d")
            .date()
            .isoformat(),
        }

    def history_parameters(self, bounds: dict) -> dict:
        return {
            "from_date": bounds["from"],
            "to_date": bounds["to"],
        }

    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry(native_scope(parameters))

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
