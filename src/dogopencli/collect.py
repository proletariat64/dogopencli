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
    REQUEST_NOT_ALLOWED,
    TIMEOUT,
    CliError,
)
from .jsonutil import canonical
from .result_policy import AcquisitionEvidence, check_complete
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
                if response.status in (401, 403):
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


# Opt-in List SDK: existing collectors above keep their accepted behavior.
# Native business parsing, identity selection and request policy remain leaf-owned.


def _list_identity(
    row: dict[str, Any],
    primary_id: dict[str, Any],
    sources: dict[str, str],
) -> str:
    """Compute an internal, type-aware identity; never decorate a native row."""
    import hashlib

    values: list[Any] = []
    for field in primary_id["fields"]:
        value = row.get(field)
        if (
            value is None
            or isinstance(value, (dict, list))
            or (isinstance(value, str) and not value.strip())
        ):
            raise CliError(INVALID_RESPONSE, f"missing native identity field {field}")
        values.append(value)
    try:
        encoded = canonical(values)
    except (TypeError, ValueError, OverflowError) as error:
        raise CliError(INVALID_RESPONSE, "invalid native identity value") from error
    if primary_id["type"] == "field":
        return encoded
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    previous = sources.setdefault(digest, encoded)
    if previous != encoded:
        raise CliError(INVALID_RESPONSE, "composite primary identity hash collision")
    return digest


def _list_timestamp(value: Any) -> tuple[str, Any]:
    """Comparable native times; do not infer time zones or coerce invalid values."""
    from datetime import datetime, timezone
    from decimal import Decimal

    if type(value) in (int, float, Decimal):
        try:
            number = Decimal(str(value))
        except (ValueError, ArithmeticError) as error:
            raise CliError(INVALID_RESPONSE, "invalid identity timestamp") from error
        if not number.is_finite():
            raise CliError(INVALID_RESPONSE, "non-finite identity timestamp")
        return ("numeric", number)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "invalid identity timestamp") from error
        if parsed.tzinfo is None:
            raise CliError(INVALID_RESPONSE, "timestamp requires explicit timezone")
        return ("datetime", parsed.astimezone(timezone.utc))
    raise CliError(INVALID_RESPONSE, "missing or invalid identity timestamp")


def _list_allowed_sizes(capability: TransportCapability) -> set[int]:
    contract = capability.contract
    sizes = set(contract.allowed_page_sizes) or {contract.page_size}
    for _key, _allowed, _fixed, page_sizes in contract.json_body_contracts:
        sizes.update(page_sizes)
    return sizes


@dataclass
class _PageBudget:
    remaining: int


def _merge_list_row(
    row: dict,
    primary_id: dict,
    latest_by: str | None,
    ordered: list[dict],
    positions: dict[str, int],
    hashes: dict[str, str],
) -> tuple[int, int]:
    record_id = _list_identity(row, primary_id, hashes)
    previous_index = positions.get(record_id)
    if previous_index is None:
        positions[record_id] = len(ordered)
        ordered.append(row)
        return 0, 0
    previous = ordered[previous_index]
    if canonical(row) == canonical(previous):
        return 1, 0
    if latest_by is None:
        ordered[previous_index] = row
    else:
        newer = _list_timestamp(row.get(latest_by))
        older = _list_timestamp(previous.get(latest_by))
        if newer[0] != older[0]:
            raise CliError(INVALID_RESPONSE, "mixed native timestamp formats")
        if newer[1] >= older[1]:
            ordered[previous_index] = row
    return 1, 1


