"""Explicit scoped full-current publications on registered _record assets."""

from pathlib import Path
from typing import Any

from .errors import CliError
from .jsonutil import canonical, parse
from .leaves.lifecycle import lifecycle_lock
from .leaves.registry import Registry
from .workflow_storage import connection


def namespace(artifact: dict) -> str:
    return canonical(
        {
            key: artifact[key]
            for key in ("leaf", "operation", "environment", "parameters")
        }
        | {"scope": artifact["metadata"]["scope"]}
    )


def installed(db: Any) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM information_schema.tables WHERE "
            "table_schema='main' AND "
            "table_name='_dogopencli_current_publications'"
        ).fetchone()
    )


def pointer(db: Any, binding: dict, key: str) -> str | None:
    if not installed(db):
        return None
    row = db.execute(
        "SELECT export_id FROM _dogopencli_current_publications WHERE "
        "relation_name=? AND namespace=?",
        [binding["relation"], key],
    ).fetchone()
    return row[0] if row else None


def guard(db: Any, binding: dict) -> None:
    from .workflow_keyed import installed as table_installed

    for table in ("_dogopencli_keyed_receipts", "_dogopencli_range_publications"):
        if (
            table_installed(db, table)
            and db.execute(
                f"SELECT 1 FROM {table} WHERE relation_name=? LIMIT 1",
                [binding["relation"]],
            ).fetchone()
        ):
            raise CliError(
                "WORKFLOW_ERROR",
                "Current relation has incompatible keyed/range ownership",
            )


def preview(artifact: dict) -> dict:
    with connection(artifact["binding"]) as db:
        guard(db, artifact["binding"])
        key = namespace(artifact)
        previous = pointer(db, artifact["binding"], key)
        count = 0
        replayed = False
        if installed(db):
            if previous:
                count = parse(
                    db.execute(
                        "SELECT artifact FROM _dogopencli_observations WHERE "
                        "export_id=?",
                        [previous],
                    ).fetchone()[0]
                )["record_count"]
            replayed = bool(
                db.execute(
                    "SELECT 1 FROM _dogopencli_publication_receipts WHERE export_id=?",
                    [artifact["id"]],
                ).fetchone()
            )
        return {
            "namespace": parse(key),
            "expected_current": previous,
            "existing_count": count,
            "new_count": 0 if replayed else artifact["record_count"],
            "current_count": count,
            "current_effect": "replace_exact_scope",
            "count_basis": "current_publication_in_exact_scope",
        }


def current(artifact: dict) -> dict:
    from .workflow_storage import read

    with connection(artifact["binding"]) as db:
        previous = pointer(db, artifact["binding"], namespace(artifact))
        receipt = (
            parse(
                db.execute(
                    "SELECT receipt FROM _dogopencli_publication_receipts "
                    "WHERE export_id=?",
                    [previous],
                ).fetchone()[0]
            )
            if previous
            else None
        )
    if previous is None:
        return {
            "export_id": None,
            "records": [],
            "namespace": parse(namespace(artifact)),
        }
    return {
        **read(artifact["binding"], previous),
        "receipt": receipt,
        "namespace": parse(namespace(artifact)),
    }


def publications(binding: dict) -> list[dict]:
    with connection(binding) as db:
        if not installed(db):
            return []
        return [
            parse(row[0])
            for row in db.execute(
                "SELECT r.receipt FROM _dogopencli_current_publications p "
                "JOIN _dogopencli_publication_receipts r ON "
                "p.export_id=r.export_id WHERE p.relation_name=?",
                [binding["relation"]],
            ).fetchall()
        ]


