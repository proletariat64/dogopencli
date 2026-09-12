"""Query capability plugin interface and registry (ADR 0001).

A capability declares its endpoint contract, request body shape, local
filter semantics and response parser. Core transport, cache and output do
not carry domain knowledge; new capabilities register here without
modifying the core layers.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from ..helpspec import BizNode


@dataclass(frozen=True)
class EndpointContract:
    """Verified inquiry endpoint; the shared allowlist rejects anything else."""

    method: str
    host: str
    path: str
    page_size: int
    one_based: bool
    allowed_body_keys: frozenset[str]
    # Verified larger capacity allowing one full-candidate rebuild on
    # business-success coverage gaps. None means no rebuild clause (Channel).
    rebuild_page_size: int | None = None
    scope_field: str | None = None
    # A repeated business identifier with differing content prevents proof of
    # completeness without making that identifier a deduplication key.
    consistency_field: str | None = None


@dataclass(frozen=True)
class ParsedPage:
    records: list[dict[str, Any]]
    page_num: int
    page_size: int
    total_count: int
    total_pages: int


class Capability(Protocol):
    name: str
    source_config_key: str
    default_scope: str
    contract: EndpointContract
    id_field: str
    table_columns: tuple[str, ...]

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        """Request body for one collection page of a full scope."""
        ...

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        """Filter fields of a validated request body, normalized to lists."""
        ...

    def filter_records(
        self, records: list[dict[str, Any]], filters: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        """Exact local match: OR within one field, AND across fields."""
        ...

    def sort_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deterministic local order for cache storage and display."""
        ...

    def identity_key(self, record: dict[str, Any]) -> Any:
        """Dedup key within one candidate: identical content collapses, a key
        collision with different content is a conflict."""
        ...

    def parse_page(self, body: bytes) -> ParsedPage:
        """Formal parser shared by every transport for this capability."""
        ...


_REGISTRY: dict[str, Capability] = {}
_COMMANDS: dict[str, tuple[BizNode, ...]] = {}


def register(capability: Capability, *, commands: tuple[BizNode, ...] = ()) -> None:
    _REGISTRY[capability.name] = capability
    _COMMANDS[capability.name] = commands


def command_nodes() -> tuple[BizNode, ...]:
    return tuple(node for commands in _COMMANDS.values() for node in commands)


def get_capability(name: str) -> Capability:
    return _REGISTRY[name]


def _load_builtins() -> None:
    from .payment.channel import CHANNEL_CAPABILITY, CHANNEL_LIST_NODE
    from .payment.cost import COST_CAPABILITY, COST_LIST_NODE
    from .payment.sla import SLA_CAPABILITY, SLA_GET_NODE, SLA_LIST_NODE

    register(CHANNEL_CAPABILITY, commands=(CHANNEL_LIST_NODE,))
    register(COST_CAPABILITY, commands=(COST_LIST_NODE,))
    register(SLA_CAPABILITY, commands=(SLA_LIST_NODE, SLA_GET_NODE))


_load_builtins()
