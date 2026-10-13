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
so readers only ever see the old or new data and its matching quality evidence.
"""

import hashlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from ...cache import Cache, SnapshotMeta, namespace
from ...errors import INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from ...jsonutil import canonical, parse
from ...result_policy import AcquisitionEvidence
from . import spec

INDEX_SCOPE = "__index__"
SOURCE_KIND = "cdp"

ENTRY_CAPTURE = "capture"
ENTRY_RETENTION = "retention"
ENTRY_FORMAT = "acquisition_format"
ACQUISITION_FORMAT = 1


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
    # Exact retention holes; a later missing day must not erase earlier
    # verified empty days in this capture's acquisition window.
    missing_days: tuple[str, ...] = ()
    acquisition: AcquisitionEvidence | None = None
    requested_from: str | None = None
    requested_to: str | None = None
    # Read-only adapter for pre-evidence snapshots; never serialized on reads.
    legacy_evidence: AcquisitionEvidence | None = field(default=None, repr=False)

    @property
    def evidence(self) -> AcquisitionEvidence:
        # Old list captures were admitted only after complete acquisition.
        return (
            self.acquisition
            or self.legacy_evidence
            or AcquisitionEvidence.for_collection(
                complete=True,
                reported_total=self.reported_total,
                collected_total=self.reported_total
                if self.reported_total is not None
                else self.row_count,
            )
        )

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
            "missing_days": list(self.missing_days),
            "acquisition": self.acquisition.record() if self.acquisition else None,
            "requested_from": self.requested_from,
            "requested_to": self.requested_to,
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
        missing_days = record.get("missing_days", [])
        if not isinstance(missing_days, list) or any(
            not isinstance(day, str) for day in missing_days
        ):
            raise _invalid("cached capture missing days are invalid")
        for day in missing_days:
            try:
                if (
                    _format_series_time(datetime.strptime(day, "%Y%m%d"), "%Y%m%d")
                    != day
                ):
                    raise ValueError
            except ValueError as error:
                raise _invalid("cached capture missing days are invalid") from error
        for boundary in ("requested_from", "requested_to"):
            value = record.get(boundary)
            if value is not None:
                try:
                    if (
                        not isinstance(value, str)
                        or _format_series_time(
                            datetime.strptime(value, "%Y%m%d"), "%Y%m%d"
                        )
                        != value
                    ):
                        raise ValueError
                except ValueError as error:
                    raise _invalid("cached acquisition window is invalid") from error
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
            missing_days=tuple(sorted(set(missing_days))),
            acquisition=(
                AcquisitionEvidence.from_record(record["acquisition"])
                if record.get("acquisition") is not None
                else None
            ),
            requested_from=record.get("requested_from", window_from),
            requested_to=record.get("requested_to", window_to),
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
        try:
            record = parse(body)
        except (ValueError, TypeError) as error:
            raise _invalid("cached capture index JSON is invalid") from error
        if not isinstance(record, dict):
            raise _invalid("cached capture index is invalid")
        entry_type = record.get("type")
        if entry_type == ENTRY_FORMAT:
            if record.get("version") != ACQUISITION_FORMAT:
                raise _invalid("unsupported cached acquisition format")
        elif entry_type == ENTRY_CAPTURE:
            entry = CaptureEntry.from_record(record)
            if entry.acquisition is None:
                capture = store.current(entry.namespace)
                if capture is None:
                    raise _invalid("cached capture coverage is invalid")
                if capture.acquisition is not None:
                    entry = replace(
                        entry,
                        acquisition=AcquisitionEvidence.from_record(
                            capture.acquisition
                        ),
                    )
                elif not (capture.backend_complete and capture.dataset_complete):
                    entry = replace(
                        entry,
                        legacy_evidence=AcquisitionEvidence(
                            scope_complete=capture.backend_complete,
                            dataset_complete=capture.dataset_complete,
                            collected_total=capture.row_count,
                            reported_total=entry.reported_total,
                            reasons=("COVERAGE_UNPROVEN",),
                        ),
                    )
            data.captures.append(entry)
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
    if (
        snapshot.source_kind != SOURCE_KIND
        or snapshot.simulated
        or snapshot.snapshot_id != entry.snapshot_id
        or snapshot.scope != entry.scope
        or entry.source_origin not in (None, f"https://{spec.HOST}")
        or entry.tenant not in (None, spec.TENANT)
    ):
        raise _invalid("cached capture source is invalid")
    # Snapshot leaves do not permit retention trims: storage must contain the
    # whole validated candidate, including candidates without reported totals.
    if (
        entry.profile == spec.PROFILE_SNAPSHOT
        and entry.acquisition is not None
        and entry.row_count != entry.acquisition.collected_total
    ):
        raise _invalid("cached snapshot acquisition count does not match storage")
    if entry.acquisition is not None and (
        snapshot.acquisition != entry.acquisition.record()
        or snapshot.backend_complete != entry.acquisition.scope_complete
        or snapshot.dataset_complete != entry.acquisition.dataset_complete
    ):
        raise _invalid("cached acquisition evidence does not match capture")
    if entry.legacy_evidence is not None and (
        snapshot.backend_complete != entry.legacy_evidence.scope_complete
        or snapshot.dataset_complete != entry.legacy_evidence.dataset_complete
    ):
        raise _invalid("cached legacy acquisition flags do not match capture")
    rows = []
    for expected_seqid, (seqid, body) in enumerate(stored, 1):
        if seqid != expected_seqid:
            raise _invalid("cached capture storage sequence is invalid")
        try:
            record = parse(body)
        except (ValueError, TypeError) as error:
            raise _invalid("cached capture record JSON is invalid") from error
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
    # Keep publication order across reloads so equal acquisition timestamps
    # still distinguish a later complete capture from older retained evidence.
    # Older readers reject this unknown row type before exposing new partial captures.
    records: list[dict[str, Any]] = [
        {"type": ENTRY_FORMAT, "version": ACQUISITION_FORMAT},
        *(entry.record() for entry in data.captures),
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


def _format_series_time(value: datetime, format_string: str) -> str:
    """Keep the declared format while padding years on every platform."""
    return value.strftime(format_string.replace("%Y", f"{value.year:04d}"))


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
                if _format_series_time(parsed, list_spec.series_format) != value:
                    raise ValueError
            except ValueError as error:
                raise _invalid(
                    f"record has invalid series time {field_name}"
                ) from error
            return _format_series_time(parsed, "%Y%m%d")
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
    if list_spec.path == ("cash", "balances"):
        # Latest's legacy scope has no variant selector. Profile plus the
        # persisted contract distinguishes it from new daily captures.
        candidates = [
            variant for variant in leaf.variants if variant.profile == entry.profile
        ]
        if len(candidates) != 1:
            raise _invalid("retained cash balance variant is unknown")
        return candidates[0]
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


@dataclass(frozen=True)
class _RankedRecord:
    """One retained record ranked on its own capture's verified series axis."""

    namespace: str
    series: str
    identity: str
    fetched_at: str
    seqid: int
    body: str


