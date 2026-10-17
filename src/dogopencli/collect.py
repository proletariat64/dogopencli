"""Bounded collection and recovery for real CDP business queries (ADR 0003).

Core owns the recovery mechanics; leaves keep pagination semantics and the
completeness judgment. Each candidate is built independently from the
backend: the default page size first, bounded retries (1s, 2s; a valid
Retry-After that fits the remaining budget wins) for network failures and
HTTP 429/502/503/504, and, only for contracts that declare a verified
larger capacity, exactly
one full-candidate rebuild when business success shows capacity truncation
or coverage gaps. No fallback to small overlapping pages, no merging across
candidates. Authentication, permission, unknown-schema and generic
business errors are never hidden by retries or page shrinking.

Contracts with a fixed total stop at the page range the first total
declares and reject any later change. Contracts that set
``running_total=True`` instead treat interim totals as
backend estimates: they acquire until the first short page, tolerate
changing interim totals, and let only the final converged total validate
completeness.
"""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from .contracts import Capability, TransportCapability
from .errors import (
    AUTH_REQUIRED,
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    TIMEOUT,
    CliError,
)
from .jsonutil import canonical
from .result_policy import AcquisitionEvidence
from .transport import QueryRequest, TransportResponse, validate_request
from .transport.cdp import FetchFailed

RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})
RETRY_WAITS = (1.0, 2.0)
REFRESH_BUDGET_SECONDS = 900.0
MAX_PAGES = 1000


def _monotonic() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


@dataclass(frozen=True)
class CollectedScope:
    """One independently built candidate; records hold first-seen content."""

    records: list[dict[str, Any]]
    complete: bool
    total_count: int | None
    page_size: int
    pages: int
    rebuilt: bool
    deadline: float
    evidence: AcquisitionEvidence | None = None


