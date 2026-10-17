"""Verified SLA requests and parsing behind the local leaf interface."""

import json
from dataclasses import dataclass
from typing import Any

from dogopencli.collect import collect_scope, execute_bounded
from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    NOT_FOUND,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse

PAGE_SIZE = 5000
FILTER_FIELDS = {
    "bizCategory": "bizCategory",
    "creditorCurrency": "creditorCurrency",
    "regionCode": "regionCode",
    "status": "status",
}


def response_document(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict):
        raise CliError(INVALID_RESPONSE, "response envelope is not an object")
    if document.get("success") is not True:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return document


@dataclass(frozen=True)
class BaselineList:
    name: str = "payment.sla.baselines.list"
    default_scope: str = "baselines"
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="iglobalfundcontrol.alipay.com",
        path="/api/fundOutSlaBaseline/queryFundOutSlaBaseline",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset(
            {
                "bizCategory",
                "bizLegalEntity",
                "creditorCurrency",
                "regionCode",
                "status",
                "pageNo",
                "pageSize",
            }
        ),
        rebuild_page_size=10000,
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope != self.default_scope
            or page_num < 0
            or page_size not in (PAGE_SIZE, 10000)
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified SLA list request")
        return {"pageNo": page_num, "pageSize": page_size}

    def identity_key(self, row: dict[str, Any]) -> str:
        return row["id"]

    def parse_page(self, body: bytes) -> ParsedPage:
        document = response_document(body)
        for key in ("pageNo", "pageSize", "totalCount"):
            if type(document.get(key)) is not int:
                raise CliError(INVALID_RESPONSE, f"invalid pagination field {key}")
        number, size, total = (
            document[key] for key in ("pageNo", "pageSize", "totalCount")
        )
        if number < 0 or size <= 0 or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid SLA pagination metadata")
        rows = document.get("resultDataList", [] if total == 0 else None)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(INVALID_RESPONSE, "invalid resultDataList")
        if (total == 0 and rows) or len(rows) > size:
            raise CliError(INVALID_RESPONSE, "inconsistent SLA page capacity")
        for row in rows:
            if not isinstance(row.get("id"), str) or not row["id"].strip():
                raise CliError(INVALID_RESPONSE, "row is missing id")
        return ParsedPage(rows, number, size, total, -(-total // size))


@dataclass(frozen=True)
class BaselineDetail:
    name: str = "payment.sla.baselines.get"
    contract: EndpointContract = EndpointContract(
        method="GET",
        host="iglobalfundcontrol.alipay.com",
        path="/api/fundOutSlaBaseline/getFundOutSlaBaselineDetail",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"slaBaselineId"}),
    )


SLA_CAPABILITY = BaselineList()
SLA_DETAIL = BaselineDetail()


def parse_detail(body: bytes, identity: str) -> dict[str, Any]:
    detail = response_document(body).get("resultData")
    if detail is None:
        raise CliError(NOT_FOUND, f"SLA baseline {identity} does not exist")
    if not isinstance(detail, dict):
        raise CliError(INVALID_RESPONSE, "invalid resultData")
    if detail.get("id") != identity:
        raise CliError(
            INVALID_RESPONSE, "detail id does not match the requested slaBaselineId"
        )
    return detail


FILTERS = {
    "biz_category": "bizCategory",
    "creditor_currency": "creditorCurrency",
    "region_code": "regionCode",
    "status": "status",
    "biz_legal_entity": "bizLegalEntity",
}


def native_filters(parameters: dict[str, Any]) -> dict[str, str]:
    result = {}
    for flag, value in parameters.items():
        key = flag.replace("-", "_")
        if key not in FILTERS or value is None or value == []:
            continue
        values = value if isinstance(value, list) else [value]
        if len(values) != 1 or not isinstance(values[0], str) or not values[0].strip():
            raise CliError(
                INVALID_ARGUMENT, f"{flag} requires one nonempty value", exit_code=2
            )
        result[FILTERS[key]] = values[0]
    return result


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        native_filters(parameters)
        return SLA_CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_filters(parameters))

    def collector(
        self, capability: Any, transport: Any, scope: str, *, progress: Any = None
    ) -> Any:
        candidate = collect_scope(
            capability,
            transport,
            capability.default_scope,
            json.loads(scope),
            progress=progress,
        )
        return candidate

    def get(
        self, session: Any, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        response = execute_bounded(
            SLA_DETAIL, session.transport(SLA_DETAIL), {"slaBaselineId": identity}
        )
        return parse_detail(response.body, identity)

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        filters = native_filters(parameters)
        if "bizLegalEntity" in filters:
            raise CliError(
                INVALID_ARGUMENT,
                "Business legal entity has no verified cached field; use --live",
                exit_code=2,
            )
        return [
            row
            for row in records
            if all(
                row.get(FILTER_FIELDS[key]) == value for key, value in filters.items()
            )
        ]


adapter = Adapter()
