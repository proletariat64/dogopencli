"""Native prefund List with two qualified status views and local currency selection."""

import json
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
PAGE_SIZE = 10
STATUS_VIEWS = (("APPROVED", "CLOSED"), ("SUBMITTED", "REJECTED", "CLOSED_SUBMITTED"))


def native_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    status = parameters.get("status")
    values = [status] if isinstance(status, str) else status
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) for value in values)
    ):
        raise CliError(
            INVALID_ARGUMENT,
            "prefunds require one qualified repeated status set",
            exit_code=2,
        )
    selected = set(values)
    view = next((view for view in STATUS_VIEWS if set(view) == selected), None)
    if view is None:
        raise CliError(
            INVALID_ARGUMENT,
            "use APPROVED+CLOSED or SUBMITTED+REJECTED+CLOSED_SUBMITTED",
            exit_code=2,
        )
    return {"tntInstId": TENANT, "timeZone": "GMt+8", "statusList": list(view)}


class Inquiry:
    name = "liquidity.operations.prefunds.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="GET",
            host="iliquidity.alipay.com",
            path="/queryPreFundingOrderList.json",
            page_size=PAGE_SIZE,
            one_based=False,
            encoding="query",
            allowed_body_keys=frozenset(
                {"tntInstId", "timeZone", "preFundingOrderQueryVO"}
            ),
            fixed_body_values=(("tntInstId", TENANT), ("timeZone", "GMt+8")),
            json_body_contracts=(
                (
                    "preFundingOrderQueryVO",
                    frozenset({"tntInstId", "statusList", "rowStart", "pageSize"}),
                    (("tntInstId", TENANT), ("statusList", values["statusList"])),
                    frozenset({PAGE_SIZE}),
                ),
            ),
        )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            scope != canonical(self.values)
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified prefund request")
        return {
            "tntInstId": TENANT,
            "timeZone": "GMt+8",
            "preFundingOrderQueryVO": json.dumps(
                {
                    "tntInstId": TENANT,
                    "statusList": self.values["statusList"],
                    "rowStart": row_start,
                    "pageSize": page_size,
                }
            ),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            raise CliError(INVALID_RESPONSE, "invalid prefund business success marker")
        if not document["resultFlag"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        node = document.get("result")
        if not isinstance(node, dict):
            raise CliError(INVALID_RESPONSE, "prefund result is not an object")
        if "success" in node:
            if type(node["success"]) is not bool:
                raise CliError(
                    INVALID_RESPONSE, "invalid inner business success marker"
                )
            if not node["success"]:
                raise CliError(
                    BUSINESS_QUERY_FAILED, "backend reported a business failure"
                )
        rows, total = node.get("dataValue"), node.get("count")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid prefund records or native total")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not row["id"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE, "native prefund id must be a nonempty string"
                )
            if "tntInstId" in row and row["tntInstId"] != TENANT:
                raise CliError(
                    INVALID_RESPONSE, "prefund tenant contradicts query scope"
                )
        return rows, total

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        if scope != canonical(self.values):
            raise CliError(INVALID_RESPONSE, "prefund acquisition scope changed")
        if any(
            "status" in row and row["status"] not in self.values["statusList"]
            for row in rows
        ):
            raise CliError(INVALID_RESPONSE, "prefund status is outside requested view")


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry(native_scope(parameters))

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_scope(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        values = parameters.get("currency") or []
        if isinstance(values, str):
            values = [values]
        return [row for row in records if not values or row.get("currency") in values]


adapter = Adapter()
