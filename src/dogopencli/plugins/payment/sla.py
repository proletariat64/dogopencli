"""Payment product SLA baseline capability: list plus per-ID detail.

Contract source: docs/research/payment/2026-09-08-sla-query-contracts.md
List: POST /api/fundOutSlaBaseline/queryFundOutSlaBaseline, zero-based
pageNo, explicit pageSize, success envelope with resultDataList/totalCount.
Detail: GET /api/fundOutSlaBaseline/getFundOutSlaBaselineDetail with the
verified query parameter slaBaselineId naming a list ``id``; success=true
with resultData=null means the baseline does not exist. A refresh collects
the full list and then every detail serially and publishes them together;
a detail is never substituted by its list row.
"""

from dataclasses import dataclass
from typing import Any

from ...errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    NOT_FOUND,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from ...jsonutil import parse
from .. import EndpointContract, ParsedPage

PAGE_SIZE = 5000

LIST_CONTRACT = EndpointContract(
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

DETAIL_CONTRACT = EndpointContract(
    method="GET",
    host="iglobalfundcontrol.alipay.com",
    path="/api/fundOutSlaBaseline/getFundOutSlaBaselineDetail",
    page_size=0,
    one_based=False,
    allowed_body_keys=frozenset({"slaBaselineId"}),
)

# Verified request field -> list record field. bizLegalEntity is a verified
# request parameter but the list response does not return the business legal
# entity field, so no local filter can be built on it.
FILTER_FIELDS = {
    "bizCategory": "bizCategory",
    "creditorCurrency": "creditorCurrency",
    "regionCode": "regionCode",
    "status": "status",
}

REQUEST_FILTER_KEYS = tuple(FILTER_FIELDS) + ("bizLegalEntity",)

PAGINATION_KEYS = ("pageNo", "pageSize", "totalCount")


def _invalid(message: str) -> CliError:
    return CliError(INVALID_RESPONSE, message)


def _record_key(record: dict[str, Any]) -> tuple[int, Any]:
    row_id = record.get("id")
    if isinstance(row_id, str) and row_id.isdigit():
        return (0, int(row_id))
    return (1, str(row_id))


def detail_body(baseline_id: str) -> dict[str, Any]:
    return {"slaBaselineId": baseline_id}


def parse_detail(body: bytes, baseline_id: str) -> dict[str, Any]:
    """Detail response; success with resultData=null means not found."""
    try:
        document = parse(body)
    except ValueError as error:
        raise _invalid("response is not valid JSON") from error
    if not isinstance(document, dict):
        raise _invalid("response envelope is not an object")
    if document.get("success") is not True:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    detail = document.get("resultData")
    if detail is None:
        raise CliError(NOT_FOUND, f"SLA baseline {baseline_id} does not exist")
    if not isinstance(detail, dict):
        raise _invalid("invalid resultData")
    if detail.get("id") != baseline_id:
        raise _invalid("detail id does not match the requested slaBaselineId")
    return detail


@dataclass(frozen=True)
class SlaDetailCapability:
    """Transport-facing handle for the detail endpoint (no pagination)."""

    name: str = "payment.sla.baselines.get"
    contract: EndpointContract = DETAIL_CONTRACT


@dataclass(frozen=True)
class SlaCapability:
    name: str = "payment.sla.baselines.list"
    source_config_key: str = "payment_sla"
    default_scope: str = "baselines"
    contract: EndpointContract = LIST_CONTRACT
    id_field: str = "id"
    table_columns: tuple[str, ...] = (
        "id",
        "bizCategory",
        "regionCode",
        "creditorCurrency",
        "status",
        "debitorSuccessSla",
        "creditorSuccessSla",
        "timezone",
        "holidayLimit",
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        return {"pageNo": page_num, "pageSize": page_size}

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        filters: dict[str, list[str]] = {}
        for key in REQUEST_FILTER_KEYS:
            if key not in body:
                continue
            value = body[key]
            values = value if isinstance(value, list) else [value]
            if not values or not all(isinstance(item, str) for item in values):
                raise CliError(REQUEST_NOT_ALLOWED, f"invalid filter value for {key}")
            filters[key] = list(values)
        return filters

    def filter_records(
        self, records: list[dict[str, Any]], filters: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        local = {key: values for key, values in filters.items() if key in FILTER_FIELDS}
        return [
            record
            for record in records
            if all(
                record.get(FILTER_FIELDS[key]) in values
                for key, values in local.items()
            )
        ]

    def sort_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deterministic local order: original id ascending."""
        return sorted(records, key=_record_key)

    def identity_key(self, record: dict[str, Any]) -> Any:
        return record.get(self.id_field)

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except ValueError as error:
            raise _invalid("response is not valid JSON") from error
        if not isinstance(document, dict):
            raise _invalid("response envelope is not an object")
        if document.get("success") is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        paging: dict[str, int] = {}
        for key in PAGINATION_KEYS:
            value = document.get(key)
            if isinstance(value, bool) or not isinstance(value, int):
                raise _invalid(f"invalid pagination field {key}")
            paging[key] = value
        if paging["pageSize"] <= 0:
            raise _invalid("invalid pagination field pageSize")
        rows: list[dict[str, Any]] = []
        if "resultDataList" not in document:
            # Verified branch: a successful zero-total response omits the
            # list key entirely; explicit null or a missing key with a
            # positive total are not normalized into an empty list.
            if paging["totalCount"] != 0:
                raise _invalid("missing resultDataList")
        else:
            raw_rows = document["resultDataList"]
            if not isinstance(raw_rows, list) or not all(
                isinstance(row, dict) for row in raw_rows
            ):
                raise _invalid("invalid resultDataList")
            rows = list(raw_rows)
        if paging["totalCount"] == 0 and rows:
            raise _invalid("inconsistent empty result")
        if len(rows) > paging["pageSize"]:
            raise _invalid("page returned more rows than pageSize")
        for row in rows:
            row_id = row.get("id")
            if not isinstance(row_id, str) or not row_id:
                raise _invalid("row is missing id")
        total_pages = -(-paging["totalCount"] // paging["pageSize"])
        return ParsedPage(
            records=rows,
            page_num=paging["pageNo"],
            page_size=paging["pageSize"],
            total_count=paging["totalCount"],
            total_pages=total_pages,
        )


SLA_CAPABILITY = SlaCapability()
SLA_DETAIL = SlaDetailCapability()
