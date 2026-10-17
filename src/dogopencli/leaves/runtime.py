"""Common inquiry, quality and single-slot cache policy for installed leaves."""

import hashlib
import math
from argparse import Namespace
from contextlib import nullcontext
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.collect import collect_scope
from dogopencli.config import DEFAULT_TTL_HOURS, tomllib
from dogopencli.errors import CliError
from dogopencli.inquiry import inquiry_session
from dogopencli.jsonutil import canonical, parse
from dogopencli.result_policy import (
    AcquisitionEvidence,
    check_complete,
    evidence_for,
    prepare_result,
)
from dogopencli.temporary_query import display_options, is_stale, window_rows

from .registry import Leaf


def cache_for(config_file: Path) -> Cache:
    return Cache(config_file.parent / "leaf-cache.sqlite3")


def _ttl(config_file: Path) -> float:
    try:
        document = (
            tomllib.loads(config_file.read_text()) if config_file.exists() else {}
        )
        value = document.get("cache", {}).get("ttl_hours", DEFAULT_TTL_HOURS)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError
        return float(value)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise CliError(
            "CONFIG_ERROR",
            "cache.ttl_hours must be a finite nonnegative number",
            exit_code=2,
        ) from exc


def _validate_records(rows: Any, identity: list[str]) -> list[dict]:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise CliError("INVALID_RESPONSE", "records must be business objects")
    seen = set()
    for row in rows:
        if identity:
            if any(field not in row or row[field] is None for field in identity):
                raise CliError("INVALID_RESPONSE", "record identity is missing")
            key = canonical([row[field] for field in identity])
            if key in seen:
                raise CliError("INVALID_RESPONSE", "record identity is duplicated")
            seen.add(key)
    return rows


def _project(rows: list[dict], fields: list[str] | None) -> list[dict]:
    if fields is None:
        return rows
    if any(field not in row for row in rows for field in fields):
        raise CliError(
            "INVALID_ARGUMENT",
            "requested field is absent from a returned record",
            exit_code=2,
        )
    return [{field: row[field] for field in fields} for row in rows]


def _contract_id(leaf: Leaf, capability: Any) -> str:
    def basic(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: basic(item) for key, item in value.items()}
        if isinstance(value, (set, frozenset)):
            return sorted(basic(item) for item in value)
        if isinstance(value, (list, tuple)):
            return [basic(item) for item in value]
        return value

    operations = {
        name: [
            {key: value for key, value in parameter.items() if key != "description"}
            for parameter in operation.get("parameters", [])
        ]
        for name, operation in leaf.manifest["operations"].items()
    }
    context = {
        "identity": leaf.manifest["identity"],
        "operations": operations,
        "adapter_binding": leaf.manifest["adapter"],
        "adapter_sha256": leaf.adapter_sha256,
        "capability": capability.name,
        "native_contract": basic(asdict(capability.contract)),
    }
    return hashlib.sha256(canonical(context).encode()).hexdigest()


