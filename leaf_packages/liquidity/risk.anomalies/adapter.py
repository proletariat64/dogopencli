"""Native risk anomalies List and detail through the host SDK."""

from datetime import datetime, timedelta
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
MODE = "RISK_ALERT"
PAGE_SIZE = 50
TIME_FORMAT = "%Y-%m-%d %H:%M:%S（GMT+08）"
TIME_FIELDS = (
    "gmtCreate",
    "gmtModified",
    "firstAlertTime",
    "nextAlertTime",
    "closeRiskTime",
)
INTEGER_FIELDS = ("riskProcessingTime", "alertNum")
STRING_FIELDS = (
    "id",
    "riskMode",
    "gmtCreate",
    "gmtModified",
    "riskScenario",
    "riskCategory",
    "riskEvent",
    "riskStatus",
    "riskLevel",
    "riskAlertLevel",
    "riskObject",
    "riskSourceObject",
    "firstAlertTime",
    "nextAlertTime",
    "closeRiskTime",
)


def native_scope(parameters: dict[str, Any]) -> dict[str, str]:
    dates = []
    for field in ("from_date", "to_date"):
        value = parameters.get(field)
        try:
            if (
                not isinstance(value, str)
                or len(value) != 8
                or not value.isascii()
                or not value.isdigit()
            ):
                raise ValueError
            day = datetime.strptime(value, "%Y%m%d")
            if day.strftime("%Y%m%d") != value:
                raise ValueError
        except (TypeError, ValueError) as error:
            raise CliError(
                INVALID_ARGUMENT,
                "risk dates require valid YYYYMMDD bounds",
                exit_code=EXIT_USAGE,
            ) from error
        dates.append(day)
    if dates[1] - dates[0] != timedelta(days=1):
        raise CliError(
            INVALID_ARGUMENT,
            "risk --to-date must be exactly one day after --from-date",
            exit_code=EXIT_USAGE,
        )
    return {
        "tntInstId": TENANT,
        "riskMode": MODE,
        "timeZone": "GMT+08",
        "startTime": dates[0].strftime("%Y-%m-%d"),
        "endTime": dates[1].strftime("%Y-%m-%d"),
    }


def validate_record(row: Any) -> None:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("id"), str)
        or not row["id"].strip()
    ):
        raise CliError(INVALID_RESPONSE, "risk id must be a nonempty native string")
    if row.get("riskMode") != MODE:
        raise CliError(INVALID_RESPONSE, "risk record mode contradicts query scope")
    if "tntInstId" in row and row["tntInstId"] != TENANT:
        raise CliError(INVALID_RESPONSE, "risk record tenant contradicts query scope")
    if not row.get("gmtCreate"):
        raise CliError(INVALID_RESPONSE, "risk record has no native Risk Time")
    for field in STRING_FIELDS:
        if field in row and not isinstance(row[field], str):
            raise CliError(INVALID_RESPONSE, f"risk {field} must be a native string")
    for field in INTEGER_FIELDS:
        if field in row and type(row[field]) is not int:
            raise CliError(INVALID_RESPONSE, f"risk {field} must be a native integer")
    for field in TIME_FIELDS:
        value = row.get(field)
        if value:
            try:
                if datetime.strptime(value, TIME_FORMAT).strftime(TIME_FORMAT) != value:
                    raise ValueError
            except (TypeError, ValueError) as error:
                raise CliError(
                    INVALID_RESPONSE,
                    f"risk {field} has an unverified native time format",
                ) from error


class Inquiry:
    name = "liquidity.risk.anomalies.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/api/risk/event/getAll.json",
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
            raise CliError(REQUEST_NOT_ALLOWED, "unverified risk List request")
        return {**self.values, "rowStart": row_start, "pageSize": page_size}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(
                INVALID_RESPONSE, "risk response is not valid JSON"
            ) from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "invalid risk business success marker")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        node = document.get("data")
        if not isinstance(node, dict):
            raise CliError(INVALID_RESPONSE, "risk data is not an object")
        rows, total = node.get("data"), node.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid risk records or native total")
        for row in rows:
            validate_record(row)
        return rows, total


class DetailInquiry:
    name = "liquidity.risk.anomalies.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/api/risk/event/detail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"riskEventId"}),
        fixed_body_values=(),
        encoding="form",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT,
                "detail identity must be a nonempty string",
                exit_code=2,
            )
        return {"riskEventId": identity}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "detail success marker is not boolean")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        detail = document
        detail = detail.get("data")
        if not isinstance(detail, dict):
            raise CliError(INVALID_RESPONSE, "detail container is not an object")
        value = detail.get("id")
        if not isinstance(value, str) or not value.strip() or value != identity:
            raise CliError(INVALID_RESPONSE, "detail identity does not match request")
        if detail.get("riskMode") != "RISK_ALERT":
            raise CliError(INVALID_RESPONSE, "detail mode contradicts requested scope")
        if "tntInstId" in detail and detail["tntInstId"] != TENANT:
            raise CliError(
                INVALID_RESPONSE, "detail tenant contradicts requested scope"
            )
        return detail


DETAIL = DetailInquiry()


class Adapter:
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
