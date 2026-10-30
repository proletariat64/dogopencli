"""Native investment decision task inquiries through the host SDK."""

from datetime import datetime, timedelta, timezone
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
TASK_TYPES = ("FUND_DECISION_TASK", "PRODUCT_DECISION_TASK")
WIDTHS = (5000, 10)
SOURCE_ZONE = timezone(timedelta(hours=8))
NAME = "liquidity.investment.strategy_results"


def task_type(parameters: dict[str, Any]) -> str:
    value = parameters.get("task_type")
    if value not in TASK_TYPES:
        raise CliError(
            INVALID_ARGUMENT, "an explicit native task-type is required", exit_code=2
        )
    return value


def native_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    kind = task_type(parameters)
    days = []
    for key in ("from_date", "to_date"):
        value = parameters.get(key)
        try:
            if not isinstance(value, str) or not value.isascii():
                raise ValueError
            form = "%Y%m%d" if len(value) == 8 else "%Y-%m-%d"
            day = datetime.strptime(value, form)
            if day.strftime(form) != value:
                raise ValueError
        except (TypeError, ValueError) as error:
            raise CliError(
                INVALID_ARGUMENT,
                "dates require valid YYYY-MM-DD or YYYYMMDD",
                exit_code=2,
            ) from error
        days.append(day)
    if days[0] > days[1]:
        raise CliError(
            INVALID_ARGUMENT, "from-date must not exceed to-date", exit_code=2
        )
    return {
        "tntInstId": TENANT,
        "taskType": kind,
        "triggerStartDate": days[0].strftime("%Y-%m-%d 00:00:00"),
        "triggerEndDate": days[1].strftime("%Y-%m-%d 23:59:59"),
    }


def business_data(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except (ValueError, UnicodeError) as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get("success")) is not bool:
        raise CliError(INVALID_RESPONSE, "response requires a boolean success flag")
    if not document["success"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    data = document.get("data")
    if not isinstance(data, dict):
        raise CliError(INVALID_RESPONSE, "response data is not an object")
    return data


def validate_identity(row: Any, field: str, kind: str) -> None:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get(field), str)
        or not row[field].strip()
    ):
        raise CliError(
            INVALID_RESPONSE, "task identity must be a nonempty native string"
        )
    if row.get("taskType") != kind:
        raise CliError(INVALID_RESPONSE, "task type contradicts requested scope")
    if "tntInstId" in row and row["tntInstId"] != TENANT:
        raise CliError(INVALID_RESPONSE, "task tenant contradicts requested scope")


class Inquiry:
    name = NAME + ".list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/api/increment/decision/task/queryPage.json",
            page_size=5000,
            allowed_page_sizes=WIDTHS,
            one_based=False,
            allowed_body_keys=frozenset({*values, "rowStart", "pageSize"}),
            fixed_body_values=tuple(values.items()),
        )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            scope != canonical(self.values)
            or type(page_size) is not int
            or page_size not in WIDTHS
            or type(row_start) is not int
            or row_start < 0
            or row_start % page_size
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified task List request")
        return {**self.values, "rowStart": row_start, "pageSize": page_size}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        data = business_data(body)
        rows, total = data.get("data"), data.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid task rows or native total")
        for row in rows:
            validate_identity(row, "id", self.values["taskType"])
            stamp = row.get("triggerDate")
            try:
                if type(stamp) is not int:
                    raise ValueError
                day = datetime.fromtimestamp(stamp / 1000, SOURCE_ZONE).strftime(
                    "%Y-%m-%d"
                )
            except (ValueError, OverflowError, OSError) as error:
                raise CliError(
                    INVALID_RESPONSE, "invalid native triggerDate timestamp"
                ) from error
            if (
                not self.values["triggerStartDate"][:10]
                <= day
                <= self.values["triggerEndDate"][:10]
            ):
                raise CliError(
                    INVALID_RESPONSE, "task triggerDate contradicts requested bounds"
                )
        return rows, total


class DetailInquiry:
    name = NAME + ".get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/api/increment/decision/task/taskDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"taskId"}),
        encoding="form",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        task_type(parameters)
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT, "task lookup must be a nonempty string", exit_code=2
            )
        return {"taskId": identity}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        row = business_data(body)
        validate_identity(row, "taskId", task_type(parameters))
        if row["taskId"] != identity:
            raise CliError(
                INVALID_RESPONSE, "task detail identity contradicts requested lookup"
            )
        return row


class Adapter:
    def history_bounds(self, parameters: dict) -> dict:
        native = native_scope(parameters)
        return {
            "from": datetime.strptime(native["triggerStartDate"], "%Y-%m-%d %H:%M:%S")
            .date()
            .isoformat(),
            "to": datetime.strptime(native["triggerEndDate"], "%Y-%m-%d %H:%M:%S")
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

    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        task_type(parameters)
        return DetailInquiry()

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
