"""Narrow native inquiry contract implemented by locally installed leaves."""

from collections.abc import Callable
from typing import Any, Protocol

from dogopencli.collect import CollectedScope
from dogopencli.contracts import DetailCapability, TransportCapability


class LeafAdapter(Protocol):
    def capability(self, parameters: dict[str, Any]) -> TransportCapability: ...

    def scope(self, parameters: dict[str, Any]) -> str: ...

    def source_capability(
        self, name: str, parameters: dict[str, Any]
    ) -> TransportCapability: ...

    def source_scope(self, name: str, parameters: dict[str, Any]) -> str: ...

    def assemble(
        self,
        records_by_source: dict[str, list[dict[str, Any]]],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]: ...

    def collector(
        self,
        capability: TransportCapability,
        transport: Any,
        scope: str,
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> CollectedScope: ...

    def detail_capability(self, parameters: dict[str, Any]) -> DetailCapability: ...

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]: ...
