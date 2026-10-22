"""One verified payment configuration page through the host List SDK."""

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
    ("name", "ruleName"),
    ("status", "status"),
    ("communication_mode", "communicationMode"),
    ("integration_mode", "integrationMode"),
    ("entity", "bizLegalEntityList"),
    ("business_line", "businessCategoryList"),
    ("bank", "debtorInstList"),
    ("currency", "creditorCurrencyList"),
    ("region", "creditorCountryList"),
    ("bank_account", "debtorAccountNoList"),
    ("clearing_network", "clearingNetworkList"),
)
ARRAY_FIELDS = (
    "bizLegalEntityList",
    "businessCategoryList",
    "debtorInstList",
    "creditorCurrencyList",
    "creditorCountryList",
    "debtorAccountNoList",
    "clearingNetworkList",
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
    name = "payment.rules.retry.list"
    page_url = (
        "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
        "abnormalTransactionManagement/retryRule"
    )
    contract = EndpointContract(
        method="GET",
        host="ifundcontrolprodops.alipay.com",
        path="/api/fundOut/flowOperation/exceptionRetryRule/page",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
        fixed_body_values=(("pageNo", 0), ("pageSize", PAGE_SIZE)),
        encoding="query",
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
        data = document.get("data")
        if not isinstance(data, dict):
            raise CliError(INVALID_RESPONSE, "configuration data is not an object")
        for field in ("pageNo", "pageSize", "totalCount", "totalPageNo"):
            if type(data.get(field)) is not int or data[field] < 0:
                raise CliError(
                    INVALID_RESPONSE,
                    "pagination fields require nonnegative native integers",
                )
        rows, total = data.get("businessDataList"), data["totalCount"]
        if (
            not isinstance(rows, list)
            or data["pageNo"] != 0
            or data["pageSize"] != PAGE_SIZE
        ):
            raise CliError(INVALID_RESPONSE, "invalid configuration rows or page echo")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("ruleId"), str)
                or not row["ruleId"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE,
                    "configuration identity must be a nonblank native string",
                )
        # totalPageNo is a native placeholder; the SDK uses totalCount instead.
        return ParsedPage(rows, 0, PAGE_SIZE, total, -(-total // PAGE_SIZE))


CAPABILITY = Inquiry()


class Adapter:
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

        def matches(row: dict[str, Any]) -> bool:
            for parameter, field in FILTERS:
                accepted = parameters.get(parameter)
                if not accepted:
                    continue
                value = row.get(field)
                if field in ARRAY_FIELDS:
                    matched = isinstance(value, list) and any(
                        isinstance(item, str) and item in accepted for item in value
                    )
                else:
                    matched = isinstance(value, str) and value in accepted
                if not matched:
                    return False
            return True

        return sorted(
            (row for row in records if matches(row)), key=lambda row: row["ruleId"]
        )


adapter = Adapter()
