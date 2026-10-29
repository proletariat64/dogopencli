"""Explicit native identity and ordering for incremental current history."""

from pathlib import Path
from typing import Any

from .errors import CliError
from .jsonutil import canonical, parse
from .leaves.lifecycle import lifecycle_lock
from .leaves.registry import Registry
from .workflow_storage import connection, exact_match


def invalid(message: str) -> None:
    raise CliError(
        "WORKFLOW_ERROR", message + "; preserve the exact observation instead"
    )


def contract(artifact: dict) -> dict:
    value = artifact.get("keyed_contract")
    if not isinstance(value, dict):
        invalid("Leaf export has no declared keyed identity/ordering contract")
    fields = value.get("identity")
    ordering = value.get("ordering", {})
    if (
        not isinstance(fields, list)
        or not fields
        or any(not isinstance(field, str) or not field for field in fields)
        or len(fields) != len(set(fields))
        or not isinstance(value.get("namespace"), dict)
        or not value["namespace"]
        or value.get("cross_range_equivalence") is not True
        or not isinstance(ordering, dict)
        or ordering.get("mode") not in {"source_version", "latest_observed"}
    ):
        invalid(
            "Keyed merge requires explicit identity, business namespace and "
            "cross-range equivalence"
        )
    if ordering["mode"] == "source_version" and (
        not isinstance(ordering.get("field"), str)
        or ordering.get("comparison") not in {"lexical", "numeric"}
    ):
        invalid("Source-version ordering requires a declared field and comparison")
    return value


def namespace(artifact: dict) -> str:
    value = contract(artifact)
    return canonical(
        {key: artifact[key] for key in ("leaf", "operation", "environment")}
        | {"native": value["namespace"]}
    )


def installed(db: Any, table: str) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM information_schema.tables WHERE "
            "table_schema='main' AND table_name=?",
            [table],
        ).fetchone()
    )


def claimed(db: Any, binding: dict) -> bool:
    return installed(db, "_dogopencli_keyed_receipts") and bool(
        db.execute(
            "SELECT 1 FROM _dogopencli_keyed_receipts WHERE relation_name=? LIMIT 1",
            [binding["relation"]],
        ).fetchone()
    )


def active(artifact: dict) -> bool:
    with connection(artifact["binding"]) as db:
        return claimed(db, artifact["binding"])


def guard(db: Any, binding: dict) -> None:
    for table in ("_dogopencli_current_publications", "_dogopencli_range_publications"):
        if (
            installed(db, table)
            and db.execute(
                f"SELECT 1 FROM {table} WHERE relation_name=? LIMIT 1",
                [binding["relation"]],
            ).fetchone()
        ):
            invalid(
                "Current relation already has replacement publications; keyed"
                " ownership is ambiguous"
            )
    if not claimed(db, binding):
        relation = '"' + binding["relation"].replace('"', '""') + '"'
        if db.execute(f"SELECT 1 FROM {relation} LIMIT 1").fetchone():
            invalid("Existing current rows have no keyed ownership")


def entries(artifact: dict) -> dict[str, dict]:
    facts = contract(artifact)
    result = {}
    for row in artifact["records"]:
        if any(
            field not in row
            or row[field] is None
            or isinstance(row[field], (list, dict))
            for field in facts["identity"]
        ):
            invalid("Export row lacks a scalar native identity")
        key = canonical([row[field] for field in facts["identity"]])
        if key in result and canonical(result[key]) != canonical(row):
            invalid("Export contains conflicting rows for one native identity")
        version(artifact, row)
        result[key] = row
    return result


def version(artifact: dict, row: dict) -> Any:
    order = contract(artifact)["ordering"]
    if order["mode"] == "latest_observed":
        return artifact["completed_at"]
    value = row.get(order["field"])
    if order["comparison"] == "lexical":
        if not isinstance(value, str) or not value:
            invalid("Source-version field requires a nonempty sortable string")
    else:
        from decimal import Decimal

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float, Decimal))
            or not Decimal(str(value)).is_finite()
        ):
            invalid("Source-version field requires a finite native number")
    return value


