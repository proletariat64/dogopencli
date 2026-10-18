"""Risk event thresholds: native inquiry contract and full-record collection."""

from dataclasses import dataclass
from typing import Any

from dogopencli import collect
from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse

PAGE_SIZE = 10
TENANT = "GUAPW3SG"


@dataclass(frozen=True)
class Inquiry:
    name: str = "liquidity.risk.thresholds.list"
    page_url: str = LIQUIDITY_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/api/risk/benchmark/riskEventBenchmarkQuery.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "rowStart", "pageSize"}),
        fixed_body_values=(("tntInstId", TENANT), ("pageSize", PAGE_SIZE)),
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
            raise CliError(REQUEST_NOT_ALLOWED, "unverified risk.thresholds request")
        return {"rowStart": row_start, "pageSize": PAGE_SIZE, "tntInstId": TENANT}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "response envelope is not an object")
        if type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "success is not boolean")
        if document["success"] is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        result = document.get("data")
        if not isinstance(result, dict):
            raise CliError(INVALID_RESPONSE, "response result is not an object")
        if result.get("success") is False:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        rows, total = result.get("data"), result.get("totalCount")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(
                INVALID_RESPONSE, "record container is not a list of objects"
            )
        if type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE, "reported total is not a nonnegative integer"
            )
        for row in rows:
            value = row.get("benchmarkId")
            if (
                not isinstance(value, (str, int))
                or isinstance(value, bool)
                or (isinstance(value, str) and not value.strip())
            ):
                raise CliError(
                    INVALID_RESPONSE, "record is missing identity field benchmarkId"
                )
        return rows, total


CAPABILITY = Inquiry()


@dataclass(frozen=True)
class DetailInquiry:
    name: str = "liquidity.risk.thresholds.get"
    page_url: str = LIQUIDITY_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/api/risk/benchmark/riskEventBenchmarkDetailDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"benchmarkId"}),
        encoding="form",
    )


DETAIL = DetailInquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return ""

    def get(
        self, session: Any, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        response = collect.execute_bounded(
            DETAIL,
            session.transport(DETAIL),
            {"benchmarkId": identity},
        )
        try:
            document = parse(response.body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "response envelope is not an object")
        if type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "detail success flag is not boolean")
        if document["success"] is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        detail = document.get("data")
        if not isinstance(detail, dict):
            raise CliError(INVALID_RESPONSE, "detail is not an object")
        value = detail.get("benchmarkId")
        if (
            not isinstance(value, (str, int))
            or isinstance(value, bool)
            or (isinstance(value, str) and not value.strip())
            or str(value) != identity
        ):
            raise CliError(
                INVALID_RESPONSE,
                "detail benchmarkId does not match the requested identity",
            )
        return detail

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