def _short_page_candidate(
    capability: Any,
    transport: Any,
    scope: str,
    collection: dict,
    size: int,
    deadline: float,
    page_budget: _PageBudget,
    progress: Callable[[int, int], None] | None,
    previous_holes: list[dict],
    observations: list[dict],
) -> CollectedScope:
    import hashlib

    from .short_page import RecordHole, ShortPageWalk

    mode = collection["paging"]["mode"]
    pages = 0
    hashes: dict[str, str] = {}

    def read(start: int, width: int) -> list[dict]:
        nonlocal pages
        remaining_seconds(deadline)
        if page_budget.remaining < 1:
            raise CliError(TIMEOUT, "List global page budget exhausted", retryable=True)
        position = (
            start
            if mode == "offset"
            else start // width + (1 if capability.contract.one_based else 0)
        )
        body = capability.page_body(scope, position, width)
        page_budget.remaining -= 1
        pages += 1
        try:
            response = execute_bounded(capability, transport, body, deadline)
            if mode == "offset":
                rows, _total = capability.parse_rows(response.body)
            else:
                page = capability.parse_page(response.body)
                if page.page_size != width or page.page_num != position:
                    raise CliError(INVALID_RESPONSE, "native page echo mismatch")
                rows = page.records
        except CliError as error:
            classify = getattr(capability, "pagination_hole", None)
            fingerprint = (
                classify(error)
                if error.code == BUSINESS_QUERY_FAILED and callable(classify)
                else None
            )
            if fingerprint is None:
                raise
            if not isinstance(fingerprint, str) or not fingerprint.strip():
                raise CliError(
                    INVALID_RESPONSE, "invalid record-hole fingerprint"
                ) from error
            raise RecordHole(
                hashlib.sha256(fingerprint.encode()).hexdigest()
            ) from error
        finally:
            if progress is not None:
                progress(pages, pages)
        if (
            not isinstance(rows, list)
            or len(rows) > width
            or any(not isinstance(row, dict) for row in rows)
        ):
            raise CliError(INVALID_RESPONSE, "invalid native List records or size")
        if capability.contract.scope_field is not None and any(
            row.get(capability.contract.scope_field) != scope for row in rows
        ):
            raise CliError(INVALID_RESPONSE, "native row is outside requested scope")
        validator = getattr(capability, "validate_rows_scope", None)
        if validator is not None:
            validator(rows, scope)
        return rows

    def fingerprint(row: dict) -> str:
        # Neighbor identities prevent stale positional skips after reordering.
        # Hash field identities too: operational state never stores account IDs.
        value = _list_identity(row, collection["primary_id"], hashes)
        return hashlib.sha256(value.encode()).hexdigest()

    walk = ShortPageWalk(
        read,
        fingerprint,
        size=size,
        sizes=_list_allowed_sizes(capability),
        numbered=mode == "page_number",
        observations=observations,
    )
    rows = walk.run(previous_holes)
    remaining_seconds(deadline)
    ordered: list[dict] = []
    positions: dict[str, int] = {}
    duplicates = conflicts = 0
    for row in rows:
        duplicate, conflict = _merge_list_row(
            row,
            collection["primary_id"],
            collection.get("latest_by"),
            ordered,
            positions,
            hashes,
        )
        duplicates += duplicate
        conflicts += conflict
    reasons = []
    if observations:
        reasons.append("PAGINATION_HOLES_BYPASSED")
    if duplicates:
        reasons.append("CROSS_PAGE_OR_INTRA_PAGE_DUPLICATES")
    if conflicts:
        reasons.append("IDENTITY_CONTENT_CONFLICT")
        if collection.get("latest_by") is None:
            reasons.append("LAST_ARRIVAL_WINS")
    evidence = AcquisitionEvidence.for_collection(
        complete=not duplicates and not conflicts,
        reported_total=None,
        collected_total=len(ordered),
        arrivals=len(rows),
        total_semantics="unknown",
        coverage_basis="qualified_short_page",
        reasons=tuple(reasons),
    )
    evidence = replace(
        evidence,
        attempts=(
            {
                "page_size": size,
                "pages": pages,
                "arrivals": len(rows),
                "unique_count": len(ordered),
                "duplicate_count": duplicates,
                "conflict_count": conflicts,
                "reported_total": None,
                "complete": evidence.scope_complete,
                "reasons": list(evidence.reasons),
                "termination_reason": "two_empty_batches",
                "terminal_batches": walk.terminal_batches,
                "source_end": walk.end,
                "holes": list(observations),
                "hole_count": sum(h["end"] - h["start"] for h in observations),
                "history_checked": walk.history_checked,
                "history_matched": walk.history_matched,
            },
        ),
    )
    return CollectedScope(
        ordered, evidence.scope_complete, None, size, pages, False, deadline, evidence
    )


