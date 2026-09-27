"""Shared retained-money and exact-match semantics for PTR inquiries."""

import math
from decimal import Decimal
from typing import Any

from ...errors import INVALID_ARGUMENT, INVALID_RESPONSE, CliError

MONEY_STRING_FIELDS = frozenset({"currency", "currencyCode", "currencyValue"})
MONEY_INTEGER_FIELDS = frozenset({"cent", "centFactor"})


def is_nullable_number(value: Any) -> bool:
    """Accept finite JSON numbers without rounding integers or decimals."""
    return (
        value is None
        or type(value) is int
        or type(value) is float
        and math.isfinite(value)
        or isinstance(value, Decimal)
        and value.is_finite()
    )


def project_money(value: Any, *, error_prefix: str) -> dict[str, Any] | None:
    """Validate and retain the shared PTR monetary projection."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CliError(INVALID_RESPONSE, f"{error_prefix} object")
    selected = {
        key: item
        for key, item in value.items()
        if key in MONEY_STRING_FIELDS | MONEY_INTEGER_FIELDS | {"amount"}
    }
    for field, item in selected.items():
        valid = (
            is_nullable_number(item)
            if field == "amount"
            else item is None
            or type(item) is (str if field in MONEY_STRING_FIELDS else int)
        )
        if not valid:
            raise CliError(INVALID_RESPONSE, f"{error_prefix} field type")
    return selected


def money_schema() -> dict[str, Any]:
    """Build the nullable allowlisted money-object schema."""
    properties: dict[str, Any] = {
        key: {"type": ["string", "null"]} for key in sorted(MONEY_STRING_FIELDS)
    }
    properties.update(
        {key: {"type": ["integer", "null"]} for key in sorted(MONEY_INTEGER_FIELDS)}
    )
    properties["amount"] = {"type": ["number", "null"]}
    return {
        "type": ["object", "null"],
        "additionalProperties": False,
        "properties": properties,
    }


def filter_exact(
    records: list[dict[str, Any]],
    filters: dict[str, list[str]],
    *,
    allowed_fields: set[str],
    error_message: str,
) -> list[dict[str, Any]]:
    """Match nested whole strings: OR within a field, AND across fields."""
    if any(
        field not in allowed_fields
        or not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) or not value.strip() for value in values)
        for field, values in filters.items()
    ):
        raise CliError(INVALID_ARGUMENT, error_message)

    def matches(row: dict[str, Any]) -> bool:
        for path, values in filters.items():
            value: Any = row
            for part in path.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if not isinstance(value, str) or value not in values:
                return False
        return True

    return [row for row in records if matches(row)]
