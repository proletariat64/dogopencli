"""Native business-date validation; no capture history or retention storage."""

from datetime import datetime
from typing import Any

from ...errors import INVALID_RESPONSE, CliError
from . import spec


def _invalid(message):
    return CliError(INVALID_RESPONSE, message)


def _format_series_time(value: datetime, format_string: str) -> str:
    """Keep the declared format while padding years on every platform."""
    return value.strftime(format_string.replace("%Y", f"{value.year:04d}"))


def series_value(
    list_spec: spec.ListSpec, record: dict[str, Any], fetched_at: str
) -> str:
    """Verified series axis of one record; unknown ordering rejects refresh."""
    if list_spec.profile == spec.PROFILE_DATED:
        field_name = list_spec.series_field
        value = record.get(field_name) if field_name else None
        if not isinstance(value, str) or not value.strip():
            raise _invalid(
                f"record is missing its verified series time {field_name};"
                " business-date filtering is unavailable"
            )
        if list_spec.series_format is not None:
            try:
                parsed = datetime.strptime(value, list_spec.series_format)
                if _format_series_time(parsed, list_spec.series_format) != value:
                    raise ValueError
            except ValueError as error:
                raise _invalid(
                    f"record has invalid series time {field_name}"
                ) from error
            return _format_series_time(parsed, "%Y%m%d")
        return value
    # Capture-history records order by capture time explicitly (ADR 0017);
    # capture time is never relabelled as source observation time.
    return fetched_at
