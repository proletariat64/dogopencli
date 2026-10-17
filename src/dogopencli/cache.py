"""SQLite snapshot cache (ADR 0003, ADR 0005).

Each installed leaf owns one namespace; each namespace holds
one current snapshot published atomically. Readers only ever see the
complete old or the complete new snapshot. No cookies or tokens are ever
stored here.
"""

import fcntl
import os
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from time import monotonic, sleep
from typing import Any

from .errors import INVALID_RESPONSE, LOCKED, CliError
from .jsonutil import canonical, parse
from .result_policy import AcquisitionEvidence

# SQLite lock messages matched when sqlite_errorcode is unavailable.
_SQLITE_LOCKED_MESSAGES = ("database is locked", "database table is locked")

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
    row_count INTEGER NOT NULL,
    source_path TEXT,
    acquisition TEXT
);
CREATE TABLE IF NOT EXISTS records (
    namespace TEXT NOT NULL,
    seqid INTEGER NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (namespace, seqid)
);
"""


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
    source_path: str | None = None
    acquisition: dict[str, Any] | None = None


def _snapshot_from_row(row: tuple) -> SnapshotMeta:
    acquisition = None
    if row[15] is not None:
        try:
            document = parse(row[15])
        except ValueError as error:
            raise CliError(
                INVALID_RESPONSE, "cached acquisition metadata is not valid JSON"
            ) from error
        acquisition = AcquisitionEvidence.from_record(document).record()
    snapshot = SnapshotMeta(
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
        source_path=row[14],
        acquisition=acquisition,
    )
    if snapshot.acquisition is not None:
        evidence = AcquisitionEvidence.from_record(snapshot.acquisition)
        if (
            evidence.scope_complete != snapshot.backend_complete
            or evidence.dataset_complete != snapshot.dataset_complete
            or evidence.collected_total < snapshot.row_count
        ):
            raise CliError(INVALID_RESPONSE, "cached acquisition metadata conflicts")
    return snapshot


def _sqlite_errors(method):
    @wraps(method)
    def call(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except sqlite3.Error as error:
            code = getattr(error, "sqlite_errorcode", 0) & 0xFF
            locked = code in (
                getattr(sqlite3, "SQLITE_BUSY", 5),
                getattr(sqlite3, "SQLITE_LOCKED", 6),
            )
            # Python 3.10 does not expose sqlite_errorcode.
            locked = locked or str(error) in _SQLITE_LOCKED_MESSAGES
            raise CliError(
                LOCKED if locked else "CACHE_ERROR",
                "cache is busy; retry later"
                if locked
                else "cache database operation failed",
                retryable=locked,
            ) from error

    return call


class Cache:
    def __init__(self, path: Path) -> None:
        self._path = path

    def _connect_readonly(self) -> sqlite3.Connection:
        return sqlite3.connect(
            self._path.resolve().as_uri() + "?mode=ro",
            uri=True,
            isolation_level=None,
            timeout=10.0,
        )

    @staticmethod
    def _snapshot_columns(connection: sqlite3.Connection) -> str | None:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(snapshots)")}
        if not columns:
            return None
        optional = ", ".join(
            name if name in columns else f"NULL AS {name}"
            for name in ("source_path", "acquisition")
        )
        return (
            "namespace, capability, scope, source_kind, snapshot_id,"
            " dataset_id, simulated, backend_complete, dataset_complete,"
            " fetched_at, loaded_at, source_observed_from,"
            " source_observed_to, row_count, " + optional
        )

    def _connect(self) -> sqlite3.Connection:
        parent = self._path.parent
        parent.mkdir(parents=True, exist_ok=True)
        os.chmod(parent, 0o700)
        connection = sqlite3.connect(self._path, isolation_level=None, timeout=10.0)
        os.chmod(self._path, 0o600)
        try:
            mode = connection.execute("PRAGMA journal_mode").fetchone()
            if mode is None or str(mode[0]).lower() != "wal":
                # Concurrent first connections can make the WAL transition return
                # SQLITE_BUSY without invoking SQLite's busy timeout. Retry only
                # this initialization step, with the same ten-second bound.
                deadline = monotonic() + 10.0
                timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
                connection.execute("PRAGMA busy_timeout=0")
                try:
                    while True:
                        try:
                            mode = connection.execute(
                                "PRAGMA journal_mode=WAL"
                            ).fetchone()
                            break
                        except sqlite3.OperationalError as error:
                            code = getattr(error, "sqlite_errorcode", 0) & 0xFF
                            busy = code == getattr(sqlite3, "SQLITE_BUSY", 5) or (
                                code == 0 and str(error) in _SQLITE_LOCKED_MESSAGES
                            )
                            remaining = deadline - monotonic()
                            if not busy or remaining <= 0:
                                raise
                            sleep(min(0.01, remaining))
                finally:
                    connection.execute(f"PRAGMA busy_timeout={timeout}")
                if mode is None or str(mode[0]).lower() != "wal":
                    raise CliError("CACHE_ERROR", "cache requires WAL journal mode")
            connection.executescript(SCHEMA)
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(snapshots)")
            }
            if not {"source_path", "acquisition"} <= columns:
                # Another connection may have migrated since our first check.
                connection.execute("BEGIN IMMEDIATE")
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(snapshots)")
                }
                if "source_path" not in columns:
                    connection.execute(
                        "ALTER TABLE snapshots ADD COLUMN source_path TEXT"
                    )
                if "acquisition" not in columns:
                    connection.execute(
                        "ALTER TABLE snapshots ADD COLUMN acquisition TEXT"
                    )
                connection.execute("COMMIT")
            return connection
        except BaseException:
            connection.close()
            raise

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
        fd = None
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            if fd is not None:
                os.close(fd)
            raise CliError(
                LOCKED, "another refresh holds the cache lock", retryable=True
            ) from error
        except OSError as error:
            if fd is not None:
                os.close(fd)
            raise CliError("IO_ERROR", "cannot acquire cache refresh lock") from error
        try:
            yield
        finally:
            # Keep the inode: unlinking a flock file permits concurrent owners.
            os.close(fd)

    @_sqlite_errors
    def remove(self, namespace_name: str) -> bool:
        if not self._path.exists():
            return False
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            removed = (
                connection.execute(
                    "DELETE FROM snapshots WHERE namespace = ?", (namespace_name,)
                ).rowcount
                > 0
            )
            connection.execute(
                "DELETE FROM records WHERE namespace = ?", (namespace_name,)
            )
            connection.execute("COMMIT")
            return removed
        finally:
            connection.close()

    @_sqlite_errors
    def current(self, namespace_name: str) -> SnapshotMeta | None:
        if not self._path.exists():
            return None
        connection = self._connect_readonly()
        try:
            columns = self._snapshot_columns(connection)
            if columns is None:
                return None
            row = connection.execute(
                "SELECT " + columns + " FROM snapshots WHERE namespace = ?",
                (namespace_name,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return _snapshot_from_row(row)

    @_sqlite_errors
    def records(self, namespace_name: str) -> list[tuple[int, str]]:
        if not self._path.exists():
            return []
        connection = self._connect_readonly()
        try:
            rows = connection.execute(
                "SELECT seqid, body FROM records WHERE namespace = ? ORDER BY seqid",
                (namespace_name,),
            ).fetchall()
        finally:
            connection.close()
        return [(row[0], row[1]) for row in rows]

    @_sqlite_errors
    def read(
        self, namespace_name: str
    ) -> tuple[SnapshotMeta | None, list[tuple[int, str]]]:
        """One consistent point-in-time view: snapshot meta plus its records."""
        if not self._path.exists():
            return None, []
        connection = self._connect_readonly()
        try:
            connection.execute("BEGIN DEFERRED")
            columns = self._snapshot_columns(connection)
            if columns is None:
                return None, []
            row = connection.execute(
                "SELECT " + columns + " FROM snapshots WHERE namespace = ?",
                (namespace_name,),
            ).fetchone()
            records_exist = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'records'"
            ).fetchone()
            if records_exist is None and row is None:
                return None, []
            rows = connection.execute(
                "SELECT seqid, body FROM records WHERE namespace = ? ORDER BY seqid",
                (namespace_name,),
            ).fetchall()
            connection.execute("COMMIT")
        finally:
            connection.close()
        snapshot = _snapshot_from_row(row) if row is not None else None
        return snapshot, [(record[0], record[1]) for record in rows]

    @_sqlite_errors
    def publish(self, meta: SnapshotMeta, records: Iterable[tuple[int, str]]) -> None:
        """Atomically replace the namespace snapshot; failures keep the old one."""
        self.publish_many(((meta, records),))

    @_sqlite_errors
    def publish_many(
        self,
        writes: Iterable[tuple[SnapshotMeta, Iterable[tuple[int, str]]]],
        deletes: Iterable[str] = (),
    ) -> None:
        """Atomically replace several namespaces and drop others.

        Liquidity list/detail acquisition publishes a capture, its leaf
        index and any retention eviction as one transaction (ADR 0016/0017):
        readers only ever see the complete old or the complete new state.
        """
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for name in deletes:
                connection.execute("DELETE FROM records WHERE namespace = ?", (name,))
                connection.execute("DELETE FROM snapshots WHERE namespace = ?", (name,))
            for meta, records in writes:
                if meta.namespace.startswith("temporary-query:"):
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS cache_format "
                        "(version INTEGER NOT NULL)"
                    )
                    connection.execute(
                        "INSERT INTO cache_format SELECT 157 "
                        "WHERE NOT EXISTS (SELECT 1 FROM cache_format)"
                    )
                if meta.acquisition is not None:
                    evidence = AcquisitionEvidence.from_record(meta.acquisition)
                    if (
                        evidence.scope_complete != meta.backend_complete
                        or evidence.dataset_complete != meta.dataset_complete
                        or evidence.collected_total < meta.row_count
                    ):
                        raise CliError(
                            "INVALID_RESPONSE", "acquisition metadata conflicts"
                        )
                connection.execute(
                    "DELETE FROM records WHERE namespace = ?", (meta.namespace,)
                )
                connection.execute(
                    "DELETE FROM snapshots WHERE namespace = ?", (meta.namespace,)
                )
                connection.execute(
                    "INSERT INTO snapshots (namespace, capability, scope,"
                    " source_kind, snapshot_id, dataset_id, simulated,"
                    " backend_complete, dataset_complete, fetched_at, loaded_at,"
                    " source_observed_from, source_observed_to, row_count,"
                    " source_path, acquisition) VALUES"
                    " (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                        meta.source_path,
                        canonical(meta.acquisition)
                        if meta.acquisition is not None
                        else None,
                    ),
                )
                connection.executemany(
                    "INSERT INTO records (namespace, seqid, body) VALUES (?, ?, ?)",
                    ((meta.namespace, seqid, body) for seqid, body in records),
                )
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
