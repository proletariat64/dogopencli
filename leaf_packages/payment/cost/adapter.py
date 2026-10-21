"""Payment fee specifications: complete native source, exact local views."""

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

COST_TYPE = "FUND_OUT_CHANNEL_TRANS_FEE"
PAGE_SIZE = 5000
FILTERS = {
    "legal_entity_code": "legalEntity",
    "financial_inst_code": "financialInst",
    "account_alias": "bankAccountAliasName",
    "trans_currency_code": "transCurrencyCode",
    "charge_bearer": "chargeBearer",
    "clearing_network_name": "clearingNetworkName",
}


def validate_filters(parameters: dict[str, Any]) -> None:
    for name in FILTERS:
        values = parameters.get(name)
        if values is not None and (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "cost filters require nonblank exact strings",
                exit_code=2,
            )


class Inquiry:
    name = "payment.cost.list"
    page_url = (
        "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
    )
    contract = EndpointContract(
        method="POST",
        host="iglobalfundcontrol.alipay.com",
        path="/api/fundCost/query.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"costTypeCode", "pageNo", "pageSize"}),
        fixed_body_values=(("costTypeCode", COST_TYPE), ("pageSize", PAGE_SIZE)),
        scope_field="itemType",
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope != COST_TYPE
            or type(page_num) is not int
            or page_num < 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified payment cost request")
        return {"costTypeCode": COST_TYPE, "pageNo": page_num, "pageSize": page_size}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "cost response is not JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "cost response requires boolean success")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        page, size, total = (
            document.get("pageNo"),
            document.get("pageSize"),
            document.get("totalCount"),
        )
        if (
            any(type(value) is not int for value in (page, size, total))
            or page < 0
            or size != PAGE_SIZE
            or total < 0
        ):
            raise CliError(INVALID_RESPONSE, "invalid cost pagination")
        rows = document.get("resultDataList", [] if total == 0 else None)
        if (
            not isinstance(rows, list)
            or len(rows) > size
            or (total == 0 and rows)
            or any(
                not isinstance(row, dict)
                or not isinstance(row.get("itemId"), str)
                or not row["itemId"].strip()
                or row.get("itemType") != COST_TYPE
                for row in rows
            )
        ):
            raise CliError(
                INVALID_RESPONSE, "invalid native cost rows, identity or type"
            )
        return ParsedPage(rows, page, size, total, -(-total // size))


CAPABILITY = Inquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        validate_filters(parameters)
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        validate_filters(parameters)
        return COST_TYPE

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        validate_filters(parameters)
        return sorted(
            (
                row
                for row in records
                if all(
                    isinstance(row.get(field), str) and row[field] in parameters[name]
                    for name, field in FILTERS.items()
                    if parameters.get(name) is not None
                )
            ),
            key=lambda row: row["itemId"],
        )


adapter = Adapter()