def execute(
    leaf: Leaf, operation: str, parameters: dict, args: Namespace, config_file: Path
) -> tuple[Any, dict]:
    """Execute one supported action; publication always uses the full candidate."""

    def now() -> datetime:
        return datetime.now(timezone.utc)

    store = cache_for(config_file)
    namespace = "leaf:" + leaf.id
    limit, offset, fields = display_options(args)
    if operation == "prune":
        with store.refresh_lock():
            removed = store.remove(namespace)
        return {"leaf": leaf.id, "pruned": removed}, {"source": "cache"}
    if operation == "get":
        capability = leaf.adapter.capability(parameters)
        with inquiry_session(
            config_file=config_file, startup_url=getattr(capability, "page_url", None)
        ) as session:
            record = leaf.adapter.get(session, parameters, args.detail_identity)
        if not isinstance(record, dict):
            raise CliError("INVALID_RESPONSE", "detail response must be an object")
        _validate_records([record], leaf.manifest.get("identity", []))
        data = _project([record], fields)[0]
        return data, {
            **AcquisitionEvidence(
                scope_complete=True,
                dataset_complete=True,
                collected_total=1,
                reported_total=1,
                arrivals=1,
                unique_count=1,
                duplicate_count=0,
                total_semantics="unique_objects",
            ).meta(),
            "source": "live",
            "leaf": leaf.id,
            "operation": "get",
            "query": {**parameters, "id": args.detail_identity},
            "fetched_at": now().isoformat(),
            "returned_count": 1,
        }
    live = operation == "refresh" or args.live
    ttl = _ttl(config_file)
    with store.refresh_lock() if operation == "refresh" else nullcontext():
        if operation == "refresh" and leaf.installation_token is not None:
            try:
                status = leaf.path.stat()
                current_token = (status.st_dev, status.st_ino, status.st_ctime_ns)
            except OSError as error:
                raise CliError(
                    "LEAF_NOT_FOUND", "Leaf was removed before refresh started"
                ) from error
            if current_token != leaf.installation_token:
                raise CliError(
                    "LEAF_NOT_FOUND", "Leaf installation changed; run refresh again"
                )
        if live:
            capability = leaf.adapter.capability(parameters)
            scope = leaf.adapter.scope(parameters)
            try:
                effective_scope = parse(scope)
            except ValueError:
                effective_scope = scope
            contract_id = _contract_id(leaf, capability)
            fetched_at = now().isoformat()
            with inquiry_session(
                config_file=config_file,
                startup_url=getattr(capability, "page_url", None),
            ) as session:
                transport = session.transport(capability)
                collector = getattr(leaf.adapter, "collector", collect_scope)
                collected = collector(capability, transport, scope)
            rows = _validate_records(
                collected.records, leaf.manifest.get("identity", [])
            )
            evidence = evidence_for(collected)
            query = parameters
            stale = False
            check_complete(
                evidence, require_complete=args.require_complete, mode=operation
            )
            _project(window_rows(rows, limit, offset), fields)
            published = operation == "refresh" and bool(rows)
            if published:
                snapshot = SnapshotMeta(
                    namespace=namespace,
                    capability=leaf.id,
                    scope=canonical(
                        {
                            "parameters": query,
                            "native_scope": effective_scope,
                            "contract_id": contract_id,
                        }
                    ),
                    source_kind="cdp",
                    snapshot_id=hashlib.sha256(canonical(rows).encode()).hexdigest(),
                    dataset_id=None,
                    simulated=False,
                    backend_complete=evidence.scope_complete,
                    dataset_complete=evidence.dataset_complete,
                    fetched_at=fetched_at,
                    loaded_at=fetched_at,
                    source_observed_from=None,
                    source_observed_to=None,
                    row_count=len(rows),
                    acquisition=evidence.record(),
                )
                store.publish(
                    snapshot,
                    [(index, canonical(row)) for index, row in enumerate(rows, 1)],
                )
        else:
            snapshot, stored = store.read(namespace)
            if snapshot is None:
                raise CliError(
                    "CACHE_MISS",
                    f"no cached snapshot; run: dogopencli {leaf.domain} "
                    f"refresh {leaf.name}",
                )
            try:
                rows = _validate_records(
                    [parse(body) for _, body in stored],
                    leaf.manifest.get("identity", []),
                )
                context = parse(snapshot.scope)
                query = context["parameters"]
                effective_scope = context["native_scope"]
                contract_id = context["contract_id"]
                if (
                    not isinstance(query, dict)
                    or len(rows) != snapshot.row_count
                    or [i for i, _ in stored] != list(range(1, len(rows) + 1))
                ):
                    raise ValueError
            except (ValueError, TypeError, KeyError) as exc:
                raise CliError(
                    "INVALID_RESPONSE", "cached snapshot is invalid"
                ) from exc
            capability = leaf.adapter.capability(query)
            if contract_id != _contract_id(leaf, capability):
                raise CliError(
                    "CACHE_CONTRACT_CHANGED",
                    "Leaf contract changed; refresh before replay",
                )
            evidence = AcquisitionEvidence.from_record(snapshot.acquisition)
            fetched_at = snapshot.fetched_at
            stale = is_stale(snapshot, ttl, now())
            if args.require_fresh and stale:
                raise CliError("CACHE_STALE", "saved acquisition is stale")
            check_complete(
                evidence, require_complete=args.require_complete, mode="cache"
            )
            definitions = leaf.manifest["operations"]["list"].get("parameters", [])
            for definition in definitions:
                key = definition["name"].replace("-", "_")
                if key in args.explicit_parameters and not definition.get(
                    "local_field"
                ):
                    raise CliError(
                        "INVALID_ARGUMENT",
                        f"--{definition['name']} has no supported offline filter",
                        exit_code=2,
                    )
            rows = leaf.adapter.filter(
                rows,
                {
                    key: value
                    for key, value in parameters.items()
                    if key in args.explicit_parameters
                },
            )
        matched = len(rows)
        displayed = _project(window_rows(rows, limit, offset), fields)
        source_acquisition = evidence.record()
        requested_coverage = True
        if not live:
            requested_coverage = all(
                key not in args.explicit_parameters
                or parameters.get(key) == value
                or canonical(parameters.get(key)) == canonical(value)
                for key, value in query.items()
            )
            if not requested_coverage:
                evidence = replace(
                    evidence,
                    scope_complete=False,
                    reasons=tuple(
                        dict.fromkeys((*evidence.reasons, "COVERAGE_UNPROVEN"))
                    ),
                )
                check_complete(
                    evidence, require_complete=args.require_complete, mode="cache"
                )
        meta = {
            "leaf": leaf.id,
            "operation": operation,
            "source": "live" if live else "cache",
            "backend": "cdp",
            "simulated": False,
            "query": query,
            "scope": effective_scope,
            "contract_id": contract_id,
            "fetched_at": fetched_at,
            "stale": stale,
            "matched_total": matched,
            "returned_count": len(displayed),
            "has_more": offset + len(displayed) < matched,
            **evidence.meta(),
            "unique_count": evidence.unique_count,
            "duplicate_count": evidence.duplicate_count,
            "total_semantics": evidence.total_semantics,
        }
        if not live:
            meta["source_acquisition"] = source_acquisition
            meta["requested_coverage"] = requested_coverage
            meta["local_filters"] = {
                key: value
                for key, value in parameters.items()
                if key in args.explicit_parameters
            }
            if not matched:
                meta["cache_only_absence"] = (
                    "No matching saved records; backend absence is not established."
                )
        if operation == "refresh":
            meta["published"] = published
            return {
                "leaf": leaf.id,
                "published": published,
                "row_count": len(rows),
            }, prepare_result(meta, mode="refresh")
        return displayed, prepare_result(meta, mode="live" if live else "cache")
