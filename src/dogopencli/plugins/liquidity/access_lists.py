"""Verified access-list settings; bank row identity remains unavailable (#176)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ... import collect as collect_mod
from ...errors import INVALID_RESPONSE, CliError
from ...jsonutil import canonical
from ...result_policy import AcquisitionEvidence
from .spec import ENV_RESULT_FLAG, SETTINGS, TENANT, DeferredLeaf, ListSpec

if TYPE_CHECKING:
    from ...collect import CollectedScope

_NOTES = (
    "Native settings, independent of entity, bank and cash-account directories.",
    "Filters match exact native values locally after acquisition; all statuses"
    " are retained by default. VALID/INVALID do not establish activation semantics.",
    "Native row offsets, stable overlap and terminal witnesses establish coverage;"
    " source counts alone do not prove completeness.",
    "Native timestamps and raw fields are preserved; capture time is separate.",
    "Reported total counts native row occurrences; arrivals and unique"
    " identities are reported independently, with duplicates incomplete.",
    "An observed empty native DTO tntInstId is preserved as unset;"
    " fixed request tenant binds acquisition scope, never a synthesized row value.",
)

ENTITY_WHITELIST = ListSpec(
    path=("reference", "whitelist", "entity"),
    kind=SETTINGS,
    title="entity whitelist settings",
    endpoint="/instFilterConfigQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    total=("result", "count"),
    total_checks=(("count",),),
    require_inner_success=True,
    identity=("instId",),
    page_size=5000,
    schema_version="access-lists-v1",
    vo_field="instFilterConfigQuery",
    template={
        "tntInstId": TENANT,
        "instFilterConfigQuery": {"tntInstId": TENANT, "timezone": "GMT+08"},
    },
    filters=(
        ("entity", "instId"),
        ("financial_code", "instCode"),
        ("status", "status"),
    ),
    table_columns=("instId", "instName", "instCode", "status", "gmtModified"),
    notes=_NOTES,
)

ACCOUNT_BLACKLIST = ListSpec(
    path=("reference", "blacklist", "account"),
    kind=SETTINGS,
    title="account blacklist settings",
    endpoint="/accountFilterConfigQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    total=("result", "count"),
    total_checks=(("count",),),
    require_inner_success=True,
    identity=("aliasName",),
    page_size=5000,
    schema_version="access-lists-v1",
    vo_field="accountFilterConfigQuery",
    template={
        "tntInstId": TENANT,
        "accountFilterConfigQuery": {
            "tntInstId": TENANT,
            "timezone": "GMT+08",
            "currentArea": "3",
        },
    },
    filters=(
        ("entity", "instId"),
        ("bank_id", "bankId"),
        ("account_alias", "aliasName"),
        ("status", "status"),
    ),
    table_columns=("aliasName", "instId", "bankId", "currency", "status"),
    notes=_NOTES,
)

ACCESS_LISTS = (ENTITY_WHITELIST, ACCOUNT_BLACKLIST)
ACCESS_PATHS = frozenset(item.path for item in ACCESS_LISTS)
BANK_BLACKLIST = DeferredLeaf(
    ("reference", "blacklist", "bank", "list"),
    SETTINGS,
    "identity-unproven",
    "Native bank row/version identity remains unproven: conflicting duplicate"
    " bankId values cannot identify separate native records. No executable"
    " inquiry, refresh or prune is available until identity is verified (#176).",
)


def collect_access_list(
    capability: Any,
    transport: Any,
    scope: str,
    deadline: float,
    progress: Callable[[int, int], None] | None,
) -> CollectedScope:
    """Collect only verified row-offset sources, with independent witnesses.

    A proven short 5000 page restarts at 1000 without reusing candidate rows.
    Witness arrivals are tracked separately from acquisition arrivals. Backend
    failures remain hard; only a finite budget or stable count shortfall can
    return validated partial rows.
    """
    from ...collect import CollectedScope

    attempts: list[dict[str, Any]] = []
    reasons: list[str] = []
    expected: int | None = None
    width = 5000
    arrived: list[dict[str, Any]] = []
    ordered: list[dict[str, Any]] = []
    seen: dict[tuple[str, ...], str] = {}
    boundaries: list[int] = []
    pages = 0
    offset = 0
    coverage = False

    def budget_available() -> bool:
        if pages >= collect_mod.MAX_PAGES or time.monotonic() >= deadline:
            reasons.append("COLLECTION_BUDGET_EXHAUSTED")
            return False
        return True

    def fetch(start: int, size: int, purpose: str) -> list[dict[str, Any]]:
        nonlocal pages, expected
        response = collect_mod.execute_bounded(
            capability, transport, capability.page_body(scope, start, size), deadline
        )
        rows, total = capability.parse_rows(response.body)
        capability.validate_rows_scope(rows, scope)
        if total is None:
            raise CliError(INVALID_RESPONSE, "access list has no native total")
        if expected is None:
            expected = total
        elif total != expected:
            raise CliError(INVALID_RESPONSE, "backend total changed during collection")
        if len(rows) > size or start + len(rows) > total:
            raise CliError(INVALID_RESPONSE, "access list exceeds native page bounds")
        pages += 1
        attempts.append(
            {
                "purpose": purpose,
                "rowStart": start,
                "pageSize": size,
                "arrivals": len(rows),
                "reported_total": total,
            }
        )
        return rows

    while budget_available():
        rows = fetch(offset, width, "acquisition")
        assert expected is not None
        if width == 5000 and rows and len(rows) < min(width, expected - offset):
            for attempt in attempts:
                attempt["discarded"] = True
            reasons.append("PAGE_SIZE_CAPPED")
            arrived.clear()
            ordered.clear()
            seen.clear()
            boundaries.clear()
            offset = 0
            width = 1000
            continue
        if rows and len(rows) < min(width, expected - offset):
            reasons.append("PAGE_SIZE_CAPPED")
        for row in rows:
            key = capability.identity_key(row)
            content = canonical(row)
            if key in seen:
                if seen[key] != content:
                    raise CliError(INVALID_RESPONSE, "conflicting access-list identity")
            else:
                seen[key] = content
                ordered.append(row)
        if rows and offset:
            boundaries.append(offset)
        arrived.extend(rows)
        if progress is not None:
            progress(pages, max(pages, -(-expected // width)))
        if not rows and offset < expected:
            reasons.append("COUNT_SHORTFALL")
            break
        offset += len(rows)
        if offset < expected:
            continue
        if expected == 0:
            if budget_available():
                coverage = not fetch(0, 1000, "empty-witness")
            break
        # Recheck the beginning and every join between acquisition pages;
        # a separate exact-total read validates the end boundary.
        start = 1 if expected > 1 else 0
        starts = dict.fromkeys((start, *(boundary - 1 for boundary in boundaries)))
        for start in starts:
            if not budget_available():
                break
            overlap = fetch(start, 1000, "overlap-witness")
            if not overlap:
                reasons.append("COVERAGE_UNPROVEN")
                break
            if overlap != arrived[start : start + len(overlap)]:
                raise CliError(
                    INVALID_RESPONSE, "access-list overlap changed during query"
                )
        else:
            if budget_available():
                terminal = fetch(expected, 1000, "terminal-witness")
                coverage = not terminal and len(arrived) == expected == len(ordered)
        break

    evidence = AcquisitionEvidence.for_collection(
        complete=coverage,
        reported_total=expected,
        collected_total=len(ordered),
        arrivals=len(arrived),
        total_semantics="occurrences",
        reasons=tuple(dict.fromkeys(reasons)),
        attempts=tuple(attempts),
    )
    return CollectedScope(
        records=ordered,
        complete=evidence.scope_complete,
        total_count=expected,
        page_size=width,
        pages=pages,
        rebuilt=False,
        deadline=deadline,
        evidence=evidence,
    )