def apply(config_file: Path, plan: dict, artifact: dict, committed_at: str) -> dict:
    binding = artifact["binding"]
    key = namespace(artifact)
    if (
        canonical(plan.get("namespace")) != key
        or plan.get("scope") != artifact["metadata"]["scope"]
    ):
        raise CliError(
            "WORKFLOW_ERROR", "Replacement namespace differs from exact export"
        )
    with lifecycle_lock(Registry(config_file)):
        with connection(binding, write=True) as db:
            db.execute("BEGIN TRANSACTION")
            guard(db, binding)
            db.execute(
                "CREATE TABLE IF NOT EXISTS _dogopencli_current_publications "
                "(relation_name VARCHAR NOT NULL, namespace VARCHAR NOT NULL,"
                " export_id VARCHAR NOT NULL, PRIMARY KEY(relation_name, "
                "namespace))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS _dogopencli_publication_receipts "
                "(export_id VARCHAR PRIMARY KEY, receipt VARCHAR NOT NULL)"
            )
            replay = db.execute(
                "SELECT receipt FROM _dogopencli_publication_receipts WHERE "
                "export_id=?",
                [artifact["id"]],
            ).fetchone()
            if replay:
                saved = db.execute(
                    "SELECT artifact FROM _dogopencli_observations WHERE export_id=?",
                    [artifact["id"]],
                ).fetchone()
                if not saved or canonical(parse(saved[0])) != canonical(artifact):
                    raise CliError(
                        "WORKFLOW_ERROR",
                        "Exact export differs from committed publication",
                    )
                db.execute("ROLLBACK")
                return {**parse(replay[0]), "replayed": True, "inserted_count": 0}
            previous = pointer(db, binding, key)
            if previous != plan["expected_current"]:
                raise CliError(
                    "WORKFLOW_ERROR",
                    "Stale replacement plan: current publication changed; "
                    "compile a new import plan",
                )
            db.execute(
                "CREATE TABLE IF NOT EXISTS _dogopencli_observations "
                "(export_id VARCHAR PRIMARY KEY, leaf_id VARCHAR NOT NULL, "
                "relation_name VARCHAR NOT NULL, action VARCHAR NOT NULL, "
                "committed_at VARCHAR NOT NULL, artifact VARCHAR NOT NULL, "
                "receipt VARCHAR NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS _dogopencli_observation_rows "
                "(export_id VARCHAR NOT NULL, ordinal BIGINT NOT NULL, "
                "_record VARCHAR NOT NULL, PRIMARY KEY(export_id, ordinal))"
            )
            receipt = {
                "export_id": artifact["id"],
                "current_export_id": artifact["id"],
                "previous_current": previous,
                "plan_id": plan["id"],
                "action": "replace-full",
                "binding": binding,
                "record_count": artifact["record_count"],
                "committed_at": committed_at,
                "current_effect": "replace_exact_scope",
                "scope": artifact["metadata"]["scope"],
                "environment": artifact["environment"],
                "namespace": parse(key),
            }
            saved = db.execute(
                "SELECT artifact FROM _dogopencli_observations WHERE export_id=?",
                [artifact["id"]],
            ).fetchone()
            if saved and canonical(parse(saved[0])) != canonical(artifact):
                raise CliError(
                    "WORKFLOW_ERROR", "Exact export differs from committed observation"
                )
            if not saved:
                db.execute(
                    "INSERT INTO _dogopencli_observations VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        artifact["id"],
                        binding["leaf"],
                        binding["relation"],
                        "replace-full",
                        committed_at,
                        canonical(artifact),
                        canonical(receipt),
                    ],
                )
                if artifact["records"]:
                    db.executemany(
                        "INSERT INTO _dogopencli_observation_rows VALUES (?, ?, ?)",
                        [
                            (artifact["id"], ordinal, canonical(row))
                            for ordinal, row in enumerate(artifact["records"])
                        ],
                    )
            relation = '"' + binding["relation"].replace('"', '""') + '"'
            if previous:
                # Multiset subtraction preserves unrelated occurrences, including
                # identical rows published in other query namespaces.
                missing = db.execute(
                    "SELECT _record FROM _dogopencli_observation_rows WHERE "
                    f"export_id=? EXCEPT ALL SELECT _record FROM {relation}",
                    [previous],
                ).fetchone()
                if missing:
                    raise CliError(
                        "WORKFLOW_ERROR",
                        "Current rows differ from committed publication",
                    )
                db.execute(
                    "CREATE TEMP TABLE retained_current AS SELECT _record "
                    f"FROM {relation} EXCEPT ALL SELECT _record FROM "
                    "_dogopencli_observation_rows WHERE export_id=?",
                    [previous],
                )
                db.execute(f"DELETE FROM {relation}")
                db.execute(
                    f"INSERT INTO {relation} SELECT _record FROM retained_current"
                )
            db.execute(
                f"INSERT INTO {relation} SELECT _record FROM "
                "_dogopencli_observation_rows WHERE export_id=? ORDER BY "
                "ordinal",
                [artifact["id"]],
            )
            db.execute(
                "INSERT INTO _dogopencli_publication_receipts VALUES (?, ?)",
                [artifact["id"], canonical(receipt)],
            )
            db.execute(
                "INSERT INTO _dogopencli_current_publications VALUES (?, ?, "
                "?) ON CONFLICT (relation_name, namespace) DO UPDATE SET "
                "export_id=excluded.export_id",
                [binding["relation"], key, artifact["id"]],
            )
            db.execute("COMMIT")
            return {
                **receipt,
                "replayed": False,
                "inserted_count": artifact["record_count"],
            }
