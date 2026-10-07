"""Liquidity query flows: offline cache reads and explicit live inquiries.

Default queries read local captures only — never the browser. ``--live``
performs the bounded inquiry through the existing CDP session and never
writes the cache; live partial results keep explicit incompleteness
metadata and ``--require-complete`` fails on them. Queries demanding
missing or evicted coverage use the existing incomplete-result behavior,
never a misleading empty result or NOT_FOUND.
"""

import argparse
import re
import shlex
import sys
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from ... import config as config_mod
from ...cache import Cache
from ...cached_query import is_stale
from ...errors import (
    BUSINESS_QUERY_FAILED,
    CACHE_MISS,
    CACHE_STALE,
    EXIT_FAILURE,
    EXIT_OK,
    EXIT_USAGE,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    UNSUPPORTED_CAPABILITY,
    CliError,
)
from ...inquiry import inquiry_session
from ...jsonutil import canonical
from ...result_policy import evidence_for, prepare_result
from ...table import render_table
from ...transport.cdp import CdpQueryTransport
from ..envelope import is_business_refusal
from . import details as detail_store
from . import spec as spec_mod
from . import store as capture_store
from .collect import acquire_liquidity_list
from .common import emit, identity_values, load_config, now, provided, scope_flags
from .leaves import DEFERRED_BY_PATH, DetailLeaf, ListLeaf, detail_leaf, list_leaf
from .qualified_getters import detail_context_meta


def _display_options(args: argparse.Namespace) -> tuple[int, int, list[str] | None]:
    if args.all and (args.limit is not None or args.offset is not None):
        raise CliError(
            INVALID_ARGUMENT,
            "--all conflicts with explicit --limit/--offset",
            exit_code=EXIT_USAGE,
        )
    limit = 100 if args.limit is None else args.limit
    if limit <= 0:
        raise CliError(
            INVALID_ARGUMENT,
            "--limit must be a positive integer",
            exit_code=EXIT_USAGE,
        )
    offset = 0 if args.offset is None else args.offset
    if offset < 0:
        raise CliError(
            INVALID_ARGUMENT, "--offset must not be negative", exit_code=EXIT_USAGE
        )
    fields: list[str] | None = None
    if args.fields is not None:
        fields = [name.strip() for name in args.fields.split(",") if name.strip()]
        if not fields:
            raise CliError(
                INVALID_ARGUMENT,
                "--fields must name at least one field",
                exit_code=EXIT_USAGE,
            )
    return limit, offset, fields


def _project(
    window: list[dict[str, Any]], fields: list[str] | None
) -> list[dict[str, Any]]:
    if fields is None:
        return window
    return [
        {name: record[name] for name in fields if name in record} for record in window
    ]


def _emit_window(
    args: argparse.Namespace,
    columns: tuple[str, ...],
    window: list[dict[str, Any]],
    meta: dict[str, Any],
    fields: list[str] | None,
    error: dict[str, Any] | None = None,
) -> int:
    meta = prepare_result(
        meta,
        require_complete=args.require_complete,
        mode="live" if args.live else "cache",
    )
    window = _project(window, fields)
    if args.format == "table":
        selected = tuple(fields) if fields is not None else columns
        sys.stdout.write(render_table(window, selected, meta) + "\n")
    else:
        emit(window, meta, error)
    return EXIT_FAILURE if error is not None else EXIT_OK


def _emit_object(
    args: argparse.Namespace,
    columns: tuple[str, ...],
    record: Any,
    meta: dict[str, Any],
    fields: list[str] | None,
) -> int:
    if args.format == "table" and isinstance(record, dict):
        rows = _project([record], fields)
        selected = tuple(fields) if fields is not None else columns
        sys.stdout.write(render_table(rows, selected, meta) + "\n")
    else:
        if fields is not None and isinstance(record, dict):
            record = _project([record], fields)[0]
        emit(record, meta)
    return EXIT_OK


