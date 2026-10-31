"""Narrow native inquiry contract implemented by locally installed leaves."""

from typing import Any, Protocol

from dogopencli.contracts import DetailCapability, TransportCapability


class LeafAdapter(Protocol):
    def capability(self, parameters: dict[str, Any]) -> TransportCapability: ...

    def scope(self, parameters: dict[str, Any]) -> str: ...

    def source_capability(
        self, name: str, parameters: dict[str, Any]
    ) -> TransportCapability: ...

    def source_scope(self, name: str, parameters: dict[str, Any]) -> str: ...

    def validate_sources(
        self,
        retained_records_by_source: dict[str, list[dict[str, Any]]],
        parameters: dict[str, Any],
    ) -> None: ...

    def assemble(
        self,
        records_by_source: dict[str, list[dict[str, Any]]],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]: ...

    def detail_capability(self, parameters: dict[str, Any]) -> DetailCapability: ...

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]: ...
