"""Issue #82 swap list candidate; production registration remains gated."""

from datetime import datetime
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

VERSION = "funding-execution-v0.1"

SWAP_ORDERS = ListSpec(
    path=("operations", "swaps"),
    kind=RUNTIMES,
    title="swap orders",
    endpoint="/swapOrderQuery.json",
    method="POST",
    encoding=ENC_FORM,
    envelope=ENV_RESULT_FLAG,
    require_inner_success=True,
    container=("result", "swapOrderVOList"),
    total=("result", "count"),
    identity=("dealId",),
    profile=PROFILE_HISTORY,
    page_size=10,
    template={
        "tntInstId": TENANT,
        "swapOrderQueryVO": {
            "tntInstId": TENANT,
            "nearLegDebitEntity": [],
            "nearLegCreditEntity": [],
            "tradeStartDate": "",
            "tradeEndDate": "",
            "nearLegStartDate": "",
            "nearLegEndDate": "",
            "farLegStartDate": "",
            "farLegEndDate": "",
        },
    },
    vo_field="swapOrderQueryVO",
    scope_options=(
        ScopeOption(
            "trade_from",
            "tradeStartDate",
            "Inclusive native trade date start (YYYYMMDD); pair with --trade-to.",
            required=True,
            date=True,
        ),
        ScopeOption(
            "trade_to",
            "tradeEndDate",
            "Inclusive native trade date end (YYYYMMDD); pair with --trade-from.",
            required=True,
            date=True,
        ),
    ),
    table_columns=(
        "dealId",
        "tradeDate",
        "nearLegValueDate",
        "farLegValueDate",
        "nearLegDebitCcy",
        "nearLegDebitAmount",
        "nearLegCreditCcy",
        "nearLegCreditAmount",
        "status",
    ),
    projection="swap_orders",
    schema_version=VERSION,
    notes=(
        "Inquiry-only native form query; fixed width 10 and rowStart offsets.",
        "Fixed entity filters are the current native empty arrays on both"
        " legs; this is the current authorized native listing scope.",
        "Both trade date bounds are required. The unbounded default source"
        " listing has observed overlapping pages and is not enabled.",
        "dealId identifies a native Deal ID within this tenant and query scope;"
        " orderId and hedgeOrderId are separate source identifiers.",
        "tradeDate, nearLegValueDate and farLegValueDate are separate YYYYMMDD"
        " business dates; capture time is not their observation time.",
        "Amounts and FX rates preserve source strings without unit conversion;"
        " null, blank and zero remain distinct.",
        "Raw status values are retained without unverified local meanings.",
        "History captures retain each exact native filter scope; no local"
        " date filtering or merging across captures supplies source coverage.",
    ),
)

# The user approved a required trade-date-only candidate. The unbounded native
# default remains excluded. Production CLI UAT and local Kimi CLI CI/review
# must pass before this scoped allowlist is populated.
RELEASED: frozenset[str] = frozenset()


def validate_swap_query(values: dict[str, Any]) -> None:
    """Trade dates belong to an exact history scope, not dated retention."""
    start = values.get("tradeStartDate")
    end = values.get("tradeEndDate")
    if start is None or end is None:
        raise CliError(
            INVALID_ARGUMENT,
            "swap trade dates require both --trade-from and --trade-to",
            exit_code=EXIT_USAGE,
        )
    if start is not None and end is not None and start > end:
        raise CliError(
            INVALID_ARGUMENT,
            "swap trade date start is after its end",
            exit_code=EXIT_USAGE,
        )


def validate_swap_rows_scope(
    rows: list[dict[str, Any]], values: dict[str, Any]
) -> None:
    """Validate native tenant and trade scope before data escapes acquisition."""
    start = values.get("tradeStartDate")
    end = values.get("tradeEndDate")
    for row in rows:
        if row.get("tntInstId") != TENANT:
            raise CliError(INVALID_RESPONSE, "swap order tenant is outside query scope")
        day = row.get("tradeDate")
        try:
            if (
                not isinstance(day, str)
                or len(day) != 8
                or not day.isascii()
                or not day.isdigit()
            ):
                raise ValueError
            datetime.strptime(day, "%Y%m%d")
        except ValueError as error:
            raise CliError(
                INVALID_RESPONSE, "swap order tradeDate is not a valid YYYYMMDD"
            ) from error
        if start is not None and end is not None and not start <= day <= end:
            raise CliError(
                INVALID_RESPONSE, "swap order tradeDate is outside requested scope"
            )