def _local_filters(
    args: argparse.Namespace, variant: spec_mod.ListSpec
) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for entry in variant.filters:
        flag, field = entry[0], entry[1]
        public = entry[2] if len(entry) > 2 else "--" + flag.replace("_", "-")
        values = getattr(args, flag, [])
        if any(not value.strip() for value in values):
            raise CliError(
                INVALID_ARGUMENT,
                f"{public} must be nonempty",
                exit_code=EXIT_USAGE,
            )
        if values:
            filters[field] = list(values)
    return filters


def _matches(record: dict[str, Any], filters: dict[str, list[str]]) -> bool:
    return all(record.get(field) in values for field, values in filters.items())


def _match(
    records: list[dict[str, Any]], filters: dict[str, list[str]]
) -> list[dict[str, Any]]:
    return [record for record in records if _matches(record, filters)]


def _sort_rows(
    variant: spec_mod.ListSpec, records: list[dict[str, Any]], fetched_at: str
) -> list[dict[str, Any]]:
    def key(record: dict[str, Any]) -> tuple[str, ...]:
        identity = tuple(canonical(record.get(field)) for field in variant.identity)
        if variant.profile == spec_mod.PROFILE_DATED:
            series = capture_store.series_value(variant, record, fetched_at)
            return (series, *identity)
        return identity

    return sorted(records, key=key)


def _coverage_meta(entries: list[capture_store.CaptureEntry]) -> list[dict[str, Any]]:
    return [
        {
            "namespace": entry.namespace,
            "window_from": entry.window_from,
            "window_to": entry.window_to,
            "missing_days": list(entry.missing_days),
            "fetched_at": entry.fetched_at,
            "row_count": entry.row_count,
            "acquisition": entry.evidence.record(),
        }
        for entry in entries
    ]


