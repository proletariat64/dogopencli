"""Public temporal value parsing and normalization (Issue #127).

Dates are calendar days, clocks are times of day, and datetimes are either
explicit instants (strict ISO 8601 second precision with an offset) or
offset-free native local values whose source timezone stays unknown. No
timezone is ever inferred from the host, tenant, UI label or capture time.
"""

import re
from datetime import datetime

# Native local datetime representation used by liquidity history scopes.
LOCAL_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# Compact native clock representation.
COMPACT_CLOCK_FORMAT = "%H%M%S"

_LOCAL_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}")
_INSTANT_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})"
)
_NUMERIC_OFFSET_PATTERN = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})([+-][0-9]{2}:[0-9]{2})"
)
_CLOCK_PATTERN = re.compile(r"(?:[0-9]{2}:[0-9]{2}:[0-9]{2}|[0-9]{6})")


def parse_iso_instant(value: str) -> datetime:
    """Strict ISO 8601 second-precision instant with an explicit offset.

    Accepts ``Z`` or a numeric ``±HH:MM`` offset; rejects the unknown-offset
    form ``-00:00``, fractional seconds, leap seconds and missing offsets.
    Returns a timezone-aware datetime.
    """
    if not isinstance(value, str) or not _INSTANT_PATTERN.fullmatch(value):
        raise ValueError(f"not an ISO 8601 second-precision instant: {value!r}")
    if value.endswith("-00:00"):
        raise ValueError(f"unknown-offset -00:00 carries no instant: {value!r}")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")


def parse_numeric_offset_instant(value: str) -> datetime:
    """Like :func:`parse_iso_instant` but only explicit numeric ``±HH:MM``
    offsets; the UTC designator ``Z`` is not a numeric offset."""
    if not isinstance(value, str) or not _NUMERIC_OFFSET_PATTERN.fullmatch(value):
        raise ValueError(f"not a numeric-offset instant: {value!r}")
    if value.endswith("-00:00"):
        raise ValueError(f"unknown-offset -00:00 carries no instant: {value!r}")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")


def normalize_local_datetime(value: str) -> str:
    """Offset-free local datetime to the native ``YYYY-MM-DD HH:mm:ss`` form.

    Accepts the canonical ``T`` syntax and the legacy space-separated syntax;
    rejects offset-bearing values because no source-zone conversion is
    established.
    """
    if not isinstance(value, str) or not _LOCAL_PATTERN.fullmatch(value):
        raise ValueError(f"not an offset-free local datetime: {value!r}")
    parsed = datetime.strptime(value[:10] + " " + value[11:], LOCAL_DATETIME_FORMAT)
    return parsed.strftime(LOCAL_DATETIME_FORMAT)


def normalize_clock(value: str) -> str:
    """Time of day to the native compact ``HHmmss`` representation.

    Accepts the canonical colon form ``HH:mm:ss`` and the legacy compact
    form ``HHmmss``.
    """
    if not isinstance(value, str) or not _CLOCK_PATTERN.fullmatch(value):
        raise ValueError(f"not a time of day: {value!r}")
    compact = value.replace(":", "")
    parsed = datetime.strptime(compact, COMPACT_CLOCK_FORMAT)
    return parsed.strftime(COMPACT_CLOCK_FORMAT)
