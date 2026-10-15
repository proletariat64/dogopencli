"""Native single-day fund-demand statistics, independent of individual demands."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from ...result_policy import AcquisitionEvidence
from .account_forecasts import ACCOUNT_OPTIONS
from .spec import ENV_SUCCESS, PAGE_SINGLE, RUNTIMES, ListSpec

if TYPE_CHECKING:
    from ...collect import CollectedScope

FIELDS = ("statisticalDate", "inflowAmount", "outflowAmount", "totalAmount")
LABELS = frozenset(
    f"{hour:02}:{minute:02}" for hour in range(24) for minute in (0, 15, 30, 45)
)
INTRADAY = ListSpec(
    path=("forecast", "account_demands_intraday"),
    kind=RUNTIMES,
    title="account fund-demand intraday statistics",
    endpoint="/passiveFundDemandsIntraDayStatistical.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data",),
    identity=("statisticalDate",),
    pagination=PAGE_SINGLE,
    paged_request=False,
    scope_options=ACCOUNT_OPTIONS,
    projection="account_demands_intraday",
    schema_version="account-demands-intraday-v1",
    table_columns=FIELDS,
    notes=(
        "One account and one YYYYMMDD business day; from-date must equal to-date.",
        "Identity is the native HH:mm label within the saved account/day scope.",
        "One native statistics request without pagination; [] is valid empty data.",
        "Nonempty complete coverage is 96 unique fifteen-minute labels; missing"
        " labels remain incomplete and are never filled with zeroes.",
        "Observed labels align local expected-value time floor intervals, not"
        " cumulative totals. Source amounts are independent of individual demands.",
        "The source has no timezone or currency fields; account metadata is"
        " reference information and no timezone is assigned to slot labels.",
        "SUCCESS and NO_NEED_PROCESS contributed in the qualified sample; other"
        " status inclusion is unverified. Two NDF demands were omitted by source.",
        "Native amount strings, null, empty and absent fields remain distinct;"
        " no sum from demand rows.",
    ),
)


def validate_query(values: dict[str, Any]) -> None:
    day = values.get("startDate")
    try:
        if not isinstance(day, str) or not re.fullmatch(r"[0-9]{8}", day):
            raise ValueError
        datetime.strptime(day, "%Y%m%d")
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT,
            "intraday requires a valid business date YYYYMMDD",
            exit_code=EXIT_USAGE,
        ) from error
    if day != values.get("endDate"):
        raise CliError(
            INVALID_ARGUMENT,
            "intraday requires one business day: from-date must equal to-date",
            exit_code=EXIT_USAGE,
        )


def project(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("statisticalDate") not in LABELS:
        raise CliError(
            INVALID_RESPONSE,
            "intraday statisticalDate must be a fifteen-minute HH:mm label",
        )
    for field in FIELDS[1:]:
        value = row.get(field)
        if value is None or value == "":
            continue
        if not isinstance(value, str) or not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
            raise CliError(
                INVALID_RESPONSE, f"intraday {field} must be a native decimal string"
            )
        try:
            if not Decimal(value).is_finite():
                raise InvalidOperation
        except InvalidOperation as error:
            raise CliError(INVALID_RESPONSE, f"intraday {field} is invalid") from error
    return {field: row[field] for field in FIELDS if field in row}


def validate_rows(rows: list[dict[str, Any]], values: dict[str, Any]) -> None:
    from .account_forecasts import validate_account_query

    try:
        validate_query(values)
        validate_account_query(values)
        if any(not values.get(field) for field in ("aliasName", "entity", "bankId")):
            raise CliError(INVALID_ARGUMENT, "intraday account context is missing")
    except CliError as error:
        raise CliError(
            INVALID_RESPONSE, "intraday acquisition scope is invalid"
        ) from error
    labels = [row["statisticalDate"] for row in rows]
    if len(labels) != len(set(labels)):
        raise CliError(INVALID_RESPONSE, "duplicate intraday statisticalDate identity")


def collect(
    capability: Any, transport: Any, scope: str, deadline: float, progress: Any
) -> CollectedScope:
    from ... import collect as shared
    from ...collect import CollectedScope

    response = shared.execute_bounded(
        capability, transport, capability.page_body(scope, 0), deadline
    )
    rows, _ = capability.parse_rows(response.body)
    capability.validate_rows_scope(rows, scope)
    complete = not rows or {row["statisticalDate"] for row in rows} == LABELS
    evidence = AcquisitionEvidence.for_collection(
        complete=complete,
        reported_total=None,
        collected_total=len(rows),
        arrivals=len(rows),
        reasons=() if complete else ("INTRADAY_SLOT_GAP",),
        attempts=(
            {
                "contract": "account-demands-intraday-v1",
                "expected_nonempty_slots": 96,
                "arrivals": len(rows),
            },
        ),
    )
    if progress is not None:
        progress(1, 1)
    shared.remaining_seconds(deadline)
    return CollectedScope(
        rows, evidence.scope_complete, None, 0, 1, False, deadline, evidence
    )