def run_list(args: argparse.Namespace) -> int:
    leaf = list_leaf(args.command_path[1:-1])
    limit, offset, fields = _display_options(args)
    resolved = leaf.resolve(provided(args, scope_flags(leaf)))
    variant = resolved.spec
    filters = _local_filters(args, variant)
    config = load_config()
    if args.live:
        return _run_list_live(
            args, leaf, resolved, filters, limit, offset, fields, config
        )
    store = Cache(config.cache_path)
    index = capture_store.read_index(store, variant.name)
    refresh_hint = (
        "run: dogopencli refresh liquidity "
        + " ".join(leaf.path)
        + _hint_options(leaf, resolved.request_values)
    )
    if index is None:
        raise CliError(CACHE_MISS, f"no cached liquidity capture; {refresh_hint}")
    selected, covered = capture_store.select_captures(
        index, variant, resolved.scope_key, resolved.window
    )
    if not selected:
        raise CliError(
            CACHE_MISS,
            "no retained capture covers the requested scope; " + refresh_hint,
        )

    pairs: list[tuple[capture_store.CaptureEntry, dict[str, Any]]] = []
    seen: set[tuple[str, ...]] = set()
    capability = leaf.capability(variant)
    occurrences_seen: Counter[tuple[str, ...]] = Counter()
    authority_by_day: dict[str, capture_store.CaptureEntry | None] = {}
    # Newest acquisition first: when retained captures overlap, a later
    # corrected value must win over the older capture of the same identity.
    for _, entry in sorted(
        enumerate(selected),
        key=lambda pair: (pair[1].fetched_at, pair[0]),
        reverse=True,
    ):
        occurrences: Counter[tuple[str, ...]] = Counter()
        missing_days = set(entry.missing_days)
        capture_rows = capture_store.read_capture(store, entry)
        if variant.identity:
            capture_ids: set[tuple[str, ...]] = set()
            for record in capture_rows:
                identity = capability.identity_key(record)
                if identity in capture_ids:
                    raise CliError(
                        INVALID_RESPONSE,
                        "cached capture contains duplicate native identities",
                    )
                capture_ids.add(identity)
        for record in capture_rows:
            if variant.profile == spec_mod.PROFILE_DATED:
                window_from, window_to = resolved.window
                assert window_from is not None and window_to is not None
                assert entry.window_from is not None and entry.window_to is not None
                day = capture_store.series_value(variant, record, "")
                if day not in authority_by_day:
                    authority_by_day[day] = capture_store.authoritative_capture(
                        selected, day
                    )
                # Another complete capture can restore coverage, but cannot
                # make this capture's retained partial-day rows complete.
                if not (
                    window_from <= day <= window_to
                    and entry.window_from <= day <= entry.window_to
                    and day not in missing_days
                    and authority_by_day[day] == entry
                ):
                    continue
            identity = capability.identity_key(record)
            if not variant.identity:
                occurrences[identity] += 1
                if occurrences[identity] > occurrences_seen[identity]:
                    pairs.append((entry, record))
                continue
            if identity in seen:
                continue
            seen.add(identity)
            pairs.append((entry, record))
        occurrences_seen |= occurrences
    kept_pairs = [
        (entry, record) for entry, record in pairs if _matches(record, filters)
    ]
    rows = [record for _, record in kept_pairs]
    # Every returned row needs fresh evidence, and fresh captures together
    # must cover the whole requested window, including verified empty days.
    # Testing individual redundancy misses overlapping expired empty captures.
    contributing = {entry.namespace for entry, _ in kept_pairs}
    current = now()
    window_start, window_end = resolved.window
    quality_entries = (
        capture_store.active_captures(selected, window_start, window_end)
        if window_start is not None and window_end is not None
        else selected
    )
    fresh_entries = [
        entry
        for entry in quality_entries
        if not is_stale(_capture_meta_view(entry), config.ttl_hours, current)
    ]
    fresh_namespaces = {entry.namespace for entry in fresh_entries}
    fresh_coverage = (
        capture_store.covers_window(
            fresh_entries, window_start, window_end, authority=selected
        )
        if window_start is not None and window_end is not None
        else bool(fresh_entries)
    )
    contributors = [
        entry
        for entry in quality_entries
        if entry.namespace in contributing or entry.namespace in fresh_namespaces
    ] or list(selected)
    latest = max(contributors, key=lambda entry: entry.fetched_at)
    stale_entries = [
        entry
        for entry in quality_entries
        if entry.namespace not in fresh_namespaces
        and (entry.namespace in contributing or not fresh_coverage)
    ]
    stale = bool(stale_entries)
    if args.require_fresh and stale:
        oldest = min(stale_entries, key=lambda entry: entry.fetched_at)
        raise CliError(
            CACHE_STALE,
            f"cached capture is older than {config.ttl_hours:g} hours"
            f" (fetched_at {oldest.fetched_at})",
        )
    rows = _sort_rows(variant, rows, latest.fetched_at)
    matched_total = len(rows)
    window = rows[offset:] if args.all else rows[offset : offset + limit]
    reported = sum(entry.reported_total or entry.row_count for entry in selected)
    meta = {
        "source": "cache",
        "backend": "cdp",
        "kind": variant.kind,
        "simulated": False,
        "capability": variant.name,
        "scope": resolved.scope_key,
        "requested_window": (
            list(resolved.window) if resolved.window[0] is not None else None
        ),
        "retained_coverage": _coverage_meta(selected),
        "snapshot_id": latest.snapshot_id,
        "dataset_id": None,
        "fetched_at": latest.fetched_at,
        "loaded_at": None,
        "stale": stale,
        "complete": covered,
        "dataset_complete": None,
        "source_observed_from": None,
        "source_observed_to": None,
        "reported_total": reported,
        "matched_total": matched_total,
        "returned_count": len(window),
        "has_more": offset + len(window) < matched_total,
    }
    evidence = capture_store.query_evidence(
        quality_entries, covered, len(pairs), window=resolved.window
    )
    meta.update(evidence.meta())
    return _emit_window(args, variant.table_columns, window, meta, fields)