def collect_scope(
    capability: Capability,
    transport: Any,
    scope: str,
    filters: dict[str, Any] | None = None,
    *,
    budget_seconds: float | None = None,
    max_pages: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> CollectedScope:
    """Collect the full backend scope with bounded recovery.

    Returns the candidate; ``complete=False`` means coverage could not be
    verified even after the single allowed rebuild (callers decide between
    refusing to publish and returning marked partial live results). Hard
    failures raise CliError.
    """
    budget = REFRESH_BUDGET_SECONDS if budget_seconds is None else budget_seconds
    deadline = _monotonic() + budget
    page_cap = MAX_PAGES if max_pages is None else max_pages
    body_filters = dict(filters or {})
    result = _attempt(
        capability,
        transport,
        scope,
        body_filters,
        capability.contract.page_size,
        deadline,
        page_cap,
        progress,
    )
    if result.complete:
        return result
    rebuild_size = capability.contract.rebuild_page_size
    if rebuild_size is None or capability.contract.page_size == rebuild_size:
        return result
    rebuilt = _attempt(
        capability,
        transport,
        scope,
        body_filters,
        rebuild_size,
        deadline,
        page_cap,
        progress,
    )
    assert result.evidence is not None and rebuilt.evidence is not None
    evidence = replace(
        rebuilt.evidence,
        attempts=result.evidence.attempts + rebuilt.evidence.attempts,
    )
    return replace(
        rebuilt,
        rebuilt=True,
        evidence=evidence,
    )


def _attempt(
    capability: Capability,
    transport: Any,
    scope: str,
    filters: dict[str, Any],
    page_size: int,
    deadline: float,
    max_pages: int,
    progress: Callable[[int, int], None] | None,
) -> CollectedScope:
    contract = capability.contract
    first_page = 1 if contract.one_based else 0
    expected_total: int | None = None
    total_pages = 0
    seen: dict[Any, str] = {}
    observed_content: dict[str, str] = {}
    observed_versions: dict[str, str] = {}
    consistency_unproven = False
    ordered: list[dict[str, Any]] = []
    rows = 0
    pages = 0
    page_num = first_page
    while True:
        if _monotonic() >= deadline:
            raise CliError(TIMEOUT, "collection budget exhausted", retryable=True)
        body = capability.page_body(scope, page_num, page_size)
        body.update(filters)
        response = execute_bounded(capability, transport, body, deadline)
        page = capability.parse_page(response.body)
        if len(page.records) > page_size:
            raise CliError(INVALID_RESPONSE, "page returned more rows than pageSize")
        if contract.scope_field is not None and any(
            record.get(contract.scope_field) != scope for record in page.records
        ):
            raise CliError(
                INVALID_RESPONSE, "response rows do not match requested scope"
            )
        # Verified empty-result shape: the page-number echo is zeroed, which
        # is not a pagination error. Any other wrong echo — including on an
        # empty page — is rejected, so a garbage empty response can never be
        # accepted as a complete empty scope.
        zeroed_empty_echo = (
            expected_total is None
            and page.page_num == 0
            and page.total_count == 0
            and page.total_pages == 0
            and not page.records
        )
        if page.page_size != page_size or (
            page.page_num != page_num and not zeroed_empty_echo
        ):
            raise CliError(
                INVALID_RESPONSE,
                "pagination echo mismatch: requested page "
                f"{page_num} size {page_size}, got page {page.page_num} "
                f"size {page.page_size}",
            )
        if contract.running_total:
            # Interim totals are running estimates: track the latest, never
            # compare across pages, and terminate on the first short page.
            expected_total = page.total_count
            total_pages = math.ceil(expected_total / page_size)
        elif expected_total is None:
            expected_total = page.total_count
            total_pages = math.ceil(expected_total / page_size)
            if not contract.single_page and total_pages > max_pages:
                raise CliError(
                    TIMEOUT,
                    f"page budget exceeded: {total_pages} pages > {max_pages}",
                )
        elif page.total_count != expected_total:
            raise CliError(INVALID_RESPONSE, "backend total changed during collection")
        pages += 1
        if pages > max_pages:
            raise CliError(
                TIMEOUT,
                f"page budget exceeded: {pages} pages > {max_pages}",
            )
        done_pages = page_num - first_page + 1
        if (
            not contract.single_page
            and not contract.running_total
            and not page.records
            and done_pages < total_pages
        ):
            raise CliError(
                INVALID_RESPONSE,
                "collection made no progress: empty page before the range end",
            )
        for record in page.records:
            rows += 1
            content = canonical(record)
            if contract.consistency_field is not None:
                business_id = record.get(contract.consistency_field)
                if business_id is not None:
                    business_key = canonical(business_id)
                    if contract.consistency_version_field is not None:
                        version_value = record.get(contract.consistency_version_field)
                        version = canonical(version_value)
                        previous_version = observed_versions.setdefault(
                            business_key, version
                        )
                        if previous_version != version:
                            consistency_unproven = True
                        business_key = canonical((business_key, version))
                    previous_content = observed_content.setdefault(
                        business_key, content
                    )
                    if previous_content != content:
                        if contract.has_identity:
                            raise CliError(
                                INVALID_RESPONSE,
                                "conflicting content for business identity",
                            )
                        consistency_unproven = True
            if not contract.has_identity:
                ordered.append(record)
                continue
            record_id = capability.identity_key(record)
            if record_id is None or (
                isinstance(record_id, str) and not record_id.strip()
            ):
                raise CliError(INVALID_RESPONSE, "response record identity is missing")
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
        if progress is not None:
            progress(pages, max(total_pages, pages))
        if contract.single_page:
            break
        if contract.running_total:
            if len(page.records) < page_size:
                break
        elif done_pages >= total_pages:
            break
        page_num += 1
    remaining_seconds(deadline)
    total = expected_total if expected_total is not None else 0
    evidence = AcquisitionEvidence.for_collection(
        complete=len(ordered) == total and not consistency_unproven,
        reported_total=total,
        collected_total=len(ordered),
        arrivals=rows,
        has_identity=contract.has_identity,
        total_semantics=contract.total_semantics,
        duplicate_policy=contract.duplicate_policy,
        reasons=("BUSINESS_CONSISTENCY_UNPROVEN",) if consistency_unproven else (),
    )
    evidence = replace(
        evidence,
        attempts=(
            {
                "page_size": page_size,
                "pages": pages,
                "arrivals": rows,
                "unique_count": evidence.unique_count,
                "duplicate_count": evidence.duplicate_count,
                "reported_total": total,
                "complete": evidence.scope_complete,
                "reasons": list(evidence.reasons),
            },
        ),
    )
    return CollectedScope(
        records=ordered,
        complete=evidence.scope_complete,
        total_count=total,
        page_size=page_size,
        pages=pages,
        rebuilt=False,
        deadline=deadline,
        evidence=evidence,
    )


def _retry_after_seconds(response: TransportResponse | None) -> float | None:
    if response is None or response.retry_after is None:
        return None
    try:
        value = float(response.retry_after)
    except ValueError:
        return None
    return value if math.isfinite(value) and value >= 0 else None


def remaining_seconds(deadline: float) -> float:
    remaining = deadline - _monotonic()
    if remaining <= 0:
        raise CliError(TIMEOUT, "collection budget exhausted", retryable=True)
    return remaining


def execute_before_deadline(transport: Any, request: QueryRequest, deadline: float):
    response = transport.execute(request, timeout=remaining_seconds(deadline))
    remaining_seconds(deadline)
    return response


def execute_bounded(
    capability: TransportCapability,
    transport: Any,
    body: dict[str, Any],
    deadline: float | None = None,
) -> TransportResponse:
    """Execute a verified inquiry with shared retry and deadline policy.

    Acquisition supplies its remaining deadline; an independent detail inquiry
    gets the normal inquiry budget. Business-envelope policy stays with callers.
    """
    if deadline is None:
        deadline = _monotonic() + REFRESH_BUDGET_SECONDS
    request = QueryRequest(
        capability=capability.name,
        method=capability.contract.method,
        host=capability.contract.host,
        path=capability.contract.path,
        body=body,
    )
    validate_request(request, capability.contract)
    attempt = 0
    while True:
        response: TransportResponse | None = None
        failure: CliError | None = None
        try:
            response = execute_before_deadline(transport, request, deadline)
        except FetchFailed as error:
            failure = CliError(
                TIMEOUT,
                f"network failure during business query: {error}",
                retryable=True,
            )
        if failure is None and response is not None:
            if response.status == 200:
                return response
            if response.status not in RETRYABLE_STATUSES:
                if response.status == 401:
                    raise CliError(
                        AUTH_REQUIRED,
                        "the backend rejected the dedicated browser session;"
                        " run: dogopencli login",
                    )
                raise CliError(
                    BUSINESS_QUERY_FAILED,
                    f"unexpected HTTP status {response.status}",
                )
        if attempt >= len(RETRY_WAITS):
            if failure is not None:
                raise failure
            status = response.status if response is not None else "unknown"
            raise CliError(
                BUSINESS_QUERY_FAILED,
                f"HTTP {status} persisted after bounded retries",
                retryable=True,
            )
        wait = _retry_after_seconds(response)
        if wait is None:
            wait = RETRY_WAITS[attempt]
        if wait > deadline - _monotonic():
            raise CliError(
                TIMEOUT,
                "collection budget exhausted while waiting to retry",
                retryable=True,
            )
        _sleep(wait)
        attempt += 1
