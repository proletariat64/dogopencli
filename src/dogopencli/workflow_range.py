"""Explicit exporter-covered calendar replacement on registered current assets."""

from pathlib import Path
from typing import Any

from .errors import CliError
from .jsonutil import canonical, parse
from .leaves.lifecycle import lifecycle_lock
from .leaves.registry import Registry
from .workflow_history import calendar
from .workflow_keyed import installed, save_observation
from .workflow_storage import connection


def invalid(message: str) -> None:
    raise CliError(
        "WORKFLOW_ERROR", message + "; preserve the exact observation instead"
    )


def contract(artifact: dict) -> dict:
    value = artifact.get("range_replacement_contract")
    if (
        not isinstance(value, dict)
        or value.get("interpretation") != "calendar_date"
        or value.get("boundary") != "inclusive"
        or not isinstance(value.get("namespace"), dict)
        or not value["namespace"]
        or not isinstance(value.get("field"), str)
        or not value["field"]
        or not isinstance(value.get("format"), str)
    ):
        invalid("Export lacks explicit native range replacement coverage")
    try:
        left, right = calendar(value["from"], value), calendar(value["to"], value)
        if left > right:
            invalid("Replacement range is reversed")
        for row in artifact["records"]:
            if not left <= calendar(row[value["field"]], value) <= right:
                invalid("Export row lies outside established replacement range")
    except (KeyError, TypeError, ValueError) as error:
        raise CliError(
            "WORKFLOW_ERROR", "Invalid native replacement coverage"
        ) from error
    return value


def namespace(artifact: dict) -> str:
    value = contract(artifact)
    return canonical(
        {key: artifact[key] for key in ("leaf", "operation", "environment")}
        | {"native": value["namespace"]}
    )


def compatible(db: Any, artifact: dict) -> None:
    previous = pointer(db, artifact)
    if previous is None:
        return
    saved = db.execute(
        "SELECT contract FROM _dogopencli_range_publications "
        "WHERE relation_name=? AND namespace=?",
        [artifact["binding"]["relation"], namespace(artifact)],
    ).fetchone()[0]
    if saved != canonical(semantics(artifact)):
        invalid("Replacement semantics differ from retained current history")


def semantics(artifact: dict) -> dict:
    return {k: v for k, v in contract(artifact).items() if k not in {"from", "to"}}


def bounds(artifact: dict) -> tuple[int, int]:
    value = contract(artifact)
    return calendar(value["from"], value).toordinal(), calendar(
        value["to"], value
    ).toordinal()


def guard(db: Any, binding: dict) -> None:
    for table in ("_dogopencli_current_publications", "_dogopencli_keyed_receipts"):
        if (
            installed(db, table)
            and db.execute(
                f"SELECT 1 FROM {table} WHERE relation_name=? LIMIT 1",
                [binding["relation"]],
            ).fetchone()
        ):
            invalid("Current relation has incompatible full/keyed ownership")
    if (
        not installed(db, "_dogopencli_range_publications")
        or not db.execute(
            "SELECT 1 FROM _dogopencli_range_publications WHERE "
            "relation_name=? LIMIT 1",
            [binding["relation"]],
        ).fetchone()
    ):
        relation = '"' + binding["relation"].replace('"', '""') + '"'
        if db.execute(f"SELECT 1 FROM {relation} LIMIT 1").fetchone():
            invalid("Existing current rows have no range ownership")


def active(artifact: dict) -> bool:
    with connection(artifact["binding"]) as db:
        return installed(db, "_dogopencli_range_publications") and bool(
            db.execute(
                "SELECT 1 FROM _dogopencli_range_publications WHERE "
                "relation_name=? LIMIT 1",
                [artifact["binding"]["relation"]],
            ).fetchone()
        )