def _eviction_record(
    entry: CaptureEntry, dropped: int, *, partial: bool
) -> dict[str, Any]:
    return {
        "namespace": entry.namespace,
        "window_from": entry.window_from,
        "window_to": entry.window_to,
        "dropped_records": dropped,
        "partial": partial,
    }


def _retained_window_from(
    profile: str,
    entry: CaptureEntry,
    lost: list[_RankedRecord],
) -> str | None:
    """Narrow a lost leading boundary without discarding earlier empty days.

    Interior retention holes are represented by missing_days. A lost record
    on a later day does not invalidate the verified empty days before it.
    """
    if profile != spec.PROFILE_DATED or entry.window_from is None:
        return entry.window_from
    missing = set(entry.missing_days) | {item.series for item in lost}
    start = entry.window_from
    while start in missing:
        try:
            start = _next_day_like(start)
        except OverflowError:
            # The final calendar day has no successor or retained coverage.
            return None
    return start


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
    acquisition: AcquisitionEvidence | None = None,
) -> PublishPlan:
    """Validate and lay out one acquisition; never writes anything.

    The caller decides whether source and final retained quality satisfy its
    strictness requirement before committing this plan.
    """
    profile = list_spec.profile
    acquisition = acquisition or AcquisitionEvidence.for_collection(
        complete=True,
        reported_total=reported_total,
        collected_total=len(rows),
        has_identity=bool(list_spec.identity),
    )
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
        # Replacement is namespace identity. Retention narrows a trimmed
        # capture's indexed window, so its window no longer names the
        # acquisition it stands for, and matching on the window would leave
        # two index entries pointing at one namespace.
        if entry.namespace == entry_ns:
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
        acquisition=acquisition,
        requested_from=window_from,
        requested_to=window_to,
    )
    capture_meta = SnapshotMeta(
        namespace=entry_ns,
        capability=list_spec.name,
        scope=scope,
        source_kind=SOURCE_KIND,
        snapshot_id=snapshot_id,
        dataset_id=None,
        simulated=False,
        backend_complete=acquisition.scope_complete,
        dataset_complete=acquisition.dataset_complete,
        acquisition=acquisition.record(),
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
        if entry.profile == spec.PROFILE_DATED and not entry.window_to:
            raise _invalid(
                "retention ordering is unavailable; refresh rejected and the"
                " previous cache is retained"
            )
    excess = total - cap
    # Retention is record-granular (ADR 0017): overlapping captures cannot be
    # ranked as wholes without discarding newer records, so every retained
    # record is decoded with its own capture's variant and ranked on the
    # verified series axis with a stable identity tie-breaker.
    ranked: list[_RankedRecord] = []
    for entry in entries:
        stored_rows = pending_rows.get(entry.namespace)
        if stored_rows is None:
            stored_rows = store.read(entry.namespace)[1]
        entry_spec = _owning_variant(list_spec, entry)
        for seqid, body in stored_rows:
            record = parse(body)
            ranked.append(
                _RankedRecord(
                    namespace=entry.namespace,
                    series=series_value(entry_spec, record, entry.fetched_at),
                    identity=_identity_of(entry_spec, record),
                    fetched_at=entry.fetched_at,
                    seqid=seqid,
                    body=body,
                )
            )
    # Acquisition time breaks identity ties: an older copy of one record must
    # evict before the newer correction of it, whatever their namespaces.
    ranked.sort(
        key=lambda item: (
            # Cash daily days are compact; latest capture timestamps are ISO.
            # Compare calendar prefixes without inventing a daily timezone or
            # relabelling the capture axis. Report each original series value.
            item.series.replace("-", "", 2)
            if list_spec.path == ("cash", "balances")
            else item.series,
            item.identity,
            item.fetched_at,
            item.namespace,
            item.seqid,
        )
    )
    evicted_records = ranked[:excess]
    surviving = ranked[excess:]
    kept_rows: dict[str, list[_RankedRecord]] = {}
    for item in surviving:
        kept_rows.setdefault(item.namespace, []).append(item)
    lost_rows: dict[str, list[_RankedRecord]] = {}
    for item in evicted_records:
        lost_rows.setdefault(item.namespace, []).append(item)

    survivors: list[CaptureEntry] = []
    evicted: list[dict[str, Any]] = []
    for entry in entries:
        remaining = kept_rows.get(entry.namespace, [])
        lost = lost_rows.get(entry.namespace, [])
        if not lost:
            survivors.append(entry)
            continue
        retained_from = _retained_window_from(entry.profile, entry, lost)
        if not remaining and (
            entry.profile != spec.PROFILE_DATED
            or retained_from is None
            or entry.window_to is None
            or retained_from > entry.window_to
        ):
            if entry.namespace != entry_ns:
                plan.dropped_namespaces.append(entry.namespace)
            else:
                plan.capture_records = []
            if lost:
                evicted.append(_eviction_record(entry, len(lost), partial=False))
            continue
        remaining.sort(key=lambda item: item.seqid)
        bodies = [item.body for item in remaining]
        trimmed_entry = CaptureEntry(
            namespace=entry.namespace,
            scope=entry.scope,
            window_from=retained_from,
            window_to=entry.window_to,
            profile=entry.profile,
            fetched_at=entry.fetched_at,
            row_count=len(remaining),
            reported_total=entry.reported_total,
            snapshot_id=hashlib.sha256(canonical(bodies).encode()).hexdigest(),
            kind=entry.kind,
            source_origin=entry.source_origin,
            tenant=entry.tenant,
            missing_days=entry.missing_days,
            acquisition=entry.evidence,
            requested_from=entry.requested_from,
            requested_to=entry.requested_to,
        )
        trimmed_meta = SnapshotMeta(
            namespace=entry.namespace,
            capability=list_spec.name,
            scope=entry.scope,
            source_kind=SOURCE_KIND,
            snapshot_id=trimmed_entry.snapshot_id,
            dataset_id=None,
            simulated=False,
            backend_complete=entry.evidence.scope_complete,
            dataset_complete=entry.evidence.dataset_complete,
            acquisition=entry.evidence.record(),
            fetched_at=entry.fetched_at,
            loaded_at=loaded_at,
            source_observed_from=trimmed_entry.window_from,
            source_observed_to=trimmed_entry.window_to,
            row_count=len(remaining),
        )
        trimmed_records = [(index, body) for index, body in enumerate(bodies, 1)]
        if entry.namespace == entry_ns:
            plan.capture_meta = trimmed_meta
            plan.capture_records = trimmed_records
        else:
            plan.trimmed[entry.namespace] = (trimmed_meta, trimmed_records)
        survivors.append(trimmed_entry)
        evicted.append(_eviction_record(entry, len(lost), partial=True))
    if any(entry.profile == spec.PROFILE_DATED for entry in entries):
        # Older captures cannot repair a newer capture's lost day, but a newer
        # complete acquisition can. Publication order breaks fetched_at ties.
        generations = {
            entry.namespace: (entry.fetched_at, index)
            for index, entry in enumerate(entries)
        }
        lost_days: dict[str, dict[str, tuple[str, int]]] = {}
        scopes = {entry.namespace: entry.scope for entry in entries}
        for item in evicted_records:
            scope_days = lost_days.setdefault(scopes[item.namespace], {})
            generation = generations[item.namespace]
            previous = scope_days.get(item.series)
            if previous is None or generation > previous:
                scope_days[item.series] = generation
        for index, entry in enumerate(survivors):
            affected = [
                day
                for day, lost_generation in lost_days.get(entry.scope, {}).items()
                if entry.window_from is not None
                and entry.window_to is not None
                and entry.window_from <= day <= entry.window_to
                and generations[entry.namespace] <= lost_generation
            ]
            if affected:
                survivors[index] = replace(
                    entry,
                    missing_days=tuple(sorted(set(entry.missing_days) | set(affected))),
                )
    plan.index = IndexData(captures=survivors)
    plan.eviction = EvictionReport(
        dropped=len(evicted_records),
        retained=len(surviving),
        retained_from=surviving[0].series if surviving else None,
        tie_break=surviving[0].identity if surviving else None,
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


def _latest_balance_scope_key(scope: str) -> str:
    """Match legacy selector ordering without rewriting captures or broadening scope."""
    from .capability import decode_scope, encode_scope

    try:
        values = decode_scope(scope)
    except CliError:
        return scope  # Opaque or malformed scope strings remain exact-match only.
    for field_name in ("entitys", "aliasNames"):
        if field_name not in values:
            continue
        selection = values[field_name]
        if not isinstance(selection, list) or any(
            not isinstance(value, str) or not value.strip() for value in selection
        ):
            return scope
        values[field_name] = sorted(set(selection))
    return encode_scope(values)


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
    latest_balances = list_spec.endpoint == "/latestBalanceQuery.json"
    lookup = _latest_balance_scope_key(scope) if latest_balances else scope
    scoped = [
        entry
        for entry in data.captures
        if (_latest_balance_scope_key(entry.scope) if latest_balances else entry.scope)
        == lookup
    ]
    if list_spec.profile in (spec.PROFILE_SNAPSHOT, spec.PROFILE_HISTORY):
        latest = max(
            enumerate(scoped),
            key=lambda pair: (pair[1].fetched_at, pair[0]),
            default=(0, None),
        )[1]
        complete = (
            latest is not None
            and latest.evidence.scope_complete
            and latest.evidence.dataset_complete
        )
        if latest is not None and list_spec.profile == spec.PROFILE_HISTORY:
            # Retention can split the newest capture at its identity boundary.
            # Its original total remains evidence of the acquired scope;
            # merely selecting the retained suffix cannot restore coverage.
            complete = complete and latest.row_count == latest.evidence.collected_total
        return ([latest] if latest is not None else []), complete
    window_from, window_to = window
    if window_from is None or window_to is None:
        raise CliError(INVALID_ARGUMENT, "dated queries require a business window")
    covering = [
        entry
        for entry in scoped
        if entry.window_from is not None
        and entry.window_to is not None
        and (entry.requested_from or entry.window_from) <= window_to
        and (entry.requested_to or entry.window_to) >= window_from
    ]
    if list_spec.path == ("cash", "balances") and covering:
        from .cash_balances import binding_universe

        # Resolve the universe BEFORE authority, rows or coverage are combined.
        # A newer roster does not silently extend an older ALL capture.
        newest = max(
            enumerate(covering), key=lambda pair: (pair[1].fetched_at, pair[0])
        )[1]
        universe = binding_universe(newest.evidence)
        covering = [
            entry for entry in covering if binding_universe(entry.evidence) == universe
        ]
    return covering, covers_window(covering, window_from, window_to)


def authoritative_capture(entries: list[CaptureEntry], day: str) -> CaptureEntry | None:
    """Newest request owns its whole original window, including missing rows."""
    candidates = [
        (index, entry)
        for index, entry in enumerate(entries)
        if (first := entry.requested_from or entry.window_from) is not None
        and (last := entry.requested_to or entry.window_to) is not None
        and first <= day <= last
    ]
    return max(
        candidates, key=lambda pair: (pair[1].fetched_at, pair[0]), default=(0, None)
    )[1]


def coverage_segments(
    entries: list[CaptureEntry], start: str, end: str
) -> list[tuple[str, CaptureEntry | None]]:
    """Only request, trim and hole boundaries can change day-level authority."""
    boundaries = {start}
    for entry in entries:
        for first, last in (
            (
                entry.requested_from or entry.window_from,
                entry.requested_to or entry.window_to,
            ),
            (entry.window_from, entry.window_to),
        ):
            if first is not None and start < first <= end:
                boundaries.add(first)
            if last is not None and start <= last < end:
                boundaries.add(_next_day_like(last))
        for day in entry.missing_days:
            if start <= day <= end:
                boundaries.add(day)
                if day < end:
                    boundaries.add(_next_day_like(day))
    return [(day, authoritative_capture(entries, day)) for day in sorted(boundaries)]


def active_captures(
    entries: list[CaptureEntry], start: str, end: str
) -> list[CaptureEntry]:
    active = {
        entry.namespace
        for _, entry in coverage_segments(entries, start, end)
        if entry is not None
    }
    return [entry for entry in entries if entry.namespace in active]


def covers_window(
    entries: list[CaptureEntry],
    start: str,
    end: str,
    *,
    authority: list[CaptureEntry] | None = None,
) -> bool:
    """Every requested segment needs the latest request's complete evidence."""
    available = {entry.namespace for entry in entries}
    for day, entry in coverage_segments(
        authority if authority is not None else entries, start, end
    ):
        if (
            entry is None
            or entry.namespace not in available
            or not entry.evidence.scope_complete
            or not entry.evidence.dataset_complete
            or entry.window_from is None
            or entry.window_to is None
            or not entry.window_from <= day <= entry.window_to
            or day in entry.missing_days
        ):
            return False
    return True


def query_evidence(
    entries: list[CaptureEntry],
    covered: bool,
    collected_total: int,
    *,
    window: tuple[str | None, str | None] = (None, None),
) -> AcquisitionEvidence:
    """Aggregate source quality without adding totals from overlapping captures."""
    if window[0] is not None and window[1] is not None:
        # Refresh plans include overlapping historical captures. Only the
        # current owners of the requested days supply quality evidence.
        entries = active_captures(entries, window[0], window[1])
    evidence = entries[0].evidence if len(entries) == 1 else None
    # A count for a wider acquisition cannot be a count for a queried subwindow.
    exact_window = len(entries) == 1 and (
        window[0] is None
        or window
        == (
            entries[0].requested_from or entries[0].window_from,
            entries[0].requested_to or entries[0].window_to,
        )
    )
    same_collection = (
        evidence is not None
        and exact_window
        and collected_total == evidence.collected_total
    )
    reasons = tuple(
        dict.fromkeys(code for entry in entries for code in entry.evidence.reasons)
    )
    if not covered and any(
        entry.missing_days or entry.row_count < entry.evidence.collected_total
        for entry in entries
    ):
        reasons += ("RETENTION_GAP",)
    if not covered and not reasons:
        reasons = ("COVERAGE_UNPROVEN",)
    return AcquisitionEvidence(
        scope_complete=covered,
        dataset_complete=covered,
        collected_total=collected_total,
        reported_total=evidence.reported_total if evidence and exact_window else None,
        arrivals=evidence.arrivals if evidence and same_collection else None,
        unique_count=collected_total
        if evidence and evidence.unique_count is not None
        else None,
        duplicate_count=evidence.duplicate_count
        if evidence and same_collection
        else None,
        total_semantics=evidence.total_semantics if evidence else "unknown",
        reasons=tuple(dict.fromkeys(reasons)),
        attempts=evidence.attempts if evidence else (),
        requested_count=evidence.requested_count if evidence and exact_window else None,
        resolved_count=collected_total
        if evidence and exact_window and evidence.resolved_count is not None
        else None,
    )


def retained_evidence(
    plan: PublishPlan,
    list_spec: spec.ListSpec,
    scope: str,
    window: tuple[str | None, str | None],
) -> AcquisitionEvidence:
    """Quality of the requested result after the proposed retention transaction."""
    entries, covered = select_captures(plan.index, list_spec, scope, window)
    return query_evidence(entries, covered, len(plan.capture_records), window=window)


def _next_day_like(value: str) -> str:
    """Successor of a day string in lexical window terms (YYYYMMDD)."""
    try:
        parsed = datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return value + " "
    return _format_series_time(parsed + timedelta(days=1), "%Y%m%d")
