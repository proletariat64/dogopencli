"""Liquidity capture storage and the 1,000,000-record retention policy.

Layout per business leaf (ADR 0016/0017): one ``__index__`` namespace lists
the leaf's retained captures; each capture is its own namespace of validated
records. Settings/reference leaves keep one current capture per scope
(replace semantics). Time-series leaves (capture history or dated windows)
retain every explicit acquisition until the per-leaf cap; overflow
atomically evicts the oldest records by the verified series axis with a
stable identity tie-breaker, warns on stderr and narrows the published
coverage. Non-time-series overflow rejects the refresh. Every publish —
capture, index, eviction — lands in one ``Cache.publish_many`` transaction,
so readers only ever see complete old or complete new state.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ...cache import Cache, SnapshotMeta, namespace
from ...errors import INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from ...jsonutil import canonical, parse
from . import spec

INDEX_SCOPE = "__index__"
SOURCE_KIND = "cdp"

ENTRY_CAPTURE = "capture"
ENTRY_RETENTION = "retention"


def _invalid(message: str) -> CliError:
    return CliError(INVALID_RESPONSE, message)


@dataclass(frozen=True)
class CaptureEntry:
    """One retained list capture tracked by the leaf index."""

    namespace: str
    scope: str
    window_from: str | None
    window_to: str | None
    profile: str
    fetched_at: str
    row_count: int
    reported_total: int | None
    snapshot_id: str
    # Cache identity beyond the namespace: the mandatory business kind and
    # the source origin/tenant this capture was acquired from.
    kind: str | None = None
    source_origin: str | None = None
    tenant: str | None = None

    def record(self) -> dict[str, Any]:
        return {
            "type": ENTRY_CAPTURE,
            "namespace": self.namespace,
            "scope": self.scope,
            "window_from": self.window_from,
            "window_to": self.window_to,
            "profile": self.profile,
            "fetched_at": self.fetched_at,
            "row_count": self.row_count,
            "reported_total": self.reported_total,
            "snapshot_id": self.snapshot_id,
            "kind": self.kind,
            "source_origin": self.source_origin,
            "tenant": self.tenant,
        }

    @staticmethod
    def from_record(record: dict[str, Any]) -> "CaptureEntry":
        namespace_value = record.get("namespace")
        scope_value = record.get("scope")
        fetched_at = record.get("fetched_at")
        row_count = record.get("row_count")
        snapshot_id = record.get("snapshot_id")
        if (
            not isinstance(namespace_value, str)
            or not isinstance(scope_value, str)
            or not isinstance(fetched_at, str)
            or isinstance(row_count, bool)
            or not isinstance(row_count, int)
            or not isinstance(snapshot_id, str)
        ):
            raise _invalid("cached capture index is invalid")
        window_from = record.get("window_from")
        window_to = record.get("window_to")
        reported_total = record.get("reported_total")
        profile = record.get("profile")
        if profile not in (
            spec.PROFILE_SNAPSHOT,
            spec.PROFILE_HISTORY,
            spec.PROFILE_DATED,
        ):
            raise _invalid("cached capture profile is invalid")
        kind = record.get("kind")
        source_origin = record.get("source_origin")
        tenant = record.get("tenant")
        return CaptureEntry(
            namespace=namespace_value,
            scope=scope_value,
            window_from=window_from if isinstance(window_from, str) else None,
            window_to=window_to if isinstance(window_to, str) else None,
            profile=profile,
            fetched_at=fetched_at,
            row_count=row_count,
            reported_total=(
                reported_total
                if isinstance(reported_total, int)
                and not isinstance(reported_total, bool)
                else None
            ),
            snapshot_id=snapshot_id,
            kind=kind if isinstance(kind, str) else None,
            source_origin=source_origin if isinstance(source_origin, str) else None,
            tenant=tenant if isinstance(tenant, str) else None,
        )


@dataclass(frozen=True)
class EvictionReport:
    """Truthful retention metadata for one eviction (ADR 0017)."""

    dropped: int
    retained: int
    retained_from: str | None
    tie_break: str | None
    evicted: tuple[dict[str, Any], ...]

    def record(self, at: str) -> dict[str, Any]:
        return {
            "type": ENTRY_RETENTION,
            "at": at,
            "dropped": self.dropped,
            "retained": self.retained,
            "retained_from": self.retained_from,
            "tie_break": self.tie_break,
            "evicted": list(self.evicted),
        }


@dataclass
class IndexData:
    captures: list[CaptureEntry] = field(default_factory=list)
    evictions: list[dict[str, Any]] = field(default_factory=list)


def index_namespace(capability: str) -> str:
    return namespace(capability, INDEX_SCOPE, SOURCE_KIND)


def capture_namespace(capability: str, scope: str, suffix: str) -> str:
    return namespace(capability, f"{scope}@{suffix}", SOURCE_KIND)


def read_index(store: Cache, capability: str) -> IndexData | None:
    snapshot, stored = store.read(index_namespace(capability))
    if snapshot is None:
        return None
    data = IndexData()
    for _, body in stored:
        record = parse(body)
        if not isinstance(record, dict):
            raise _invalid("cached capture index is invalid")
        entry_type = record.get("type")
        if entry_type == ENTRY_CAPTURE:
            data.captures.append(CaptureEntry.from_record(record))
        elif entry_type == ENTRY_RETENTION:
            data.evictions.append(record)
        else:
            raise _invalid("cached capture index is invalid")
    return data


def read_capture(store: Cache, entry: CaptureEntry) -> list[dict[str, Any]]:
    snapshot, stored = store.read(entry.namespace)
    if (
        snapshot is None
        or snapshot.row_count != len(stored)
        or len(stored) != entry.row_count
    ):
        raise _invalid("cached capture coverage is invalid")
    rows = []
    for _, body in stored:
        record = parse(body)
        if not isinstance(record, dict):
            raise _invalid("cached capture record is invalid")
        rows.append(record)
    if len(rows) != entry.row_count:
        raise _invalid("cached capture coverage is invalid")
    return rows


def _index_snapshot(
    capability: str,
    data: IndexData,
    loaded_at: str,
) -> tuple[SnapshotMeta, list[tuple[int, str]]]:
    records: list[dict[str, Any]] = [
        entry.record()
        for entry in sorted(
            data.captures,
            key=lambda entry: (
                entry.window_to or "",
                entry.fetched_at,
                entry.namespace,
            ),
        )
    ]
    records.extend(data.evictions[-8:])
    meta = SnapshotMeta(
        namespace=index_namespace(capability),
        capability=capability,
        scope=INDEX_SCOPE,
        source_kind=SOURCE_KIND,
        snapshot_id=hashlib.sha256(canonical(records).encode()).hexdigest(),
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at=loaded_at,
        loaded_at=loaded_at,
        source_observed_from=None,
        source_observed_to=None,
        row_count=len(records),
    )
    return meta, [(index, canonical(record)) for index, record in enumerate(records, 1)]


def series_value(
    list_spec: spec.ListSpec, record: dict[str, Any], fetched_at: str
) -> str:
    """Verified series axis of one record; unknown ordering rejects refresh."""
    if list_spec.profile == spec.PROFILE_DATED:
        field_name = list_spec.series_field
        value = record.get(field_name) if field_name else None
        if not isinstance(value, str) or not value.strip():
            raise _invalid(
                f"record is missing its verified series time {field_name};"
                " retention ordering is unavailable"
            )
        if list_spec.series_format is not None:
            try:
                parsed = datetime.strptime(value, list_spec.series_format)
                if parsed.strftime(list_spec.series_format) != value:
                    raise ValueError
            except ValueError as error:
                raise _invalid(
                    f"record has invalid series time {field_name}"
                ) from error
            return parsed.strftime("%Y%m%d")
        return value
    # Capture-history records order by capture time explicitly (ADR 0017);
    # capture time is never relabelled as source observation time.
    return fetched_at


def _owning_variant(list_spec: spec.ListSpec, entry: CaptureEntry) -> spec.ListSpec:
    """Use the retained capture's selector, not the refreshing variant."""
    from .capability import decode_scope
    from .leaves import LIST_LEAVES

    leaf = LIST_LEAVES.get(list_spec.path)
    if leaf is None or len(leaf.variants) == 1:
        return list_spec
    scope = decode_scope(entry.scope)
    candidates = [
        variant
        for variant in leaf.variants
        if all(
            scope.get(option.field) == option.match
            for option in variant.scope_options
            if option.match
        )
    ]
    if len(candidates) != 1:
        raise _invalid("retained capture variant is unknown; refresh rejected")
    return candidates[0]


