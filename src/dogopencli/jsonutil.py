"""JSON helpers preserving decimal precision; never converts through float."""

import json
from decimal import Decimal
from typing import Any


def parse(text: str | bytes) -> Any:
    return json.loads(text, parse_float=Decimal)


def canonical(value: Any) -> str:
    """Canonical JSON with sorted object keys and exact decimal rendering."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite number")
        return str(value)
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(json.dumps(k) + ":" + canonical(value[k]) for k in sorted(value))
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(canonical(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)
