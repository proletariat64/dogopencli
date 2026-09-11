"""SQLite snapshot cache (ADR 0003, ADR 0005).

Namespaces isolate capability + scope + source_kind; each namespace holds
one current snapshot published atomically. Readers only ever see the
complete old or the complete new snapshot. No cookies or tokens are ever
stored here.
"""

import os
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .errors import LOCKED, CliError

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    namespace TEXT PRIMARY KEY,
    capability TEXT NOT NULL,
    scope TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    dataset_id TEXT,
    simulated INTEGER NOT NULL,
    backend_complete INTEGER NOT NULL,
    dataset_complete INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    loaded_at TEXT NOT NULL,
    source_observed_from TEXT,
    source_observed_to TEXT,
    row_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    namespace TEXT NOT NULL,
    seqid INTEGER NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (namespace, seqid)
);
"""


def namespace(capability: str, scope: str, source_kind: str) -> str:
    return f"{capability}:{scope}:{source_kind}"


@dataclass(frozen=True)
class SnapshotMeta:
    namespace: str
    capability: str
    scope: str
    source_kind: str
    snapshot_id: str
    dataset_id: str | None
    simulated: bool
    backend_complete: bool
    dataset_complete: bool
    fetched_at: str
    loaded_at: str
    source_observed_from: str | None
    source_observed_to: str | None
    row_count: int


def _snapshot_from_row(row: tuple) -> SnapshotMeta:
    return SnapshotMeta(
        namespace=row[0],
        capability=row[1],
        scope=row[2],
        source_kind=row[3],
        snapshot_id=row[4],
        dataset_id=row[5],
        simulated=bool(row[6]),
        backend_complete=bool(row[7]),
        dataset_complete=bool(row[8]),
        fetched_at=row[9],
        loaded_at=row[10],
        source_observed_from=row[11],
        source_observed_to=row[12],
        row_count=row[13],
    )


class Cache:
    def __init__(self, path: Path) -> None:
        self._path = path

    def _connect(self) -> sqlite3.Connection:
        parent = self._path.parent
        parent.mkdir(parents=True, exist_ok=True)
        os.chmod(parent, 0o700)
        connection = sqlite3.connect(self._path, isolation_level=None, timeout=10.0)
        os.chmod(self._path, 0o600)
        # WAL lets concurrent readers keep one consistent snapshot view
        # while a writer publishes a replacement. The mode persists in the
        # database header; a racing publish makes the pragma transiently
        # busy, and an already-initialised database stays in WAL anyway.
        try:
            mode = connection.execute("PRAGMA journal_mode").fetchone()
            if mode is None or str(mode[0]).lower() != "wal":
                connection.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        connection.executescript(SCHEMA)
        return connection

    @contextmanager
    def refresh_lock(self):
        lock_path = self._path.with_name(self._path.name + ".refresh.lock")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(self._path.parent, 0o700)
        except OSError as error:
            raise CliError(
                "IO_ERROR", "cannot create private cache directory"
            ) from error
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise CliError(
                LOCKED, "another refresh holds the cache lock", retryable=True
            ) from error
        except OSError as error:
            raise CliError(
                "IO_ERROR", "cannot create private cache refresh lock"
            ) from error
        try:
            os.close(fd)
            yield
        finally:
            lock_path.unlink(missing_ok=True)

    def current(self, namespace_name: str) -> SnapshotMeta | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT namespace, capability, scope, source_kind, snapshot_id,"
                " dataset_id, simulated, backend_complete, dataset_complete,"
                " fetched_at, loaded_at, source_observed_from,"
                " source_observed_to, row_count"
                " FROM snapshots WHERE namespace = ?",
                (namespace_name,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return _snapshot_from_row(row)

    def records(self, namespace_name: str) -> list[tuple[int, str]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT seqid, body FROM records WHERE namespace = ? ORDER BY seqid",
                (namespace_name,),
            ).fetchall()
        finally:
            connection.close()
        return [(row[0], row[1]) for row in rows]

    def read(
        self, namespace_name: str
    ) -> tuple[SnapshotMeta | None, list[tuple[int, str]]]:
        """One consistent point-in-time view: snapshot meta plus its records."""
        connection = self._connect()
        try:
            connection.execute("BEGIN DEFERRED")
            row = connection.execute(
                "SELECT namespace, capability, scope, source_kind, snapshot_id,"
                " dataset_id, simulated, backend_complete, dataset_complete,"
                " fetched_at, loaded_at, source_observed_from,"
                " source_observed_to, row_count"
                " FROM snapshots WHERE namespace = ?",
                (namespace_name,),
            ).fetchone()
            rows = connection.execute(
                "SELECT seqid, body FROM records WHERE namespace = ? ORDER BY seqid",
                (namespace_name,),
            ).fetchall()
            connection.execute("COMMIT")
        finally:
            connection.close()
        snapshot = _snapshot_from_row(row) if row is not None else None
        return snapshot, [(record[0], record[1]) for record in rows]

    def publish(self, meta: SnapshotMeta, records: Iterable[tuple[int, str]]) -> None:
        """Atomically replace the namespace snapshot; failures keep the old one."""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM records WHERE namespace = ?", (meta.namespace,)
            )
            connection.execute(
                "DELETE FROM snapshots WHERE namespace = ?", (meta.namespace,)
            )
            connection.execute(
                "INSERT INTO snapshots VALUES"
                " (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    meta.namespace,
                    meta.capability,
                    meta.scope,
                    meta.source_kind,
                    meta.snapshot_id,
                    meta.dataset_id,
                    int(meta.simulated),
                    int(meta.backend_complete),
                    int(meta.dataset_complete),
                    meta.fetched_at,
                    meta.loaded_at,
                    meta.source_observed_from,
                    meta.source_observed_to,
                    meta.row_count,
                ),
            )
            connection.executemany(
                "INSERT INTO records (namespace, seqid, body) VALUES (?, ?, ?)",
                ((meta.namespace, seqid, body) for seqid, body in records),
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
