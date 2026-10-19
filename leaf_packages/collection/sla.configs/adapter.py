"""Native collection SLA List and independent detail through the host SDK."""

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

FILTERS = (
    ("business_line", "businessCategory"),
    ("entity", "legalEntityCode"),
    ("currency", "creditorCurrency"),
    ("region", "creditorRegion"),
)
PAGE_SIZE = 1000


def validate_filters(parameters: dict[str, Any]) -> None:
    for parameter, _ in FILTERS:
        values = parameters.get(parameter)
        if values is None:
            continue
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "local filters require nonblank exact string values",
                exit_code=2,
            )


class Inquiry:
    name = "collection.sla.configs.list"
    page_url = "https://igfc.alipay.com/receivedPayment/sla/fundInSla"
    contract = EndpointContract(
        method="POST",
        host="iglobalfundcontrol.alipay.com",
        path="/api/fundInSlaConfig/search.json",
        page_size=PAGE_SIZE,
        one_based=False,
        single_page=True,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
        fixed_body_values=(("pageNo", 0), ("pageSize", PAGE_SIZE)),
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope != "all"
            or type(page_num) is not int
            or page_num != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED,
                "only the verified first configuration page is allowed",
            )
        return {"pageNo": 0, "pageSize": PAGE_SIZE}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "response requires a boolean success flag")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
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
        number = document["pageNo"]
        if document["pageSize"] != PAGE_SIZE or number != 0:
            raise CliError(INVALID_RESPONSE, "configuration pagination echo mismatch")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("slaConfigId"), str)
                or not row["slaConfigId"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE,
                    "configuration identity must be a nonblank native string",
                )
        return ParsedPage(rows, number, PAGE_SIZE, total, -(-total // PAGE_SIZE))


class DetailInquiry:
    name = "collection.sla.configs.get"
    page_url = "https://igfc.alipay.com/receivedPayment/sla/fundInSla"
    contract = EndpointContract(
        method="GET",
        host="iglobalfundcontrol.alipay.com",
        path="/api/fundInSlaConfig/getDetailBySlaConfigId.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"slaConfigId"}),
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT, "slaConfigId must be nonblank", exit_code=2
            )
        return {"slaConfigId": identity}

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
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected SLA detail inquiry")
        detail = document.get("resultData")
        if not isinstance(detail, dict) or detail.get("slaConfigId") != identity:
            raise CliError(INVALID_RESPONSE, "native SLA detail identity differs")
        required = tuple(field for _, field in FILTERS) + (
            "endToEndSla",
            "ipayInnerSla",
            "holidayLimit",
        )
        if any(field not in detail for field in required):
            raise CliError(
                INVALID_RESPONSE, "SLA detail is missing required business fields"
            )
        holiday = detail["holidayLimit"]
        if holiday is not None and (
            not isinstance(holiday, dict)
            or any(
                not isinstance(holiday.get(field), list)
                or any(not isinstance(value, str) for value in holiday[field])
                for field in ("currencyCodes", "regionCodes")
            )
        ):
            raise CliError(
                INVALID_RESPONSE, "SLA holidayLimit requires complete string arrays"
            )
        return detail


CAPABILITY = Inquiry()


class Adapter:
    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DetailInquiry()

    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        validate_filters(parameters)
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        validate_filters(parameters)
        return "all"

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        validate_filters(parameters)
        return sorted(
            (
                row
                for row in records
                if all(
                    not parameters.get(parameter)
                    or row.get(field) in parameters[parameter]
                    for parameter, field in FILTERS
                )
            ),
            key=lambda row: (
                (0, int(row["slaConfigId"]), row["slaConfigId"])
                if row["slaConfigId"].isascii() and row["slaConfigId"].isdigit()
                else (1, row["slaConfigId"])
            ),
        )


adapter = Adapter()
