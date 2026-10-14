"""Bounded liquidity acquisition: strict rowStart-offset and single-response.

Offset leaves follow the verified pagination: increment rowStart by the
leaf's configured page size; the reported total must stay fixed, page
arrivals must keep typed identities consistent, and completeness requires
the unique identity count to equal the fixed total. Observed overlapping
pages therefore retain incomplete evidence; default result policy allows
validated partial rows while strict mode refuses them.

Single-response leaves issue exactly the one verified request: routes that
return their whole scoped set in one response (products; no-pagination
routes like cash flows and metrics). A present reported total must equal
the row count. There is no invented offset collection.
"""

import time
from collections.abc import Callable
from typing import Any

from ... import collect as collect_mod
from ...collect import CollectedScope
from ...errors import INVALID_RESPONSE, TIMEOUT, CliError
from ...jsonutil import canonical
from ...result_policy import AcquisitionEvidence
from . import spec
from .capability import LiquidityListCapability


def collect_liquidity_scope(
    capability: LiquidityListCapability,
    transport: Any,
    scope: str,
    *,
    budget_seconds: float | None = None,
    deadline: float | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> CollectedScope:
    """Collect one liquidity scope with its declared pagination style."""
    budget = (
        collect_mod.REFRESH_BUDGET_SECONDS if budget_seconds is None else budget_seconds
    )
    deadline = time.monotonic() + budget if deadline is None else deadline
    if capability.descriptor.projection == "account_capacity":
        from .account_capacity import collect_capacity

        return collect_capacity(capability, transport, scope, deadline, progress)
    if capability.descriptor.endpoint == "/queryEnquireRateList.json":
        return _collect_bank(capability, transport, scope, deadline, progress)
    if capability.descriptor.pagination == spec.PAGE_SINGLE:
        return _collect_single(capability, transport, scope, deadline, progress)
    return _collect_offset(capability, transport, scope, deadline, progress)


def _merge_page(
    capability: LiquidityListCapability,
    seen: dict[tuple[str, ...], str],
    ordered: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    """First-seen content wins; an identity conflict is a hard failure."""
    for record in rows:
        record_id = capability.identity_key(record)
        content = canonical(record)
        previous = seen.get(record_id)
        if previous is not None:
            if previous != content:
                raise CliError(
                    INVALID_RESPONSE,
                    f"conflicting content for record id {record_id}",
                )
            continue
        seen[record_id] = content
        ordered.append(record)


def _collect_offset(
    capability: LiquidityListCapability,
    transport: Any,
    scope: str,
    deadline: float,
    progress: Callable[[int, int], None] | None,
) -> CollectedScope:
    if not capability.descriptor.identity:
        raise CliError(
            INVALID_RESPONSE, "offset acquisition requires a native identity"
        )
    seen: dict[tuple[str, ...], str] = {}
    ordered: list[dict[str, Any]] = []
    expected_total: int | None = None
    arrivals = 0
    pages = 0
    row_start = 0
    page_size = capability.descriptor.page_size
    while True:
        if time.monotonic() >= deadline:
            raise CliError(TIMEOUT, "collection budget exhausted", retryable=True)
        body = capability.page_body(scope, row_start)
        response = collect_mod.execute_bounded(capability, transport, body, deadline)
        rows, reported = capability.parse_rows(response.body)
        capability.validate_rows_scope(rows, scope)
        if reported is None:
            raise CliError(
                INVALID_RESPONSE,
                "offset acquisition requires a reported total",
            )
        page_total = reported
        if expected_total is None:
            expected_total = page_total
            if page_total > collect_mod.MAX_PAGES * page_size:
                raise CliError(
                    TIMEOUT,
                    f"page budget exceeded: {page_total} rows at {page_size} per page",
                    retryable=True,
                )
        elif page_total != expected_total:
            raise CliError(INVALID_RESPONSE, "backend total changed during collection")
        assert expected_total is not None  # reconciled on every page above
        if len(rows) > page_size:
            raise CliError(
                INVALID_RESPONSE, "page returned more rows than the verified page size"
            )
        pages += 1
        if pages > collect_mod.MAX_PAGES:
            raise CliError(TIMEOUT, "page budget exceeded", retryable=True)
        if not rows and arrivals < expected_total:
            raise CliError(
                INVALID_RESPONSE,
                "collection made no progress: empty page before the total",
            )
        arrivals += len(rows)
        _merge_page(capability, seen, ordered, rows)
        if progress is not None:
            progress(pages, max(-(-expected_total // page_size), pages))
        if row_start + page_size >= expected_total:
            break
        row_start += page_size
    collect_mod.remaining_seconds(deadline)
    assert expected_total is not None
    complete = arrivals == expected_total == len(ordered)
    return CollectedScope(
        records=ordered,
        complete=complete,
        total_count=expected_total,
        page_size=page_size,
        pages=pages,
        rebuilt=False,
        deadline=deadline,
        evidence=AcquisitionEvidence.for_collection(
            complete=complete,
            reported_total=expected_total,
            collected_total=len(ordered),
            arrivals=arrivals,
        ),
    )


def _collect_single(
    capability: LiquidityListCapability,
    transport: Any,
    scope: str,
    deadline: float,
    progress: Callable[[int, int], None] | None,
) -> CollectedScope:
    if time.monotonic() >= deadline:
        raise CliError(TIMEOUT, "collection budget exhausted", retryable=True)
    body = capability.page_body(scope, 0)
    response = collect_mod.execute_bounded(capability, transport, body, deadline)
    rows, total = capability.parse_rows(response.body)
    capability.validate_rows_scope(rows, scope)
    seen: dict[tuple[str, ...], str] = {}
    ordered: list[dict[str, Any]] = []
    if capability.descriptor.identity:
        _merge_page(capability, seen, ordered, rows)
    else:
        ordered = rows
    if total is not None and (total != len(rows) or total != len(ordered)):
        # A reported total the single response does not cover can never be
        # normalized into an empty or partial complete dataset. Duplicate
        # arrivals cannot prove completeness merely because deduplication
        # happens to produce the reported number of identities.
        complete = False
    else:
        complete = True
    evidence = AcquisitionEvidence.for_collection(
        complete=complete,
        reported_total=total,
        collected_total=len(ordered),
        arrivals=len(rows),
        has_identity=bool(capability.descriptor.identity),
    )
    complete = evidence.scope_complete
    if progress is not None:
        progress(1, 1)
    collect_mod.remaining_seconds(deadline)
    return CollectedScope(
        records=ordered,
        complete=complete,
        total_count=total,
        page_size=capability.descriptor.page_size,
        pages=1,
        rebuilt=False,
        deadline=deadline,
        evidence=evidence,
    )


def acquire_liquidity_list(
    session: Any,
    capability: LiquidityListCapability,
    scope: str,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> CollectedScope:
    """Acquire one list, including its leaf-specific native composition."""
    if capability.descriptor.path == ("cash", "accounts"):
        from .unified_accounts import collect_accounts

        return collect_accounts(session, capability, scope, progress=progress)
    if capability.descriptor.path == ("cash", "balances"):
        from .cash_balances import collect_balances

        return collect_balances(session, capability, scope, progress=progress)
    if capability.descriptor.projection == "forecast_accuracy":
        from .forecast_accuracy import collect_accuracy

        return collect_accuracy(session, capability, scope, progress=progress)
    return collect_liquidity_scope(
        capability, session.transport(capability), scope, progress=progress
    )


def _collect_bank(capability, transport, scope, deadline, progress):
    """Acquire the verified descending quote-date group contract (2026-10-15)."""
    seen = {}
    ordered = []
    dates = set()
    arrivals = 0
    total = None
    row_start = 0
    pages = 0
    reasons = []
    previous_date = None
    size = capability.descriptor.page_size
    while True:
        collect_mod.remaining_seconds(deadline)
        if pages >= collect_mod.MAX_PAGES:
            raise CliError(TIMEOUT, "bank group page budget exceeded", retryable=True)
        response = collect_mod.execute_bounded(
            capability, transport, capability.page_body(scope, row_start), deadline
        )
        rows, reported = capability.parse_rows(response.body)
        capability.validate_rows_scope(rows, scope)
        if reported is None:
            raise CliError(INVALID_RESPONSE, "bank inquiry requires native group total")
        if total is None:
            total = reported
            if total > size * collect_mod.MAX_PAGES:
                raise CliError(
                    TIMEOUT, "bank group page budget exceeded", retryable=True
                )
        elif total != reported:
            raise CliError(
                INVALID_RESPONSE, "backend total changed during bank collection"
            )
        pages += 1
        groups = list(dict.fromkeys(row["quoteDate"] for row in rows))
        # Rows belonging to each date must remain contiguous in descending order.
        native_dates = [row["quoteDate"] for row in rows]
        if native_dates != sorted(native_dates, reverse=True):
            reasons.append("BANK_GROUP_ORDER_UNPROVEN")
        if dates.intersection(groups):
            reasons.append("BANK_GROUP_OVERLAP")
        if previous_date is not None and groups and groups[0] >= previous_date:
            reasons.append("BANK_GROUP_BOUNDARY_UNPROVEN")
        if len(groups) > size:
            reasons.append("BANK_GROUP_PAGE_WIDTH_UNPROVEN")
        remaining = max(0, total - row_start)
        if len(groups) != min(size, remaining):
            reasons.append("BANK_GROUP_COUNT_SHORTFALL")
        arrivals += len(rows)
        _merge_page(capability, seen, ordered, rows)
        dates.update(groups)
        if groups:
            previous_date = groups[-1]
        if progress is not None:
            progress(pages, max(-(-total // size), pages))
        if reasons or row_start + size >= total:
            break
        row_start += size
    if len(dates) != total:
        reasons.append("BANK_GROUP_COVERAGE_UNPROVEN")
    complete = not reasons and arrivals == len(ordered)
    evidence = AcquisitionEvidence.for_collection(
        complete=complete,
        reported_total=total,
        collected_total=len(ordered),
        arrivals=arrivals,
        total_semantics="quote_date_groups",
        reasons=tuple(reasons),
        attempts=(
            {
                "contract": "bank-quote-date-groups-v1",
                "pages": pages,
                "collected_groups": len(dates),
                "reported_groups": total,
            },
        ),
    )
    collect_mod.remaining_seconds(deadline)
    return CollectedScope(
        records=ordered,
        complete=evidence.scope_complete,
        total_count=total,
        page_size=size,
        pages=pages,
        rebuilt=False,
        deadline=deadline,
        evidence=evidence,
    )
