"""Native Efficient Service fee-order contract, independently verified for #97."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from .spec import (
    ENV_RESULT_FLAG,
    PROFILE_DATED,
    RUNTIMES,
    TENANT,
    ListSpec,
    ScopeOption,
)

FIELDS = (
    "id",
    "tntInstId",
    "area",
    "bankAliasName",
    "bizEntityCode",
    "bizLine",
    "bizOrderNo",
    "bizType",
    "clientId",
    "clientPriceId",
    "currency",
    "currencyPair",
    "exchangeRate",
    "feeAmount",
    "fundLinkedNo",
    "gmtCreate",
    "gmtModified",
    "pricingCurrency",
    "serviceDate",
    "serviceTime",
    "serviceType",
    "transAmount",
)
FEE_ORDERS = ListSpec(
    path=("pricing", "fee-orders"),
    kind=RUNTIMES,
    title="Efficient Service fee orders",
    endpoint="/getFeeOrderList.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    total=("result", "count"),
    identity=("id",),
    require_inner_success=True,
    profile=PROFILE_DATED,
    series_field="serviceDate",
    series_format="%Y%m%d",
    template={
        "tntInstId": TENANT,
        "feeOrderListQueryVO": {
            "tntInstId": TENANT,
            "timeZone": "GMT+08",
        },
    },
    vo_field="feeOrderListQueryVO",
    page_size=10,
    scope_options=(
        ScopeOption(
            "from_date",
            "beginDate",
            "Inclusive Service Date start (YYYYMMDD), native GMT+08; at "
            "most 31 calendar days.",
            required=True,
            date=True,
            window="from",
        ),
        ScopeOption(
            "to_date",
            "endDate",
            "Inclusive Service Date end (YYYYMMDD), native GMT+08; at "
            "most 31 calendar days.",
            required=True,
            date=True,
            window="to",
        ),
    ),
    table_columns=(
        "id",
        "serviceDate",
        "feeAmount",
        "pricingCurrency",
        "transAmount",
        "currency",
    ),
    projection="fee_orders",
    schema_version="fee-orders-v1",
    notes=(
        "New fee-order inquiry; valuations list/get remain unsupported. "
        "No valuation alias or cache migration.",
        "Required inclusive beginDate/endDate bound native serviceDate, "
        "with at most 31 calendar days and fixed query timeZone GMT+08. "
        "No broad-window fallback.",
        "Native GET uses tenant GUAPW3SG and feeOrderListQueryVO JSON, "
        "rowStart/pageSize offsets of width 10, result.data and "
        "result.count.",
        "Native id identifies a fee order within the fixed tenant. "
        "Fee(Pricing CCY) is feeAmount with pricingCurrency; "
        "Transaction Amount is transAmount with currency. Decimal "
        "source strings are preserved without conversion or inferred "
        "valuation.",
        "serviceTime/gmtCreate/gmtModified are naive source YYYY-MM-DD "
        "HH:mm:ss strings, without inferred UTC offset; serviceDate is "
        "the query/retention business day and fetched_at is capture "
        "time.",
        "Raw status is preserved when present; it is absent from the "
        "observed source sample. Unknown fields are excluded.",
    ),
)


def validate_fee_query(values: dict[str, Any]) -> None:
    start = datetime.strptime(values["beginDate"], "%Y%m%d")
    end = datetime.strptime(values["endDate"], "%Y%m%d")
    if not 0 <= (end - start).days <= 30:
        raise CliError(
            INVALID_ARGUMENT,
            "fee-order range must contain 1 to 31 inclusive calendar days",
            exit_code=EXIT_USAGE,
        )


def project_fee_order(row: dict[str, Any]) -> dict[str, Any]:
    def invalid(field: str) -> None:
        raise CliError(INVALID_RESPONSE, f"fee_orders.{field}: invalid native field")

    if row.get("tntInstId") != TENANT:
        invalid("tntInstId")
    if not isinstance(row.get("id"), str) or not row["id"].strip():
        invalid("id")
    for field in (*FIELDS, "status"):
        value = row.get(field)
        if value is not None and not isinstance(value, str):
            invalid(field)
    date = row.get("serviceDate")
    try:
        if (
            not isinstance(date, str)
            or len(date) != 8
            or not date.isascii()
            or not date.isdigit()
        ):
            raise ValueError
        datetime.strptime(date, "%Y%m%d")
    except ValueError:
        invalid("serviceDate")
    for field in ("feeAmount", "transAmount", "exchangeRate"):
        value = row.get(field)
        if value is None or value == "":
            continue
        try:
            if not Decimal(value).is_finite():
                raise ValueError
        except (InvalidOperation, ValueError):
            invalid(field)
    for amount, currency in (
        ("feeAmount", "pricingCurrency"),
        ("transAmount", "currency"),
    ):
        if row.get(amount) not in (None, ""):
            unit = row.get(currency)
            if not isinstance(unit, str) or not re.fullmatch(r"[A-Z]{3}", unit):
                invalid(currency)
    for field in ("serviceTime", "gmtCreate", "gmtModified"):
        value = row.get(field)
        if value is None or value == "":
            continue
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            if parsed.strftime("%Y-%m-%d %H:%M:%S") != value:
                raise ValueError
        except ValueError:
            invalid(field)
    return {field: row[field] for field in (*FIELDS, "status") if field in row}
