"""Registered Duckdog observations and transactional replay receipts.

The registered _record table remains the current view. Observation rows live in
host tables, keyed by export occurrence and ordinal, without business deduplication.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .errors import CliError
from .jsonutil import canonical, parse
from .leaves.lifecycle import lifecycle_lock
from .leaves.registry import Registry


@contextmanager
def connection(binding: dict, *, write: bool = False) -> Iterator[Any]:
    import duckdb

    location = Path(binding["database"])
    if not location.is_file():
        raise CliError("WORKFLOW_ERROR", "Registered Duckdog database is missing")
    try:
        with duckdb.connect(str(location), read_only=not write) as db:
            owner = db.execute(
                "SELECT leaf_id FROM _dogopencli_leaf_ownership WHERE relation_name=?",
                [binding["relation"]],
            ).fetchone()
            relation = binding["relation"].replace('"', '""')
            columns = db.execute(f'PRAGMA table_info("{relation}")').fetchall()
            table = db.execute(
                "SELECT table_type FROM information_schema.tables WHERE "
                "table_schema='main' AND lower(table_name)=?",
                [binding["relation"]],
            ).fetchone()
            if (
                owner != (binding["leaf"],)
                or table != ("BASE TABLE",)
                or [(r[1], r[2]) for r in columns] != [("_record", "VARCHAR")]
            ):
                raise CliError(
                    "WORKFLOW_ERROR",
                    "Registered destination ownership or schema conflicts",
                )
            yield db
    except duckdb.Error as error:
        raise CliError(
            "WORKFLOW_ERROR",
            "Cannot access registered Duckdog observations; check ownership, "
            "schema and writer availability",
        ) from error


def exists(db: Any) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='main'"
            " AND table_name='_dogopencli_observations'"
        ).fetchone()
    )


def receipts(binding: dict) -> list[dict]:
    with connection(binding) as db:
        if not exists(db):
            return []
        return [
            parse(row[0])
            for row in db.execute(
                "SELECT receipt FROM _dogopencli_observations WHERE leaf_id=? AND "
                "relation_name=? ORDER BY committed_at, export_id",
                [binding["leaf"], binding["relation"]],
            ).fetchall()
        ]


def read(binding: dict, export_id: str) -> dict:
    with connection(binding) as db:
        if not exists(db):
            raise CliError("WORKFLOW_ERROR", "Observation has not been imported")
        batch = db.execute(
            "SELECT artifact, receipt FROM _dogopencli_observations WHERE "
            "export_id=? AND leaf_id=? AND relation_name=?",
            [export_id, binding["leaf"], binding["relation"]],
        ).fetchone()
        if batch is None:
            raise CliError("WORKFLOW_ERROR", "Observation has not been imported")
        artifact, receipt = map(parse, batch)
        rows = [
            parse(row[0])
            for row in db.execute(
                "SELECT _record FROM _dogopencli_observation_rows WHERE "
                "export_id=? ORDER BY ordinal",
                [export_id],
            ).fetchall()
        ]
        if (
            canonical(rows) != canonical(artifact["records"])
            or len(rows) != receipt["record_count"]
        ):
            raise CliError("WORKFLOW_ERROR", "Stored observation is inconsistent")
        return {
            "export_id": export_id,
            "leaf": binding["leaf"],
            "scope": artifact["metadata"]["scope"],
            "records": rows,
            "receipt": receipt,
        }


def apply(config_file: Path, plan: dict, artifact: dict, committed_at: str) -> dict:
    binding = plan["binding"]
    with lifecycle_lock(Registry(config_file)):
        with connection(binding, write=True) as db:
            db.execute("BEGIN TRANSACTION")
            db.execute(
                "CREATE TABLE IF NOT EXISTS _dogopencli_observations (export_id "
                "VARCHAR PRIMARY KEY, leaf_id VARCHAR NOT NULL, relation_name "
                "VARCHAR NOT NULL, action VARCHAR NOT NULL, committed_at VARCHAR "
                "NOT NULL, artifact VARCHAR NOT NULL, receipt VARCHAR NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS _dogopencli_observation_rows "
                "(export_id VARCHAR NOT NULL, ordinal BIGINT NOT NULL, _record "
                "VARCHAR NOT NULL, PRIMARY KEY(export_id, ordinal))"
            )
            previous = db.execute(
                "SELECT artifact, receipt FROM _dogopencli_observations WHERE "
                "export_id=?",
                [artifact["id"]],
            ).fetchone()
            if previous:
                if canonical(parse(previous[0])) != canonical(artifact):
                    raise CliError(
                        "WORKFLOW_ERROR",
                        "Exact export differs from committed observation",
                    )
                db.execute("ROLLBACK")
                return {**parse(previous[1]), "replayed": True, "inserted_count": 0}
            receipt = {
                "export_id": artifact["id"],
                "plan_id": plan["id"],
                "action": "preserve",
                "binding": binding,
                "record_count": artifact["record_count"],
                "committed_at": committed_at,
                "current_effect": "unchanged",
                "scope": artifact["metadata"]["scope"],
                "environment": artifact["environment"],
            }
            db.execute(
                "INSERT INTO _dogopencli_observations VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    artifact["id"],
                    binding["leaf"],
                    binding["relation"],
                    "preserve",
                    committed_at,
                    canonical(artifact),
                    canonical(receipt),
                ],
            )
            if artifact["records"]:
                db.executemany(
                    "INSERT INTO _dogopencli_observation_rows VALUES (?, ?, ?)",
                    [
                        (artifact["id"], i, canonical(row))
                        for i, row in enumerate(artifact["records"])
                    ],
                )
            db.execute("COMMIT")
            return {
                **receipt,
                "replayed": False,
                "inserted_count": artifact["record_count"],
            }


def current_count(binding: dict) -> int:
    with connection(binding) as db:
        relation = binding["relation"].replace('"', '""')
        return db.execute(f'SELECT count(*) FROM "{relation}"').fetchone()[0]