def _capture_meta_view(entry: capture_store.CaptureEntry) -> Any:
    return SimpleNamespace(fetched_at=entry.fetched_at)


def _public_hint_value(option: spec_mod.ScopeOption, value: Any) -> str:
    """Inverse of public normalization: internal value to public form (#127).

    Hints print canonical spellings: ISO calendar dates, colon clocks, and
    T-form datetimes (Z for the verified-UTC rule-status interval), so a
    parsed hint re-resolves to the identical scope.
    """
    text = str(value)
    if option.date:
        match = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})", text)
        if match:
            return "-".join(match.groups())
        expanded = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}", text)
        if expanded:  # day-start/day-end expansion inverts to its day
            return expanded.group(1)
        return text
    if option.time:
        match = re.fullmatch(r"(\d{2})(\d{2})(\d{2})", text)
        if match:
            return ":".join(match.groups())
        return text
    if option.datetime_zone is not None:
        naive = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})", text)
        if naive:
            suffix = "Z" if option.datetime_zone == "utc" else ""
            return f"{naive.group(1)}T{naive.group(2)}{suffix}"
        return text
    return text


def _hint_options(leaf: ListLeaf, values: dict[str, Any]) -> str:
    parts = []
    for option in leaf.options:
        value = values.get(option.field)
        if value is None:
            continue
        flag = option.public_flag
        items = value if isinstance(value, list) else [value]
        parts.extend(
            f"{flag} {shlex.quote(_public_hint_value(option, item))}" for item in items
        )
    return (" " + " ".join(parts)) if parts else ""


def _run_list_live(
    args: argparse.Namespace,
    leaf: ListLeaf,
    resolved: Any,
    filters: dict[str, list[str]],
    limit: int,
    offset: int,
    fields: list[str] | None,
    config: config_mod.Config,
) -> int:
    variant = resolved.spec
    capability = leaf.capability(variant)
    with inquiry_session(
        config_file=config_mod.config_path(), startup_url=capability.page_url
    ) as session:
        result = acquire_liquidity_list(
            session,
            capability,
            resolved.request_scope,
            progress=lambda done, total: print(
                f"live: collected page {done}/{total}", file=sys.stderr
            ),
        )
    evidence = evidence_for(result)
    rows = _sort_rows(variant, _match(result.records, filters), now().isoformat())
    matched_total = len(rows)
    window = rows[offset:] if args.all else rows[offset : offset + limit]
    meta = {
        "source": "live",
        "backend": "cdp",
        "kind": variant.kind,
        "simulated": False,
        "capability": variant.name,
        "scope": resolved.scope_key,
        "requested_window": (
            list(resolved.window) if resolved.window[0] is not None else None
        ),
        "retained_coverage": None,
        "snapshot_id": None,
        "dataset_id": None,
        "fetched_at": now().isoformat(),
        "loaded_at": None,
        "stale": False,
        **evidence.meta(),
        "source_observed_from": None,
        "source_observed_to": None,
        "reported_total": result.total_count,
        "matched_total": matched_total,
        "returned_count": len(window),
        "has_more": offset + len(window) < matched_total,
    }
    return _emit_window(args, variant.table_columns, window, meta, fields)


