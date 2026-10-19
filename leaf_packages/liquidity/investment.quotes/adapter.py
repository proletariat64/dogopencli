"""Qualified QUOTED response and complete native quotation detail root."""

from datetime import datetime
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

PAGE_SIZE = 5000
TENANT = "GUAPW3SG"


def native_dates(parameters: dict[str, Any]) -> dict[str, Any]:
    bounds = []
    for field in ("from_date", "to_date"):
        value = parameters.get(field)
        try:
            if (
                not isinstance(value, str)
                or len(value) != 8
                or not value.isascii()
                or not value.isdigit()
            ):
                raise ValueError
            if datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d") != value:
                raise ValueError
        except ValueError as error:
            raise CliError(
                INVALID_ARGUMENT,
                "value-date bounds require valid YYYYMMDD",
                exit_code=2,
            ) from error
        bounds.append(value)
    if bounds[0] > bounds[1]:
        raise CliError(INVALID_ARGUMENT, "value-date start is after end", exit_code=2)
    return {
        "dataType": "QUOTED",
        "startValueDate": bounds[0],
        "endValueDate": bounds[1],
        "timeZone": None,
    }


def document(body: bytes) -> dict[str, Any]:
    try:
        value = parse(body)
    except (ValueError, UnicodeError) as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(value, dict):
        raise CliError(INVALID_RESPONSE, "response envelope is not an object")
    return value


class Inquiry:
    name = "liquidity.investment.quotes.list"
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/quotationAnalysis.json",
            page_size=PAGE_SIZE,
            one_based=False,
            single_page=True,
            allowed_body_keys=frozenset({*values, "rowStart", "pageSize"}),
            fixed_body_values=tuple(values.items())
            + (("rowStart", 0), ("pageSize", PAGE_SIZE)),
        )

    def page_body(self, scope: str, position: int, page_size: int) -> dict[str, Any]:
        if (
            scope != canonical(self.values)
            or type(position) is not int
            or position != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "quotation List has one qualified response"
            )
        return {**self.values, "rowStart": 0, "pageSize": PAGE_SIZE}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], None]:
        value = document(body)
        if type(value.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "quotation success marker is not boolean")
        if not value["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        rows = value.get("data")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "quotation records are not an array")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("quotationOrderId"), str)
                or not row["quotationOrderId"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE, "quotation has no native string identity"
                )
            if "tntInstId" in row and row["tntInstId"] != TENANT:
                raise CliError(INVALID_RESPONSE, "quotation tenant contradicts scope")
            if "valueDate" in row:
                day = row["valueDate"]
                if (
                    not isinstance(day, str)
                    or not self.values["startValueDate"]
                    <= day
                    <= self.values["endValueDate"]
                ):
                    raise CliError(
                        INVALID_RESPONSE, "quotation valueDate contradicts scope"
                    )
        return rows, None


class DetailInquiry:
    name = "liquidity.investment.quotes.get"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/queryQuotationOrder.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"quotationOrderId"}),
        encoding="form",
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not isinstance(identity, str) or not identity.strip():
            raise CliError(
                INVALID_ARGUMENT, "quotation identity must be nonempty", exit_code=2
            )
        return {"quotationOrderId": identity}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        base = document(body).get("baseResult")
        if not isinstance(base, dict) or type(base.get("success")) is not bool:
            raise CliError(
                INVALID_RESPONSE, "quotation detail success marker is invalid"
            )
        if not base["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        root = base.get("data")
        if not isinstance(root, dict):
            raise CliError(INVALID_RESPONSE, "quotation detail root is not an object")
        detail = root.get("quotationDetail")
        if (
            not isinstance(detail, dict)
            or not isinstance(detail.get("quotationId"), str)
            or detail["quotationId"] != identity
        ):
            raise CliError(INVALID_RESPONSE, "native nested quotation identity differs")
        if "tntInstId" in root and root["tntInstId"] != TENANT:
            raise CliError(
                INVALID_RESPONSE, "quotation detail tenant contradicts scope"
            )
        return root


DETAIL = DetailInquiry()


class Adapter:
    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_dates(parameters))

    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry(native_dates(parameters))

    def detail_capability(self, parameters: dict[str, Any]) -> DetailInquiry:
        return DETAIL

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
