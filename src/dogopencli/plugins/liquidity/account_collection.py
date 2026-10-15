"""Finite full-scope collection with independent terminal proof for R06."""

import time

from ... import collect as shared
from ...collect import CollectedScope
from ...errors import INVALID_RESPONSE, CliError
from ...result_policy import AcquisitionEvidence
from .collect import _merge_page

BUDGET_SECONDS = 1800.0
MAX_PAGES = 512


def collect_account_list(capability, transport, scope, *, deadline=None, progress=None):
    deadline = time.monotonic() + BUDGET_SECONDS if deadline is None else deadline
    seen, ordered, attempts = {}, [], []
    total = None
    arrivals = start = pages = 0
    size = capability.descriptor.page_size
    terminal = False
    reasons = []
    while pages < MAX_PAGES:
        shared.remaining_seconds(deadline)
        response = shared.execute_bounded(
            capability, transport, capability.page_body(scope, start), deadline
        )
        rows, reported = capability.parse_rows(response.body)
        capability.validate_rows_scope(rows, scope)
        if reported is None:
            raise CliError(INVALID_RESPONSE, "account inquiry requires reported total")
        if total is None:
            total = reported
        elif total != reported:
            raise CliError(INVALID_RESPONSE, "backend total changed during collection")
        pages += 1
        attempts.append(
            {"row_start": start, "arrivals": len(rows), "reported_total": reported}
        )
        if len(rows) > size:
            raise CliError(INVALID_RESPONSE, "page exceeds verified page size")
        if start == total:
            if rows:
                raise CliError(INVALID_RESPONSE, "terminal offset returned records")
            terminal = True
            break
        if start + len(rows) > total:
            raise CliError(INVALID_RESPONSE, "arrivals exceed reported range")
        previous = len(ordered)
        arrivals += len(rows)
        _merge_page(capability, seen, ordered, rows)
        if rows and len(ordered) == previous:
            raise CliError(INVALID_RESPONSE, "account pagination made no progress")
        if progress:
            progress(pages, (total + size - 1) // size + 1)
        if len(rows) < min(size, total - start):
            reasons.append("PAGINATION_GAP")
        start = min(start + size, total)
    if not terminal:
        reasons.append("PAGE_BUDGET_EXHAUSTED")
    shared.remaining_seconds(deadline)
    evidence = AcquisitionEvidence.for_collection(
        complete=terminal and arrivals == total == len(ordered),
        reported_total=total,
        collected_total=len(ordered),
        arrivals=arrivals,
        reasons=tuple(reasons),
        attempts=tuple(attempts),
    )
    return CollectedScope(
        ordered, evidence.scope_complete, total, size, pages, False, deadline, evidence
    )