def _identity_of(list_spec: spec.ListSpec, record: dict[str, Any]) -> str:
    if not list_spec.identity:
        return canonical(record)
    parts: list[str] = []
    for field_name in list_spec.identity:
        value = record.get(field_name)
        if value is None or isinstance(value, (dict, list)):
            raise _invalid(f"record is missing identity field {field_name}")
        parts.append(canonical(value))
    return "|".join(parts)


@dataclass
class PublishPlan:
    """Everything one refresh must commit atomically."""

    capture_meta: SnapshotMeta
    capture_records: list[tuple[int, str]]
    trimmed: dict[str, tuple[SnapshotMeta, list[tuple[int, str]]]] = field(
        default_factory=dict
    )
    dropped_namespaces: list[str] = field(default_factory=list)
    eviction: EvictionReport | None = None
    index: IndexData = field(default_factory=IndexData)


def plan_capture_publish(
    store: Cache,
    list_spec: spec.ListSpec,
    scope: str,
    window: tuple[str | None, str | None],
    rows: list[dict[str, Any]],
    reported_total: int | None,
    fetched_at: str,
    loaded_at: str,
    *,
    cap: int = spec.RETENTION_CAP,
) -> PublishPlan:
    """Validate and lay out one acquisition; never writes anything.

    Retention is deliberate, not tolerance of failed acquisition: the caller
    publishes the plan only after complete validated acquisition.
    """
    profile = list_spec.profile
    window_from, window_to = window
    if profile == spec.PROFILE_SNAPSHOT:
        if len(rows) > cap:
            raise CliError(
                INVALID_ARGUMENT,
                f"{list_spec.leaf} holds {len(rows)} records, above the"
                f" {cap} record retention cap; refresh rejected and the"
                " previous cache is retained",
            )
        suffix = "current"
    elif profile == spec.PROFILE_DATED:
        if window_from is None or window_to is None:
            raise CliError(INVALID_ARGUMENT, "dated acquisition requires a window")
        suffix = f"{window_from}..{window_to}"
        for record in rows:
            series_value(list_spec, record, fetched_at)
    else:
        suffix = fetched_at.replace(":", "").replace("-", "").replace("+", "Z")
    entry_ns = capture_namespace(list_spec.name, scope, suffix)
    existing = read_index(store, list_spec.name) or IndexData()
    kept: list[CaptureEntry] = []
    dropped_namespaces: list[str] = []
    for entry in existing.captures:
        same_scope = entry.scope == scope
        same_window = entry.window_from == window_from and entry.window_to == window_to
        if profile == spec.PROFILE_SNAPSHOT and same_scope:
            dropped_namespaces.append(entry.namespace)
        elif profile == spec.PROFILE_DATED and same_scope and same_window:
            dropped_namespaces.append(entry.namespace)
        else:
            kept.append(entry)
    snapshot_id = hashlib.sha256(canonical(rows).encode()).hexdigest()
    new_entry = CaptureEntry(
        namespace=entry_ns,
        scope=scope,
        window_from=window_from if profile == spec.PROFILE_DATED else None,
        window_to=window_to if profile == spec.PROFILE_DATED else None,
        profile=profile,
        fetched_at=fetched_at,
        row_count=len(rows),
        reported_total=reported_total,
        snapshot_id=snapshot_id,
        kind=list_spec.kind,
        source_origin=f"https://{spec.HOST}",
        tenant=spec.TENANT,
    )
    capture_meta = SnapshotMeta(
        namespace=entry_ns,
        capability=list_spec.name,
        scope=scope,
        source_kind=SOURCE_KIND,
        snapshot_id=snapshot_id,
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at=fetched_at,
        loaded_at=loaded_at,
        source_observed_from=new_entry.window_from,
        source_observed_to=new_entry.window_to,
        row_count=len(rows),
    )
    plan = PublishPlan(
        capture_meta=capture_meta,
        capture_records=[
            (index, canonical(record)) for index, record in enumerate(rows, 1)
        ],
        dropped_namespaces=dropped_namespaces,
    )
    if profile == spec.PROFILE_SNAPSHOT:
        total = sum(entry.row_count for entry in kept) + new_entry.row_count
        if total > cap:
            raise CliError(
                INVALID_ARGUMENT,
                f"{list_spec.leaf} holds {total} records across scopes, above the"
                f" {cap} record retention cap; refresh rejected and the"
                " previous cache is retained",
            )
        plan.index = IndexData(captures=[*kept, new_entry])
        return plan
    # Time-series leaf: enforce the per-leaf cap with deterministic
    # oldest-first eviction across dates, captures and filter variants.
    pending_rows: dict[str, list[tuple[int, str]]] = {entry_ns: plan.capture_records}
    entries = [*kept, new_entry]
    total = sum(entry.row_count for entry in entries)
    if total <= cap:
        plan.index = IndexData(captures=entries)
        return plan
    for entry in entries:
        if profile == spec.PROFILE_DATED and not entry.window_to:
            raise _invalid(
                "retention ordering is unavailable; refresh rejected and the"
                " previous cache is retained"
            )
    excess = total - cap
    ordered = sorted(
        entries,
        key=lambda entry: (entry.window_to or entry.fetched_at, entry.namespace),
    )
    dropped = 0
    retained_from: str | None = None
    tie_break: str | None = None
    evicted: list[dict[str, Any]] = []
    survivors: list[CaptureEntry] = list(ordered)
    for victim in list(ordered):
        if excess <= 0:
            break
        if victim.row_count <= excess:
            excess -= victim.row_count
            dropped += victim.row_count
            survivors.remove(victim)
            if victim.namespace != entry_ns:
                plan.dropped_namespaces.append(victim.namespace)
            else:
                plan.capture_records = []
            evicted.append(
                {
                    "namespace": victim.namespace,
                    "window_from": victim.window_from,
                    "window_to": victim.window_to,
                    "dropped_records": victim.row_count,
                    "partial": False,
                }
            )
            continue
        # Split the boundary capture: drop exactly the oldest excess records
        # by (series time, identity, position) and keep the newest rest.
        if victim.namespace in pending_rows:
            stored_rows = pending_rows[victim.namespace]
        else:
            stored_rows = store.read(victim.namespace)[1]
        victim_spec = _owning_variant(list_spec, victim)
        decoded: list[tuple[str, str, int, str]] = []
        for seqid, body in stored_rows:
            record = parse(body)
            decoded.append(
                (
                    series_value(victim_spec, record, victim.fetched_at),
                    _identity_of(victim_spec, record),
                    seqid,
                    body,
                )
            )
        decoded.sort(key=lambda item: (item[0], item[1], item[2]))
        keep = decoded[excess:]
        dropped += excess
        retained_from = keep[0][0]
        tie_break = keep[0][1]
        survivors.remove(victim)
        trimmed_entry = CaptureEntry(
            namespace=victim.namespace,
            scope=victim.scope,
            window_from=retained_from
            if profile == spec.PROFILE_DATED
            else victim.window_from,
            window_to=victim.window_to,
            profile=victim.profile,
            fetched_at=victim.fetched_at,
            row_count=len(keep),
            reported_total=victim.reported_total,
            snapshot_id=hashlib.sha256(
                canonical([item[3] for item in keep]).encode()
            ).hexdigest(),
            kind=victim.kind,
            source_origin=victim.source_origin,
            tenant=victim.tenant,
        )
        survivors.append(trimmed_entry)
        trimmed_meta = SnapshotMeta(
            namespace=victim.namespace,
            capability=list_spec.name,
            scope=victim.scope,
            source_kind=SOURCE_KIND,
            snapshot_id=trimmed_entry.snapshot_id,
            dataset_id=None,
            simulated=False,
            backend_complete=True,
            dataset_complete=True,
            fetched_at=victim.fetched_at,
            loaded_at=loaded_at,
            source_observed_from=trimmed_entry.window_from,
            source_observed_to=trimmed_entry.window_to,
            row_count=len(keep),
        )
        trimmed_records = [(index, item[3]) for index, item in enumerate(keep, 1)]
        if victim.namespace == entry_ns:
            plan.capture_meta = trimmed_meta
            plan.capture_records = trimmed_records
        else:
            plan.trimmed[victim.namespace] = (trimmed_meta, trimmed_records)
        evicted.append(
            {
                "namespace": victim.namespace,
                "window_from": victim.window_from,
                "window_to": victim.window_to,
                "dropped_records": excess,
                "partial": True,
            }
        )
        excess = 0
    retained = sum(entry.row_count for entry in survivors)
    plan.index = IndexData(captures=survivors)
    plan.eviction = EvictionReport(
        dropped=dropped,
        retained=retained,
        retained_from=retained_from,
        tie_break=tie_break,
        evicted=tuple(evicted),
    )
    return plan