def run_detail(args: argparse.Namespace) -> int:
    leaf = detail_leaf(args.command_path[1:])
    detail = leaf.spec
    values = identity_values(args, leaf)
    # Validation of required/typed identity happens in detail_body.
    leaf.capability.detail_body(values)
    fields: list[str] | None = None
    if args.fields is not None:
        fields = [name.strip() for name in args.fields.split(",") if name.strip()]
        if not fields:
            raise CliError(
                INVALID_ARGUMENT,
                "--fields must name at least one field",
                exit_code=EXIT_USAGE,
            )
    config = load_config()
    if args.live:
        with inquiry_session(
            config_file=config_mod.config_path(), startup_url=leaf.capability.page_url
        ) as session:
            from .decision_history import fetch_native_detail

            payload = fetch_native_detail(session, leaf, values)
        meta = {
            "source": "live",
            "backend": "cdp",
            "kind": detail.kind,
            "simulated": False,
            "capability": detail.name,
            "identity": dict(values),
            "fetched_at": now().isoformat(),
            "loaded_at": None,
            "stale": False,
            "complete": True,
            "dataset_complete": None,
            "matched_total": 1,
            "returned_count": 1,
            "has_more": False,
        }
        if detail.schema_version:
            meta["request_scope"] = (
                {"tntInstId": spec_mod.TENANT} if detail.sends_tenant else {}
            )
        if detail.schema_version and isinstance(payload, dict) and "version" in payload:
            meta["source_version"] = payload["version"]
        meta.update(detail_context_meta(detail, values, payload))
        return _emit_object(args, detail.table_columns, payload, meta, fields)
    store = Cache(config.cache_path)
    snapshot = detail_store.read_detail_snapshot(store, detail.name)
    key = detail_store.contract_detail_key(detail, values)
    hint = (
        f"run: dogopencli refresh liquidity {' '.join(detail.path)} detail"
        f" {detail.action} "
        + " ".join(
            f"--{flag.replace('_', '-')} {shlex.quote(str(value))}"
            for flag, value in sorted(values.items())
        )
    )
    if snapshot is None:
        raise CliError(CACHE_MISS, f"no cached liquidity details; {hint}")
    stored = detail_store.read_details(store, detail.name).get(key)
    if stored is None:
        raise CliError(
            CACHE_MISS,
            "no cached native detail for this identity (the object may still"
            f" exist at the source); {hint}",
        )
    stale = is_stale(
        replace(snapshot, fetched_at=stored.fetched_at), config.ttl_hours, now()
    )
    if args.require_fresh and stale:
        raise CliError(
            CACHE_STALE,
            f"cached details are older than {config.ttl_hours:g} hours"
            f" (fetched_at {stored.fetched_at})",
        )
    meta = {
        "source": "cache",
        "backend": "cdp",
        "kind": detail.kind,
        "simulated": False,
        "capability": detail.name,
        "identity": dict(values),
        "snapshot_id": snapshot.snapshot_id,
        "dataset_id": None,
        "fetched_at": stored.fetched_at,
        "detail_fetched_at": stored.fetched_at,
        "loaded_at": None,
        "stale": stale,
        "complete": True,
        "dataset_complete": None,
        "matched_total": 1,
        "returned_count": 1,
        "has_more": False,
    }
    if detail.schema_version:
        meta["request_scope"] = (
            {"tntInstId": spec_mod.TENANT} if detail.sends_tenant else {}
        )
    if (
        detail.schema_version
        and isinstance(stored.detail, dict)
        and "version" in stored.detail
    ):
        meta["source_version"] = stored.detail["version"]
    meta.update(detail_context_meta(detail, values, stored.detail))
    return _emit_object(args, detail.table_columns, stored.detail, meta, fields)


def fetch_detail(
    transport: CdpQueryTransport, leaf: DetailLeaf, values: dict[str, str]
) -> Any:
    from ... import collect as collect_mod

    response = collect_mod.execute_bounded(
        leaf.capability, transport, leaf.capability.detail_body(values)
    )
    if is_business_refusal(response.body):
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return leaf.capability.parse_detail(response.body, values)


def run_unsupported(args: argparse.Namespace) -> int:
    leaf = DEFERRED_BY_PATH.get(args.command_path[1:])
    reason = leaf.reason if leaf is not None else "unsupported liquidity leaf"
    raise CliError(
        UNSUPPORTED_CAPABILITY,
        f"{' '.join(args.command_path)} is deferred: {reason}",
    )
