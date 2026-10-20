"""VA-rule capacity inquiry using qualified SDK short-page termination."""

from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse

PAGE_SIZE = 100


def identity_order(record: dict[str, Any]) -> tuple[Any, ...]:
    identity = record["ruleId"]
    return (
        (0, int(identity), identity)
        if identity.isascii() and identity.isdigit()
        else (1, identity)
    )


class Inquiry:
    name = "collection.va.capacity.list"
    page_url = "https://ifundbossportal.alipay.com/voucher/VARuleManage"
    contract = EndpointContract(
        method="POST",
        host="ifundboss-api.alipay.com",
        path="/ivostro/api/warningUseCount/pageList.json",
        page_size=PAGE_SIZE,
        one_based=True,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
        fixed_body_values=(("pageSize", PAGE_SIZE),),
        total_semantics="unknown",
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope != "capacity"
            or type(page_num) is not int
            or page_num < 1
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified VA capacity request")
        return {"pageNo": page_num, "pageSize": page_size}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "response requires boolean success")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        if (
            type(document.get("pageNo")) is not int
            or document["pageNo"] < 1
            or type(document.get("pageSize")) is not int
            or document["pageSize"] != PAGE_SIZE
        ):
            raise CliError(INVALID_RESPONSE, "invalid VA capacity page echoes")
        rows = document.get("resultDataList")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "VA capacity requires resultDataList")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("ruleId"), str)
                or not row["ruleId"].strip()
            ):
                raise CliError(INVALID_RESPONSE, "VA capacity requires native ruleId")
        # Native totalCount is unreliable and is not a coverage assertion.
        return ParsedPage(rows, document["pageNo"], document["pageSize"], None, None)


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry()

    def scope(self, parameters: dict[str, Any]) -> str:
        return "capacity"

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        fields = {"bank_va_rule_id": "bankAccountVaId", "va_rule_id": "ruleId"}
        return sorted(
            (
                record
                for record in records
                if all(
                    record.get(field) in parameters[name]
                    for name, field in fields.items()
                    if parameters.get(name)
                )
            ),
            key=identity_order,
        )


adapter = Adapter()
