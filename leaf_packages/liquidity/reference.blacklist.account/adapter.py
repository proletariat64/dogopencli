"""Native account blacklist records through the host offset List SDK."""

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
CONTEXT = {"tntInstId": TENANT, "timezone": "GMT+08", "currentArea": "3"}
SCOPE = canonical(CONTEXT)
FILTERS = (
    ("entity", "instId"),
    ("bank_id", "bankId"),
    ("account_alias", "aliasName"),
    ("status", "status"),
)


def validate_filters(parameters: dict[str, Any]) -> None:
    for parameter, _ in FILTERS:
        values = parameters.get(parameter)
        if values is not None and (
            not isinstance(values, list)
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise CliError(
                INVALID_ARGUMENT, "local filters require nonblank strings", exit_code=2
            )
    if any(
        value not in ("VALID", "INVALID") for value in parameters.get("status") or []
    ):
        raise CliError(INVALID_ARGUMENT, "status must be VALID or INVALID", exit_code=2)


class Inquiry:
    name = "liquidity.reference.blacklist.account.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/accountFilterConfigQuery.json",
        page_size=5000,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "accountFilterConfigQuery"}),
        fixed_body_values=(("tntInstId", TENANT),),
        allowed_page_sizes=WIDTHS,
        json_body_contracts=(
            (
                "accountFilterConfigQuery",
                frozenset(
                    {"tntInstId", "timezone", "currentArea", "rowStart", "pageSize"}
                ),
                tuple(CONTEXT.items()),
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
            raise CliError(REQUEST_NOT_ALLOWED, "unverified account blacklist request")
        return {
            "tntInstId": TENANT,
            "accountFilterConfigQuery": canonical(
                {**CONTEXT, "rowStart": row_start, "pageSize": page_size}
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
            raise CliError(INVALID_RESPONSE, "resultFlag must be boolean")
        if not document["resultFlag"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected account blacklist inquiry"
            )
        result = document.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "inner success must be boolean")
        if not result["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected account blacklist inquiry"
            )
        total = result.get("count")
        if (
            type(total) is not int
            or total < 0
            or type(document.get("count")) is not int
            or document["count"] != total
        ):
            raise CliError(INVALID_RESPONSE, "native inner and outer counts must agree")
        rows = result.get("data")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "native records are not an array")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("aliasName"), str)
                or not row["aliasName"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE, "account blacklist requires native aliasName"
                )
            if "tntInstId" in row and row["tntInstId"] not in ("", TENANT):
                raise CliError(
                    INVALID_RESPONSE, "native row tenant contradicts request"
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
                not parameters.get(parameter) or row.get(field) in parameters[parameter]
                for parameter, field in FILTERS
            )
        ]


adapter = Adapter()
