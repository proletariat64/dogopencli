"""One verified collection configuration page through the host List SDK."""

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

FILTERS = (
    ("bank_location", "supportedCountry"),
    ("currency", "supportedCurrency"),
    ("system_type", "clearingNetworkType"),
    ("system_name", "clearingNetworkId"),
    ("status", "status"),
)
PAGE_SIZE = 1000


def validate_filters(parameters: dict[str, Any]) -> None:
    for parameter, _ in FILTERS:
        values = parameters.get(parameter)
        if values is None:
            continue
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "local filters require nonblank exact string values",
                exit_code=2,
            )


class Inquiry:
    name = "collection.clearing_system.list"
    page_url = (
        "https://ifundbossportal.alipay.com/voucher/CollectionClearingSystemConfig"
    )
    contract = EndpointContract(
        method="POST",
        host="ifundboss-api.alipay.com",
        path="/ivostro/api/clearingNetworkInfo/pageList.json",
        page_size=PAGE_SIZE,
        one_based=True,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
        fixed_body_values=(("pageNo", 1), ("pageSize", PAGE_SIZE)),
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
                REQUEST_NOT_ALLOWED,
                "only the verified first configuration page is allowed",
            )
        return {"pageNo": 1, "pageSize": PAGE_SIZE}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "response requires a boolean success flag")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        if any(
            type(document.get(field)) is not int
            for field in ("pageNo", "pageSize", "totalCount")
        ):
            raise CliError(
                INVALID_RESPONSE,
                "configuration pagination fields require native integers",
            )
        rows, total = document.get("resultDataList"), document["totalCount"]
        if not isinstance(rows, list) or total < 0:
            raise CliError(
                INVALID_RESPONSE, "invalid configuration rows or native total"
            )
        empty = not rows and total == 0
        number = document["pageNo"]
        if document["pageSize"] != PAGE_SIZE or (
            number != 1 and not (empty and number == 0)
        ):
            raise CliError(INVALID_RESPONSE, "configuration pagination echo mismatch")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not row["id"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE,
                    "configuration identity must be a nonblank native string",
                )
        return ParsedPage(rows, number, PAGE_SIZE, total, -(-total // PAGE_SIZE))


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
            key=lambda row: row["id"],
        )


adapter = Adapter()
