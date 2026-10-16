"""Narrow native inquiry contract implemented by locally installed leaves."""

from collections.abc import Callable
from typing import Any, Protocol

from dogopencli.collect import CollectedScope
from dogopencli.plugins import TransportCapability


class LeafAdapter(Protocol):
    def capability(self, parameters: dict[str, Any]) -> TransportCapability: ...

    def scope(self, parameters: dict[str, Any]) -> str: ...

    def collector(
        self,
        capability: TransportCapability,
        transport: Any,
        scope: str,
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> CollectedScope: ...

    def get(
        self, session: Any, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]: ...

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]: ...
