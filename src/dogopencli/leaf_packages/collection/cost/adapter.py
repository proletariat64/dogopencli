"""Fixed-scope collection transaction-cost inquiry, owned by this package."""

from dataclasses import dataclass
from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse

COST_TYPE = "FUND_IN_CHANNEL_TRANS_FEE"
PAGE_SIZE = 1000


@dataclass(frozen=True)
class CostInquiry:
    name: str = "collection.cost.list"
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="iglobalfundcontrol.alipay.com",
        path="/api/fundCost/query.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"costTypeCode", "pageNo", "pageSize"}),
        scope_field="itemType",
        fixed_body_values=(
            ("costTypeCode", COST_TYPE),
            ("pageNo", 0),
            ("pageSize", PAGE_SIZE),
        ),
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if scope != COST_TYPE or page_num != 0 or page_size != PAGE_SIZE:
            raise CliError(REQUEST_NOT_ALLOWED, "unverified collection cost request")
        return dict(self.contract.fixed_body_values)

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "response envelope is not an object")
        if document.get("success") is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        for key in ("pageNo", "pageSize", "totalCount"):
            if type(document.get(key)) is not int:
                raise CliError(INVALID_RESPONSE, f"invalid pagination field {key}")
        total = document["totalCount"]
        if document["pageNo"] != 0 or document["pageSize"] != PAGE_SIZE or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid collection cost pagination")
        rows = document.get("resultDataList", [] if total == 0 else None)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(INVALID_RESPONSE, "missing resultDataList")
        if len(rows) > PAGE_SIZE or (total == 0 and rows):
            raise CliError(INVALID_RESPONSE, "inconsistent collection cost capacity")
        for row in rows:
            if row.get("itemType") != COST_TYPE:
                raise CliError(
                    INVALID_RESPONSE, "row itemType is outside the fixed cost type"
                )
            if not isinstance(row.get("itemId"), str) or not row["itemId"].strip():
                raise CliError(INVALID_RESPONSE, "row is missing itemId")
        return ParsedPage(rows, 0, PAGE_SIZE, total, -(-total // PAGE_SIZE))


CAPABILITY = CostInquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return COST_TYPE

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
