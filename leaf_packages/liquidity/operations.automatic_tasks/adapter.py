"""Native automatic-operation tasks through the standard List SDK."""

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
from dogopencli.temporal import (
    normalize_utc_milliseconds,
    parse_iso_millisecond_instant,
)

TENANT = "GUAPW3SG"
PAGE_SIZE = 10
PUBLIC_TIME = "%Y-%m-%dT%H:%M:%S"
NATIVE_TIME = "%Y-%m-%d %H:%M:%S"
SOURCE_ZONE = timezone(timedelta(hours=8))


def native_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    try:
        values = [parameters.get("from_time"), parameters.get("to_time")]
        if any(
            not isinstance(value, str) or len(value) != 19 or not value.isascii()
            for value in values
        ):
            raise ValueError
        start, end = (datetime.strptime(value, PUBLIC_TIME) for value in values)
        if (
            start.strftime(PUBLIC_TIME) != values[0]
            or end.strftime(PUBLIC_TIME) != values[1]
            or not timedelta(0) <= end - start < timedelta(days=31)
        ):
            raise ValueError
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT,
            "automatic tasks requires ordered --from-time/--to-time "
            "YYYY-MM-DDTHH:mm:ss in native GMT+8, fewer than 31 elapsed days apart",
            exit_code=2,
        ) from error
    return {
        "tntInstId": TENANT,
        "minDate": start.strftime(NATIVE_TIME),
        "maxDate": end.strftime(NATIVE_TIME),
    }


class Inquiry:
    name = "liquidity.operations.automatic_tasks.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/riskActionTask/listQuery.json",
            page_size=PAGE_SIZE,
            allowed_page_sizes=(PAGE_SIZE,),
            one_based=False,
            allowed_body_keys=frozenset({*values, "rowStart", "pageSize"}),
            fixed_body_values=tuple(values.items()),
            encoding="json",
        )

    def page_body(self, scope: str, position: int, page_size: int) -> dict[str, Any]:
        if (
            scope != canonical(self.values)
            or type(position) is not int
            or position < 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED,
                "automatic tasks requires its exact created-time scope "
                "and qualified width",
            )
        return {**self.values, "rowStart": position, "pageSize": page_size}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                INVALID_RESPONSE, "automatic-operation response is not JSON"
            ) from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(
                INVALID_RESPONSE, "automatic-operation success must be boolean"
            )
        if not document["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected automatic-operation inquiry"
            )
        result = document.get("data")
        if not isinstance(result, dict):
            raise CliError(
                INVALID_RESPONSE, "automatic-operation data is not an object"
            )
        rows, total = result.get("data"), result.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE, "invalid automatic-operation rows or native total"
            )
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("taskId"), str)
                or not row["taskId"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE,
                    "automatic-operation taskId must be a nonblank native string",
                )
            if "tntInstId" in row and row["tntInstId"] != TENANT:
                raise CliError(
                    INVALID_RESPONSE,
                    "automatic-operation tenant contradicts query scope",
                )
            created = row.get("gmtCreate")
            try:
                if (
                    not isinstance(created, str)
                    or len(created) != 19
                    or not created.isascii()
                ):
                    raise ValueError
                value = datetime.strptime(created, NATIVE_TIME)
                if (
                    value.strftime(NATIVE_TIME) != created
                    or not self.values["minDate"] <= created <= self.values["maxDate"]
                ):
                    raise ValueError
            except ValueError as error:
                raise CliError(
                    INVALID_RESPONSE,
                    "automatic-operation gmtCreate is malformed "
                    "or outside created-time scope",
                ) from error
        return rows, total


class Adapter:
    def history_bounds(self, parameters: dict) -> dict:
        native = native_scope(parameters)
        return {
            bound: normalize_utc_milliseconds(
                datetime.strptime(native[field], NATIVE_TIME).replace(
                    tzinfo=SOURCE_ZONE
                )
            )
            for bound, field in (("from", "minDate"), ("to", "maxDate"))
        }

    def history_parameters(self, bounds: dict) -> dict:
        values = {
            key: parse_iso_millisecond_instant(bounds[bound])
            for key, bound in (("from_time", "from"), ("to_time", "to"))
        }
        if any(value.microsecond for value in values.values()):
            raise CliError(
                INVALID_ARGUMENT,
                "automatic tasks cannot express fractional-second windows",
                exit_code=2,
            )
        return {
            key: value.astimezone(SOURCE_ZONE).strftime(PUBLIC_TIME)
            for key, value in values.items()
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
