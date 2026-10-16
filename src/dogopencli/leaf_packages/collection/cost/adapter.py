"""Collection cost uses one verified request, retaining capacity evidence."""

from typing import Any

from dogopencli.collect import collect_scope
from dogopencli.plugins.collection.cost import COLLECTION_COST_CAPABILITY, COST_TYPE


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return COLLECTION_COST_CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return COST_TYPE

    def collector(
        self, capability: Any, transport: Any, scope: str, *, progress: Any = None
    ) -> Any:
        return collect_scope(capability, transport, scope, progress=progress)

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
