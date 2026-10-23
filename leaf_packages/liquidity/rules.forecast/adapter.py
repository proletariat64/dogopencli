"""Cash forecast rule configuration: fixed Z21 scope and 1000-row native pages."""

import json
from dataclasses import dataclass
from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse

PAGE_SIZE = 1000
TENANT = "GUAPW3SG"


@dataclass(frozen=True)
class ForecastInquiry:
    name: str = "liquidity.rules.forecast.list"
    page_url: str = LIQUIDITY_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/bankCashForecastRuleQuery.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "bankCashForecastRuleQueryVO"}),
        fixed_body_values=(("tntInstId", TENANT),),
        json_body_contracts=(
            (
                "bankCashForecastRuleQueryVO",
                frozenset({"tntInstId", "instId", "rowStart", "pageSize"}),
                (("tntInstId", TENANT), ("instId", ["Z21"])),
                frozenset({PAGE_SIZE}),
            ),
        ),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            scope
            or type(page_size) is not int
            or page_size != PAGE_SIZE
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified forecast request")
        return {
            "tntInstId": TENANT,
            "bankCashForecastRuleQueryVO": json.dumps(
                {
                    "tntInstId": TENANT,
                    "instId": ["Z21"],
                    "rowStart": row_start,
                    "pageSize": PAGE_SIZE,
                }
            ),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "response envelope is not an object")
        if type(document.get("resultFlag")) is not bool:
            raise CliError(INVALID_RESPONSE, "resultFlag is not boolean")
        if document["resultFlag"] is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        result = document.get("result")
        if not isinstance(result, dict):
            raise CliError(INVALID_RESPONSE, "response result is not an object")
        if result.get("success") is False:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        rows, total = result.get("dataValue"), result.get("count")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(
                INVALID_RESPONSE, "record container is not a list of objects"
            )
        if type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE, "reported total is not a nonnegative integer"
            )
        for row in rows:
            value = row.get("ruleId")
            if (
                not isinstance(value, (str, int))
                or isinstance(value, bool)
                or (isinstance(value, str) and not value.strip())
            ):
                raise CliError(
                    INVALID_RESPONSE, "record is missing identity field ruleId"
                )
        return rows, total


CAPABILITY = ForecastInquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return ""

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
