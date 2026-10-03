"""Issue #87 bounded native transfer list, with independent release gate."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from .spec import (
    ENC_FORM,
    ENV_RESULT_FLAG,
    PROFILE_HISTORY,
    RUNTIMES,
    TENANT,
    ListSpec,
    ScopeOption,
)

STRING_FIELDS = (
    "orderNo",
    "orderId",
    "reportId",
    "tntInstId",
    "gmtCreate",
    "gmtModified",
    "debitValueDate",
    "creditValueDate",
    "debitEntity",
    "creditEntity",
    "debitBankId",
    "creditBankId",
    "debitCurrency",
    "creditCurrency",
    "debitAmount",
    "creditAmount",
    "orderStatus",
    "receiptStatus",
    "executeResult",
    "scene",
    "businessType",
    "orderType",
    "orderSource",
    "decisionMode",
)
INTEGER_FIELDS = ("gmtReturnFinnet",)
SAMPLED_FIELDS = {field: "str | null" for field in STRING_FIELDS}
SAMPLED_FIELDS.update({field: "int | null" for field in INTEGER_FIELDS})
SAMPLED_FIELDS["orderNo"] = SAMPLED_FIELDS["tntInstId"] = "str"

TRANSFER_ORDERS = ListSpec(
    path=("operations", "transfers"),
    kind=RUNTIMES,
    title="transfer orders",
    endpoint="/transferOrderQuery.json",
    method="POST",
    encoding=ENC_FORM,
    envelope=ENV_RESULT_FLAG,
    require_inner_success=True,
    container=("result", "data"),
    total=("count",),
    total_checks=(("result", "count"),),
    identity=("orderNo",),
    profile=PROFILE_HISTORY,
    page_size=10,
    template={
        "tntInstId": TENANT,
        "transferOrderQueryRequestVO": {
            "tntInstId": TENANT,
            "debitEntity": [],
            "creditEntity": [],
            "transactionStartDate": "",
            "transactionEndDate": "",
            "debitStartDate": "",
            "debitEndDate": "",
            "creditStartDate": "",
            "creditEndDate": "",
        },
    },
    vo_field="transferOrderQueryRequestVO",
    scope_options=(
        ScopeOption(
            "transaction_from",
            "transactionStartDate",
            "Native transaction query start day (YYYYMMDD); pair with "
            "--transaction-to.",
            required=True,
            date=True,
        ),
        ScopeOption(
            "transaction_to",
            "transactionEndDate",
            "Native transaction query end day (YYYYMMDD); pair with "
            "--transaction-from.",
            required=True,
            date=True,
        ),
    ),
    table_columns=(
        "orderNo",
        "gmtCreate",
        "debitCurrency",
        "debitAmount",
        "creditCurrency",
        "creditAmount",
        "orderStatus",
        "receiptStatus",
        "executeResult",
    ),
    projection="transfer_orders",
    schema_version="operations-transfers-v0.1",
    notes=(
        "Inquiry-only native POST form query with a JSON-string request VO.",
        "Both transaction query days are required; mapped to native 00:00:00 "
        "and 23:59:59.",
        "Fixed native debitEntity and creditEntity empty-array defaults; no "
        "other filters are enabled.",
        "orderNo is a nonempty string identity within the native tenant and "
        "exact query scope; orderId/reportId remain separate.",
        "Native query timestamps have no verified timezone. Raw gmtCreate "
        "and value dates are preserved without local date filtering or "
        "dated-series inference.",
        "History captures preserve exact native scopes independently; "
        "fetched_at is capture time.",
        "Monetary strings retain precision without conversion; null, blank "
        "and zero remain distinct.",
        "orderStatus, receiptStatus and executeResult remain separate raw "
        "source states without inferred meanings.",
        "Projection excludes accounts, names, aliases, contacts, operators, "
        "free text and nested logs.",
    ),
)
RELEASED: frozenset[str] = frozenset()


def map_transfer_query(values: dict[str, Any]) -> None:
    """Validate paired bounded days and map exactly to native caller strings."""
    start = values.get("transactionStartDate")
    end = values.get("transactionEndDate")
    if not isinstance(start, str) or not isinstance(end, str) or start > end:
        raise CliError(
            INVALID_ARGUMENT,
            "transfer transaction dates require an ordered "
            "--transaction-from/--transaction-to pair",
            exit_code=EXIT_USAGE,
        )
    values["transactionStartDate"] = datetime.strptime(start, "%Y%m%d").strftime(
        "%Y-%m-%d 00:00:00"
    )
    values["transactionEndDate"] = datetime.strptime(end, "%Y%m%d").strftime(
        "%Y-%m-%d 23:59:59"
    )


def project_transfer_order(row: dict[str, Any]) -> dict[str, Any]:
    """Publish only the observed business fields and preserve native types."""
    for field in ("orderNo", "tntInstId"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise CliError(
                INVALID_RESPONSE,
                f"transfer_orders.{field}: expected nonempty native string",
            )
    for field in STRING_FIELDS:
        value = row.get(field)
        if value is not None and not isinstance(value, str):
            raise CliError(
                INVALID_RESPONSE,
                f"transfer_orders.{field}: expected native string or null",
            )
    for field in ("debitAmount", "creditAmount"):
        value = row.get(field)
        if value is None or value == "":
            continue
        try:
            valid = Decimal(value).is_finite()
        except InvalidOperation:
            valid = False
        if not valid:
            raise CliError(
                INVALID_RESPONSE,
                f"transfer_orders.{field}: invalid native monetary string",
            )
    for field in INTEGER_FIELDS:
        value = row.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            raise CliError(
                INVALID_RESPONSE,
                f"transfer_orders.{field}: expected native integer or null",
            )
    return {
        field: row[field] for field in (*STRING_FIELDS, *INTEGER_FIELDS) if field in row
    }


def validate_transfer_rows_scope(rows: list[dict[str, Any]]) -> None:
    """The native query scope has no verified local row-date interpretation."""
    if any(row.get("tntInstId") != TENANT for row in rows):
        raise CliError(INVALID_RESPONSE, "transfer order tenant is outside query scope")
