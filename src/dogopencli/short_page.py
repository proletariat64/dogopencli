"""Bounded positional traversal; native parsing and transport stay in collect.

Two successful empty batches at the original stride terminate the inquiry.
Local subdivisions prove stable omissions without mixing repeated probe rows
into the output. Saved holes are hints, revalidated with neighboring identities.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from .errors import INVALID_RESPONSE, REQUEST_NOT_ALLOWED, CliError
from .jsonutil import canonical


class RecordHole(Exception):
    """An explicitly leaf-classified record error, never a generic failure."""

    def __init__(self, fingerprint: str):
        self.fingerprint = fingerprint


class TerminalPage(Exception):
    """A leaf-qualified repeated short last page, with original native echoes."""

    def __init__(self, witness: dict):
        self.witness = witness


@dataclass
class _Page:
    rows: list[dict[str, Any]] | None
    fingerprint: str = "empty"
    terminal: dict | None = None


class ShortPageWalk:
    def __init__(
        self,
        read: Callable[[int, int], list[dict[str, Any]]],
        identity: Callable[[dict], str],
        *,
        size: int,
        sizes: set[int],
        numbered: bool,
        observations: list[dict],
        retain_final_short: bool = False,
    ):
        self.fetch = read
        self.identity = identity
        self.size = size
        self.sizes = sorted((w for w in sizes if 0 < w <= size), reverse=True)
        self.numbered = numbered
        self.observations = observations
        self.retain_final_short = retain_final_short
        self.cache: dict[tuple[int, int], _Page] = {}
        self.pieces: list[tuple[int, int, _Page]] = []
        self.unresolved: list[tuple[int, int]] = []
        self.history_checked = 0
        self.history_matched = 0
        self.end = 0
        self.terminal_batches: list[dict] = []

    def read(self, start: int, size: int) -> _Page:
        key = (start, size)
        if key not in self.cache:
            try:
                self.cache[key] = _Page(self.fetch(start, size))
            except RecordHole as error:
                self.cache[key] = _Page(None, error.fingerprint)
            except TerminalPage as end:
                self.cache[key] = _Page([], terminal=end.witness)
        return self.cache[key]

    def width(self, start: int, limit: int) -> int:
        for size in self.sizes:
            if size <= limit and (not self.numbered or start % size == 0):
                return size
        raise CliError(
            REQUEST_NOT_ALLOWED,
            "short-page localization needs endpoint-qualified smaller widths",
        )

    def cover(self, lo: int, hi: int) -> Iterator[tuple[int, int]]:
        while lo < hi:
            size = self.width(lo, hi - lo)
            yield lo, size
            lo += size

    def piece(self, start: int, size: int, page: _Page) -> None:
        self.pieces.append((start, start + size, page))
        if page.rows:
            self.end = max(self.end, start + len(page.rows))
        elif page.rows is None:
            self.end = max(self.end, start + size)
        if not page.rows:
            self.observations.append(
                {
                    "start": start,
                    "end": start + size,
                    "kind": "error" if page.rows is None else "empty",
                    "fingerprint": page.fingerprint,
                }
            )

    def inspect(self, start: int, size: int, page: _Page) -> list[dict]:
        if page.rows is not None and len(page.rows) in (0, size):
            self.piece(start, size, page)
            return page.rows
        if size == 1:
            self.piece(start, size, page)
            return []
        if 1 not in self.sizes:
            # A fixed-width normal final short page still works. An interior
            # short page cannot be excused without qualified local probes.
            if page.rows is None:
                raise CliError(
                    REQUEST_NOT_ALLOWED, "record-hole recovery requires width one"
                )
            self.unresolved.append((start, start + size))
            self.piece(start, size, page)
            return page.rows
        middle = start + size // 2
        rows = []
        for lo, hi in ((start, middle), (middle, start + size)):
            for position, width in self.cover(lo, hi):
                rows.extend(self.inspect(position, width, self.read(position, width)))
        if page.rows is not None and canonical(rows) != canonical(page.rows):
            raise CliError(
                INVALID_RESPONSE,
                "native records changed across short-page subdivisions",
            )
        return rows

    def matches(self, hole: dict) -> bool:
        if 1 not in self.sizes or hole.get("right") is None:
            return False
        for side in ("left", "right"):
            position = hole.get(side + "_position")
            if position is None:
                if side == "left" and hole["start"] == 0:
                    continue
                return False
            page = self.read(position, 1)
            if not page.rows or self.identity(page.rows[0]) != hole[side]:
                return False
        positions = (
            ((p, 1) for p in range(hole["start"], hole["end"]))
            if hole["kind"] == "error"
            else self.cover(hole["start"], hole["end"])
        )
        for position, width in positions:
            page = self.read(position, width)
            if (
                page.rows != [] if hole["kind"] == "empty" else page.rows is not None
            ) or page.fingerprint != hole["fingerprint"]:
                return False
        return True

    def holes(self) -> list[dict]:
        holes: list[dict] = []
        for lo, hi, page in sorted(self.pieces, key=lambda item: item[0]):
            if page.rows or lo >= self.end:
                continue
            item = {
                "start": lo,
                "end": min(hi, self.end),
                "kind": "error" if page.rows is None else "empty",
                "fingerprint": page.fingerprint,
            }
            if (
                holes
                and holes[-1]["end"] == lo
                and holes[-1]["kind"] == item["kind"]
                and holes[-1]["fingerprint"] == item["fingerprint"]
            ):
                holes[-1]["end"] = item["end"]
            else:
                holes.append(item)
        data = [
            (lo, lo + len(page.rows), page.rows)
            for lo, _, page in self.pieces
            if page.rows
        ]
        for hole in holes:
            left = max(
                (item for item in data if item[1] <= hole["start"]),
                key=lambda item: item[1],
                default=None,
            )
            right = min(
                (item for item in data if item[0] >= hole["end"]),
                key=lambda item: item[0],
                default=None,
            )
            hole.update(
                left_position=left[1] - 1 if left else None,
                left=self.identity(left[2][-1]) if left else None,
                right_position=right[0] if right else None,
                right=self.identity(right[2][0]) if right else None,
            )
        return holes

    def run(self, previous: list[dict]) -> list[dict]:
        confirmed = {}
        for hole in previous:
            self.history_checked += 1
            if self.matches(hole):
                confirmed[hole["start"]] = hole
                self.history_matched += 1
        cursor = 0
        rows = []
        while len(self.terminal_batches) < 2:
            if cursor in confirmed:
                hole = confirmed[cursor]
                self.piece(
                    cursor,
                    hole["end"] - cursor,
                    _Page(None if hole["kind"] == "error" else [], hole["fingerprint"]),
                )
                cursor = hole["end"]
                self.terminal_batches.clear()
                continue
            limit = min(
                self.size,
                min((p - cursor for p in confirmed if p > cursor), default=self.size),
            )
            if self.numbered and cursor % self.size:
                limit = min(limit, self.size - cursor % self.size)
            width = self.width(cursor, limit)
            page = self.read(cursor, width)
            # A final successful short page needs no width-changing probes.
            # Only an interior short page needs subdivision and reconstruction.
            final_short = False
            if (
                self.retain_final_short
                and page.rows
                and len(page.rows) < width
                and width == self.size
            ):
                following = self.read(cursor + width, self.size)
                if following.rows == []:
                    after = self.read(cursor + 2 * width, self.size)
                    final_short = after.rows == []
            if final_short:
                self.piece(cursor, width, page)
                rows.extend(page.rows)
            else:
                rows.extend(self.inspect(cursor, width, page))
            if page.rows == [] and width == self.size:
                if self.terminal_batches and bool(
                    self.terminal_batches[-1].get("native_terminal")
                ) != bool(page.terminal):
                    self.terminal_batches.clear()
                self.terminal_batches.append(
                    {
                        "start": cursor,
                        "size": width,
                        **({"native_terminal": page.terminal} if page.terminal else {}),
                    }
                )
            elif page.rows is None or page.rows:
                self.terminal_batches.clear()
            cursor += width
        if any(hi < self.end for _, hi in self.unresolved):
            raise CliError(
                REQUEST_NOT_ALLOWED,
                "interior short page needs qualified smaller widths",
            )
        self.observations[:] = self.holes()
        return rows
