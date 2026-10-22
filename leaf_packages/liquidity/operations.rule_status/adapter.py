"""One fixed-width native transfer-rule run overview with explicit UTC scope."""

from datetime import datetime, timezone
from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse
from dogopencli.temporal import parse_iso_instant

TENANT = "GUAPW3SG"
PAGE_SIZE = 5000
VO = "transferRuleRecordQueryRequesVO"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
FIELDS = (
    "id",
    "ruleId",
    "executeStatus",
    "createdOrder",
    "bizNo",
    "orderStatus",
    "expectTriggerTime",
    "realTriggerTime",
    "gmtCreate",
    "gmtModified",
)
TEMPLATE = {
    "tntInstId": TENANT,
    "queryDetailed": "false",
    "executeStatusList": [],
    "createdOrderList": [],
    "orderStatusList": [],
}


def selection(parameters: dict[str, Any]) -> dict[str, str]:
    try:
        result = {
            field: parse_iso_instant(parameters.get(name))
            .astimezone(timezone.utc)
            .strftime(TIME_FORMAT)
            for name, field in (
                ("trigger_from", "triggerStartTime"),
                ("trigger_to", "triggerEndTime"),
            )
        }
        if result["triggerStartTime"] > result["triggerEndTime"]:
            raise ValueError
        return result
    except (ValueError, OverflowError) as error:
        raise CliError(
            INVALID_ARGUMENT,
            "ordered trigger bounds require whole-second ISO instants with Z "
            "or explicit numeric offset",
            exit_code=2,
        ) from error


def checked_scope(scope: str) -> dict[str, str]:
    try:
        values = parse(scope)
        if not isinstance(values, dict) or set(values) != {
            "triggerStartTime",
            "triggerEndTime",
        }:
            raise ValueError
        for value in values.values():
            if (
                not isinstance(value, str)
                or not value.isascii()
                or len(value) != 19
                or datetime.strptime(value, TIME_FORMAT).strftime(TIME_FORMAT) != value
            ):
                raise ValueError
        if values["triggerStartTime"] > values["triggerEndTime"]:
            raise ValueError
        return values
    except (ValueError, UnicodeError, OverflowError) as error:
        raise CliError(REQUEST_NOT_ALLOWED, "unverified rule-status scope") from error


def epoch(value: str) -> int:
    instant = datetime.strptime(value, TIME_FORMAT).replace(tzinfo=timezone.utc)
    # timedelta components avoid any floating-point timestamp conversion.
    delta = instant - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1000


def project(row: Any) -> dict[str, Any]:
    if (
        not isinstance(row, dict)
        or row.get("tntInstId") != TENANT
        or type(row.get("id")) is not int
        or row["id"] <= 0
    ):
        raise CliError(
            INVALID_RESPONSE,
            "rule status needs native positive integer id and exact tenant",
        )
    rule = row.get("ruleId")
    if type(rule) not in (str, int) or isinstance(rule, str) and not rule.strip():
        raise CliError(INVALID_RESPONSE, "rule status ruleId is missing or invalid")
    for field in ("executeStatus", "createdOrder"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise CliError(
                INVALID_RESPONSE, "rule status marker must be a nonblank native string"
            )
    if (
        any(not isinstance(row.get(field), str) for field in ("bizNo", "orderStatus"))
        or "realTriggerTime" not in row
    ):
        raise CliError(
            INVALID_RESPONSE,
            "rule status references/realTriggerTime are missing or invalid",
        )
    for field in ("expectTriggerTime", "realTriggerTime", "gmtCreate", "gmtModified"):
        if field not in row or field == "realTriggerTime" and row[field] is None:
            continue
        if type(row[field]) is not int or row[field] <= 0:
            raise CliError(
                INVALID_RESPONSE,
                "rule status timestamp must be positive native epoch milliseconds",
            )
    if "expectTriggerTime" not in row:
        raise CliError(INVALID_RESPONSE, "rule status expected trigger time is missing")
    return {field: row[field] for field in FIELDS if field in row}


class Inquiry:
    name = "liquidity.operations.rule_status.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/queryTransferRulePreRunRecords.json",
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
                        *TEMPLATE,
                        "rowStart",
                        "pageSize",
                        "triggerStartTime",
                        "triggerEndTime",
                    }
                ),
                (("tntInstId", TENANT), ("queryDetailed", "false"), ("rowStart", 0)),
                frozenset({PAGE_SIZE}),
            ),
        ),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        values = checked_scope(scope)
        if (
            type(row_start) is not int
            or row_start != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "rule status permits only one fixed-width response"
            )
        return {
            "tntInstId": TENANT,
            VO: canonical({**TEMPLATE, **values, "rowStart": 0, "pageSize": PAGE_SIZE}),
        }

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                INVALID_RESPONSE, "rule status response is not JSON"
            ) from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            raise CliError(INVALID_RESPONSE, "rule status resultFlag must be boolean")
        if not document["resultFlag"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected rule-status inquiry"
            )
        result = document.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            raise CliError(
                INVALID_RESPONSE, "rule status result.success must be boolean"
            )
        if not result["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected rule-status inquiry"
            )
        rows, total = result.get("data"), result.get("count")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE,
                "rule status needs native array and nonnegative integer total",
            )
        return ParsedPage(
            [project(row) for row in rows], 0, PAGE_SIZE, total, -(-total // PAGE_SIZE)
        )

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        values = checked_scope(scope)
        lower, upper = (
            epoch(values["triggerStartTime"]),
            epoch(values["triggerEndTime"]) + 999,
        )
        if any(not lower <= row["expectTriggerTime"] <= upper for row in rows):
            raise CliError(
                INVALID_RESPONSE,
                "rule status expected trigger is outside requested UTC scope",
            )


LIST = Inquiry()


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


adapter = Adapter()
