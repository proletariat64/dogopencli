"""Native inquiry-only rules.waterlevel contract; no legacy runtime dependencies."""

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
from dogopencli.jsonutil import parse

TENANT = "GUAPW3SG"


def result(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get("resultFlag")) is not bool:
        raise CliError(INVALID_RESPONSE, "invalid business success marker")
    if not document["resultFlag"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    node = document.get("result")
    if not isinstance(node, dict):
        raise CliError(INVALID_RESPONSE, "result is not an object")
    if "success" in node:
        if type(node["success"]) is not bool:
            raise CliError(INVALID_RESPONSE, "inner success is not boolean")
        if not node["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return node


def validate_row(row: Any, field: str) -> None:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get(field), (str, int))
        or isinstance(row[field], bool)
        or (isinstance(row[field], str) and not row[field].strip())
    ):
        raise CliError(
            INVALID_RESPONSE, "native identity must be a nonempty string or integer"
        )
    if "tntInstId" in row and row["tntInstId"] != TENANT:
        raise CliError(INVALID_RESPONSE, "record tenant contradicts query scope")


PAGE_SIZE = 5000


class Inquiry:
    name = "liquidity.rules.waterlevel.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/bankAccountBufferQuery.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "bankAccountBufferQueryVO"}),
        fixed_body_values=(("tntInstId", TENANT),),
        json_body_contracts=(
            (
                "bankAccountBufferQueryVO",
                frozenset(
                    {
                        "tntInstId",
                        "startCreditDate",
                        "endCreditDate",
                        "rowStart",
                        "pageSize",
                    }
                ),
                (
                    ("tntInstId", TENANT),
                    ("startCreditDate", None),
                    ("endCreditDate", None),
                ),
                frozenset({PAGE_SIZE}),
            ),
        ),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            scope
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified waterlevel request")
        return {
            "tntInstId": TENANT,
            "bankAccountBufferQueryVO": json.dumps(
                {
                    "tntInstId": TENANT,
                    "startCreditDate": None,
                    "endCreditDate": None,
                    "rowStart": row_start,
                    "pageSize": PAGE_SIZE,
                }
            ),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        node = result(body)
        rows, total = node.get("dataValue"), node.get("count")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid buffer records or count")
        for row in rows:
            validate_row(row, "bufferId")
        return rows, total


CAPABILITY = Inquiry()


class DetailInquiry:
    name = "liquidity.rules.waterlevel.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/bankAccountBufferListByAliasName.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "aliasName"}),
        fixed_body_values=(("tntInstId", TENANT),),
        encoding="query",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT, "account alias must be nonempty", exit_code=2
            )
        return {"tntInstId": TENANT, "aliasName": identity}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> list[dict[str, Any]]:
        rows = result(body).get("dataValue")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "account configuration is not an array")
        seen = set()
        for row in rows:
            validate_row(row, "bufferId")
            if row.get("aliasName") != identity:
                raise CliError(INVALID_RESPONSE, "detail account differs from lookup")
            native_id = (type(row["bufferId"]), row["bufferId"])
            if native_id in seen:
                raise CliError(
                    INVALID_RESPONSE, "ambiguous native configuration identity"
                )
            seen.add(native_id)
        return rows


DETAIL = DetailInquiry()


class Adapter:
    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL

    def capability(self, parameters: dict[str, Any]) -> Any:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return ""

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        values = parameters.get("currency") or []
        if isinstance(values, str):
            values = [values]
        return [row for row in records if not values or row.get("currency") in values]


adapter = Adapter()
