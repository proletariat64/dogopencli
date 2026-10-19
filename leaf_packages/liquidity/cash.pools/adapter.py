"""BANK cash pool settings List with full native records and members."""

from dataclasses import dataclass
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

PAGE_SIZE = 100
TENANT = "GUAPW3SG"


@dataclass(frozen=True)
class Inquiry:
    name: str = "liquidity.cash.pools.list"
    page_url: str = LIQUIDITY_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/cashPoolList.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset(
            {"tntInstId", "cashPoolCategory", "rowStart", "pageSize"}
        ),
        fixed_body_values=(
            ("tntInstId", TENANT),
            ("cashPoolCategory", "BANK"),
            ("pageSize", PAGE_SIZE),
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
            raise CliError(REQUEST_NOT_ALLOWED, "unverified cash.pools request")
        return {
            "rowStart": row_start,
            "pageSize": PAGE_SIZE,
            "tntInstId": TENANT,
            "cashPoolCategory": "BANK",
        }

    def record_identity(self, record: dict[str, Any]) -> str:
        value = record.get("id")
        if (
            not isinstance(value, (str, int))
            or isinstance(value, bool)
            or (isinstance(value, str) and not value.strip())
        ):
            raise CliError(INVALID_RESPONSE, "record is missing identity field id")
        return canonical(value)

    def validate_scope(self, record: dict[str, Any]) -> None:
        if record.get("tntInstId") not in (None, "", TENANT):
            raise CliError(
                INVALID_RESPONSE, "native tenant contradicts requested scope"
            )
        if "cashPoolCategory" in record and record["cashPoolCategory"] != "BANK":
            raise CliError(
                INVALID_RESPONSE, "native pool category contradicts BANK scope"
            )

    def validate_members(self, record: dict[str, Any], field: str, echo: str) -> None:
        members = record.get(field)
        if members is None:
            return
        if not isinstance(members, list) or any(
            not isinstance(row, dict) for row in members
        ):
            raise CliError(
                INVALID_RESPONSE, "native member container is not an object array"
            )
        parent = self.record_identity(record)
        seen: set[str] = set()
        for member in members:
            self.validate_scope(member)
            identity = self.record_identity(member)
            if identity in seen:
                raise CliError(INVALID_RESPONSE, "duplicate native member identity")
            seen.add(identity)
            if echo in member and canonical(member[echo]) != parent:
                raise CliError(
                    INVALID_RESPONSE, "native member parent identity does not match"
                )
            if field == "cashPoolMemberVOS":
                self.validate_members(member, "cashPoolSwapRuleVOS", "cashPoolMemberId")

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "response envelope is not an object")
        if type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "success is not boolean")
        if document["success"] is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        result = document.get("data")
        if not isinstance(result, dict):
            raise CliError(INVALID_RESPONSE, "response result is not an object")
        if result.get("success") is False:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        rows, total = result.get("data"), result.get("totalCount")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(
                INVALID_RESPONSE, "record container is not a list of objects"
            )
        if type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE, "reported total is not a nonnegative integer"
            )
        for row in rows:
            self.validate_scope(row)
            self.record_identity(row)
            self.validate_members(row, "cashPoolMemberVOS", "cashPoolId")
        return rows, total


CAPABILITY = Inquiry()


class DetailInquiry:
    name = "liquidity.cash.pools.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/cashPoolDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"inUse", "tntInstId", "id", "cashPoolCategory"}),
        fixed_body_values=(
            ("tntInstId", "GUAPW3SG"),
            ("inUse", "Y"),
            ("cashPoolCategory", "BANK"),
        ),
        encoding="json",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT,
                "detail identity must be a nonempty string",
                exit_code=2,
            )
        return {
            "id": identity,
            "tntInstId": "GUAPW3SG",
            "inUse": "Y",
            "cashPoolCategory": "BANK",
        }

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "detail success marker is not boolean")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        detail = document
        detail = detail.get("data")
        if not isinstance(detail, dict):
            raise CliError(INVALID_RESPONSE, "detail container is not an object")
        value = detail.get("id")
        if not isinstance(value, str) or not value.strip() or value != identity:
            raise CliError(INVALID_RESPONSE, "detail identity does not match request")
        CAPABILITY.validate_scope(detail)
        CAPABILITY.validate_members(detail, "cashPoolMemberVOS", "cashPoolId")
        return detail


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
        return records


adapter = Adapter()
