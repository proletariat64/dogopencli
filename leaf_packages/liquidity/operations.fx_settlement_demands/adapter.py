"""Native bounded FX settlement demands through the shared List SDK."""

from datetime import date
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
VO = "queryFxSettlementReportRequest"
LOCAL_FILTERS = {
    "inst_id": "instId",
    "currency": "currency",
    "account_alias": "aliasName",
    "counterparty": "counterParty",
    "sub_biz_type": "subBizType",
}


def local_filters(parameters: dict[str, Any]) -> dict[str, list[str]]:
    selected = {}
    for parameter, field in LOCAL_FILTERS.items():
        values = parameters.get(parameter) or []
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "local FX selectors require nonblank literal strings",
                exit_code=2,
            )
        if values:
            selected[field] = values
    return selected


def native_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    try:
        values = [parameters.get("from_date"), parameters.get("to_date")]
        if any(
            not isinstance(value, str) or len(value) != 10 or not value.isascii()
            for value in values
        ):
            raise ValueError
        start, end = (date.fromisoformat(value) for value in values)
        if (
            start.isoformat() != values[0]
            or end.isoformat() != values[1]
            or not 0 <= (end - start).days <= 31
        ):
            raise ValueError
    except (ValueError, TypeError) as error:
        raise CliError(
            INVALID_ARGUMENT,
            "FX settlement requires ordered YYYY-MM-DD --from-date/--to-date "
            "with date difference at most 31 days",
            exit_code=2,
        ) from error
    return {"valueDateStart": start.isoformat(), "valueDateEnd": end.isoformat()}


class Inquiry:
    name = "liquidity.operations.fx_settlement_demands.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="GET",
            host="iliquidity.alipay.com",
            path="/queryFxSettlementReportList.json",
            page_size=PAGE_SIZE,
            one_based=False,
            allowed_body_keys=frozenset({"tntInstId", VO}),
            fixed_body_values=(("tntInstId", TENANT),),
            json_body_contracts=(
                (
                    VO,
                    frozenset({*values, "offset", "size", "page"}),
                    tuple(values.items())
                    + (("offset", 0), ("size", PAGE_SIZE), ("page", 1)),
                    frozenset(),
                ),
            ),
        )

    def page_body(self, scope: str, position: int, page_size: int) -> dict[str, Any]:
        if (
            scope != canonical({"tntInstId": TENANT, **self.values})
            or type(position) is not int
            or position != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED,
                "only one qualified width-5000 FX inquiry is allowed",
            )
        return {
            "tntInstId": TENANT,
            VO: canonical({**self.values, "offset": 0, "size": PAGE_SIZE, "page": 1}),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                INVALID_RESPONSE, "FX settlement response is not JSON"
            ) from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            raise CliError(INVALID_RESPONSE, "FX settlement resultFlag must be boolean")
        if not document["resultFlag"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected FX settlement inquiry"
            )
        result = document.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "FX settlement success must be boolean")
        if not result["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected FX settlement inquiry"
            )
        rows, total = result.get("results"), result.get("count")
        if (
            not isinstance(rows, list)
            or type(total) is not int
            or total < 0
            or any(not isinstance(row, dict) for row in rows)
        ):
            raise CliError(
                INVALID_RESPONSE, "invalid FX settlement rows or native count"
            )
        for row in rows:
            if (
                type(row.get("id")) is not int
                or row["id"] <= 0
                or row.get("tntInstId") != TENANT
            ):
                raise CliError(
                    INVALID_RESPONSE,
                    "FX settlement requires its native integer id and matching tenant",
                )
            value = row.get("valueDate")
            try:
                if (
                    not isinstance(value, str)
                    or len(value) != 8
                    or not value.isascii()
                    or not value.isdigit()
                ):
                    raise ValueError
                native_day = date(int(value[:4]), int(value[4:6]), int(value[6:8]))
                if (
                    not self.values["valueDateStart"]
                    <= native_day.isoformat()
                    <= self.values["valueDateEnd"]
                ):
                    raise ValueError
            except ValueError as error:
                raise CliError(
                    INVALID_RESPONSE,
                    "FX settlement valueDate is malformed or outside query scope",
                ) from error
        return rows, total


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        local_filters(parameters)
        return Inquiry(native_scope(parameters))

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical({"tntInstId": TENANT, **native_scope(parameters)})

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        selected = local_filters(parameters)
        return [
            row
            for row in records
            if all(row.get(field) in values for field, values in selected.items())
        ]


adapter = Adapter()
