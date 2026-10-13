"""Offline snapshot reads, source identity, quality policy and metadata.

Domain filtering and SLA list/detail projection remain with their callers.
This layer never reads source files and never attempts an implicit refresh.
"""

from collections.abc import Callable, Hashable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from .cache import Cache, SnapshotMeta
from .config import Config, SourceConfig
from .errors import (
    CACHE_MISS,
    CACHE_STALE,
    INCOMPLETE_RESULT,
    INVALID_RESPONSE,
    CliError,
)
from .jsonutil import parse
from .result_policy import AcquisitionEvidence, check_complete
from .temporary_query import query_namespace as namespace
from .temporary_query import slot_context


def snapshot_meta(
    source: str | None,
    snapshot: SnapshotMeta,
    stale: bool,
    matched_total: int,
    returned_count: int,
    has_more: bool,
) -> dict[str, Any]:
    result = {
        "source": source,
        "backend": snapshot.source_kind,
        "simulated": snapshot.simulated,
        "scope": snapshot.scope,
        "snapshot_id": snapshot.snapshot_id,
        "dataset_id": snapshot.dataset_id,
        "fetched_at": snapshot.fetched_at,
        "loaded_at": snapshot.loaded_at,
        "stale": stale,
        "complete": snapshot.backend_complete,
        "dataset_complete": snapshot.dataset_complete,
        "source_observed_from": snapshot.source_observed_from,
        "source_observed_to": snapshot.source_observed_to,
        "matched_total": matched_total,
        "returned_count": returned_count,
        "has_more": has_more,
    }
    evidence = (
        AcquisitionEvidence.from_record(snapshot.acquisition)
        if snapshot.acquisition is not None
        else AcquisitionEvidence(
            scope_complete=snapshot.backend_complete,
            dataset_complete=snapshot.dataset_complete,
            collected_total=snapshot.row_count,
        )
    )
    result.update(evidence.meta())
    if snapshot.scope.startswith("{"):
        context = parse(snapshot.scope)
        if isinstance(context, dict) and "query" in context:
            result.update(slot_context(snapshot))
        else:
            result["query"] = context
    else:
        result["query"] = {"scope": snapshot.scope}
    if isinstance(result.get("query"), dict) and "scope" in result["query"]:
        result["scope"] = result["query"]["scope"]
    return result


def is_stale(snapshot: SnapshotMeta, ttl_hours: float, now: datetime) -> bool:
    return now > datetime.fromisoformat(
        snapshot.fetched_at.replace("Z", "+00:00")
    ) + timedelta(hours=ttl_hours)


@dataclass(frozen=True)
class CachedQuery:
    snapshot: SnapshotMeta
    stored: list[tuple[int, str]]
    stale: bool

    def validated_records(
        self,
        validate: Callable[[Any], None],
        identity: Callable[[dict[str, Any]], Hashable],
        *,
        coverage_error: str,
    ) -> list[dict[str, Any]]:
        """Decode and validate the whole snapshot before exposing any records.

        Domain validators own row/pair shape; this module owns storage decoding
        and coverage. Quality gates run at read time, before record validation.
        """
        records = []
        for _, body in self.stored:
            try:
                record = parse(body)
            except ValueError as error:
                raise CliError(
                    INVALID_RESPONSE, "cached record is not valid JSON"
                ) from error
            if not isinstance(record, dict):
                raise CliError(INVALID_RESPONSE, "cached record is not an object")
            validate(record)
            records.append(record)
        if len(self.stored) != self.snapshot.row_count or [
            seqid for seqid, _ in self.stored
        ] != list(range(1, self.snapshot.row_count + 1)):
            raise CliError(INCOMPLETE_RESULT, coverage_error)
        identities: set[Hashable] = set()
        for record in records:
            try:
                key = identity(record)
                if key in identities:
                    raise CliError(INCOMPLETE_RESULT, coverage_error)
                identities.add(key)
            except (KeyError, TypeError, ValueError) as error:
                raise CliError(
                    INVALID_RESPONSE, "cached record identity is invalid"
                ) from error
        return records

    def meta(
        self,
        matched_total: int,
        returned_count: int,
        *,
        offset: int = 0,
        local_filters: dict | None = None,
        requested_coverage: bool | None = True,
    ) -> dict[str, Any]:
        meta = snapshot_meta(
            "cache",
            self.snapshot,
            self.stale,
            matched_total,
            returned_count,
            offset + returned_count < matched_total,
        )
        meta["source_acquisition"] = meta["acquisition"]
        meta["local_filters"] = local_filters or {}
        meta["requested_coverage"] = requested_coverage
        if matched_total == 0:
            meta["cache_only_absence"] = (
                "No matching rows in the saved acquisition; "
                "backend absence is not established."
            )
        if requested_coverage is not True:
            evidence = AcquisitionEvidence.from_record(meta["acquisition"])
            evidence = replace(
                evidence,
                scope_complete=False,
                reasons=tuple(dict.fromkeys((*evidence.reasons, "COVERAGE_UNPROVEN"))),
            )
            meta.update(evidence.meta())
        return meta


def read_cached_query(
    config: Config,
    source: SourceConfig,
    capability: str,
    scope: str,
    *,
    refresh_command: str,
    require_fresh: bool,
    require_complete: bool,
    now: datetime,
) -> CachedQuery:
    """Read once; reject missing/foreign, stale, then incomplete snapshots.

    Identity compares publication metadata, so an imported dataset remains
    available after its source files have been removed.
    """
    try:
        store = Cache(config.cache_path)
        store.ensure_temporary_format()
        snapshot, stored = store.read(namespace(capability, scope, source.kind))
    except CliError as error:
        if error.code != INVALID_RESPONSE:
            raise
        raise CliError(
            error.code,
            f"cached {capability}: {error.message}",
            retryable=error.retryable,
            exit_code=error.exit_code,
            meta=error.meta,
        ) from error
    hint = f"run: dogopencli {refresh_command}"
    if snapshot is None:
        raise CliError(CACHE_MISS, f"no cached snapshot; {hint}")
    stale = is_stale(snapshot, config.ttl_hours, now)
    if require_fresh and stale:
        raise CliError(
            CACHE_STALE,
            f"cached snapshot is older than {config.ttl_hours:g} hours"
            f" (fetched_at {snapshot.fetched_at})",
        )
    evidence = (
        AcquisitionEvidence.from_record(snapshot.acquisition)
        if snapshot.acquisition is not None
        else AcquisitionEvidence(
            scope_complete=snapshot.backend_complete,
            dataset_complete=snapshot.dataset_complete,
            collected_total=snapshot.row_count,
        )
    )
    check_complete(evidence, require_complete=require_complete, mode="cache")
    return CachedQuery(snapshot, stored, stale)
