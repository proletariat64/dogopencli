"""Metadata-only, consistent read-only inventory of published cache captures."""

import hashlib
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .cache import Cache, SnapshotMeta, _snapshot_from_row
from .cached_query import is_stale
from .errors import CliError
from .jsonutil import parse
from .plugins.liquidity import spec as liquidity_spec
from .plugins.liquidity.store import (
    ACQUISITION_FORMAT,
    ENTRY_CAPTURE,
    ENTRY_FORMAT,
    ENTRY_RETENTION,
    CaptureEntry,
    index_namespace,
)


def opaque(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.isoformat() if parsed.tzinfo is not None else None
    except ValueError:
        return None


def date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    for pattern in ("%Y%m%d", "%Y-%m-%d"):
        try:
            if datetime.strptime(value, pattern).strftime(pattern) == value:
                return value
        except ValueError:
            pass
    return None


def reason_codes(values: Any) -> list[str]:
    return [
        v
        for v in values
        if isinstance(v, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", v)
    ]


class Inventory:
    """One connection and transaction shared by every domain adapter.

    Only internal capture indexes are decoded. SQL projections of native
    detail envelopes fetch object keys and acquisition times, never payloads.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None
        self.metadata: dict[str, SnapshotMeta | Exception] = {}

    def __enter__(self) -> "Inventory":
        if not self.path.exists():
            return self
        self.connection = Cache(self.path)._connect_readonly()
        try:
            self.connection.execute("BEGIN DEFERRED")
            columns = Cache._snapshot_columns(self.connection)
            if columns is None:
                raise ValueError("missing snapshot schema")
            for row in self.connection.execute("SELECT " + columns + " FROM snapshots"):
                try:
                    self.metadata[row[0]] = _snapshot_from_row(row)
                except (CliError, ValueError, TypeError) as error:
                    self.metadata[row[0]] = error
            return self
        except BaseException:
            self.connection.close()
            self.connection = None
            raise

    def __exit__(self, *args: Any) -> None:
        if self.connection is not None:
            self.connection.close()

    def metas(self, capability: str) -> list[SnapshotMeta]:
        values = []
        for name, meta in self.metadata.items():
            if isinstance(meta, Exception):
                # The namespace prefix is used internally, never emitted.
                if name.startswith(capability + ":"):
                    raise ValueError("invalid snapshot metadata")
            elif meta.capability == capability:
                values.append(meta)
        return values

    def count(self, name: str) -> int:
        assert self.connection is not None
        return self.connection.execute(
            "SELECT COUNT(*) FROM records WHERE namespace = ?", (name,)
        ).fetchone()[0]

    def entries(self, capability: str) -> list[CaptureEntry] | None:
        name = index_namespace(capability)
        index = self.metadata.get(name)
        if index is None:
            return None
        if isinstance(index, Exception):
            raise ValueError("invalid capture index")
        assert self.connection is not None
        entries = []
        count = 0
        for (body,) in self.connection.execute(
            "SELECT body FROM records WHERE namespace = ? ORDER BY seqid", (name,)
        ):
            count += 1
            record = parse(body)
            if not isinstance(record, dict):
                raise ValueError("invalid capture index")
            kind = record.get("type")
            if kind == ENTRY_CAPTURE:
                entries.append(CaptureEntry.from_record(record))
            elif kind == ENTRY_FORMAT:
                if record.get("version") != ACQUISITION_FORMAT:
                    raise ValueError("unsupported acquisition format")
            elif kind != ENTRY_RETENTION:
                raise ValueError("invalid capture index")
        if count != index.row_count or index.source_kind != "cdp" or index.simulated:
            raise ValueError("invalid capture index metadata")
        if len({entry.namespace for entry in entries}) != len(entries):
            raise ValueError("duplicate capture index entry")
        return entries

    def details(self, meta: SnapshotMeta) -> list[tuple[str, str | None]]:
        assert self.connection is not None
        rows = self.connection.execute(
            "SELECT json_extract(body, '$.key'), json_extract(body, '$.fetched_at'),"
            " json_type(body, '$.detail')"
            " FROM records WHERE namespace = ? ORDER BY seqid",
            (meta.namespace,),
        ).fetchall()
        if any(
            not isinstance(key, str) or payload in (None, "null")
            for key, _, payload in rows
        ):
            raise ValueError("invalid detail metadata")
        return [(key, updated) for key, updated, _ in rows]

    def detail_count(self, meta: SnapshotMeta) -> int:
        assert self.connection is not None
        return self.connection.execute(
            "SELECT COUNT(*) FROM records WHERE namespace = ?"
            " AND json_type(body, '$.detail') IS NOT NULL"
            " AND json_type(body, '$.detail') != 'null'",
            (meta.namespace,),
        ).fetchone()[0]


def capture(
    meta: SnapshotMeta,
    count: int,
    ttl: float | None,
    now: datetime,
    *,
    entry: CaptureEntry | None = None,
    key: str | None = None,
    fetched_at: str | None = None,
    detail: bool = False,
) -> dict[str, Any]:
    """Separate acquisition, retained scope and physical storage facts."""
    if meta.source_kind not in ("cdp", "snapshot"):
        raise ValueError("unrecognized cache source kind")
    updated = timestamp(meta.fetched_at if fetched_at is None else fetched_at)
    freshness = None
    if updated is not None and ttl is not None:
        from dataclasses import replace

        freshness = (
            "stale"
            if is_stale(replace(meta, fetched_at=updated), ttl, now)
            else "fresh"
        )
    source_complete = meta.backend_complete
    dataset_complete = meta.dataset_complete
    reasons: list[str] = []
    acquired = meta.row_count
    if meta.acquisition is not None:
        source_complete = meta.acquisition["scope_complete"]
        dataset_complete = meta.acquisition["dataset_complete"]
        acquired = meta.acquisition["collected_total"]
        reasons = reason_codes(meta.acquisition.get("reasons", []))
    coverage: dict[str, Any] = {}
    gaps: list[str] = []
    complete = source_complete and dataset_complete
    if entry is not None:
        evidence = entry.acquisition
        if (
            evidence is None
            and meta.acquisition is None
            and entry.reported_total is not None
        ):
            acquired = entry.reported_total
        if evidence is not None:
            source_complete = evidence.scope_complete
            dataset_complete = evidence.dataset_complete
            acquired = evidence.collected_total
            reasons = reason_codes(evidence.reasons)
        coverage = {
            "from": date(entry.window_from),
            "to": date(entry.window_to),
            "requested_from": date(entry.requested_from),
            "requested_to": date(entry.requested_to),
        }
        gaps = [day for value in entry.missing_days if (day := date(value))]
        narrowed = entry.requested_from not in (
            None,
            entry.window_from,
        ) or entry.requested_to not in (None, entry.window_to)
        trimmed = count < acquired
        complete = (
            source_complete
            and dataset_complete
            and not gaps
            and not narrowed
            and not trimmed
        )
        if gaps or narrowed or trimmed:
            reasons.append("RETENTION_GAP")
        if (
            meta.snapshot_id != entry.snapshot_id
            or meta.scope != entry.scope
            or count != entry.row_count
            or meta.source_kind != "cdp"
            or meta.simulated
            or meta.fetched_at != entry.fetched_at
            or entry.source_origin not in (None, f"https://{liquidity_spec.HOST}")
            or entry.tenant not in (None, liquidity_spec.TENANT)
            or (
                entry.acquisition is not None
                and (
                    entry.acquisition.scope_complete != meta.backend_complete
                    or entry.acquisition.dataset_complete != meta.dataset_complete
                )
            )
        ):
            raise ValueError("capture generation mismatch")
    elif not detail and count != meta.row_count:
        complete = False
        reasons.append("STORED_ROW_COUNT_MISMATCH")
    if detail:
        # A complete captured document establishes only that object's scope.
        coverage = {"unit": "native_document", "scope": "acquired objects only"}
    return {
        "capture_id": opaque(
            meta.namespace
            + "|"
            + meta.snapshot_id
            + "|"
            + (updated or "")
            + ("|" + key if key is not None else "")
        ),
        "scope_id": opaque(meta.scope if key is None else key),
        "scope_description": "acquired object"
        if detail
        else "declared retained scope (values redacted)",
        "variant": entry.profile
        if entry is not None
        else ("native_document" if detail else meta.source_kind),
        "rows": count,
        "updated": updated,
        "source_observed_from": date(meta.source_observed_from)
        or timestamp(meta.source_observed_from),
        "source_observed_to": date(meta.source_observed_to)
        or timestamp(meta.source_observed_to),
        "source_complete": source_complete,
        "dataset_complete": dataset_complete,
        "complete": complete,
        "freshness": freshness,
        "retained_coverage": coverage,
        "gaps": gaps,
        "reasons": list(dict.fromkeys(reasons)),
    }
