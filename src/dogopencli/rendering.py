"""Shared structured text rendering for public command results."""

from collections.abc import Mapping
from typing import Any

from .jsonutil import canonical


def render_text(value: Any, depth: int = 0) -> str:
    """Render labeled fields and bullet lists without changing native values."""
    padding = "  " * depth
    if isinstance(value, (Mapping, list)):
        if not value:
            kind = "object" if isinstance(value, Mapping) else "list"
            return padding + f"(empty {kind})"
        items = (
            value.items() if isinstance(value, Mapping) else ((None, v) for v in value)
        )
        lines = []
        for key, item in items:
            label = f"{key}:" if key is not None else "-"
            rendered = render_text(item, depth + 1)
            if isinstance(item, (Mapping, list)) or "\n" in rendered:
                lines.append(padding + label + "\n" + rendered)
            else:
                lines.append(padding + label + " " + rendered[len(padding) + 2 :])
        return "\n".join(lines)
    scalar = value if isinstance(value, str) and value else canonical(value)
    return "\n".join(padding + line for line in scalar.split("\n"))
