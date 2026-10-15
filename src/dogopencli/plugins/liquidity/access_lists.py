"""Verified access-list settings and user-approved latest-created bank selection."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ... import collect as collect_mod
from ...errors import INVALID_RESPONSE, CliError
from ...jsonutil import canonical
from ...result_policy import BANK_ROW_OCCURRENCES, AcquisitionEvidence
from .spec import ENV_RESULT_FLAG, SETTINGS, TENANT, ListSpec

if TYPE_CHECKING:
    from ...collect import CollectedScope

_NOTES = (
    "Native settings, independent of entity, bank and cash-account directories.",
    "Filters match exact native values locally after acquisition; all statuses"
    " are retained by default. VALID/INVALID do not establish activation semantics.",
    "Native row offsets, stable overlap and terminal witnesses establish coverage;"
    " source counts alone do not prove completeness.",
    "Native timestamps and raw fields are preserved; capture time is separate.",
    "An observed empty native DTO tntInstId is preserved as unset;"
    " fixed request tenant binds acquisition scope, never a synthesized row value.",
)
_UNIQUE_NOTE = (
    "Reported total counts native row occurrences; arrivals and unique"
    " identities are reported independently, with duplicates incomplete."
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
    notes=(*_NOTES, _UNIQUE_NOTE),
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
    notes=(*_NOTES, _UNIQUE_NOTE),
)

BANK_BLACKLIST = ListSpec(
    path=("reference", "blacklist", "bank"),
    kind=SETTINGS,
    title="bank blacklist settings, latest-created record per bank",
    endpoint="/bankFilterConfigQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    total=("result", "count"),
    total_checks=(("count",),),
    require_inner_success=True,
    identity=("bankId",),
    page_size=5000,
    schema_version="access-lists-v1",
    vo_field="bankFilterConfigQuery",
    template={
        "tntInstId": TENANT,
        "bankFilterConfigQuery": {
            "tntInstId": TENANT,
            "timezone": "GMT+08",
            "currentArea": "2",
        },
    },
    filters=(("bank_id", "bankId"), ("status", "status")),
    table_columns=("bankId", "bankName", "bankSwiftCode", "status", "gmtCreate"),
    notes=(
        *_NOTES,
        "User-approved bank identity is bankId. Retain the row with greatest"
        " native gmtCreate (nonnegative integer epoch milliseconds), before"
        " local filtering. Conflicting equal-time rows fail; identical ties collapse.",
        "Native reported total and arrivals count source rows; collected_total"
        " counts selected banks. Completeness requires raw offset/overlap/terminal"
        " coverage, not equality between native rows and selected bank count.",
    ),
)
ACCESS_LISTS = (ENTITY_WHITELIST, ACCOUNT_BLACKLIST, BANK_BLACKLIST)
ACCESS_PATHS = frozenset(item.path for item in ACCESS_LISTS)


def latest_bank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select by business bank identity, preserving first-bank order and raw rows."""
    selected: dict[str, dict[str, Any]] = {}
    seen: dict[tuple[str, int], str] = {}
    for row in rows:
        bank = row.get("bankId")
        created = row.get("gmtCreate")
        if not isinstance(bank, str) or not bank.strip():
            raise CliError(INVALID_RESPONSE, "bankId must be a nonempty native string")
        if type(created) is not int or created < 0:
            raise CliError(
                INVALID_RESPONSE,
                "bank gmtCreate must be nonnegative epoch milliseconds",
            )
        key = (bank, created)
        content = canonical(row)
        if key in seen and seen[key] != content:
            raise CliError(INVALID_RESPONSE, "conflicting bank rows share gmtCreate")
        seen[key] = content
        if bank not in selected or created > selected[bank]["gmtCreate"]:
            selected[bank] = row
    return list(selected.values())


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
    bank_selection = capability.descriptor.path == BANK_BLACKLIST.path

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
            if bank_selection:
                continue
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
                coverage = (
                    not terminal
                    and len(arrived) == expected
                    and (bank_selection or len(ordered) == expected)
                )
        break

    if bank_selection:
        ordered = latest_bank_rows(arrived)
        omitted = len(arrived) - len(ordered)
        if omitted:
            reasons.append("BANK_LATEST_CREATED_SELECTED")
        attempts.append(
            {
                "contract": "bank-blacklist-latest-gmtCreate-v1",
                "raw_rows": len(arrived),
                "selected_banks": len(ordered),
                "raw_coverage_complete": coverage,
            }
        )
        evidence = AcquisitionEvidence(
            scope_complete=coverage,
            dataset_complete=coverage,
            reported_total=expected,
            collected_total=len(ordered),
            arrivals=len(arrived),
            unique_count=len(ordered),
            duplicate_count=omitted,
            total_semantics=BANK_ROW_OCCURRENCES,
            reasons=tuple(dict.fromkeys(reasons)),
            attempts=tuple(attempts),
        )
    else:
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
