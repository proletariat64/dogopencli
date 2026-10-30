"""Native account-outflow risk observations through the standard List SDK."""

import json
import re
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
from dogopencli.temporal import parse_iso_millisecond_instant

TENANT = "GUAPW3SG"
REASON = "EXPECTED_BAL_NOT_ENOUGH"
PAGE_SIZE = 1000
NATIVE_TIME_ZONE = timezone(timedelta(hours=8))


def warning_instant(value: Any) -> datetime:
    try:
        return parse_iso_millisecond_instant(value).astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as error:
        raise CliError(
            INVALID_ARGUMENT,
            "warning bounds require known ISO8601 offsets "
            "and at most millisecond precision",
            exit_code=2,
        ) from error


def native_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    start = warning_instant(parameters.get("from_time"))
    end = warning_instant(parameters.get("to_time"))
    if start > end:
        raise CliError(INVALID_ARGUMENT, "warning bounds are reversed", exit_code=2)
    values = {
        "tntInstId": TENANT,
        "warningReason": REASON,
        "warningTimeStart": start.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
        "warningTimeEnd": end.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }
    for public, native in (("entity", "entitys"), ("bank_id", "bankIds")):
        selected = parameters.get(public) or []
        if isinstance(selected, str):
            selected = [selected]
        if not isinstance(selected, list) or any(
            not isinstance(value, str) or not value.strip() for value in selected
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "native selectors must be nonblank literal strings",
                exit_code=2,
            )
        if selected:
            values[native] = sorted(set(selected))
    return values


class Inquiry:
    name = "liquidity.risk.account_outflow.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="GET",
            host="iliquidity.alipay.com",
            path="/queryAccountflowMonitor.json",
            page_size=PAGE_SIZE,
            one_based=False,
            encoding="query",
            allowed_body_keys=frozenset(
                {"tntInstId", "accountflowMonitorQueryRequest"}
            ),
            fixed_body_values=(("tntInstId", TENANT),),
            json_body_contracts=(
                (
                    "accountflowMonitorQueryRequest",
                    frozenset({*values, "rowStart", "pageSize"}),
                    tuple(values.items()),
                    frozenset({PAGE_SIZE}),
                ),
            ),
        )

    def page_body(self, scope: str, position: int, page_size: int) -> dict[str, Any]:
        if (
            scope != canonical(self.values)
            or type(position) is not int
            or position < 0
            or position % PAGE_SIZE
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unqualified account-outflow request")
        return {
            "tntInstId": TENANT,
            "accountflowMonitorQueryRequest": json.dumps(
                {**self.values, "rowStart": position, "pageSize": page_size}
            ),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                INVALID_RESPONSE, "account-outflow response is not JSON"
            ) from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            raise CliError(
                INVALID_RESPONSE, "account-outflow requires boolean resultFlag"
            )
        if not document["resultFlag"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected account-outflow inquiry"
            )
        result = document.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            raise CliError(
                INVALID_RESPONSE, "account-outflow requires boolean inner success"
            )
        if not result["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected account-outflow inquiry"
            )
        rows, total = result.get("dataValue"), result.get("count")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE, "invalid account-outflow rows or native total"
            )
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("monitorNo"), str)
                or not row["monitorNo"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE, "native monitorNo must be a nonblank string"
                )
        return rows, total

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        if scope != canonical(self.values):
            raise CliError(
                INVALID_RESPONSE, "account-outflow acquisition scope changed"
            )
        start = warning_instant(self.values["warningTimeStart"])
        end = warning_instant(self.values["warningTimeEnd"])
        for row in rows:
            if any(
                field in row and row[field] != expected
                for field, expected in (
                    ("tntInstId", TENANT),
                    ("warningReason", REASON),
                )
            ):
                raise CliError(
                    INVALID_RESPONSE, "native row contradicts fixed query scope"
                )
            if any(
                selector in self.values and row.get(field) not in self.values[selector]
                for selector, field in (("entitys", "instId"), ("bankIds", "bankId"))
            ):
                raise CliError(
                    INVALID_RESPONSE, "native row contradicts requested selectors"
                )
            value = row.get("warningTime")
            try:
                if not isinstance(value, str) or not re.fullmatch(
                    r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value
                ):
                    raise ValueError
                instant = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=NATIVE_TIME_ZONE
                )
                if not start <= instant <= end:
                    raise ValueError
            except ValueError as error:
                raise CliError(
                    INVALID_RESPONSE, "native warningTime contradicts requested bounds"
                ) from error


class Adapter:
    def history_bounds(self, parameters: dict) -> dict:
        native = native_scope(parameters)
        return {"from": native["warningTimeStart"], "to": native["warningTimeEnd"]}

    def history_parameters(self, bounds: dict) -> dict:
        return {"from_time": bounds["from"], "to_time": bounds["to"]}

    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry(native_scope(parameters))

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
