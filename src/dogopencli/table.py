"""Human-readable table output for business queries.

A fixed quality-marker header keeps source, freshness, simulated flag and
completeness visible next to the aligned data columns. Stdlib only; the
layout is intentionally simple and stable for scripts to scan.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from .jsonutil import canonical

_META_GROUPS = (
    ("source", "backend", "scope"),
    ("fetched_at", "loaded_at", "stale"),
    ("simulated", "complete", "dataset_complete"),
    ("dataset_id", "source_observed_from", "source_observed_to"),
    ("matched_total", "returned_count", "has_more"),
)


def _text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return canonical(value)
    return str(value)


def render_table(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    meta: Mapping[str, Any],
) -> str:
    lines: list[str] = []
    for group in _META_GROUPS:
        lines.append("  ".join(f"{key}: {_text(meta.get(key))}" for key in group))
    lines.append("")
    if not rows:
        lines.append("(no rows)")
        return "\n".join(lines)
    cells = [[_text(row.get(name)) for name in columns] for row in rows]
    widths = [
        max(len(name), *(len(line[index]) for line in cells))
        for index, name in enumerate(columns)
    ]
    header = "  ".join(name.ljust(widths[index]) for index, name in enumerate(columns))
    lines.append(header)
    lines.append("  ".join("-" * width for width in widths))
    for line in cells:
        lines.append(
            "  ".join(
                value.ljust(widths[index]) for index, value in enumerate(line)
            ).rstrip()
        )
    return "\n".join(lines)
