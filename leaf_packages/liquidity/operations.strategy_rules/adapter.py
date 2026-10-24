"""Native strategy rule records through the host List SDK."""

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

NAME = "liquidity.operations.strategy_rules"
WIDTHS = (50, 10)
CATEGORIES = ("MAIN_DECISION_STRATEGY", "SUB_STRATEGY")
SUB_TYPES = ("PRINCIPAL_PLANNING", "INVESTMENT_PORTFOLIO", "INVESTMENT_PREFERENCE")


def native_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    category = parameters.get("category")
    if category not in CATEGORIES:
        raise CliError(
            INVALID_ARGUMENT, "an explicit native category is required", exit_code=2
        )
    types = parameters.get("strategy_type") or []
    if not isinstance(types, (list, tuple)) or any(
        value not in SUB_TYPES for value in types
    ):
        raise CliError(
            INVALID_ARGUMENT, "unsupported native strategy-type", exit_code=2
        )
    if category == "MAIN_DECISION_STRATEGY" and types:
        raise CliError(
            INVALID_ARGUMENT, "strategy-type applies only to SUB_STRATEGY", exit_code=2
        )
    values = {"strategyCategory": category}
    if category == "SUB_STRATEGY":
        values["strategyTypes"] = list(types or SUB_TYPES)
    return values


class Inquiry:
    name = NAME + ".list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/queryStrategyRulePage.json",
            page_size=50,
            allowed_page_sizes=WIDTHS,
            one_based=False,
            allowed_body_keys=frozenset({*values, "rowStart", "pageSize"}),
            fixed_body_values=tuple(values.items()),
            encoding="json",
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
            raise CliError(REQUEST_NOT_ALLOWED, "unverified strategy List request")
        return {**self.values, "rowStart": row_start, "pageSize": page_size}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "response requires a boolean success flag")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected strategy inquiry")
        data = document.get("data")
        if not isinstance(data, dict):
            raise CliError(INVALID_RESPONSE, "response data is not an object")
        rows, total = data.get("data"), data.get("totalCount")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid strategy rows or native total")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not row["id"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE, "strategy id must be a nonempty native string"
                )
            # The native main List consistently labels its main rows SUB_STRATEGY
            # with an empty type. Main/sub scopes are request-defined and disjoint;
            # preserve that source value but reject actual sub-type leakage.
            category = self.values["strategyCategory"]
            qualified_main_echo = (
                category == "MAIN_DECISION_STRATEGY"
                and row.get("strategyCategory") == "SUB_STRATEGY"
                and row.get("strategyType") == ""
            )
            if row.get("strategyCategory") != category and not qualified_main_echo:
                raise CliError(
                    INVALID_RESPONSE, "strategy category contradicts requested scope"
                )
            if (
                self.values["strategyCategory"] == "SUB_STRATEGY"
                and row.get("strategyType") not in self.values["strategyTypes"]
            ):
                raise CliError(
                    INVALID_RESPONSE, "strategy type contradicts requested scope"
                )
        return rows, total


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry(native_scope(parameters))

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