def _list_candidate(
    capability: Any,
    transport: Any,
    scope: str,
    collection: dict[str, Any],
    size: int,
    deadline: float,
    page_budget: _PageBudget,
    progress: Callable[[int, int], None] | None,
    previous_holes: list[dict] | None = None,
    observations: list[dict] | None = None,
) -> CollectedScope:
    """One independent native scope; positional pages are never cross-mixed."""
    mode = collection["paging"]["mode"]
    single_response = mode == "single_response"
    short_page = collection["paging"].get("termination") == "short_page"
    if short_page:
        return _short_page_candidate(
            capability,
            transport,
            scope,
            collection,
            size,
            deadline,
            page_budget,
            progress,
            previous_holes or [],
            observations if observations is not None else [],
        )
    without_total = single_response
    first_number = 1 if capability.contract.one_based else 0
    primary_id = collection["primary_id"]
    has_identity = primary_id["type"] != "unproven"
    latest_by = collection.get("latest_by")
    ordered: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    hashes: dict[str, str] = {}
    observed: set[str] = set()
    reported: int | None = None
    arrivals = 0
    duplicate_count = 0
    conflict_count = 0
    problems: list[str] = []
    if not has_identity:
        problems.append("IDENTITY_UNPROVEN")
    if not without_total and capability.contract.total_semantics != "unique_objects":
        problems.append("TOTAL_SEMANTICS_UNPROVEN")
    pages = 0

    for index in range(page_budget.remaining):
        remaining_seconds(deadline)
        position = index * size if mode == "offset" else first_number + index
        body = capability.page_body(scope, position, size)
        # Reserve one logical page across ALL fallback attempts, including
        # unsuccessful requests. HTTP-level retries remain a separate budget.
        page_budget.remaining -= 1
        response = execute_bounded(capability, transport, body, deadline)
        if mode in ("offset", "single_response"):
            rows, page_total = capability.parse_rows(response.body)
        else:
            page = capability.parse_page(response.body)
            rows, page_total = page.records, page.total_count
            empty_echo = (
                page_total == 0
                and not rows
                and page.page_num == 0
                and page.total_pages == 0
                and index == 0
            )
            if (
                page.page_size != size
                or (page.page_num != position and not empty_echo)
                or (page.total_pages != math.ceil(page_total / size) and not empty_echo)
            ):
                raise CliError(INVALID_RESPONSE, "native page echo mismatch")

        if (
            (page_total is not None if without_total else type(page_total) is not int)
            or (page_total is not None and page_total < 0)
            or not isinstance(rows, list)
            or any(not isinstance(row, dict) for row in rows)
        ):
            raise CliError(INVALID_RESPONSE, "invalid native List records or total")
        if not single_response and len(rows) > size:
            raise CliError(INVALID_RESPONSE, "native page exceeded requested size")
        if reported is None and not without_total:
            reported = page_total
            # The initial request has already consumed one slot. A fallback
            # cannot borrow the page allowance used by prior candidates.
            if (
                has_identity
                and mode != "single"
                and math.ceil(reported / size) > (1 + page_budget.remaining)
            ):
                raise CliError(
                    TIMEOUT, "List global page budget exhausted", retryable=True
                )
        elif not without_total and reported != page_total:
            raise CliError(INVALID_RESPONSE, "native List total changed during read")
        if capability.contract.scope_field is not None and any(
            row.get(capability.contract.scope_field) != scope for row in rows
        ):
            raise CliError(INVALID_RESPONSE, "native row is outside requested scope")
        scope_validator = getattr(capability, "validate_rows_scope", None)
        if scope_validator is not None:
            scope_validator(rows, scope)

        expected_rows = (
            min(size, max(0, reported - index * size)) if reported is not None else None
        )
        if expected_rows is not None and len(rows) < expected_rows:
            reason = "EMPTY_INTERIOR_PAGE" if not rows else "SHORT_NATIVE_PAGE"
            if reason not in problems:
                problems.append(reason)
        pages += 1
        arrivals += len(rows)
        for row in rows:
            if not has_identity:
                content = canonical(row)
                if content in observed:
                    if "UNEXPECTED_DUPLICATE_ROWS" not in problems:
                        problems.append("UNEXPECTED_DUPLICATE_ROWS")
                observed.add(content)
                ordered.append(row)
                continue
            duplicate, conflict = _merge_list_row(
                row, primary_id, latest_by, ordered, positions, hashes
            )
            duplicate_count += duplicate
            conflict_count += conflict

        if progress is not None:
            progress(
                pages,
                max(pages, math.ceil(reported / size)) if reported is not None else 1,
            )
        if mode in ("single", "single_response") or (
            reported is not None and (index + 1) * size >= reported
        ):
            break
        # An unqualified identity cannot diagnose or repair missing native rows.
        # Retain every arrival, but stop at observed overlap or a short page.
        if not has_identity and (
            len(rows) < size or "UNEXPECTED_DUPLICATE_ROWS" in problems
        ):
            break
    else:
        if has_identity:
            raise CliError(TIMEOUT, "List page budget exceeded", retryable=True)
        problems.append("PAGE_BUDGET_EXHAUSTED")
    remaining_seconds(deadline)
    if duplicate_count:
        problems.append("CROSS_PAGE_OR_INTRA_PAGE_DUPLICATES")
    if conflict_count:
        problems.append("IDENTITY_CONTENT_CONFLICT")
        if latest_by is None:
            problems.append("LAST_ARRIVAL_WINS")
    if reported is not None and len(ordered) != reported:
        problems.append("COUNT_MISMATCH")
    if mode == "single" and reported is not None and reported > size:
        problems.append("SINGLE_PAGE_CAPACITY")
    complete = not problems and (single_response or len(ordered) == reported)
    evidence = AcquisitionEvidence.for_collection(
        complete=complete,
        reported_total=reported,
        collected_total=len(ordered),
        arrivals=arrivals,
        has_identity=has_identity,
        total_semantics="unknown"
        if without_total
        else capability.contract.total_semantics,
        coverage_basis="qualified_single_response" if single_response else None,
        reasons=tuple(problems),
        duplicate_policy="conservative",
    )
    evidence = replace(
        evidence,
        attempts=(
            {
                "page_size": size,
                "pages": pages,
                "arrivals": arrivals,
                "unique_count": evidence.unique_count,
                "duplicate_count": evidence.duplicate_count,
                "conflict_count": conflict_count,
                "reported_total": reported,
                "complete": evidence.scope_complete,
                "reasons": list(evidence.reasons),
            },
        ),
    )
    return CollectedScope(
        records=ordered,
        complete=evidence.scope_complete,
        total_count=reported,
        page_size=size,
        pages=pages,
        rebuilt=False,
        deadline=deadline,
        evidence=evidence,
    )


