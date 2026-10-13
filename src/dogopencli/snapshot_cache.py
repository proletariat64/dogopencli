"""Metadata-only, consistent read-only inventory of temporary cache slots."""

import hashlib
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .cache import Cache, SnapshotMeta, _snapshot_from_row
from .cached_query import is_stale
from .errors import CliError


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

    Business payloads are never decoded. Metadata and row counts share one view.
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


def capture(
    meta: SnapshotMeta, count: int, ttl: float | None, now: datetime
) -> dict[str, Any]:
    """Describe the one saved acquisition without decoding business bodies."""
    if meta.source_kind not in ("cdp", "snapshot"):
        raise ValueError("unrecognized cache source kind")
    updated = timestamp(meta.fetched_at)
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
    if meta.acquisition is not None:
        source_complete = meta.acquisition["scope_complete"]
        dataset_complete = meta.acquisition["dataset_complete"]
        reasons = reason_codes(meta.acquisition.get("reasons", []))
    complete = source_complete and dataset_complete
    if count != meta.row_count:
        complete = False
        reasons.append("STORED_ROW_COUNT_MISMATCH")
    return {
        "slot_id": opaque(meta.namespace),
        "acquisition_id": opaque(meta.namespace + "|" + meta.snapshot_id),
        "scope_id": opaque(meta.scope),
        "scope_description": "original acquisition scope (values redacted)",
        "variant": meta.source_kind,
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
        "reasons": list(dict.fromkeys(reasons)),
    }
