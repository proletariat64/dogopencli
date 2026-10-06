"""Pure public temporal value parsing and normalization (Issue #127)."""

from datetime import timedelta, timezone

import pytest

from dogopencli.temporal import (
    normalize_clock,
    normalize_local_datetime,
    parse_iso_instant,
    parse_numeric_offset_instant,
)

UTC = timezone.utc
SHANGHAI = timezone(timedelta(hours=8))


class TestParseIsoInstant:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00+00:00"),
            ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            ("2026-01-01T08:00:00+08:00", "2026-01-01T00:00:00+00:00"),
            # UTC/+08 day rollover in both directions.
            ("2026-01-01T00:00:00+08:00", "2025-12-31T16:00:00+00:00"),
            ("2025-12-31T20:00:00-04:00", "2026-01-01T00:00:00+00:00"),
            ("2024-02-29T23:59:59Z", "2024-02-29T23:59:59+00:00"),
        ],
    )
    def test_equivalent_instants(self, value, expected):
        parsed = parse_iso_instant(value)
        assert parsed.astimezone(UTC).isoformat() == expected
        assert parsed.tzinfo is not None

    @pytest.mark.parametrize(
        "value",
        [
            "2026-01-01T00:00:00-00:00",  # unknown-offset form
            "2026-01-01T00:00:00",  # missing offset on a canonical instant
            "2026-01-01 00:00:00",  # space form is not an ISO instant
            "2026-01-01T00:00:00.5Z",  # fractional seconds
            "2026-01-01T00:00:00.000+08:00",  # fractional seconds
            "2026-01-01T23:59:60Z",  # leap second
            "2026-01-01t00:00:00Z",  # lowercase t
            "2026-01-01T00:00:00z",  # lowercase z
            "2026-01-01T00:00:00+0800",  # compact offset
            "2026-01-01T00:00:00+08",  # short offset
            "2026-01-01T00:00:00+24:00",  # out-of-range offset
            "2026-01-01",  # date only
            "2026-02-30T00:00:00Z",  # invalid day
            "2026-01-01T24:00:00Z",  # invalid hour
            "",
            " 2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z ",
        ],
    )
    def test_rejections(self, value):
        with pytest.raises(ValueError):
            parse_iso_instant(value)

    def test_non_string_rejected(self):
        with pytest.raises(ValueError):
            parse_iso_instant(None)


class TestParseNumericOffsetInstant:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("2025-01-01T00:00:00+08:00", "2025-01-01T00:00:00+08:00"),
            ("2024-12-31T16:00:00+00:00", "2025-01-01T00:00:00+08:00"),
            ("2024-12-31T11:00:00-05:00", "2025-01-01T00:00:00+08:00"),
        ],
    )
    def test_equivalent_instants(self, value, expected):
        parsed = parse_numeric_offset_instant(value)
        assert parsed.astimezone(SHANGHAI).isoformat() == expected

    @pytest.mark.parametrize(
        "value",
        [
            "2025-01-01T00:00:00Z",  # Z is not a numeric offset
            "2025-01-01T00:00:00-00:00",
            "2025-01-01T00:00:00",
            "2025-01-01 00:00:00+08:00",
            "2025-01-01T00:00:00.001+08:00",
            "2025-01-01T23:59:60+08:00",
            "2025-01-01T00:00:00+0800",
            "2025-02-30T00:00:00+08:00",
        ],
    )
    def test_rejections(self, value):
        with pytest.raises(ValueError):
            parse_numeric_offset_instant(value)


class TestNormalizeLocalDatetime:
    @pytest.mark.parametrize(
        "value",
        ["2026-09-30T00:00:00", "2026-09-30 00:00:00"],
    )
    def test_canonical_and_legacy_normalize_identically(self, value):
        assert normalize_local_datetime(value) == "2026-09-30 00:00:00"

    @pytest.mark.parametrize(
        "value",
        [
            "2026-09-30T00:00:00Z",  # offset-bearing
            "2026-09-30T00:00:00+08:00",  # offset-bearing
            "2026-09-30T00:00:00-00:00",
            "2026-09-30T00:00:00.5",  # fractional
            "2026-09-30 00:00:00 ",  # trailing space
            "2026-09-30",  # date only
            "2026-09-30T23:59:60",  # leap second
            "2026-02-30T00:00:00",
            "2026-09-30t00:00:00",
            "",
        ],
    )
    def test_rejections(self, value):
        with pytest.raises(ValueError):
            normalize_local_datetime(value)


class TestNormalizeClock:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("00:00:00", "000000"),
            ("000000", "000000"),
            ("23:59:59", "235959"),
            ("235959", "235959"),
            ("09:15:00", "091500"),
        ],
    )
    def test_canonical_and_legacy_normalize_identically(self, value, expected):
        assert normalize_clock(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            "24:00:00",
            "240000",
            "23:59:60",
            "235960",
            "1261",
            "09:15",
            "09:15:00.5",
            "9:15:00",
            "09150",
            "",
            " 091500",
        ],
    )
    def test_rejections(self, value):
        with pytest.raises(ValueError):
            normalize_clock(value)