def collect_list(
    capability: Any,
    transport: Any,
    scope: str,
    collection: dict[str, Any],
    *,
    domain: str,
    leaf_id: str,
    state_file: Any = None,
    budget_seconds: float | None = None,
    max_pages: int | None = None,
    progress: Callable[[int, int], None] | None = None,
    _deadline: float | None = None,
    _page_budget: _PageBudget | None = None,
) -> CollectedScope:
    """General List API for trusted, manifest-validated native Leaf contracts.

    Width fallback always starts a fresh candidate. Backend-specific business
    identity and page semantics are never inferred from JSON field names.
    """
    from .collection_state import (
        latest_holes,
        preferred_page_size,
        remember_holes,
        remember_page_size,
        state_key,
    )
    from .contracts import resolve_collection_provider

    resolve_collection_provider(domain, collection["provider"])
    if (
        collection["primary_id"]["type"] != "unproven"
    ) != capability.contract.has_identity:
        raise CliError(
            INVALID_RESPONSE,
            "List identity declaration disagrees with endpoint contract",
        )
    sizes = tuple(collection["paging"]["page_sizes"])
    single_response = collection["paging"]["mode"] == "single_response"
    short_page = collection["paging"].get("termination") == "short_page"
    if short_page and (
        collection["paging"]["mode"] not in {"offset", "page_number"}
        or collection["primary_id"]["type"] == "unproven"
    ):
        raise CliError(
            INVALID_RESPONSE,
            "short-page termination requires paginated mode and verified identity",
        )
    if single_response and (
        len(sizes) != 1 or collection["primary_id"]["type"] == "unproven"
    ):
        raise CliError(
            INVALID_RESPONSE, "single response requires one width and verified identity"
        )
    if not set(sizes).issubset(_list_allowed_sizes(capability)):
        raise CliError(REQUEST_NOT_ALLOWED, "List page width is not endpoint-qualified")
    if not sizes or max_pages is not None and max_pages < 1:
        raise CliError(INVALID_RESPONSE, "invalid List acquisition limits")
    preferred_key = state_key(leaf_id, capability, scope, sizes)
    previous_holes = (
        latest_holes(state_file, preferred_key, collection) if short_page else []
    )
    observations: list[dict] = []

    def save_history(status: str, holes: list[dict]) -> bool:
        return remember_holes(
            state_file, preferred_key, collection, {"status": status, "holes": holes}
        )

    def finish(result: CollectedScope, attempts: list[dict]) -> CollectedScope:
        assert result.evidence is not None
        if short_page and state_file is not None:
            holes = result.evidence.attempts[-1]["holes"]
            saved = save_history("complete" if result.complete else "incomplete", holes)
            selected = max(
                i for i, attempt in enumerate(attempts) if "holes" in attempt
            )
            attempts[selected] = {**attempts[selected], "history_saved": saved}
        return replace(
            result,
            rebuilt=len(attempts) > 1,
            deadline=deadline,
            evidence=replace(result.evidence, attempts=tuple(attempts)),
        )

    favored = (
        None
        if single_response
        else preferred_page_size(state_file, preferred_key, sizes)
    )
    candidates = (
        (favored, *(size for size in sizes if size != favored)) if favored else sizes
    )
    deadline = (
        _deadline
        if _deadline is not None
        else _monotonic()
        + (
            collection.get("budget_seconds", REFRESH_BUDGET_SECONDS)
            if budget_seconds is None
            else budget_seconds
        )
    )
    page_budget = (
        _page_budget
        if _page_budget is not None
        else _PageBudget(
            collection.get("max_pages", MAX_PAGES) if max_pages is None else max_pages
        )
    )
    attempts: list[dict[str, Any]] = []
    last_partial: CollectedScope | None = None
    last_timeout: CliError | None = None
    for number, size in enumerate(candidates):
        try:
            remaining = remaining_seconds(deadline)
        except CliError:
            if short_page:
                save_history("failed", observations)
            raise
        slots = len(candidates) - number
        # Allocate time to the next qualified width, not to endless first-width retries.
        attempt_deadline = min(deadline, _monotonic() + remaining / slots)
        started = _monotonic()
        pages_before = page_budget.remaining
        observations.clear()
        try:
            result = _list_candidate(
                capability,
                transport,
                scope,
                collection,
                size,
                attempt_deadline,
                page_budget,
                progress,
                previous_holes,
                observations,
            )
        except CliError as error:
            attempts.append(
                {
                    "page_size": size,
                    "pages": pages_before - page_budget.remaining,
                    "complete": False,
                    "error": error.code,
                    "elapsed_seconds": round(_monotonic() - started, 3),
                }
            )
            if error.code != TIMEOUT:
                if short_page:
                    save_history("failed", observations)
                raise
            last_timeout = error
            continue
        assert result.evidence is not None
        attempt = {
            **result.evidence.attempts[0],
            "elapsed_seconds": round(_monotonic() - started, 3),
        }
        attempts.append(attempt)
        if result.complete:
            if not single_response:
                remember_page_size(state_file, preferred_key, size)
            return finish(result, attempts)
        last_partial = result

    if last_partial is not None:
        assert last_partial.evidence is not None
        return finish(last_partial, attempts)
    if last_timeout is not None:
        if short_page:
            save_history("failed", observations)
        raise last_timeout
    raise CliError(TIMEOUT, "List collection exhausted all permitted widths")