def rows(db: Any, artifact: dict) -> dict[str, tuple]:
    if not installed(db, "_dogopencli_keyed_current"):
        return {}
    values = db.execute(
        "SELECT identity, _record, artifact, contract FROM "
        "_dogopencli_keyed_current WHERE relation_name=? AND namespace=? "
        "ORDER BY identity",
        [artifact["binding"]["relation"], namespace(artifact)],
    ).fetchall()
    if any(item[3] != canonical(contract(artifact)) for item in values):
        invalid("Keyed source contract differs from retained current history")
    return {key: (parse(record), parse(source)) for key, record, source, _ in values}


def changes(artifact: dict, previous: dict) -> tuple[dict, dict]:
    incoming = entries(artifact)
    selected = {}
    counts = {"inserted_count": 0, "updated_count": 0, "unchanged_count": 0}
    for key, row in incoming.items():
        if key not in previous:
            selected[key] = row
            counts["inserted_count"] += 1
            continue
        old, source = previous[key]
        if canonical(old) == canonical(row):
            if version(artifact, row) > version(source, old):
                selected[key] = row
            counts["unchanged_count"] += 1
            continue
        left, right = version(artifact, row), version(source, old)
        if left == right:
            invalid("Equal-version conflict for a native identity")
        if left < right:
            counts["unchanged_count"] += 1
        else:
            selected[key] = row
            counts["updated_count"] += 1
    return selected, counts


def preview(artifact: dict) -> dict:
    key = namespace(artifact)
    with connection(artifact["binding"]) as db:
        guard(db, artifact["binding"])
        previous = rows(db, artifact)
        _, counts = changes(artifact, previous)
        replayed = installed(db, "_dogopencli_keyed_receipts") and bool(
            db.execute(
                "SELECT 1 FROM _dogopencli_keyed_receipts WHERE export_id=?",
                [artifact["id"]],
            ).fetchone()
        )
    return {
        "namespace": parse(key),
        "existing_count": len(previous),
        "new_count": 0 if replayed else counts["inserted_count"],
        "current_count": len(previous),
        "current_effect": "reconcile_keyed_history",
        "count_basis": "scoped_native_identity",
        "ordering": contract(artifact)["ordering"],
        **counts,
    }


def imports(binding: dict) -> list[dict]:
    with connection(binding) as db:
        if not installed(db, "_dogopencli_keyed_receipts"):
            return []
        return [
            parse(row[0])
            for row in db.execute(
                "SELECT receipt FROM _dogopencli_keyed_receipts "
                "WHERE relation_name=? ORDER BY export_id",
                [binding["relation"]],
            ).fetchall()
        ]


def current(artifact: dict) -> dict:
    with connection(artifact["binding"]) as db:
        previous = rows(db, artifact)
    return {
        "namespace": parse(namespace(artifact)),
        "records": [value[0] for value in previous.values()],
        "provenance": [
            {"export_id": value[1]["id"], "captured_at": value[1]["completed_at"]}
            for value in previous.values()
        ],
        "ordering": contract(artifact)["ordering"],
    }


def save_observation(db: Any, artifact: dict, receipt: dict) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS _dogopencli_observations (export_id "
        "VARCHAR PRIMARY KEY, leaf_id VARCHAR NOT NULL, relation_name VARCHAR"
        " NOT NULL, action VARCHAR NOT NULL, committed_at VARCHAR NOT NULL, "
        "artifact VARCHAR NOT NULL, receipt VARCHAR NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS _dogopencli_observation_rows (export_id "
        "VARCHAR NOT NULL, ordinal BIGINT NOT NULL, _record VARCHAR NOT NULL,"
        " PRIMARY KEY(export_id, ordinal))"
    )
    saved = db.execute(
        "SELECT artifact FROM _dogopencli_observations WHERE export_id=?",
        [artifact["id"]],
    ).fetchone()
    if saved:
        if not exact_match(parse(saved[0]), artifact):
            invalid("Exact export differs from committed observation")
        return
    binding = artifact["binding"]
    db.execute(
        "INSERT INTO _dogopencli_observations VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            artifact["id"],
            binding["leaf"],
            binding["relation"],
            receipt["action"],
            receipt["committed_at"],
            canonical(artifact),
            canonical(receipt),
        ],
    )


