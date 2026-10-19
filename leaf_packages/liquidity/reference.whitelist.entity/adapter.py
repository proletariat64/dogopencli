"""Native entity whitelist records through the host List SDK."""

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
WIDTHS = (5000, 1000)
VO_FIELD = "instFilterConfigQuery"
SCOPE = canonical({"tntInstId": TENANT, "timezone": "GMT+08"})
FILTERS = (("entity", "instId"), ("financial_code", "instCode"), ("status", "status"))


def validate_filters(parameters: dict[str, Any]) -> None:
    for key, _ in FILTERS:
        values = parameters.get(key)
        if values is None:
            continue
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "local filters require nonblank exact strings",
                exit_code=2,
            )
        if key == "status" and any(
            value not in ("VALID", "INVALID") for value in values
        ):
            raise CliError(
                INVALID_ARGUMENT, "status accepts VALID or INVALID", exit_code=2
            )


class Inquiry:
    name = "liquidity.reference.whitelist.entity.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/instFilterConfigQuery.json",
        page_size=5000,
        one_based=False,
        allowed_page_sizes=WIDTHS,
        encoding="query",
        allowed_body_keys=frozenset({"tntInstId", VO_FIELD}),
        fixed_body_values=(("tntInstId", TENANT),),
        json_body_contracts=(
            (
                VO_FIELD,
                frozenset({"tntInstId", "timezone", "rowStart", "pageSize"}),
                (("tntInstId", TENANT), ("timezone", "GMT+08")),
                frozenset(WIDTHS),
            ),
        ),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            scope != SCOPE
            or type(row_start) is not int
            or row_start < 0
            or type(page_size) is not int
            or page_size not in WIDTHS
            or row_start % page_size
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "unverified entity whitelist offset or scope"
            )
        return {
            "tntInstId": TENANT,
            VO_FIELD: canonical(
                {
                    "tntInstId": TENANT,
                    "timezone": "GMT+08",
                    "rowStart": row_start,
                    "pageSize": page_size,
                }
            ),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            raise CliError(INVALID_RESPONSE, "native resultFlag must be boolean")
        if not document["resultFlag"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected entity whitelist query"
            )
        result = document.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "native result requires boolean success")
        if not result["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected entity whitelist query"
            )
        total, outer = result.get("count"), document.get("count")
        if (
            type(total) is not int
            or total < 0
            or type(outer) is not int
            or outer != total
        ):
            raise CliError(INVALID_RESPONSE, "native inner and outer counts must agree")
        rows = result.get("data")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "native entity records are not an array")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("instId"), str)
                or not row["instId"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE,
                    "entity identity must be a nonblank native instId string",
                )
            if "tntInstId" in row and row["tntInstId"] not in ("", TENANT):
                raise CliError(
                    INVALID_RESPONSE, "native entity tenant contradicts request"
                )
        return rows, total


CAPABILITY = Inquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        validate_filters(parameters)
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        validate_filters(parameters)
        return SCOPE

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        validate_filters(parameters)
        return [
            row
            for row in records
            if all(
                not parameters.get(key) or row.get(field) in parameters[key]
                for key, field in FILTERS
            )
        ]


adapter = Adapter()