def pointer(db: Any, artifact: dict) -> str | None:
    if not installed(db, "_dogopencli_range_publications"):
        return None
    row = db.execute(
        "SELECT export_id FROM _dogopencli_range_publications WHERE "
        "relation_name=? AND namespace=?",
        [artifact["binding"]["relation"], namespace(artifact)],
    ).fetchone()
    return row[0] if row else None


def counts(db: Any, artifact: dict) -> tuple[int, int]:
    if not installed(db, "_dogopencli_range_rows"):
        return 0, 0
    left, right = bounds(artifact)
    total, replaced = db.execute(
        "SELECT count(*), count(*) FILTER (WHERE native_day BETWEEN ? AND ?) "
        "FROM _dogopencli_range_rows WHERE relation_name=? AND namespace=?",
        [left, right, artifact["binding"]["relation"], namespace(artifact)],
    ).fetchone()
    return replaced, total - replaced


def preview(artifact: dict) -> dict:
    key = namespace(artifact)
    with connection(artifact["binding"]) as db:
        guard(db, artifact["binding"])
        compatible(db, artifact)
        previous = pointer(db, artifact)
        replaced, retained = counts(db, artifact)
        replayed = installed(db, "_dogopencli_range_receipts") and bool(
            db.execute(
                "SELECT 1 FROM _dogopencli_range_receipts WHERE export_id=?",
                [artifact["id"]],
            ).fetchone()
        )
    return {
        "namespace": parse(key),
        "expected_current": previous,
        "replacement_range": {k: contract(artifact)[k] for k in ("from", "to")},
        "existing_count": replaced,
        "retained_count": retained,
        "new_count": 0 if replayed else artifact["record_count"],
        "current_count": replaced + retained,
        "current_effect": "replace_covered_range",
        "count_basis": "native_replacement_range",
    }


def current(artifact: dict) -> dict:
    key = namespace(artifact)
    with connection(artifact["binding"]) as db:
        previous = pointer(db, artifact)
        values = db.execute(
            "SELECT _record, export_id FROM _dogopencli_range_rows "
            "WHERE relation_name=? AND namespace=? "
            "ORDER BY native_day, export_id, ordinal",
            [artifact["binding"]["relation"], key],
        ).fetchall()
    return {
        "export_id": previous,
        "namespace": parse(key),
        "records": [parse(row[0]) for row in values],
        "provenance": [{"export_id": row[1]} for row in values],
    }


def publications(binding: dict) -> list[dict]:
    with connection(binding) as db:
        if not installed(db, "_dogopencli_range_publications"):
            return []
        return [
            parse(row[0])
            for row in db.execute(
                "SELECT r.receipt FROM "
                "_dogopencli_range_publications p JOIN _dogopencli_range_receipts r "
                "ON p.export_id=r.export_id WHERE p.relation_name=?",
                [binding["relation"]],
            ).fetchall()
        ]


