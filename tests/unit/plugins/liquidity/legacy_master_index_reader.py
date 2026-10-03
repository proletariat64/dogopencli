"""Exact legacy master index reader and its required native dependencies.

Source: src/dogopencli/plugins/liquidity/store.py
Commit: 308d5c448abad01478330729555204a05e90d59b
Whole-source SHA256: dbde3b0fcd40c55c7cca990fe4028ac6c9c17d631f81f863710ca9b557e5925a
Functions/classes below are copied verbatim, with their original decorators.
Only unused imports and unrelated acquisition/retention functions are omitted.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dogopencli.cache import Cache, namespace
from dogopencli.errors import INVALID_RESPONSE, CliError
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity import spec

INDEX_SCOPE = "__index__"


SOURCE_KIND = "cdp"


ENTRY_CAPTURE = "capture"


ENTRY_RETENTION = "retention"


def _invalid(message: str) -> CliError:
    return CliError(INVALID_RESPONSE, message)


@dataclass(frozen=True)
class CaptureEntry:
    """One retained list capture tracked by the leaf index."""

    namespace: str
    scope: str
    window_from: str | None
    window_to: str | None
    profile: str
    fetched_at: str
    row_count: int
    reported_total: int | None
    snapshot_id: str
    # Cache identity beyond the namespace: the mandatory business kind and
    # the source origin/tenant this capture was acquired from.
    kind: str | None = None
    source_origin: str | None = None
    tenant: str | None = None
    # Exact retention holes; a later missing day must not erase earlier
    # verified empty days in this capture's acquisition window.
    missing_days: tuple[str, ...] = ()

    def record(self) -> dict[str, Any]:
        return {
            "type": ENTRY_CAPTURE,
            "namespace": self.namespace,
            "scope": self.scope,
            "window_from": self.window_from,
            "window_to": self.window_to,
            "profile": self.profile,
            "fetched_at": self.fetched_at,
            "row_count": self.row_count,
            "reported_total": self.reported_total,
            "snapshot_id": self.snapshot_id,
            "kind": self.kind,
            "source_origin": self.source_origin,
            "tenant": self.tenant,
            "missing_days": list(self.missing_days),
        }

    @staticmethod
    def from_record(record: dict[str, Any]) -> "CaptureEntry":
        namespace_value = record.get("namespace")
        scope_value = record.get("scope")
        fetched_at = record.get("fetched_at")
        row_count = record.get("row_count")
        snapshot_id = record.get("snapshot_id")
        if (
            not isinstance(namespace_value, str)
            or not isinstance(scope_value, str)
            or not isinstance(fetched_at, str)
            or isinstance(row_count, bool)
            or not isinstance(row_count, int)
            or not isinstance(snapshot_id, str)
        ):
            raise _invalid("cached capture index is invalid")
        window_from = record.get("window_from")
        window_to = record.get("window_to")
        reported_total = record.get("reported_total")
        profile = record.get("profile")
        if profile not in (
            spec.PROFILE_SNAPSHOT,
            spec.PROFILE_HISTORY,
            spec.PROFILE_DATED,
        ):
            raise _invalid("cached capture profile is invalid")
        kind = record.get("kind")
        source_origin = record.get("source_origin")
        tenant = record.get("tenant")
        missing_days = record.get("missing_days", [])
        if not isinstance(missing_days, list) or any(
            not isinstance(day, str) for day in missing_days
        ):
            raise _invalid("cached capture missing days are invalid")
        for day in missing_days:
            try:
                if datetime.strptime(day, "%Y%m%d").strftime("%Y%m%d") != day:
                    raise ValueError
            except ValueError as error:
                raise _invalid("cached capture missing days are invalid") from error
        return CaptureEntry(
            namespace=namespace_value,
            scope=scope_value,
            window_from=window_from if isinstance(window_from, str) else None,
            window_to=window_to if isinstance(window_to, str) else None,
            profile=profile,
            fetched_at=fetched_at,
            row_count=row_count,
            reported_total=(
                reported_total
                if isinstance(reported_total, int)
                and not isinstance(reported_total, bool)
                else None
            ),
            snapshot_id=snapshot_id,
            kind=kind if isinstance(kind, str) else None,
            source_origin=source_origin if isinstance(source_origin, str) else None,
            tenant=tenant if isinstance(tenant, str) else None,
            missing_days=tuple(sorted(set(missing_days))),
        )


@dataclass
class IndexData:
    captures: list[CaptureEntry] = field(default_factory=list)
    evictions: list[dict[str, Any]] = field(default_factory=list)


def index_namespace(capability: str) -> str:
    return namespace(capability, INDEX_SCOPE, SOURCE_KIND)


def read_index(store: Cache, capability: str) -> IndexData | None:
    snapshot, stored = store.read(index_namespace(capability))
    if snapshot is None:
        return None
    data = IndexData()
    for _, body in stored:
        record = parse(body)
        if not isinstance(record, dict):
            raise _invalid("cached capture index is invalid")
        entry_type = record.get("type")
        if entry_type == ENTRY_CAPTURE:
            data.captures.append(CaptureEntry.from_record(record))
        elif entry_type == ENTRY_RETENTION:
            data.evictions.append(record)
        else:
            raise _invalid("cached capture index is invalid")
    return data