def collect_sources(
    sources: dict[str, tuple[Any, str]],
    transport_factory: Callable[[Any], Any],
    assemble: Callable[
        [dict[str, list[dict[str, Any]]], dict[str, Any]], list[dict[str, Any]]
    ],
    parameters: dict[str, Any],
    collection: dict[str, Any],
    *,
    domain: str,
    leaf_id: str,
    state_file: Any = None,
    budget_seconds: float | None = None,
    max_pages: int | None = None,
) -> CollectedScope:
    """Acquire flat required sources before invoking a pure leaf-owned assembly.

    Sources share one deadline and logical page budget, including each source's
    qualified width attempts. Source failures never become empty child records.
    """
    from .contracts import resolve_collection_provider

    resolve_collection_provider(domain, collection["provider"])
    declared = collection.get("sources")
    primary_id = collection["primary_id"]
    if (
        not isinstance(declared, dict)
        or not declared
        or set(sources) != set(declared)
        or "paging" in collection
        or primary_id["type"] == "unproven"
    ):
        raise CliError(
            INVALID_RESPONSE, "invalid declared List sources or aggregate identity"
        )
    deadline = _monotonic() + (
        collection.get("budget_seconds", REFRESH_BUDGET_SECONDS)
        if budget_seconds is None
        else budget_seconds
    )
    page_limit = (
        collection.get("max_pages", MAX_PAGES) if max_pages is None else max_pages
    )
    if type(page_limit) is not int or page_limit < 1:
        raise CliError(INVALID_RESPONSE, "invalid List acquisition limits")
    page_budget = _PageBudget(page_limit)
    records: dict[str, list[dict[str, Any]]] = {}
    source_evidence: dict[str, dict[str, Any]] = {}
    rebuilt = False
    for name, policy in declared.items():
        capability, scope = sources[name]
        if (
            not isinstance(policy, dict)
            or set(policy) != {"paging", "primary_id"}
            or policy["primary_id"]["type"] == "unproven"
            or not isinstance(scope, str)
        ):
            raise CliError(INVALID_RESPONSE, "invalid flat List source policy")
        try:
            remaining_seconds(deadline)
            if page_budget.remaining < 1:
                raise CliError(
                    TIMEOUT, "List global page budget exhausted", retryable=True
                )
            transport = transport_factory(capability)
            try:
                result = collect_list(
                    capability,
                    transport,
                    scope,
                    {"provider": collection["provider"], **policy},
                    domain=domain,
                    leaf_id=leaf_id + ":" + name,
                    state_file=state_file,
                    _deadline=deadline,
                    _page_budget=page_budget,
                )
            finally:
                transport.close()
            assert result.evidence is not None
            source_evidence[name] = {
                "scope": scope,
                "acquisition": result.evidence.record(),
            }
            check_complete(result.evidence, require_complete=True)
            records[name] = result.records
            rebuilt = rebuilt or result.rebuilt
        except CliError as error:
            failures = dict(source_evidence)
            failures[name] = {
                **failures.get(name, {"scope": scope}),
                "error": {"code": error.code, "retryable": error.retryable},
            }
            raise CliError(
                error.code,
                f"Source {name}: {error.message}",
                retryable=error.retryable,
                exit_code=error.exit_code,
                meta={**(error.meta or {}), "source": name, "sources": failures},
            ) from error

    remaining_seconds(deadline)
    assembled = assemble(records, parameters)
    remaining_seconds(deadline)
    if not isinstance(assembled, list) or any(
        not isinstance(row, dict) for row in assembled
    ):
        raise CliError(INVALID_RESPONSE, "assembled List records must be objects")
    identities: set[str] = set()
    hashes: dict[str, str] = {}
    for row in assembled:
        identity = _list_identity(row, primary_id, hashes)
        if identity in identities:
            raise CliError(INVALID_RESPONSE, "assembled List identity is duplicated")
        identities.add(identity)
    evidence = AcquisitionEvidence.for_collection(
        complete=True,
        reported_total=None,
        collected_total=len(assembled),
        arrivals=len(assembled),
        total_semantics="assembled_roots",
        coverage_basis="validated_sources",
        reasons=("PAGINATION_HOLES_BYPASSED",)
        if any(
            "PAGINATION_HOLES_BYPASSED" in source["acquisition"]["reasons"]
            for source in source_evidence.values()
        )
        else (),
    )
    evidence = replace(evidence, sources=source_evidence)
    return CollectedScope(
        records=assembled,
        complete=True,
        total_count=None,
        page_size=0,
        pages=page_limit - page_budget.remaining,
        rebuilt=rebuilt,
        deadline=deadline,
        evidence=evidence,
    )
