"""One disposable acquisition per list leaf, with output-only windows."""

import hashlib
from typing import Any

from .cache import Cache, SnapshotMeta
from .errors import INVALID_RESPONSE, CliError
from .jsonutil import canonical, parse
from .result_policy import AcquisitionEvidence


def slot_namespace(leaf: str) -> str:
    return "temporary-query:" + leaf


def slot_context(snapshot: SnapshotMeta) -> dict:
    try:
        context = parse(snapshot.scope)
    except (ValueError, TypeError) as error:
        raise CliError(INVALID_RESPONSE, "cached query context is invalid") from error
    if (
        not isinstance(context, dict)
        or not isinstance(context.get("query"), dict)
        or "variant" not in context
        or "selection" not in context
    ):
        raise CliError(INVALID_RESPONSE, "cached query context is invalid")
    return context


def read_slot(store: Cache, leaf: str) -> tuple[SnapshotMeta | None, list[dict]]:
    store.ensure_temporary_format()
    snapshot, records = store.read(slot_namespace(leaf))
    try:
        rows = [parse(body) for _, body in records]
    except (ValueError, TypeError) as error:
        raise CliError(INVALID_RESPONSE, "cached query records are invalid") from error
    if snapshot is not None:
        slot_context(snapshot)
    if snapshot is not None and (
        len(rows) != snapshot.row_count
        or any(not isinstance(row, dict) for row in rows)
        or [seq for seq, _ in records] != list(range(1, len(rows) + 1))
    ):
        raise CliError(INVALID_RESPONSE, "temporary query cache is invalid")
    return snapshot, rows


def publish_slot(
    store: Cache,
    leaf: str,
    rows: list[dict],
    *,
    capability: str,
    scope: dict,
    evidence: AcquisitionEvidence,
    fetched_at: str,
    source_kind: str = "cdp",
    variant: str | None = None,
    selection: dict | None = None,
    simulated: bool = False,
    dataset_id: str | None = None,
    source_path: str | None = None,
) -> SnapshotMeta | None:
    if not rows:
        return None
    store.ensure_temporary_format()
    meta = SnapshotMeta(
        namespace=slot_namespace(leaf),
        capability=capability,
        scope=canonical({"query": scope, "variant": variant, "selection": selection}),
        source_kind=source_kind,
        snapshot_id=hashlib.sha256(canonical(rows).encode()).hexdigest(),
        dataset_id=dataset_id,
        simulated=simulated,
        backend_complete=evidence.scope_complete,
        dataset_complete=evidence.dataset_complete,
        fetched_at=fetched_at,
        loaded_at=fetched_at,
        source_observed_from=None,
        source_observed_to=None,
        row_count=len(rows),
        source_path=source_path,
        acquisition=evidence.record(),
    )
    store.publish(meta, ((i, canonical(row)) for i, row in enumerate(rows, 1)))
    return meta


def prune_slot(store: Cache, leaf: str) -> bool:
    if not store._path.exists():
        return False
    with store.refresh_lock():
        store.ensure_temporary_format()
        return store.remove(slot_namespace(leaf))


def display_options(args: Any) -> tuple[int, int, list[str] | None]:
    limit = 100 if getattr(args, "limit", None) is None else args.limit
    offset = 0 if getattr(args, "offset", None) is None else args.offset
    if limit < 0 or offset < 0:
        raise CliError(
            "INVALID_ARGUMENT", "--limit and --offset must be nonnegative", exit_code=2
        )
    fields = None
    if getattr(args, "fields", None) is not None:
        fields = [field.strip() for field in args.fields.split(",") if field.strip()]
        if not fields:
            raise CliError(
                "INVALID_ARGUMENT", "--fields must name at least one field", exit_code=2
            )
    return limit, offset, fields


def window_rows(rows: list[dict], limit: int, offset: int) -> list[dict]:
    return rows[offset:] if limit == 0 else rows[offset : offset + limit]


def capability_leaf(capability: str) -> str:
    from .plugins import cache_bindings

    for path, cap in cache_bindings().items():
        if cap.name == capability and path[-1] == "list":
            return ".".join(path[:-1])
    return capability.removesuffix(".list")


def query_namespace(capability: str, scope: str, source_kind: str) -> str:
    return slot_namespace(capability_leaf(capability))


def publish_candidate(store: Cache, snapshot: SnapshotMeta, records) -> None:
    from dataclasses import replace

    store.ensure_temporary_format()
    if not snapshot.row_count:
        return
    context = {"query": {"scope": snapshot.scope}, "variant": None, "selection": None}
    store.publish(replace(snapshot, scope=canonical(context)), records)
