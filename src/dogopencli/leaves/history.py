"""Opt-in calendar declarations; native date codecs remain leaf-owned."""

from copy import deepcopy
from datetime import date
from typing import TYPE_CHECKING

from ..errors import CliError

if TYPE_CHECKING:
    from .registry import Leaf


def invalid(message: str) -> None:
    raise CliError("INVALID_ARGUMENT", message, exit_code=2)


def calendar(value: str) -> date:
    """Accept only canonical ISO calendar dates at the host boundary."""
    try:
        if not isinstance(value, str):
            raise ValueError
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except (TypeError, ValueError) as error:
        raise CliError(
            "INVALID_ARGUMENT",
            "History requires YYYY-MM-DD calendar bounds",
            exit_code=2,
        ) from error


def resolve(leaf: "Leaf", parameters: dict) -> dict:
    declaration = leaf.manifest["operations"]["list"].get("history")
    if declaration is None:
        invalid(
            "Leaf has no native history range contract; "
            "preserve a full scoped observation instead"
        )
    applicability = declaration.get("applicability")
    if (
        applicability
        and parameters.get(applicability["parameter"].replace("-", "_"))
        not in applicability["values"]
    ):
        invalid("History is not applicable to the selected source")
    supplied = deepcopy(parameters)
    bounds = leaf.adapter.history_bounds(supplied)
    if supplied != parameters:
        invalid("History date conversion changed query parameters")
    if not isinstance(bounds, dict) or set(bounds) != {"from", "to"}:
        invalid("History date conversion must return only from and to")
    start, end = calendar(bounds["from"]), calendar(bounds["to"])
    if start > end:
        invalid("Native history range is reversed")
    maximum = declaration.get("max_day_difference")
    if maximum is not None and (end - start).days > maximum:
        invalid("History range exceeds the declared maximum day difference")
    return {
        **deepcopy(declaration),
        "format": "%Y-%m-%d",
        "from_parameter": declaration["from_parameter"].replace("-", "_"),
        "to_parameter": declaration["to_parameter"].replace("-", "_"),
        **bounds,
    }


def window_parameters(
    leaf: "Leaf", parameters: dict, bounds: dict, contract: dict
) -> dict:
    calendar(bounds["from"])
    calendar(bounds["to"])
    supplied = dict(bounds)
    patch = leaf.adapter.history_parameters(supplied)
    if supplied != bounds:
        invalid("History parameter conversion changed calendar bounds")
    if not isinstance(patch, dict) or set(patch) != {
        contract["from_parameter"],
        contract["to_parameter"],
    }:
        invalid(
            "History parameter conversion must change only declared date parameters"
        )
    if any(not isinstance(value, str) for value in patch.values()):
        invalid("History date parameters must remain strings")
    result = {**deepcopy(parameters), **patch}
    if resolve(leaf, result) != {**contract, **bounds}:
        invalid("History date conversion does not preserve the requested range")
    return result
