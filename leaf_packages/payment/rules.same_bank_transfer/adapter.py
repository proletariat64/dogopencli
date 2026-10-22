"""Native same-bank transfer rule List through the host SDK."""

from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse

PAGE_SIZE = 1000
FILTERS = (("bank", "debitInstId"), ("status", "ruleStatus"))


def validate_filters(parameters: dict[str, Any]) -> None:
    for parameter, _ in FILTERS:
        values = parameters.get(parameter)
        if values is not None and (
            not isinstance(values, list)
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise CliError(
                INVALID_ARGUMENT, "filters require nonblank exact strings", exit_code=2
            )


class Inquiry:
    name = "payment.rules.same_bank_transfer.list"
    page_url = "https://intl-fluxnet.alipay.com/payout/peer-transfer"
    contract = EndpointContract(
        method="POST",
        host="ifundboss.alipay.com",
        path="/payout/api/bookDecisionRule/search.json",
        page_size=PAGE_SIZE,
        one_based=True,
        allowed_body_keys=frozenset({"pageNum", "pageSize"}),
        fixed_body_values=(("pageNum", 1), ("pageSize", PAGE_SIZE)),
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope != "all"
            or type(page_num) is not int
            or page_num != 1
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "only the verified first rule page is allowed"
            )
        return {"pageNum": 1, "pageSize": PAGE_SIZE}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "outer success marker is not boolean")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected rule inquiry")
        result = document.get("resultObj")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "inner success marker is not boolean")
        if not result["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected rule inquiry")
        if any(
            type(result.get(key)) is not int
            for key in ("pageNum", "pageSize", "totalCount", "totalPages")
        ):
            raise CliError(
                INVALID_RESPONSE, "pagination fields require native integers"
            )
        total = result["totalCount"]
        if (
            result["pageNum"] != 1
            or result["pageSize"] != PAGE_SIZE
            or total < 0
            or result["totalPages"] != -(-total // PAGE_SIZE)
        ):
            raise CliError(INVALID_RESPONSE, "native rule pagination is inconsistent")
        rows = result.get("payoutBookDecisionRuleVOList")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "rule container is not an array")
        for row in rows:
            if (
                not isinstance(row, dict)
                or type(row.get("ruleId")) is not int
                or row["ruleId"] < 0
            ):
                raise CliError(
                    INVALID_RESPONSE, "ruleId requires a nonnegative native integer"
                )
        return ParsedPage(rows, 1, PAGE_SIZE, total, result["totalPages"])


CAPABILITY = Inquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        validate_filters(parameters)
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        validate_filters(parameters)
        return "all"

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        validate_filters(parameters)
        return sorted(
            (
                row
                for row in records
                if all(
                    not parameters.get(parameter)
                    or row.get(field) in parameters[parameter]
                    for parameter, field in FILTERS
                )
            ),
            key=lambda row: row["ruleId"],
        )


adapter = Adapter()
