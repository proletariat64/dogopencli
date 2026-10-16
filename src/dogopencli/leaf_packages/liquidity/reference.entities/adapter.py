"""Maintained entities preserve their native instId identity."""

from dataclasses import replace
from typing import Any

from dogopencli.plugins.liquidity.capability import LiquidityListCapability
from dogopencli.plugins.liquidity.collect import collect_liquidity_scope
from dogopencli.plugins.liquidity.leaves import REFERENCE_ENTITIES

CAPABILITY = LiquidityListCapability(replace(REFERENCE_ENTITIES, identity=("instId",)))


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return ""

    def collector(
        self, capability: Any, transport: Any, scope: str, *, progress: Any = None
    ) -> Any:
        return collect_liquidity_scope(capability, transport, scope, progress=progress)

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
