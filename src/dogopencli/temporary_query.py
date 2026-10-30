"""Generic output window and freshness helpers for installed leaf queries."""

from datetime import datetime, timedelta
from typing import Any

from .cache import SnapshotMeta
from .errors import CliError


def is_stale(snapshot: SnapshotMeta, ttl_hours: float, now: datetime) -> bool:
    return now > datetime.fromisoformat(
        snapshot.fetched_at.replace("Z", "+00:00")
    ) + timedelta(hours=ttl_hours)


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


def list_preview_metadata(
    matched: int,
    returned: int,
    limit: int,
    offset: int,
    *,
    custom_detail: bool | None = None,
) -> dict:
    """Describe the current display window independently of acquisition facts."""
    meta = {
        "matched_total": matched,
        "returned_count": returned,
        "has_more": offset + returned < matched,
    }
    if custom_detail is not None:
        meta.update(
            with_detail=True,
            detail_scope="custom" if custom_detail else "native_root",
            detail_count=returned,
            detail_window={"offset": offset, "limit": limit},
            detail_coverage=(
                "Only selected List rows; each custom Get follows its "
                "declared leaf relationship and coverage contract. "
                "Detail success does not expand List coverage."
                if custom_detail
                else "Only selected List rows; "
                "one native root response per row. "
                "Separate histories, logs and child pages are not acquired. "
                "Detail success does not expand List coverage."
            ),
        )
    return meta
