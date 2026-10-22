"""Native collection opening-rule configuration through the List SDK."""

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
FILTERS = (
    ("opening_rule_id", "id"),
    ("business_line", "businessCategory"),
    ("business_region", "businessRegionScope"),
    ("customer_group", "customerTags"),
    ("scene_code", "sceneCode"),
    ("collection_region", "creditArea"),
    ("currency", "currency"),
    ("transaction_type", "regionType"),
)


class AccountIsolationInquiry:
    name = "collection.account_isolation.list"
    page_url = (
        "https://ifundcontrol.alipay.com/productOperation/"
        "collectionProductManagement/networkConstruction/businessAccount"
    )
    contract = EndpointContract(
        method="POST",
        host="ifundcontrolprodops.alipay.com",
        path="/api/virtualAccountRuleConfig/search",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
        fixed_body_values=(("pageNo", 0), ("pageSize", PAGE_SIZE)),
    )

    def page_body(self, scope: str, page_no: int, page_size: int) -> dict[str, Any]:
        if (
            scope
            or type(page_no) is not int
            or page_no != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified account-isolation request")
        return {"pageNo": 0, "pageSize": PAGE_SIZE}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "success marker is not boolean")
        if not document["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected opening-rule inquiry"
            )
        data = document.get("data")
        if not isinstance(data, dict):
            raise CliError(INVALID_RESPONSE, "response data is not an object")
        if any(
            type(data.get(key)) is not int
            for key in ("pageNo", "pageSize", "totalCount")
        ):
            raise CliError(INVALID_RESPONSE, "pagination fields must be integers")
        if (
            data["pageNo"] != 0
            or data["pageSize"] != PAGE_SIZE
            or data["totalCount"] < 0
        ):
            raise CliError(INVALID_RESPONSE, "invalid opening-rule pagination")
        if "totalPageNo" in data and (
            type(data["totalPageNo"]) is not int or data["totalPageNo"] < 0
        ):
            raise CliError(
                INVALID_RESPONSE, "totalPageNo must be a nonnegative integer"
            )
        rows = data.get("businessDataList")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(INVALID_RESPONSE, "businessDataList is not an object array")
        for row in rows:
            if not isinstance(row.get("id"), str) or not row["id"].strip():
                raise CliError(INVALID_RESPONSE, "opening rule requires a string id")
        return ParsedPage(
            rows, 0, PAGE_SIZE, data["totalCount"], -(-data["totalCount"] // PAGE_SIZE)
        )


CAPABILITY = AccountIsolationInquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> AccountIsolationInquiry:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        for parameter, _ in FILTERS:
            values = parameters.get(parameter) or []
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise CliError(
                    INVALID_ARGUMENT, "local filters must be nonblank", exit_code=2
                )
        return ""

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        selected = records
        for parameter, field in FILTERS:
            values = parameters.get(parameter) or []
            if values:
                selected = [row for row in selected if row.get(field) in values]
        return sorted(selected, key=lambda row: row["id"])


adapter = Adapter()
