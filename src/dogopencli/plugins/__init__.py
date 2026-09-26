"""Query capability plugin interface and registry (ADR 0001).

A capability declares its endpoint contract, request body shape, local
filter semantics and response parser. Core transport, cache and output do
not carry domain knowledge; new capabilities register here without
modifying the core layers.
"""

from collections.abc import Callable
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
    # Exact required request values for capabilities with a fixed acquisition.
    fixed_body_values: tuple[tuple[str, str | int], ...] = ()


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
_DESCRIPTIONS: dict[tuple[str, ...], Callable[[BizNode], dict[str, Any]]] = {}


def register(
    capability: Capability,
    *,
    commands: tuple[BizNode, ...] = (),
    description: Callable[[BizNode], dict[str, Any]] | None = None,
) -> None:
    _REGISTRY[capability.name] = capability
    _COMMANDS[capability.name] = commands
    if description is not None:
        for node in commands:
            _DESCRIPTIONS[node.path] = description


def command_nodes() -> tuple[BizNode, ...]:
    return tuple(node for commands in _COMMANDS.values() for node in commands)


def get_description(node: BizNode) -> dict[str, Any]:
    """Invoke the offline description provider registered with this command."""
    return _DESCRIPTIONS[node.path](node)


def get_capability(name: str) -> Capability:
    return _REGISTRY[name]


def _load_builtins() -> None:
    from .collection.cost import COLLECTION_COST_CAPABILITY, COLLECTION_COST_LIST_NODE
    from .collection.reading import description as collection_description
    from .collection.sla import (
        COLLECTION_SLA,
        COLLECTION_SLA_GET_NODE,
        COLLECTION_SLA_LIST_NODE,
    )
    from .collection.sla_reading import description as sla_description
    from .collection.va_rule import (
        COLLECTION_VA_RULE_GET_NODE,
        COLLECTION_VA_RULE_LIST_NODE,
        COLLECTION_VA_RULES,
    )
    from .collection.va_rule_reading import description as va_rule_description
    from .payment.channel import CHANNEL_CAPABILITY, CHANNEL_LIST_NODE
    from .payment.cost import COST_CAPABILITY, COST_LIST_NODE
    from .payment.reading import description
    from .payment.sla import SLA_CAPABILITY, SLA_GET_NODE, SLA_LIST_NODE

    register(
        COLLECTION_SLA,
        commands=(COLLECTION_SLA_LIST_NODE, COLLECTION_SLA_GET_NODE),
        description=sla_description,
    )
    register(
        COLLECTION_VA_RULES,
        commands=(COLLECTION_VA_RULE_LIST_NODE, COLLECTION_VA_RULE_GET_NODE),
        description=va_rule_description,
    )
    register(
        COLLECTION_COST_CAPABILITY,
        commands=(COLLECTION_COST_LIST_NODE,),
        description=collection_description,
    )
    register(CHANNEL_CAPABILITY, commands=(CHANNEL_LIST_NODE,), description=description)
    register(COST_CAPABILITY, commands=(COST_LIST_NODE,), description=description)
    register(
        SLA_CAPABILITY, commands=(SLA_LIST_NODE, SLA_GET_NODE), description=description
    )


_load_builtins()
