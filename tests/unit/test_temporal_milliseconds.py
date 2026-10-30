"""Public opt-in temporal parsing keeps exact millisecond precision."""

from datetime import date, datetime, timezone

import pytest

from dogopencli import temporal


def test_millisecond_input_normalizes_offset_without_rounding():
    assert (
        temporal.normalize_utc_milliseconds("2026-10-16T09:30:00.123+08:00")
        == "2026-10-16T01:30:00.123Z"
    )
    assert temporal.parse_date_or_instant("2026-10-16") == date(2026, 10, 16)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-10-16T01:30:00Z", "2026-10-16T01:30:00.000Z"),
        ("2026-10-16T01:30:00.1Z", "2026-10-16T01:30:00.100Z"),
        ("2026-10-16T01:30:00.12Z", "2026-10-16T01:30:00.120Z"),
        ("2026-10-16T00:30:00.999-01:00", "2026-10-16T01:30:00.999Z"),
    ],
)
def test_explicit_instant_precision_and_offsets(value, expected):
    assert temporal.normalize_utc_milliseconds(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-16T01:30:00.1234Z",
        "2026-10-16T01:30:00-00:00",
        "2026-10-16T01:30:00",
        "2026-10-16 01:30:00Z",
        "2026-02-30",
        "20261016",
        "2026-10-16T01:30:60Z",
        "2026-10-16T01:30:00+24:00",
    ],
)
def test_date_or_instant_rejects_unknown_or_unrepresentable_input(value):
    with pytest.raises(ValueError):
        temporal.parse_date_or_instant(value)


def test_normalization_rejects_naive_or_submillisecond_datetime():
    for value in [
        datetime(2026, 10, 16),
        datetime(2026, 10, 16, microsecond=1, tzinfo=timezone.utc),
    ]:
        with pytest.raises(ValueError):
            temporal.normalize_utc_milliseconds(value)
