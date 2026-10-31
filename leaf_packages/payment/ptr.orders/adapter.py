"""Existing outflow PTR orders: stable padded reads, then exact window trim."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INCOMPLETE_RESULT,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse
from dogopencli.temporal import (
    normalize_utc_milliseconds,
    parse_iso_millisecond_instant,
    parse_numeric_offset_instant,
)

SHANGHAI = timezone(timedelta(hours=8))
PAGE_SIZE = 500
BASELINE = "productionTrialRunFundOutAbilityVO"
STRINGS = frozenset(
    {
        "ptrOrderId",
        "caseId",
        "caseName",
        "caseType",
        "allocateOrderId",
        "finNetId",
        "bizRequestId",
        "creditorAccountAliasName",
        "creditorCurrency",
        "obo",
        "fvt",
        "referenceObo",
        "purposeCode",
        "orderStatus",
        "verifyStatus",
        "ptrFinalResult",
        "failureReason",
        "verifyFvtResult",
        "verifyOboResult",
        "verifyReferenceOboResult",
        "spentTime",
        "spentTimeInfoSource",
        "transactionRateRef",
    }
)
TIMESTAMPS = frozenset(
    {
        "gmtModified",
        "gmtCreate",
        "bizRequestTime",
        "lastVerificationDt",
        "allocatePayoutTime",
    }
)
BASELINE_STRINGS = frozenset(
    {
        "clearingSystemName",
        "debtorAccountAliasName",
        "financialInstCode",
        "regulatoryRequiredObo",
        "supportFvt",
        "supportObo",
        "supportReferenceObo",
        "integrationMode",
        "communicationMode",
    }
)
FILTERS = {
    "id": "ptrOrderId",
    "case_id": "caseId",
    "channel": f"{BASELINE}.financialInstCode",
    "debtor_account": f"{BASELINE}.debtorAccountAliasName",
    "debtor_currency": "debtorAmount.currencyCode",
    "creditor_currency": "creditorCurrency",
    "clearing_system": f"{BASELINE}.clearingSystemName",
    "order_status": "orderStatus",
    "verify_status": "verifyStatus",
    "final_result": "ptrFinalResult",
}


def invalid(message: str) -> None:
    raise CliError(INVALID_RESPONSE, message)


def finite_number(value: Any) -> bool:
    return (
        value is None
        or type(value) is int
        or type(value) is float
        and math.isfinite(value)
        or isinstance(value, Decimal)
        and value.is_finite()
    )


def project_money(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        invalid("PTR order money must be an object or null")
    strings = {"currency", "currencyCode", "currencyValue"}
    integers = {"cent", "centFactor"}
    retained = {
        key: item
        for key, item in value.items()
        if key in strings | integers | {"amount"}
    }
    for key, item in retained.items():
        valid = (
            finite_number(item)
            if key == "amount"
            else item is None or type(item) is (str if key in strings else int)
        )
        if not valid:
            invalid("invalid PTR order money field type")
    return retained


def project_order(row: Any) -> dict[str, Any]:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("ptrOrderId"), str)
        or not row["ptrOrderId"].strip()
        or type(row.get("gmtModified")) is not int
        or not isinstance(row.get(BASELINE), dict)
    ):
        invalid("PTR order requires native ptrOrderId, gmtModified and baseline object")
    retained = {}
    for key in STRINGS | TIMESTAMPS | {"transactionRate"}:
        if key not in row:
            continue
        value = row[key]
        valid = (
            finite_number(value)
            if key == "transactionRate"
            else value is None or type(value) is (str if key in STRINGS else int)
        )
        if not valid:
            invalid("invalid PTR order retained field type")
        retained[key] = value
    baseline = {
        key: value for key, value in row[BASELINE].items() if key in BASELINE_STRINGS
    }
    if any(value is not None and type(value) is not str for value in baseline.values()):
        invalid("invalid PTR order baseline field type")
    retained[BASELINE] = baseline
    for key in ("debtorAmount", "returnAmount"):
        if key in row:
            retained[key] = project_money(row[key])
    return retained


def validate_filters(parameters: dict[str, Any]) -> None:
    for name in FILTERS:
        values = parameters.get(name)
        if values is not None and (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "PTR filters require nonblank exact strings",
                exit_code=2,
            )


@dataclass(frozen=True)
class Window:
    from_time: str
    to_time: str
    start_ms: int
    end_ms: int
    native_begin: str
    native_end: str

    @property
    def scope(self) -> str:
        return canonical({"from_time": self.from_time, "to_time": self.to_time})


def window(parameters: dict[str, Any]) -> Window:
    validate_filters(parameters)
    try:
        start, end = (
            parse_numeric_offset_instant(parameters.get(name)).astimezone(SHANGHAI)
            for name in ("from_time", "to_time")
        )
        if (
            not start < end
            or end - start > timedelta(days=31)
            or end > datetime.now(timezone.utc)
        ):
            raise ValueError("invalid updated-time interval")
        return Window(
            start.isoformat(timespec="seconds"),
            end.isoformat(timespec="seconds"),
            int(start.timestamp()) * 1000,
            int(end.timestamp()) * 1000,
            (start - timedelta(seconds=1)).isoformat(sep=" ", timespec="seconds")[:-6],
            (end + timedelta(seconds=1)).isoformat(sep=" ", timespec="seconds")[:-6],
        )
    except (ValueError, OverflowError) as error:
        raise CliError(
            INVALID_ARGUMENT,
            "updated bounds require valid second-precision numeric offsets, an ordered "
            "interval of at most 31 days and a nonfuture cutoff; -00:00 is unknown",
            exit_code=2,
        ) from error


@dataclass(frozen=True)
class Inquiry:
    window: Window
    name = "payment.ptr.orders.list"
    page_url = (
        "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
        "productPTRManagement/orderInquiry"
    )

    @property
    def contract(self) -> EndpointContract:
        return EndpointContract(
            method="GET",
            host="iglobalfundcontrol.alipay.com",
            path="/api/ptr/manage/query.json",
            page_size=PAGE_SIZE,
            one_based=False,
            allowed_body_keys=frozenset(
                {"pageNo", "pageSize", "modifiedTimeBegin", "modifiedTimeEnd"}
            ),
            fixed_body_values=(
                ("pageNo", 0),
                ("pageSize", PAGE_SIZE),
                ("modifiedTimeBegin", self.window.native_begin),
                ("modifiedTimeEnd", self.window.native_end),
            ),
            encoding="query",
        )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope != self.window.scope
            or type(page_num) is not int
            or page_num != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "only the bound PTR order first page is allowed"
            )
        return dict(self.contract.fixed_body_values)

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                INVALID_RESPONSE, "PTR order response is not valid JSON"
            ) from error
        if not isinstance(document, dict):
            invalid("PTR order envelope must be an object")
        if document.get("success") is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        if (
            type(document.get("pageNo")) is not int
            or document["pageNo"] != 0
            or type(document.get("pageSize")) is not int
            or document["pageSize"] != PAGE_SIZE
            or type(document.get("totalCount")) is not int
            or document["totalCount"] < 0
            or not isinstance(document.get("resultDataList"), list)
        ):
            invalid("invalid PTR order rows or pagination echo")
        total = document["totalCount"]
        if total > PAGE_SIZE:
            raise CliError(
                INCOMPLETE_RESULT, "PTR order padded scope exceeds fixed 500 coverage"
            )
        rows = [project_order(row) for row in document["resultDataList"]]
        if any(
            not self.window.start_ms - 1000
            <= row["gmtModified"]
            <= self.window.end_ms + 1000
            for row in rows
        ):
            invalid("PTR order falls outside the padded acquisition window")
        return ParsedPage(rows, 0, PAGE_SIZE, total, 1 if total else 0)


class Adapter:
    def history_bounds(self, parameters: dict[str, Any]) -> dict[str, str]:
        selected = window(parameters)
        return {
            "from": normalize_utc_milliseconds(selected.from_time),
            "to": normalize_utc_milliseconds(
                parse_numeric_offset_instant(selected.to_time)
                - timedelta(milliseconds=1)
            ),
        }

    def history_parameters(self, bounds: dict[str, str]) -> dict[str, str]:
        try:
            start = parse_iso_millisecond_instant(bounds["from"])
            upper = parse_iso_millisecond_instant(bounds["to"])
            if start.microsecond != 0 or upper.microsecond != 999000:
                raise ValueError("PTR windows require whole-second public endpoints")
            parameters = {
                "from_time": start.astimezone(SHANGHAI).isoformat(timespec="seconds"),
                "to_time": (upper + timedelta(milliseconds=1))
                .astimezone(SHANGHAI)
                .isoformat(timespec="seconds"),
            }
            window(parameters)
            return parameters
        except (ValueError, OverflowError) as error:
            raise CliError(
                INVALID_ARGUMENT,
                "PTR history windows must recover an ordered whole-second interval",
                exit_code=2,
            ) from error

    def source_capability(self, name: str, parameters: dict[str, Any]) -> Inquiry:
        if name not in {"first", "second"}:
            raise CliError(REQUEST_NOT_ALLOWED, "undeclared PTR order source")
        return Inquiry(window(parameters))

    def source_scope(self, name: str, parameters: dict[str, Any]) -> str:
        return self.source_capability(name, parameters).window.scope

    def scope(self, parameters: dict[str, Any]) -> str:
        return window(parameters).scope

    def assemble(
        self, records_by_source: dict[str, list[dict]], parameters: dict[str, Any]
    ) -> list[dict]:
        selected_window = window(parameters)
        first_rows = sorted(
            records_by_source["first"], key=lambda row: row["ptrOrderId"]
        )
        second_rows = sorted(
            records_by_source["second"], key=lambda row: row["ptrOrderId"]
        )
        # Both sources have already proved total/unique-identity coverage. Thus
        # retained projection equality also proves their native counts agree.
        if canonical(first_rows) != canonical(second_rows):
            raise CliError(
                INCOMPLETE_RESULT,
                "PTR order padded scope changed between complete reads",
            )
        return [
            row
            for row in first_rows
            if selected_window.start_ms <= row["gmtModified"] < selected_window.end_ms
        ]

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        validate_filters(parameters)

        def matches(row: dict[str, Any]) -> bool:
            for name, path in FILTERS.items():
                accepted = parameters.get(name)
                if accepted is None:
                    continue
                value: Any = row
                for part in path.split("."):
                    value = value.get(part) if isinstance(value, dict) else None
                if not isinstance(value, str) or value not in accepted:
                    return False
            return True

        return [row for row in records if matches(row)]


adapter = Adapter()
