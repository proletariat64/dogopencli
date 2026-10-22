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

PAGE_SIZE = 1000
DETAIL_FIELDS = (
    "assembleStrategy",
    "assignInfo",
    "bankRuleId",
    "clientEntity",
    "creditAreas",
    "entity",
    "memo",
    "regionType",
    "ruleStatus",
    "sceneCodes",
    "vaRuleId",
)


def business_document(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except (ValueError, UnicodeError) as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get("success")) is not bool:
        raise CliError(INVALID_RESPONSE, "response requires a boolean success flag")
    if not document["success"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return document


def validate_identity(row: Any) -> None:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("vaRuleId"), str)
        or not row["vaRuleId"].strip()
    ):
        raise CliError(
            INVALID_RESPONSE, "VA rule identity must be a nonblank native string"
        )


def identity_order(row: dict[str, Any]) -> tuple[Any, ...]:
    identity = row["vaRuleId"]
    return (
        (0, int(identity), identity)
        if identity.isascii() and identity.isdigit()
        else (1, identity)
    )


class Inquiry:
    name = "collection.va.rules.list"
    page_url = "https://ifundbossportal.alipay.com/voucher/VARuleManage"
    contract = EndpointContract(
        method="POST",
        host="ifundboss-api.alipay.com",
        path="/ivostro/api/virtualAccountRule/list.json",
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
        document = business_document(body)
        if any(
            type(document.get(field)) is not int
            for field in ("pageNo", "pageSize", "totalCount")
        ):
            raise CliError(
                INVALID_RESPONSE,
                "configuration pagination fields require native integers",
            )
        total = document["totalCount"]
        rows = document.get("resultDataList", [] if total == 0 else None)
        if not isinstance(rows, list) or total < 0:
            raise CliError(
                INVALID_RESPONSE, "invalid configuration rows or native total"
            )
        if document["pageNo"] != 1 or document["pageSize"] != PAGE_SIZE:
            raise CliError(INVALID_RESPONSE, "VA rule pagination echo mismatch")
        for row in rows:
            validate_identity(row)
        return ParsedPage(rows, 1, PAGE_SIZE, total, -(-total // PAGE_SIZE))


CAPABILITY = Inquiry()


class DetailInquiry:
    name = "collection.va.rules.get"
    page_url = Inquiry.page_url
    contract = EndpointContract(
        method="GET",
        host="ifundboss-api.alipay.com",
        path="/ivostro/api/virtualAccountRule/detail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"vaRuleId"}),
        encoding="query",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT,
                "VA rule lookup must be a nonblank string",
                exit_code=2,
            )
        return {"vaRuleId": identity}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        row = business_document(body).get("resultObj")
        validate_identity(row)
        if row["vaRuleId"] != identity:
            raise CliError(INVALID_RESPONSE, "detail vaRuleId does not match request")
        if any(field not in row for field in DETAIL_FIELDS):
            raise CliError(
                INVALID_RESPONSE, "VA rule detail is missing core business fields"
            )
        return row


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return CAPABILITY

    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DetailInquiry()

    def scope(self, parameters: dict[str, Any]) -> str:
        return "all"

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return sorted(records, key=identity_order)


adapter = Adapter()
