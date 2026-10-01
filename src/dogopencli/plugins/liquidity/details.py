"""Per-object native-detail storage (ADR 0016).

Detail acquisition is independent of list acquisition: each explicit detail
refresh upserts exactly one object's genuine native detail with its own
identity and fetch time; a failed detail refresh publishes nothing and never
invalidates a separately successful list refresh. Offline ``get`` reads only
this store — never a list-row substitute — and a missing cached detail is a
cache/coverage miss with a detail-refresh hint, never proof that the
business object does not exist.
"""

import hashlib
from dataclasses import dataclass
from typing import Any

from ...cache import Cache, SnapshotMeta, namespace
from ...errors import INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from ...jsonutil import canonical, parse
from . import spec

DETAIL_SCOPE = "detail"
SOURCE_KIND = "cdp"


def _invalid(message: str) -> CliError:
    return CliError(INVALID_RESPONSE, message)


@dataclass(frozen=True)
class StoredDetail:
    key: str
    detail: Any
    fetched_at: str


def details_namespace(capability: str) -> str:
    return namespace(capability, DETAIL_SCOPE, SOURCE_KIND)


def detail_key(values: dict[str, str]) -> str:
    """Canonical storage key from validated identity option values."""
    return "|".join(f"{flag}={values[flag]}" for flag in sorted(values))


def read_details(store: Cache, capability: str) -> dict[str, StoredDetail]:
    snapshot, stored = store.read(details_namespace(capability))
    details: dict[str, StoredDetail] = {}
    if snapshot is None:
        return details
    for _, body in stored:
        record = parse(body)
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("key"), str)
            or not isinstance(record.get("fetched_at"), str)
            or "detail" not in record
        ):
            raise _invalid("cached detail record is invalid")
        details[record["key"]] = StoredDetail(
            key=record["key"],
            detail=record["detail"],
            fetched_at=record["fetched_at"],
        )
    if len(details) != snapshot.row_count:
        raise _invalid("cached detail coverage is invalid")
    return details


def read_detail_snapshot(store: Cache, capability: str) -> SnapshotMeta | None:
    return store.current(details_namespace(capability))


def upsert_detail(
    store: Cache,
    capability: str,
    key: str,
    detail: Any,
    fetched_at: str,
    loaded_at: str,
    *,
    cap: int = spec.RETENTION_CAP,
) -> SnapshotMeta:
    """Atomically replace the detail store with one object upserted.

    Details are not a time series: exceeding the per-leaf cap rejects the
    refresh and preserves the previous valid store (ADR 0017).
    """
    existing = read_details(store, capability)
    if key not in existing and len(existing) >= cap:
        raise CliError(
            INVALID_ARGUMENT,
            f"{capability} already retains {cap} details, at the retention"
            " cap; refresh rejected and the previous cache is retained",
        )
    existing[key] = StoredDetail(key=key, detail=detail, fetched_at=fetched_at)
    records = [
        {"key": entry.key, "detail": entry.detail, "fetched_at": entry.fetched_at}
        for entry in sorted(existing.values(), key=lambda entry: entry.key)
    ]
    snapshot = SnapshotMeta(
        namespace=details_namespace(capability),
        capability=capability,
        scope=DETAIL_SCOPE,
        source_kind=SOURCE_KIND,
        snapshot_id=hashlib.sha256(canonical(records).encode()).hexdigest(),
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at=fetched_at,
        loaded_at=loaded_at,
        source_observed_from=None,
        source_observed_to=None,
        row_count=len(records),
    )
    store.publish(
        snapshot,
        [(index, canonical(record)) for index, record in enumerate(records, 1)],
    )
    return snapshot
