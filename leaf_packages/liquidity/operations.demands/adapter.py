"""Native bounded funding-demand List through the host collection SDK."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
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
from dogopencli.temporal import (
    normalize_local_datetime,
    normalize_utc_milliseconds,
    parse_iso_millisecond_instant,
)

TENANT = "GUAPW3SG"
PAGE_SIZE = 5000
PUBLIC_TIME = "%Y-%m-%dT%H:%M:%S"
NATIVE_TIME = "%Y-%m-%d %H:%M:%S"
SOURCE_ZONE = timezone(timedelta(hours=8))
STRING_FIELDS = (
    "taskId",
    "tntInstId",
    "source",
    "sourceId",
    "instId",
    "bankId",
    "currency",
    "amount",
    "executeTime",
    "status",
    "instructionStatus",
    "riskActionType",
    "isNeedReview",
)


def timestamp(value: Any, format_string: str) -> datetime:
    if not isinstance(value, str) or len(value) != 19 or not value.isascii():
        raise ValueError
    normalized = normalize_local_datetime(value)
    parsed = datetime.strptime(normalized, NATIVE_TIME)
    if parsed.strftime(format_string) != value:
        raise ValueError
    return parsed


def native_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    try:
        start = timestamp(parameters.get("from_time"), PUBLIC_TIME)
        end = timestamp(parameters.get("to_time"), PUBLIC_TIME)
        if start > end:
            raise ValueError
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT,
            "demands requires ordered --from-time/--to-time YYYY-MM-DDTHH:mm:ss; "
            "Beijing GMT+08:00; offsets are unsupported",
            exit_code=EXIT_USAGE,
        ) from error
    return {
        "tntInstId": TENANT,
        "source": ["FUND_REQUIRE"],
        "startExecuteTime": start.strftime(NATIVE_TIME),
        "endExecuteTime": end.strftime(NATIVE_TIME),
    }


def validate_record(row: Any) -> None:
    if not isinstance(row, dict):
        raise CliError(INVALID_RESPONSE, "funding demand is not an object")
    if row.get("tntInstId") != TENANT or row.get("source") != "FUND_REQUIRE":
        raise CliError(
            INVALID_RESPONSE, "funding demand tenant or source contradicts scope"
        )
    for field in STRING_FIELDS:
        if field in row and not isinstance(row[field], str):
            raise CliError(
                INVALID_RESPONSE, f"funding demand {field} must be a native string"
            )
    for field in ("taskId", "currency", "amount", "executeTime"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise CliError(
                INVALID_RESPONSE, f"funding demand {field} is missing or blank"
            )
    try:
        if not Decimal(row["amount"]).is_finite():
            raise InvalidOperation
        timestamp(row["executeTime"], NATIVE_TIME)
    except (InvalidOperation, ValueError) as error:
        raise CliError(
            INVALID_RESPONSE, "invalid native demand amount or execution time"
        ) from error


class Inquiry:
    name = "liquidity.operations.demands.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="GET",
            host="iliquidity.alipay.com",
            path="/riskActionTaskQuery.json",
            page_size=PAGE_SIZE,
            one_based=False,
            allowed_body_keys=frozenset({"tntInstId", "riskActionTaskQueryVO"}),
            fixed_body_values=(("tntInstId", TENANT),),
            json_body_contracts=(
                (
                    "riskActionTaskQueryVO",
                    frozenset({*values, "rowStart", "pageSize"}),
                    tuple(values.items()) + (("rowStart", 0), ("pageSize", PAGE_SIZE)),
                    frozenset({PAGE_SIZE}),
                ),
            ),
        )

    def page_body(self, scope: str, position: int, page_size: int) -> dict[str, Any]:
        if (
            scope != canonical(self.values)
            or type(position) is not int
            or position != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "demands has one fixed bounded inquiry")
        return {
            "tntInstId": TENANT,
            "riskActionTaskQueryVO": json.dumps(
                {**self.values, "rowStart": 0, "pageSize": PAGE_SIZE}
            ),
        }

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "demand response is not JSON") from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            raise CliError(INVALID_RESPONSE, "invalid demand business marker")
        if not document["resultFlag"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        node = document.get("result")
        if not isinstance(node, dict) or type(node.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "invalid demand inner business marker")
        if not node["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        rows, total = node.get("dataValue"), node.get("count")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid demand rows or native count")
        if total > PAGE_SIZE or len(rows) > PAGE_SIZE:
            raise CliError(
                INVALID_RESPONSE, "demand scope exceeds 5000; narrow execution bounds"
            )
        for row in rows:
            validate_record(row)
        return ParsedPage(rows, 0, PAGE_SIZE, total, -(-total // PAGE_SIZE))

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        if scope != canonical(self.values):
            raise CliError(INVALID_RESPONSE, "demand acquisition scope is inconsistent")
        for row in rows:
            if (
                not self.values["startExecuteTime"]
                <= row["executeTime"]
                <= self.values["endExecuteTime"]
            ):
                raise CliError(
                    INVALID_RESPONSE, "demand execution time is outside query scope"
                )


class DetailInquiry:
    name = "liquidity.operations.demands.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/riskActionTaskQueryDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"taskId", "tntInstId"}),
        encoding="query",
        fixed_body_values=(("tntInstId", TENANT),),
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT, "detail lookup must be nonempty", exit_code=2
            )
        value = identity
        return {"taskId": value, "tntInstId": TENANT}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "detail response is not JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "detail envelope is not an object")
        if type(document.get("resultFlag")) is not bool:
            raise CliError(INVALID_RESPONSE, "detail success marker is not boolean")
        if not document["resultFlag"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected the detail inquiry")
        result = document.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "detail inner success marker is invalid")
        if not result["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected the detail inquiry")
        detail = result.get("riskActionVO")
        if not isinstance(detail, dict) or not detail:
            raise CliError(INVALID_RESPONSE, "detail root is not a nonempty object")
        if not isinstance(detail.get("taskId"), str) or detail["taskId"] != identity:
            raise CliError(
                INVALID_RESPONSE, "detail identity differs from the requested lookup"
            )
        tenant = detail.get("tntInstId")
        if tenant not in (None, "", TENANT):
            raise CliError(
                INVALID_RESPONSE, "detail tenant contradicts requested scope"
            )
        if detail.get("source") != "FUND_REQUIRE":
            raise CliError(INVALID_RESPONSE, "detail source is not FUND_REQUIRE")
        return detail


DETAIL = DetailInquiry()


class Adapter:
    def history_bounds(self, parameters: dict) -> dict:
        native = native_scope(parameters)
        return {
            bound: normalize_utc_milliseconds(
                datetime.strptime(native[field], NATIVE_TIME).replace(
                    tzinfo=SOURCE_ZONE
                )
            )
            for bound, field in (("from", "startExecuteTime"), ("to", "endExecuteTime"))
        }

    def history_parameters(self, bounds: dict) -> dict:
        values = {
            key: parse_iso_millisecond_instant(bounds[bound])
            for key, bound in (("from_time", "from"), ("to_time", "to"))
        }
        if any(value.microsecond for value in values.values()):
            raise CliError(
                INVALID_ARGUMENT,
                "demands cannot express fractional-second windows",
                exit_code=EXIT_USAGE,
            )
        return {
            key: value.astimezone(SOURCE_ZONE).strftime(PUBLIC_TIME)
            for key, value in values.items()
        }

    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL

    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry(native_scope(parameters))

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
