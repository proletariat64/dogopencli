"""Transactional durable sync state, separate from temporary acquisition caches.

The installed registry owns public ``_record`` tables. This module owns a distinct
metadata schema and never adopts external relations. Acquisition callers must
supply complete authoritative evidence; records and coverage commit together.
"""

from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb

from .errors import INCOMPLETE_RESULT, INVALID_RESPONSE, LOCKED, CliError
from .jsonutil import canonical, parse

_SCHEMA = "_dogopencli_sync"
_EMPTY = {"targets": [], "coverage": [], "attempts": []}


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _error(message: str) -> CliError:
    return CliError("DATASET_ERROR", message)


class SyncStore:
    """One writer, atomic publication, and explicit read-only inspection."""

    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        self.db = None
        self._lock = None
        self._verified_relations = set()

    def __enter__(self):
        import fcntl

        if not self.path.is_file():
            raise _error("Registered Duckdog database is missing")
        self._lock = self.path.with_suffix(self.path.suffix + ".sync.lock").open("a+")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._lock.close()
            self._lock = None
            raise CliError(
                LOCKED, "Another sync writer is active", retryable=True
            ) from error
        try:
            self.db = duckdb.connect(str(self.path))
            self._initialize()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        if self.db is not None:
            self.db.close()
            self.db = None
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    @contextmanager
    def acquisition(self):
        """Keep writer ownership while permitting existing read-only selectors."""
        self.db.close()
        self.db = None
        try:
            yield
        finally:
            self.db = duckdb.connect(str(self.path))

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN TRANSACTION")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException as error:
            self.db.execute("ROLLBACK")
            if isinstance(error, duckdb.Error):
                raise _error(
                    "Duckdog sync transaction failed; prior data preserved"
                ) from error
            raise

    def _initialize(self):
        with self._transaction():
            exists = self.db.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name=?",
                [_SCHEMA],
            ).fetchone()
            if exists:
                try:
                    version = self.db.execute(
                        f"SELECT version FROM {_SCHEMA}.owner"
                    ).fetchall()
                except duckdb.Error as error:
                    raise _error("Refusing to adopt an unowned sync schema") from error
                if version != [(1,)]:
                    raise _error("Unsupported sync storage version")
                self.db.execute(
                    f"UPDATE {_SCHEMA}.attempts SET state='interrupted', diagnostic=? "
                    "WHERE state='running'",
                    [
                        canonical(
                            {
                                "code": "INTERRUPTED",
                                "message": "Previous writer ended before completion",
                                "retryable": True,
                            }
                        )
                    ],
                )
                return
            self.db.execute(f"CREATE SCHEMA {_SCHEMA}")
            self.db.execute(f"CREATE TABLE {_SCHEMA}.owner (version INTEGER)")
            self.db.execute(f"INSERT INTO {_SCHEMA}.owner VALUES (1)")
            self.db.execute(
                f"CREATE TABLE {_SCHEMA}.targets "
                "(id VARCHAR PRIMARY KEY, identity VARCHAR UNIQUE, document VARCHAR)"
            )
            self.db.execute(
                f"CREATE TABLE {_SCHEMA}.attempts "
                "(id VARCHAR PRIMARY KEY, target_id VARCHAR, chunk VARCHAR, "
                "started_at VARCHAR, finished_at VARCHAR, state VARCHAR, "
                "diagnostic VARCHAR)"
            )
            self.db.execute(
                f"CREATE TABLE {_SCHEMA}.coverage "
                "(target_id VARCHAR, chunk VARCHAR, acquired_at VARCHAR, "
                "state VARCHAR, row_count BIGINT, evidence VARCHAR, attempt_id "
                "VARCHAR, "
                "PRIMARY KEY(target_id, chunk))"
            )
            self.db.execute(
                f"CREATE TABLE {_SCHEMA}.records "
                "(namespace VARCHAR, key VARCHAR, relation VARCHAR, record VARCHAR, "
                "version VARCHAR, acquired_at VARCHAR, "
                "PRIMARY KEY(namespace, key))"
            )
            self.db.execute(
                f"CREATE TABLE {_SCHEMA}.observations "
                "(namespace VARCHAR, generation VARCHAR, key VARCHAR, record VARCHAR, "
                "acquired_at VARCHAR, PRIMARY KEY(namespace, generation, key))"
            )

    def _binding(self, target):
        relation, leaf_id = target.get("relation"), target.get("leaf_id")
        if (
            not isinstance(relation, str)
            or not relation
            or not isinstance(leaf_id, str)
        ):
            raise _error("Sync target requires an installed leaf relation")
        try:
            owner = self.db.execute(
                "SELECT leaf_id FROM _dogopencli_leaf_ownership WHERE relation_name=?",
                [relation.lower()],
            ).fetchone()
            kind = self.db.execute(
                "SELECT table_type FROM information_schema.tables "
                "WHERE table_schema='main' AND lower(table_name)=lower(?)",
                [relation],
            ).fetchone()
            columns = self.db.execute(
                f"PRAGMA table_info({_quote(relation)})"
            ).fetchall()
        except duckdb.Error as error:
            raise _error("Registered Duckdog ownership/table is missing") from error
        if owner != (leaf_id,) or kind != ("BASE TABLE",):
            raise _error("Refusing to publish to an unowned Duckdog relation")
        if [(row[1], row[2]) for row in columns] != [("_record", "VARCHAR")]:
            raise _error("Registered Duckdog table has incompatible columns")
        return relation

    @staticmethod
    def _namespace(target):
        return canonical(
            {
                "leaf_id": target["leaf_id"],
                "variant": target.get("variant", "default"),
                "scope": target.get("namespace", {}),
            }
        )

    def save_target(self, target: dict) -> dict:
        self._binding(target)
        document = dict(target)
        identity = canonical(
            document.get("identity", {k: v for k, v in document.items() if k != "id"})
        )
        previous = self.db.execute(
            f"SELECT id FROM {_SCHEMA}.targets WHERE identity=?", [identity]
        ).fetchone()
        document["id"] = document.get("id") or (
            previous[0] if previous else str(uuid4())
        )
        with self._transaction():
            self.db.execute(
                f"INSERT INTO {_SCHEMA}.targets VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET identity=excluded.identity, "
                "document=excluded.document",
                [document["id"], identity, canonical(document)],
            )
        return document

    def targets(self) -> list[dict]:
        return [
            parse(row[0])
            for row in self.db.execute(
                f"SELECT document FROM {_SCHEMA}.targets ORDER BY id"
            ).fetchall()
        ]

    def _target(self, target_id):
        row = self.db.execute(
            f"SELECT document FROM {_SCHEMA}.targets WHERE id=?", [target_id]
        ).fetchone()
        if row is None:
            raise _error("Unknown sync target")
        return parse(row[0])

    def start_attempt(self, target_id: str, chunk: dict, *, started_at: str) -> str:
        self._target(target_id)
        attempt = str(uuid4())
        self.db.execute(
            f"INSERT INTO {_SCHEMA}.attempts VALUES (?, ?, ?, ?, NULL, "
            f"'running', NULL)",
            [attempt, target_id, canonical(chunk), started_at],
        )
        return attempt

    def fail_attempt(
        self, attempt_id: str, diagnostic: dict, *, finished_at: str
    ) -> None:
        self.db.execute(
            f"UPDATE {_SCHEMA}.attempts SET state='failed', finished_at=?, "
            f"diagnostic=? "
            "WHERE id=? AND state='running'",
            [finished_at, canonical(diagnostic), attempt_id],
        )

    def coverage(self, target_id: str) -> list[dict]:
        return self._coverage(self.db, target_id)

    @staticmethod
    def _coverage(db, target_id=None):
        where = " WHERE target_id=?" if target_id else ""
        rows = db.execute(
            f"SELECT target_id, chunk, acquired_at, state, row_count, evidence, "
            f"attempt_id "
            f"FROM {_SCHEMA}.coverage{where} ORDER BY target_id, chunk",
            [target_id] if target_id else [],
        ).fetchall()
        return [
            {
                "target_id": r[0],
                "chunk": parse(r[1]),
                "acquired_at": r[2],
                "state": r[3],
                "row_count": r[4],
                "evidence": parse(r[5]),
                "attempt_id": r[6],
            }
            for r in rows
        ]

    def records(self, target_id: str, *, observations: bool = False) -> list[dict]:
        namespace = self._namespace(self._target(target_id))
        table = "observations" if observations else "records"
        return [
            parse(r[0])
            for r in self.db.execute(
                f"SELECT record FROM {_SCHEMA}.{table} WHERE namespace=? ORDER BY key",
                [namespace],
            ).fetchall()
        ]

    def publish(
        self,
        attempt_id: str,
        rows: Iterable[dict],
        *,
        key_fields: tuple[str, ...],
        mode: str,
        evidence: dict,
        acquired_at: str,
        version_field: str | None = None,
        version_kind: str = "number",
        allow_empty_key_components: bool = False,
    ) -> dict:
        if (
            evidence.get("complete") is not True
            or evidence.get("authoritative") is not True
        ):
            raise CliError(
                INCOMPLETE_RESULT,
                "Durable publication requires complete authoritative evidence",
            )
        if mode not in {"settings", "runtime", "observation"} or not key_fields:
            raise _error("Invalid sync publication policy")
        attempt = self.db.execute(
            f"SELECT target_id, chunk, state FROM {_SCHEMA}.attempts WHERE id=?",
            [attempt_id],
        ).fetchone()
        if attempt is None or attempt[2] != "running":
            raise _error("Sync publication requires a running attempt")
        target = self._target(attempt[0])
        relation = self._binding(target)
        namespace = self._namespace(target)
        with self._transaction():
            if relation not in self._verified_relations:
                mismatch = self.db.execute(
                    f"SELECT 1 FROM (SELECT _record FROM {_quote(relation)} EXCEPT ALL "
                    f"SELECT record FROM {_SCHEMA}.records WHERE relation=?) LIMIT 1",
                    [relation],
                ).fetchone()
                missing = self.db.execute(
                    f"SELECT 1 FROM (SELECT record FROM {_SCHEMA}.records WHERE "
                    f"relation=? EXCEPT ALL "
                    f"SELECT _record FROM {_quote(relation)}) LIMIT 1",
                    [relation],
                ).fetchone()
                if mismatch or missing:
                    raise _error(
                        "Refusing to adopt or overwrite existing records "
                        "outside sync ownership"
                    )
                self._verified_relations.add(relation)
            self.db.execute(
                "CREATE OR REPLACE TEMP TABLE sync_stage "
                "(key VARCHAR, record VARCHAR, version VARCHAR)"
            )
            batch = []
            count = 0
            for row in rows:
                if not isinstance(row, dict) or any(
                    k not in row
                    or (not allow_empty_key_components and row[k] in (None, ""))
                    for k in key_fields
                ):
                    raise CliError(
                        INVALID_RESPONSE, "Sync row has missing native identity"
                    )
                version = (
                    self._version(row.get(version_field), version_kind)
                    if version_field
                    else None
                )
                batch.append(
                    (canonical([row[k] for k in key_fields]), canonical(row), version)
                )
                count += 1
                if len(batch) == 1000:
                    self._stage(batch)
                    batch = []
            if batch:
                self._stage(batch)
            conflict = self.db.execute(
                "SELECT 1 FROM sync_stage GROUP BY key "
                "HAVING count(DISTINCT record)>1 LIMIT 1"
            ).fetchone()
            if conflict:
                raise CliError(
                    INVALID_RESPONSE,
                    "Conflicting native identities in sync acquisition",
                )
            self.db.execute(
                "CREATE OR REPLACE TEMP TABLE sync_values AS SELECT DISTINCT * "
                "FROM sync_stage"
            )
            if mode == "observation":
                self.db.execute(
                    f"INSERT INTO {_SCHEMA}.observations SELECT ?, ?, key, "
                    f"record, ? FROM sync_values",
                    [namespace, attempt_id, acquired_at],
                )
            older = unchanged = updated = 0
            existing = self.db.execute(
                f"SELECT count(*) FROM sync_values v JOIN {_SCHEMA}.records r "
                f"ON v.key=r.key WHERE r.namespace=?",
                [namespace],
            ).fetchone()[0]
            inserted = (
                self.db.execute("SELECT count(*) FROM sync_values").fetchone()[0]
                - existing
            )
            if mode == "runtime":
                unchanged = self.db.execute(
                    f"SELECT count(*) FROM sync_values v JOIN {_SCHEMA}.records "
                    f"r ON v.key=r.key "
                    "WHERE r.namespace=? AND v.record=r.record",
                    [namespace],
                ).fetchone()[0]
                if version_field:
                    invalid = self.db.execute(
                        f"SELECT 1 FROM sync_values v JOIN {_SCHEMA}.records r "
                        f"ON v.key=r.key "
                        "WHERE r.namespace=? AND r.version IS NULL LIMIT 1",
                        [namespace],
                    ).fetchone()
                    if invalid:
                        raise _error(
                            "Source version policy changed; requalify the stored target"
                        )
                    conflict = self.db.execute(
                        f"SELECT 1 FROM sync_values v JOIN {_SCHEMA}.records r "
                        f"ON v.key=r.key "
                        "WHERE r.namespace=? AND CAST(v.version AS "
                        "DECIMAL(38,9))=CAST(r.version AS DECIMAL(38,9)) "
                        "AND v.record<>r.record LIMIT 1",
                        [namespace],
                    ).fetchone()
                    if conflict:
                        raise CliError(
                            INVALID_RESPONSE,
                            "Equal source versions have conflicting records",
                        )
                    older = self.db.execute(
                        f"SELECT count(*) FROM sync_values v JOIN "
                        f"{_SCHEMA}.records r ON v.key=r.key "
                        "WHERE r.namespace=? AND CAST(v.version AS "
                        "DECIMAL(38,9))<CAST(r.version AS DECIMAL(38,9))",
                        [namespace],
                    ).fetchone()[0]
                    self.db.execute(
                        f"DELETE FROM sync_values v USING {_SCHEMA}.records r "
                        f"WHERE v.key=r.key AND r.namespace=? "
                        "AND CAST(v.version AS DECIMAL(38,9))<CAST(r.version "
                        "AS DECIMAL(38,9))",
                        [namespace],
                    )
                self.db.execute(
                    f"DELETE FROM sync_values v USING {_SCHEMA}.records r WHERE "
                    f"v.key=r.key AND r.namespace=? "
                    "AND v.record=r.record",
                    [namespace],
                )
                updated = existing - unchanged - older
            affected = (
                " AND key IN (SELECT key FROM sync_values)" if mode == "runtime" else ""
            )
            self.db.execute(
                "CREATE OR REPLACE TEMP TABLE sync_affected AS "
                f"SELECT record FROM {_SCHEMA}.records WHERE namespace=?{affected} "
                "UNION SELECT record FROM sync_values",
                [namespace],
            )
            self.db.execute(
                f"DELETE FROM {_SCHEMA}.records WHERE namespace=?{affected}",
                [namespace],
            )
            self.db.execute(
                f"INSERT INTO {_SCHEMA}.records "
                "SELECT ?, key, ?, record, version, ? FROM sync_values",
                [namespace, relation, acquired_at],
            )
            self.db.execute(
                f"DELETE FROM {_quote(relation)} WHERE _record IN (SELECT "
                f"record FROM sync_affected)"
            )
            self.db.execute(
                f"INSERT INTO {_quote(relation)} SELECT record FROM {_SCHEMA}.records "
                "WHERE relation=? AND record IN (SELECT record FROM sync_affected)",
                [relation],
            )
            stored = self.db.execute(
                f"SELECT count(*) FROM {_SCHEMA}.records WHERE namespace=?", [namespace]
            ).fetchone()[0]
            self.db.execute(
                f"INSERT INTO {_SCHEMA}.coverage VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(target_id, chunk) DO UPDATE SET "
                "acquired_at=excluded.acquired_at, "
                "state=excluded.state, row_count=excluded.row_count, "
                "evidence=excluded.evidence, "
                "attempt_id=excluded.attempt_id",
                [
                    attempt[0],
                    attempt[1],
                    acquired_at,
                    "complete_nonempty" if count else "complete_empty",
                    count,
                    canonical(evidence),
                    attempt_id,
                ],
            )
            self.db.execute(
                f"UPDATE {_SCHEMA}.attempts SET state='complete', finished_at=? "
                f"WHERE id=?",
                [acquired_at, attempt_id],
            )
        return {
            "target_id": attempt[0],
            "attempt_id": attempt_id,
            "acquired": count,
            "stored": stored,
            "inserted": inserted,
            "updated": updated,
            "unchanged": unchanged,
            "older": older,
        }

    @staticmethod
    def _version(value, kind):
        try:
            if kind == "datetime":
                if not isinstance(value, str):
                    raise ValueError
                moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if moment.tzinfo is None:
                    raise ValueError
                delta = moment.astimezone(timezone.utc) - datetime(
                    1970, 1, 1, tzinfo=timezone.utc
                )
                value = (
                    delta.days * 86400000000
                    + delta.seconds * 1000000
                    + delta.microseconds
                )
            elif kind != "number":
                raise ValueError
            if isinstance(value, bool) or value is None:
                raise ValueError
            number = Decimal(str(value))
            if (
                not number.is_finite()
                or abs(number) >= Decimal("1e29")
                or number.as_tuple().exponent < -9
            ):
                raise ValueError
            return str(number)
        except (ValueError, TypeError, InvalidOperation) as error:
            raise CliError(
                INVALID_RESPONSE, "Invalid qualified source version"
            ) from error

    def _stage(self, batch):
        self.db.execute(
            "INSERT INTO sync_stage SELECT unnest(?), unnest(?), unnest(?)",
            [[row[i] for row in batch] for i in range(3)],
        )

    @staticmethod
    def status(path: Path) -> dict[str, Any]:
        path = Path(path)
        if not path.is_file():
            return {key: list(value) for key, value in _EMPTY.items()}
        try:
            with duckdb.connect(str(path), read_only=True) as db:
                exists = db.execute(
                    "SELECT 1 FROM information_schema.schemata WHERE schema_name=?",
                    [_SCHEMA],
                ).fetchone()
                if not exists:
                    return {key: list(value) for key, value in _EMPTY.items()}
                targets = [
                    parse(row[0])
                    for row in db.execute(
                        f"SELECT document FROM {_SCHEMA}.targets ORDER BY id"
                    ).fetchall()
                ]
                attempts = [
                    {
                        "id": r[0],
                        "target_id": r[1],
                        "chunk": parse(r[2]),
                        "started_at": r[3],
                        "finished_at": r[4],
                        "state": r[5],
                        "diagnostic": parse(r[6]) if r[6] else None,
                    }
                    for r in db.execute(
                        f"SELECT * FROM {_SCHEMA}.attempts ORDER BY rowid"
                    ).fetchall()
                ]
                coverage = SyncStore._coverage(db)
                for target in targets:
                    target["row_count"] = db.execute(
                        f"SELECT count(*) FROM {_SCHEMA}.records WHERE namespace=?",
                        [SyncStore._namespace(target)],
                    ).fetchone()[0]
                    previous = [a for a in attempts if a["target_id"] == target["id"]]
                    target["last_attempt"] = previous[-1] if previous else None
                    complete = [a for a in previous if a["state"] == "complete"]
                    target["last_success"] = complete[-1] if complete else None
                return {"targets": targets, "coverage": coverage, "attempts": attempts}
        except duckdb.Error as error:
            raise _error("Cannot inspect Duckdog sync state") from error
