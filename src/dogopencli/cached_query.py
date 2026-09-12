"""Offline snapshot reads, source identity, quality policy and metadata.

Domain filtering and SLA list/detail projection remain with their callers.
This layer never reads source files and never attempts an implicit refresh.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .cache import Cache, SnapshotMeta, namespace
from .config import SOURCE_SNAPSHOT, Config, SourceConfig
from .errors import CACHE_MISS, CACHE_STALE, INCOMPLETE_RESULT, CliError


def snapshot_meta(
    source: str | None,
    snapshot: SnapshotMeta,
    stale: bool,
    matched_total: int,
    returned_count: int,
    has_more: bool,
) -> dict[str, Any]:
    return {
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


def is_stale(snapshot: SnapshotMeta, ttl_hours: float, now: datetime) -> bool:
    return now > datetime.fromisoformat(
        snapshot.fetched_at.replace("Z", "+00:00")
    ) + timedelta(hours=ttl_hours)


@dataclass(frozen=True)
class CachedQuery:
    snapshot: SnapshotMeta
    stored: list[tuple[int, str]]
    stale: bool

    def meta(
        self, matched_total: int, returned_count: int, *, offset: int = 0
    ) -> dict[str, Any]:
        return snapshot_meta(
            "cache",
            self.snapshot,
            self.stale,
            matched_total,
            returned_count,
            offset + returned_count < matched_total,
        )


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
    snapshot, stored = Cache(config.cache_path).read(
        namespace(capability, scope, source.kind)
    )
    hint = f"run: dogopencli {refresh_command}"
    if snapshot is None:
        raise CliError(CACHE_MISS, f"no cached snapshot; {hint}")
    if (source.dataset_id is not None and snapshot.dataset_id != source.dataset_id) or (
        source.kind == SOURCE_SNAPSHOT
        and snapshot.source_path != str(source.path.expanduser().resolve())
    ):
        raise CliError(
            CACHE_MISS,
            f"cached dataset does not match the configured source identity; {hint}",
        )
    stale = is_stale(snapshot, config.ttl_hours, now)
    if require_fresh and stale:
        raise CliError(
            CACHE_STALE,
            f"cached snapshot is older than {config.ttl_hours:g} hours"
            f" (fetched_at {snapshot.fetched_at})",
        )
    if require_complete and not snapshot.backend_complete:
        raise CliError(
            INCOMPLETE_RESULT,
            "cached snapshot does not cover the complete backend scope",
        )
    return CachedQuery(snapshot, stored, stale)
