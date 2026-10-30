"""Registered Duckdog observations and transactional replay receipts.

The registered _record table remains the current view. Observation rows live in
host tables, keyed by export occurrence and ordinal, without business deduplication.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
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
            len(rows) != artifact["record_count"]
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


def header(artifact: dict) -> dict:
    """The metadata committed with canonical ordinal rows; no second row blob."""
    return {key: value for key, value in artifact.items() if key != "records"}


def metadata_match(saved: str, artifact: dict) -> bool:
    # stage_rows separately compared every retained row to this exact input.
    return canonical(parse(saved)) == canonical(header(artifact))


def exact_match(left: dict, right: dict) -> bool:
    """Compare frozen values without constructing two whole-corpus strings."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    left_rows, right_rows = left.get("records"), right.get("records")
    return (
        isinstance(left_rows, list)
        and isinstance(right_rows, list)
        and len(left_rows) == len(right_rows)
        and canonical({k: v for k, v in left.items() if k != "records"})
        == canonical({k: v for k, v in right.items() if k != "records"})
        and all(
            canonical(a) == canonical(b)
            for a, b in zip(left_rows, right_rows, strict=True)
        )
    )


def publication_progress(
    artifact: dict, *, replayed: bool, inserted_count: int
) -> None:
    """Report only after an exact publication commit or validated receipt replay."""
    from .progress import report

    report(
        phase="publication",
        export_id=artifact["id"],
        expected_rows=artifact["record_count"],
        committed_rows=artifact["record_count"],
        replayed=replayed,
        inserted_count=inserted_count,
    )


BATCH_ROWS = 10000


def stage_checkpoint(phase: str, count: int) -> None:
    """Fault-injection seam at durable boundaries; no external progress state."""


def stage_rows(db: Any, artifact: dict) -> None:
    """Commit bounded hidden batches, checking exact retained rows on resume.

    Observation/publication receipts alone expose data. Staged rows survive an
    interruption but never appear in observations or registered current tables.
    """
    from .progress import report

    report(
        phase="staging",
        export_id=artifact["id"],
        expected_rows=artifact["record_count"],
        staged_rows=0,
        resumed_staged_rows=0,
        committed_rows=0,
        replayed=False,
        inserted_count=0,
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS _dogopencli_observation_rows "
        "(export_id VARCHAR NOT NULL, ordinal BIGINT NOT NULL, _record "
        "VARCHAR NOT NULL, PRIMARY KEY(export_id, ordinal))"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS _dogopencli_import_staging "
        "(export_id VARCHAR PRIMARY KEY, metadata VARCHAR NOT NULL)"
    )
    metadata = canonical(header(artifact))
    previous = db.execute(
        "SELECT metadata FROM _dogopencli_import_staging WHERE export_id=?",
        [artifact["id"]],
    ).fetchone()
    if previous and previous[0] != metadata:
        raise CliError("WORKFLOW_ERROR", "Exact export differs from staged import")
    db.execute(
        "INSERT INTO _dogopencli_import_staging VALUES (?, ?) ON CONFLICT DO NOTHING",
        [artifact["id"], metadata],
    )
    retained = db.execute(
        "SELECT count(*) FROM _dogopencli_observation_rows WHERE export_id=?",
        [artifact["id"]],
    ).fetchone()[0]
    if retained > len(artifact["records"]):
        raise CliError("WORKFLOW_ERROR", "Staged row count differs from exact export")
    for start in range(0, len(artifact["records"]), BATCH_ROWS):
        end = min(start + BATCH_ROWS, len(artifact["records"]))
        rows = [canonical(row) for row in artifact["records"][start:end]]
        if start < retained:
            saved = db.execute(
                "SELECT ordinal, _record FROM _dogopencli_observation_rows "
                "WHERE export_id=? AND ordinal>=? AND ordinal<? ORDER BY ordinal",
                [artifact["id"], start, end],
            ).fetchall()
            if saved != list(enumerate(rows, start)):
                raise CliError(
                    "WORKFLOW_ERROR", "Exact export differs from staged rows"
                )
            report(staged_rows=end, resumed_staged_rows=end)
            continue
        with NamedTemporaryFile(mode="w+", encoding="utf-8", suffix=".jsonl") as stream:
            for ordinal, row in enumerate(rows, start):
                stream.write(canonical({"ordinal": ordinal, "_record": row}) + "\n")
            stream.flush()
            db.execute("BEGIN TRANSACTION")
            db.execute(
                "INSERT INTO _dogopencli_observation_rows SELECT ?, ordinal, _record "
                "FROM read_json(?, format='newline_delimited', "
                "columns={ordinal:'BIGINT', _record:'VARCHAR'})",
                [artifact["id"], stream.name],
            )
            stage_checkpoint("before_batch_commit", end)
            db.execute("COMMIT")
            report(staged_rows=end)
            stage_checkpoint("after_batch_commit", end)


def apply(config_file: Path, plan: dict, artifact: dict, committed_at: str) -> dict:
    binding = plan["binding"]
    with lifecycle_lock(Registry(config_file)):
        with connection(binding, write=True) as db:
            stage_rows(db, artifact)
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
                if not metadata_match(previous[0], artifact):
                    raise CliError(
                        "WORKFLOW_ERROR",
                        "Exact export differs from committed observation",
                    )
                db.execute("ROLLBACK")
                publication_progress(artifact, replayed=True, inserted_count=0)
                return {
                    **parse(previous[1]),
                    "action": "preserve",
                    "current_effect": "unchanged",
                    "replayed": True,
                    "inserted_count": 0,
                }
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
                    canonical(header(artifact)),
                    canonical(receipt),
                ],
            )
            stage_checkpoint("before_publication_commit", artifact["record_count"])
            db.execute("COMMIT")
            publication_progress(
                artifact, replayed=False, inserted_count=artifact["record_count"]
            )
            stage_checkpoint("after_publication_commit", artifact["record_count"])
            return {
                **receipt,
                "replayed": False,
                "inserted_count": artifact["record_count"],
            }


def current_count(binding: dict) -> int:
    with connection(binding) as db:
        relation = binding["relation"].replace('"', '""')
        return db.execute(f'SELECT count(*) FROM "{relation}"').fetchone()[0]
