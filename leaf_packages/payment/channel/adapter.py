"""Payment channels: host-owned collection and hard native-ID conflict failure."""

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse

SCOPES = ("EXTERNAL", "LIQUIDITY", "MANUAL", "SETTLEMENT")
PAGE_SIZE = 100
PAGE_SIZES = tuple(range(1, PAGE_SIZE + 1))
FILTERS = {
    "financial_inst_id": "financialInstCode",
    "debit_inst_country_code": "debitInstCountryCode",
    "status": "status",
    "debit_account_name": "debitAccountName",
    "debit_account_no": "debitAccountNo",
    "clearing_system_name": "clearingSystemName",
    "debit_currency": "debitCurrency",
    "credit_currency": "creditCurrency",
}


def fail(message: str, code: str = "INVALID_RESPONSE") -> None:
    raise CliError(code, message, exit_code=2 if code == "INVALID_ARGUMENT" else 1)


def validate(parameters: dict) -> None:
    if parameters.get("payout_type", "EXTERNAL") not in SCOPES:
        fail("one verified payout-type is required", "INVALID_ARGUMENT")
    for name in FILTERS:
        values = parameters.get(name)
        if values is not None and (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            fail("channel filters require exact nonblank strings", "INVALID_ARGUMENT")


class Inquiry:
    name = "payment.channel.channels"
    page_url = (
        "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
    )
    contract = EndpointContract(
        method="POST",
        host="ifundboss-api.alipay.com",
        path="/payout/api/ability/search.json",
        page_size=PAGE_SIZE,
        one_based=True,
        scope_field="payoutType",
        allowed_body_keys=frozenset({"payoutType", "pageNum", "pageSize"}),
        allowed_page_sizes=PAGE_SIZES,
        duplicate_policy="allow_identical_overlap",
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict:
        if (
            scope not in SCOPES
            or type(page_num) is not int
            or page_num < 1
            or type(page_size) is not int
            or page_size not in PAGE_SIZES
        ):
            fail("unverified payment channel request", "REQUEST_NOT_ALLOWED")
        return {"payoutType": scope, "pageNum": page_num, "pageSize": page_size}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                "INVALID_RESPONSE", "channel response is not JSON"
            ) from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            fail("channel outer success must be boolean")
        if not document["success"]:
            message = document.get("msg")
            if (
                document.get("msgCode") == "IPAY_RS_510090020"
                and document.get("status") is False
                and isinstance(message, str)
                and "debit account not exists" in message
            ):
                raise CliError(
                    "BUSINESS_QUERY_FAILED",
                    "channel query encountered the known missing debit account",
                    meta={"channel_record_hole": message},
                )
            fail("backend outer channel query failed", "BUSINESS_QUERY_FAILED")
        if "status" in document:
            if type(document["status"]) is not bool:
                fail("channel outer status must be boolean")
            if not document["status"]:
                fail("backend channel status failed", "BUSINESS_QUERY_FAILED")
        result = document.get("resultObj")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            fail("channel inner success must be boolean")
        if not result["success"]:
            fail("backend inner channel query failed", "BUSINESS_QUERY_FAILED")
        keys = ("pageNum", "pageSize", "totalCount", "totalPages")
        if any(type(result.get(key)) is not int for key in keys):
            fail("channel page metadata must be native integers")
        page, size, total, pages = (result[key] for key in keys)
        if size not in PAGE_SIZES or total < 0 or pages < 0 or page < 1:
            fail("channel native pagination is invalid or clamped")
        rows = result.get("payoutAbilityVOList")
        if not isinstance(rows, list) or len(rows) > size:
            fail("channel native records or pagination are invalid")
        for row in rows:
            if not isinstance(row, dict):
                fail("channel records must be objects")
            identity = row.get("abilityId")
            if type(identity) not in (int, str) or (
                isinstance(identity, str) and not identity.strip()
            ):
                fail("channel requires native abilityId")
        return ParsedPage(rows, page, size, total, pages)

    def pagination_hole(self, error: CliError) -> str | None:
        if error.code == "BUSINESS_QUERY_FAILED" and isinstance(error.meta, dict):
            value = error.meta.get("channel_record_hole")
            if isinstance(value, str) and value:
                return value
        return None

    def pagination_terminal(self, page: ParsedPage, requested_page: int) -> bool:
        # The host additionally requires exact repetition of a previously read
        # successful short page at this same width, including every native field.
        return page.page_num < requested_page and 0 < len(page.records) < page.page_size


CAPABILITY = Inquiry()


class Adapter:
    def capability(self, parameters: dict) -> Inquiry:
        validate(parameters)
        return CAPABILITY

    def scope(self, parameters: dict) -> str:
        validate(parameters)
        return parameters.get("payout_type", "EXTERNAL")

    def filter(self, records: list[dict], parameters: dict) -> list[dict]:
        validate(parameters)
        return [
            row
            for row in records
            if all(
                isinstance(row.get(field), str) and row[field] in parameters[name]
                for name, field in FILTERS.items()
                if parameters.get(name) is not None
            )
        ]


adapter = Adapter()
