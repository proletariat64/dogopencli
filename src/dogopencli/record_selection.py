"""Record choice and selection facts within one independent acquisition.

Pagination and native source coverage belong to the caller. A selector is never
shared across width candidates, native sources or independent exports.
"""

from typing import Any

from .errors import INVALID_RESPONSE, CliError
from .jsonutil import canonical


def record_identity(
    row: dict[str, Any],
    primary_id: dict[str, Any],
    sources: dict[str, str],
) -> str:
    """Compute an internal, type-aware identity; never decorate a native row."""
    import hashlib

    values: list[Any] = []
    for field in primary_id["fields"]:
        value = row.get(field)
        if (
            field not in row
            or isinstance(value, (dict, list))
            or (
                (value is None or (isinstance(value, str) and not value.strip()))
                and not primary_id.get("allow_empty_components", False)
            )
        ):
            raise CliError(INVALID_RESPONSE, f"missing native identity field {field}")
        values.append(value)
    try:
        encoded = canonical(values)
    except (TypeError, ValueError, OverflowError) as error:
        raise CliError(INVALID_RESPONSE, "invalid native identity value") from error
    if primary_id["type"] == "field":
        return encoded
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    previous = sources.setdefault(digest, encoded)
    if previous != encoded:
        raise CliError(INVALID_RESPONSE, "composite primary identity hash collision")
    return digest


def _list_timestamp(value: Any) -> tuple[str, Any]:
    """Comparable native times; do not infer time zones or coerce invalid values."""
    from datetime import datetime, timezone
    from decimal import Decimal

    if type(value) in (int, float, Decimal):
        try:
            number = Decimal(str(value))
        except (ValueError, ArithmeticError) as error:
            raise CliError(INVALID_RESPONSE, "invalid identity timestamp") from error
        if not number.is_finite():
            raise CliError(INVALID_RESPONSE, "non-finite identity timestamp")
        return ("numeric", number)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "invalid identity timestamp") from error
        if parsed.tzinfo is None:
            raise CliError(INVALID_RESPONSE, "timestamp requires explicit timezone")
        return ("datetime", parsed.astimezone(timezone.utc))
    raise CliError(INVALID_RESPONSE, "missing or invalid identity timestamp")


class RecordSelection:
    """Own identity, arrival order, version choice and their evidence together."""

    def __init__(
        self,
        primary_id: dict,
        latest_by: str | None = None,
        *,
        count_source_contents: bool = False,
    ) -> None:
        self.primary_id = primary_id
        self.latest_by = latest_by
        self.has_identity = primary_id["type"] != "unproven"
        self.records: list[dict] = []
        self.arrivals = 0
        self.duplicates = 0
        self.conflicts = 0
        self.ties = 0
        self._positions: dict[str, int] = {}
        self._hashes: dict[str, str] = {}
        self._contents: set[str] = set()
        self._count_contents = count_source_contents or latest_by is not None
        self._unproven_contents: set[str] = set()
        self.unproven_overlap = False

    def identity(self, row: dict) -> str:
        return record_identity(row, self.primary_id, self._hashes)

    def add(self, row: dict) -> None:
        self.arrivals += 1
        if not self.has_identity:
            content = canonical(row)
            self.unproven_overlap |= content in self._unproven_contents
            self._unproven_contents.add(content)
            self.records.append(row)
            return
        if self.latest_by is not None:
            order = _list_timestamp(row.get(self.latest_by))
            if (
                self.records
                and order[0] != _list_timestamp(self.records[0].get(self.latest_by))[0]
            ):
                raise CliError(INVALID_RESPONSE, "mixed native timestamp formats")
        record_id = self.identity(row)
        if self._count_contents:
            self._contents.add(canonical(row))
        previous_index = self._positions.get(record_id)
        if previous_index is None:
            self._positions[record_id] = len(self.records)
            self.records.append(row)
            return
        self.duplicates += 1
        previous = self.records[previous_index]
        if canonical(row) == canonical(previous):
            return
        self.conflicts += 1
        if self.latest_by is None:
            self.records[previous_index] = row
        else:
            newer = _list_timestamp(row.get(self.latest_by))
            older = _list_timestamp(previous.get(self.latest_by))
            if newer[0] != older[0]:
                raise CliError(INVALID_RESPONSE, "mixed native timestamp formats")
            self.ties += int(newer[1] == older[1])
            if newer[1] >= older[1]:
                self.records[previous_index] = row

    @property
    def selection(self) -> dict | None:
        if self.latest_by is None:
            return None
        return {
            "latest_by": self.latest_by,
            "resolved_version_count": len(self._contents) - len(self.records),
            "equal_order_count": self.ties,
            "identical_duplicate_count": self.arrivals - len(self._contents),
        }

    def coverage_count(self, total_semantics: str) -> int:
        return (
            len(self._contents)
            if total_semantics == "source_row_occurrences"
            else len(self.records)
        )

    def reasons(self, *, include_selected_duplicates: bool = False) -> list[str]:
        reasons = []
        if self.duplicates and (self.latest_by is None or include_selected_duplicates):
            reasons.append("CROSS_PAGE_OR_INTRA_PAGE_DUPLICATES")
        if self.conflicts:
            reasons.append(
                "LATEST_BY_SELECTION" if self.latest_by else "IDENTITY_CONTENT_CONFLICT"
            )
            if self.latest_by is None:
                reasons.append("LAST_ARRIVAL_WINS")
        if self.ties:
            reasons.append("LATEST_BY_TIE")
        return reasons
