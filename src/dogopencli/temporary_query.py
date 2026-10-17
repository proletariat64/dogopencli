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