def apply(config_file: Path, plan: dict, artifact: dict, committed_at: str) -> dict:
    binding, key = artifact["binding"], namespace(artifact)
    value = contract(artifact)
    left, right = bounds(artifact)
    if canonical(plan.get("namespace")) != key or plan.get("replacement_range") != {
        k: value[k] for k in ("from", "to")
    }:
        invalid("Replacement plan differs from frozen native range")
    with lifecycle_lock(Registry(config_file)):
        with connection(binding, write=True) as db:
            db.execute("BEGIN TRANSACTION")
            guard(db, binding)
            db.execute(
                "CREATE TABLE IF NOT EXISTS _dogopencli_range_publications "
                "(relation_name VARCHAR, namespace VARCHAR, "
                "export_id VARCHAR NOT NULL, contract VARCHAR NOT "
                "NULL, PRIMARY KEY(relation_name, namespace))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS _dogopencli_range_receipts "
                "(export_id VARCHAR PRIMARY KEY, relation_name "
                "VARCHAR NOT NULL, receipt VARCHAR NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS _dogopencli_range_rows "
                "(relation_name VARCHAR, namespace VARCHAR, "
                "export_id VARCHAR, ordinal BIGINT, native_day INTEGER, "
                "_record VARCHAR NOT NULL, PRIMARY "
                "KEY(relation_name, namespace, export_id, ordinal))"
            )
            replay = db.execute(
                "SELECT receipt FROM _dogopencli_range_receipts WHERE export_id=?",
                [artifact["id"]],
            ).fetchone()
            if replay:
                saved = db.execute(
                    "SELECT artifact FROM _dogopencli_observations WHERE export_id=?",
                    [artifact["id"]],
                ).fetchone()
                if not saved or canonical(parse(saved[0])) != canonical(artifact):
                    invalid("Exact export differs from committed range publication")
                db.execute("ROLLBACK")
                return {**parse(replay[0]), "replayed": True, "inserted_count": 0}
            compatible(db, artifact)
            previous = pointer(db, artifact)
            if previous != plan["expected_current"]:
                invalid(
                    "Stale replacement plan: current publication "
                    "changed; compile a new import plan"
                )
            replaced, retained = counts(db, artifact)
            receipt = {
                "export_id": artifact["id"],
                "previous_current": previous,
                "plan_id": plan["id"],
                "action": "replace-range",
                "binding": binding,
                "namespace": parse(key),
                "scope": artifact["metadata"]["scope"],
                "environment": artifact["environment"],
                "replacement_range": plan["replacement_range"],
                "record_count": artifact["record_count"],
                "removed_count": replaced,
                "retained_count": retained,
                "committed_at": committed_at,
                "current_effect": "replace_covered_range",
            }
            save_observation(db, artifact, receipt)
            relation = '"' + binding["relation"].replace('"', '""') + '"'
            selected = [binding["relation"], key, left, right]
            # Subtract owned occurrences; retain equal rows in other scopes.
            missing = db.execute(
                "SELECT _record FROM _dogopencli_range_rows WHERE "
                "relation_name=? AND namespace=? "
                f"AND native_day BETWEEN ? AND ? EXCEPT ALL SELECT "
                f"_record FROM {relation}",
                selected,
            ).fetchone()
            if missing:
                invalid("Current rows differ from committed range publication")
            db.execute(
                "CREATE TEMP TABLE retained_range AS SELECT _record "
                f"FROM {relation} EXCEPT ALL SELECT _record FROM "
                f"_dogopencli_range_rows "
                "WHERE relation_name=? AND namespace=? AND native_day BETWEEN ? AND ?",
                selected,
            )
            db.execute(f"DELETE FROM {relation}")
            db.execute(f"INSERT INTO {relation} SELECT _record FROM retained_range")
            db.execute(
                "DELETE FROM _dogopencli_range_rows WHERE "
                "relation_name=? AND namespace=? AND native_day BETWEEN ? AND ?",
                selected,
            )
            if artifact["records"]:
                db.executemany(
                    "INSERT INTO _dogopencli_range_rows VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (
                            binding["relation"],
                            key,
                            artifact["id"],
                            i,
                            calendar(row[value["field"]], value).toordinal(),
                            canonical(row),
                        )
                        for i, row in enumerate(artifact["records"])
                    ],
                )
                db.executemany(
                    f"INSERT INTO {relation} VALUES (?)",
                    [(canonical(row),) for row in artifact["records"]],
                )
            db.execute(
                "INSERT INTO _dogopencli_range_receipts VALUES (?, ?, ?)",
                [artifact["id"], binding["relation"], canonical(receipt)],
            )
            db.execute(
                "INSERT INTO _dogopencli_range_publications VALUES (?, ?, ?, ?) "
                "ON CONFLICT(relation_name, namespace) DO UPDATE SET "
                "export_id=excluded.export_id, contract=excluded.contract",
                [
                    binding["relation"],
                    key,
                    artifact["id"],
                    canonical(semantics(artifact)),
                ],
            )
            db.execute("COMMIT")
            return {
                **receipt,
                "replayed": False,
                "inserted_count": artifact["record_count"],
            }
