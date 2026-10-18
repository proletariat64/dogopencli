"""Native credit settings: full source lines and unmodified nested members."""

import json
from dataclasses import dataclass
from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse

PAGE_SIZE = 100
TENANT = "GUAPW3SG"


def native_identity(value: Any) -> str:
    if type(value) not in (str, int) or (isinstance(value, str) and not value.strip()):
        raise CliError(
            INVALID_RESPONSE, "native identity must be a nonempty string or integer"
        )
    return canonical(value)


@dataclass(frozen=True)
class CreditInquiry:
    name: str = "liquidity.cash.credit_lines.list"
    page_url: str = LIQUIDITY_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/queryBankCreditLineByParams.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "bankCreditLineQuery"}),
        fixed_body_values=(("tntInstId", TENANT),),
        json_body_contracts=(
            (
                "bankCreditLineQuery",
                frozenset({"rowStart", "pageSize"}),
                (),
                frozenset({PAGE_SIZE}),
            ),
        ),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            scope
            or type(page_size) is not int
            or page_size != PAGE_SIZE
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified credit request")
        return {
            "tntInstId": TENANT,
            "bankCreditLineQuery": json.dumps(
                {"rowStart": row_start, "pageSize": PAGE_SIZE}
            ),
        }

    def validate_record(self, row: dict[str, Any]) -> None:
        parent = native_identity(row.get("id"))
        if "tntInstId" in row and row["tntInstId"] != TENANT:
            raise CliError(
                INVALID_RESPONSE, "credit line tenant is outside requested scope"
            )
        members = row.get("bankAccountCreditLineList")
        if members is None:
            return
        if not isinstance(members, list) or any(
            not isinstance(member, dict) for member in members
        ):
            raise CliError(INVALID_RESPONSE, "credit members are not an object array")
        seen: set[str] = set()
        for member in members:
            identity = native_identity(member.get("id"))
            if identity in seen:
                raise CliError(
                    INVALID_RESPONSE, "duplicate native credit member identity"
                )
            seen.add(identity)
            if (
                "creditLineId" in member
                and native_identity(member["creditLineId"]) != parent
            ):
                raise CliError(
                    INVALID_RESPONSE, "credit member parent identity mismatch"
                )
            if "tntInstId" in member and member["tntInstId"] != TENANT:
                raise CliError(
                    INVALID_RESPONSE, "credit member tenant is outside requested scope"
                )

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "response envelope is not an object")
        if type(document.get("resultFlag")) is not bool:
            raise CliError(INVALID_RESPONSE, "resultFlag is not boolean")
        if document["resultFlag"] is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        result = document.get("result")
        if not isinstance(result, dict):
            raise CliError(INVALID_RESPONSE, "response result is not an object")
        if result.get("success") is False:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        if result.get("success") is not True:
            raise CliError(INVALID_RESPONSE, "inner success is not boolean true")
        rows, total = result.get("data"), document.get("count")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(
                INVALID_RESPONSE, "record container is not a list of objects"
            )
        if (
            type(total) is not int
            or total < 0
            or type(result.get("count")) is not int
            or result["count"] != total
        ):
            raise CliError(
                INVALID_RESPONSE,
                "credit outer and inner totals must agree as nonnegative integers",
            )
        for row in rows:
            self.validate_record(row)
        return rows, total


CAPABILITY = CreditInquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return ""

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