def apply(config_file: Path, plan: dict, artifact: dict, committed_at: str) -> dict:
    binding = artifact["binding"]
    key = namespace(artifact)
    if canonical(plan.get("namespace")) != key:
        invalid("Keyed plan namespace differs from frozen export")
    with lifecycle_lock(Registry(config_file)):
        with connection(binding, write=True) as db:
            from .workflow_storage import stage_rows

            stage_rows(db, artifact)
            db.execute("BEGIN TRANSACTION")
            guard(db, binding)
            db.execute(
                "CREATE TABLE IF NOT EXISTS _dogopencli_keyed_current "
                "(relation_name VARCHAR, namespace VARCHAR, identity VARCHAR,"
                " _record VARCHAR NOT NULL, artifact VARCHAR NOT NULL, "
                "contract VARCHAR NOT NULL, PRIMARY KEY(relation_name, "
                "namespace, identity))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS _dogopencli_keyed_receipts "
                "(export_id VARCHAR PRIMARY KEY, relation_name VARCHAR NOT "
                "NULL, receipt VARCHAR NOT NULL)"
            )
            replay = db.execute(
                "SELECT receipt FROM _dogopencli_keyed_receipts WHERE export_id=?",
                [artifact["id"]],
            ).fetchone()
            if replay:
                saved = db.execute(
                    "SELECT artifact FROM _dogopencli_observations WHERE export_id=?",
                    [artifact["id"]],
                ).fetchone()
                if not saved or not exact_match(parse(saved[0]), artifact):
                    invalid("Exact export differs from keyed receipt")
                db.execute("ROLLBACK")
                return {
                    **parse(replay[0]),
                    "replayed": True,
                    "inserted_count": 0,
                    "updated_count": 0,
                }
            previous = rows(db, artifact)
            selected, counts = changes(artifact, previous)
            receipt = {
                "export_id": artifact["id"],
                "plan_id": plan["id"],
                "action": "keyed",
                "binding": binding,
                "scope": artifact["metadata"]["scope"],
                "environment": artifact["environment"],
                "namespace": parse(key),
                "record_count": artifact["record_count"],
                "committed_at": committed_at,
                "captured_at": artifact["completed_at"],
                "ordering": contract(artifact)["ordering"],
                "current_effect": "reconcile_keyed_history",
                **counts,
            }
            save_observation(db, artifact, receipt)
            relation = '"' + binding["relation"].replace('"', '""') + '"'
            for identity, row in selected.items():
                if identity in previous:
                    old = canonical(previous[identity][0])
                    found = db.execute(
                        f"SELECT rowid FROM {relation} WHERE _record=? LIMIT 1", [old]
                    ).fetchone()
                    if not found:
                        invalid("Current rows differ from committed keyed history")
                    db.execute(f"DELETE FROM {relation} WHERE rowid=?", [found[0]])
                db.execute(f"INSERT INTO {relation} VALUES (?)", [canonical(row)])
                db.execute(
                    "INSERT INTO _dogopencli_keyed_current VALUES (?, ?, ?, "
                    "?, ?, ?) ON CONFLICT (relation_name, namespace, "
                    "identity) DO UPDATE SET _record=excluded._record, "
                    "artifact=excluded.artifact, contract=excluded.contract",
                    [
                        binding["relation"],
                        key,
                        identity,
                        canonical(row),
                        canonical(
                            {
                                name: artifact[name]
                                for name in ("id", "completed_at", "keyed_contract")
                            }
                        ),
                        canonical(contract(artifact)),
                    ],
                )
            db.execute(
                "INSERT INTO _dogopencli_keyed_receipts VALUES (?, ?, ?)",
                [artifact["id"], binding["relation"], canonical(receipt)],
            )
            db.execute("COMMIT")
            return {**receipt, "replayed": False}