def commit_plan(
    store: Cache, capability: str, plan: PublishPlan, loaded_at: str
) -> None:
    """Atomically publish the capture, trims, drops and the leaf index."""
    writes: list[tuple[SnapshotMeta, list[tuple[int, str]]]] = []
    if any(
        entry.namespace == plan.capture_meta.namespace for entry in plan.index.captures
    ):
        writes.append((plan.capture_meta, plan.capture_records))
    writes.extend(plan.trimmed.values())
    if plan.eviction is not None:
        plan.index.evictions.append(plan.eviction.record(loaded_at))
    writes.append(_index_snapshot(capability, plan.index, loaded_at))
    store.publish_many(writes, deletes=plan.dropped_namespaces)


def select_captures(
    data: IndexData,
    list_spec: spec.ListSpec,
    scope: str,
    window: tuple[str | None, str | None],
) -> tuple[list[CaptureEntry], bool]:
    """Captures answering one query, and whether retained coverage suffices.

    A window outside retained coverage is missing coverage, never an empty
    result: coverage_ok=False drives the existing incomplete-result behavior.
    """
    scoped = [entry for entry in data.captures if entry.scope == scope]
    if list_spec.profile in (spec.PROFILE_SNAPSHOT, spec.PROFILE_HISTORY):
        latest = max(scoped, key=lambda entry: entry.fetched_at, default=None)
        return ([latest] if latest is not None else []), latest is not None
    window_from, window_to = window
    if window_from is None or window_to is None:
        raise CliError(INVALID_ARGUMENT, "dated queries require a business window")
    covering = [
        entry
        for entry in scoped
        if entry.window_from is not None
        and entry.window_to is not None
        and entry.window_from <= window_to
        and entry.window_to >= window_from
    ]
    return covering, _covered(covering, window_from, window_to)


def _covered(entries: list[CaptureEntry], start: str, end: str) -> bool:
    intervals = sorted(
        (entry.window_from, entry.window_to)
        for entry in entries
        if entry.window_from is not None and entry.window_to is not None
    )
    cursor = start
    for interval_from, interval_to in intervals:
        if interval_from > cursor:
            return False
        if interval_to >= cursor:
            cursor = _next_day_like(interval_to)
            if cursor > end:
                return True
    return cursor > end


def _next_day_like(value: str) -> str:
    """Successor of a day string in lexical window terms (YYYYMMDD)."""
    try:
        parsed = datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return value + " "
    return (parsed + timedelta(days=1)).strftime("%Y%m%d")
