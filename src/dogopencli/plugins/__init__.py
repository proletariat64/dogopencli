"""Query capability plugin interface and registry (ADR 0001).

A capability declares its endpoint contract, request body shape, local
filter semantics and response parser. Core transport, cache and output do
not carry domain knowledge; new capabilities register here without
modifying the core layers.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast

from ..helpspec import BizNode

if TYPE_CHECKING:
    from ..collect import CollectedScope


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
    # True when the backend's interim totalCount is a running estimate
    # (VA capacity): acquire until the first short page, tolerate changing
    # interim totals, and let only the final converged total validate
    # completeness. False keeps the verified fixed-total contract.
    running_total: bool = False
    # Wire encoding of the validated body: ``json`` posts a JSON body,
    # ``form`` posts application/x-www-form-urlencoded, ``query`` serializes
    # into the URL query. GET always uses ``query`` regardless of this
    # declaration; the default ``json`` preserves existing POST contracts.
    encoding: str = "json"
    # RPC inquiries wrap the validated object in a one-element JSON array.
    # Nested inquiry fields remain default-deny at the shared boundary.
    nested_body_keys: tuple[tuple[str, frozenset[str]], ...] = ()
    # Only one response is verified for fixed-page inquiries. A reported
    # total beyond its capacity becomes a coverage gap, never a new request.
    single_page: bool = False
    # Native list identity is the counting unit for these paginated contracts.
    # No existing capability permits repeated arrivals to prove completeness.
    total_semantics: str = "unique_objects"
    duplicate_policy: str = "conservative"
    has_identity: bool = True
    # Business keys and versions do not establish native row identity.
    # Distinct content under an unverified key leaves consistency unproven.
    consistency_version_field: str | None = None
    # Named GET sources can carry an exact inquiry object as a JSON string.
    # Its keys, fixed scope and optional page widths are validated before execution.
    json_body_contracts: tuple[
        tuple[str, frozenset[str], tuple[tuple[str, str | int], ...], frozenset[int]],
        ...,
    ] = ()


@dataclass(frozen=True)
class ParsedPage:
    records: list[dict[str, Any]]
    page_num: int
    page_size: int
    total_count: int
    total_pages: int


class TransportCapability(Protocol):
    """The narrow transport-facing seam: one named, allowlisted endpoint.

    Detail inquiries are single allowlisted requests without pagination,
    filters or sorting; they still pass the same default-deny validation.
    """

    @property
    def name(self) -> str: ...

    @property
    def contract(self) -> EndpointContract: ...


class Capability(Protocol):
    # Read-only protocol properties accept both attributes and properties on
    # the implementing class, frozen or not.
    @property
    def name(self) -> str: ...

    @property
    def source_config_key(self) -> str: ...

    @property
    def id_field(self) -> str: ...

    @property
    def table_columns(self) -> tuple[str, ...]: ...

    @property
    def default_scope(self) -> str:
        """Acquisition/cache scope selected by the capability."""
        ...

    @property
    def contract(self) -> EndpointContract:
        """Read-only request contract, possibly bound to an explicit scope."""
        ...

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


class ConfigurationCapability(Capability, Protocol):
    """Complete lists with declared local filters and cached-row validation."""

    @property
    def command_path(self) -> str: ...

    @property
    def filters(self) -> tuple[tuple[str, str], ...]: ...

    def validate_row(self, row: Any) -> None: ...


class NamedCapability(Protocol):
    """The registration seam: the registry stores and indexes by name.

    Peer plugins register capability objects narrower than the full
    acquisition protocol (single-request details, deferred discovery
    handles); shared mechanics that need more receive the concrete type
    from their own caller.
    """

    @property
    def name(self) -> str: ...


_CollectedCapability = TypeVar(
    "_CollectedCapability", bound=Capability, contravariant=True
)
_RegisteredCapability = TypeVar("_RegisteredCapability", bound=NamedCapability)


class ScopeCollector(Protocol[_CollectedCapability]):
    """A registered domain acquisition policy using shared bounded transport."""

    def __call__(
        self,
        capability: _CollectedCapability,
        transport: Any,
        scope: str,
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> "CollectedScope": ...


_REGISTRY: dict[str, NamedCapability] = {}
# Registration checks each callback against its capability type. Lookup is by
# capability name, while invocation always uses the caller's bound instance.
_COLLECTORS: dict[str, ScopeCollector[Any]] = {}
_REFRESH_HINTS: dict[str, Callable[[Any], str]] = {}
_COMMANDS: dict[str, tuple[BizNode, ...]] = {}
_REFRESH_COMMANDS: dict[str, tuple[BizNode, ...]] = {}
_GROUPS: dict[str, tuple[BizNode, ...]] = {}
_DESCRIPTIONS: dict[tuple[str, ...], Callable[[BizNode], dict[str, Any]]] = {}


def register(
    capability: _RegisteredCapability,
    *,
    commands: tuple[BizNode, ...] = (),
    refresh_commands: tuple[BizNode, ...] = (),
    groups: tuple[BizNode, ...] = (),
    description: Callable[[BizNode], dict[str, Any]] | None = None,
    collector: ScopeCollector[Any] | None = None,
    refresh_hint: Callable[[_RegisteredCapability], str] | None = None,
) -> None:
    _REGISTRY[capability.name] = capability
    if collector is None:
        _COLLECTORS.pop(capability.name, None)
    else:
        _COLLECTORS[capability.name] = collector
    if refresh_hint is None:
        _REFRESH_HINTS.pop(capability.name, None)
    else:
        _REFRESH_HINTS[capability.name] = refresh_hint
    _COMMANDS[capability.name] = commands
    _REFRESH_COMMANDS[capability.name] = refresh_commands
    _GROUPS[capability.name] = groups
    if description is not None:
        for node in (*commands, *refresh_commands):
            _DESCRIPTIONS[node.path] = description


def collect_complete_scope(
    capability: Capability,
    transport: Any,
    scope: str,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> "CollectedScope":
    """Use the registered policy, preserving the caller's exact bound scope."""
    from ..collect import collect_scope

    collector = _COLLECTORS.get(capability.name, collect_scope)
    return collector(capability, transport, scope, progress=progress)


def refresh_command(capability: ConfigurationCapability) -> str:
    """Return a runnable refresh hint for the actual acquisition scope."""
    hint = _REFRESH_HINTS.get(capability.name)
    return (
        hint(capability) if hint is not None else f"refresh {capability.command_path}"
    )


def command_nodes() -> tuple[BizNode, ...]:
    return tuple(node for commands in _COMMANDS.values() for node in commands)


def refresh_nodes() -> tuple[BizNode, ...]:
    return tuple(node for nodes in _REFRESH_COMMANDS.values() for node in nodes)


def group_nodes() -> tuple[BizNode, ...]:
    return tuple(node for nodes in _GROUPS.values() for node in nodes)


def get_description(node: BizNode) -> dict[str, Any]:
    """Invoke the offline description provider registered with this command."""
    return _DESCRIPTIONS[node.path](node)


def cache_bindings() -> dict[tuple[str, ...], NamedCapability]:
    """Discover inquiry/refresh ownership from the installed registrations."""
    return {
        node.path: _REGISTRY[name]
        for declarations in (_COMMANDS, _REFRESH_COMMANDS)
        for name, nodes in declarations.items()
        for node in nodes
        if getattr(_REGISTRY[name], "cache_enabled", True)
    }


def get_capability(name: str) -> Capability:
    """Full acquisition capability; only valid for complete-list plugins."""
    return cast(Capability, _REGISTRY[name])


def _load_builtins() -> None:
    from .collection.account_isolation import (
        ACCOUNT_ISOLATION,
    )
    from .collection.account_isolation import (
        GROUP_NODE as isolation_group,
    )
    from .collection.account_isolation import (
        LIST_NODE as isolation_list,
    )
    from .collection.account_isolation import (
        REFRESH_NODE as isolation_refresh,
    )
    from .collection.account_isolation_reading import (
        description as isolation_description,
    )
    from .collection.cost import COLLECTION_COST_CAPABILITY, COLLECTION_COST_LIST_NODE
    from .collection.cost import REFRESH_NODE as cost_refresh
    from .collection.network_config import (
        CAPABILITIES,
        group_node,
        list_node,
        refresh_node,
    )
    from .collection.network_reading import description as network_description
    from .collection.reading import description as collection_description
    from .collection.sla import (
        COLLECTION_SLA,
        COLLECTION_SLA_GET_NODE,
        COLLECTION_SLA_LIST_NODE,
    )
    from .collection.sla import REFRESH_NODE as sla_refresh
    from .collection.sla_reading import description as sla_description
    from .collection.va_capacity import (
        COLLECTION_VA_CAPACITY,
        COLLECTION_VA_CAPACITY_LIST_NODE,
    )
    from .collection.va_capacity import REFRESH_NODE as capacity_refresh
    from .collection.va_capacity_reading import (
        description as va_capacity_description,
    )
    from .collection.va_rule import (
        COLLECTION_VA_RULE_GET_NODE,
        COLLECTION_VA_RULE_LIST_NODE,
        COLLECTION_VA_RULES,
    )
    from .collection.va_rule import REFRESH_NODE as va_refresh
    from .collection.va_rule_reading import description as va_rule_description
    from .payment import (
        ptr,
        ptr_orders,
        ptr_orders_reading,
        ptr_reading,
        rules,
        rules_reading,
    )
    from .payment.channel import CHANNEL_CAPABILITY, CHANNEL_LIST_NODE
    from .payment.cost import COST_CAPABILITY, COST_LIST_NODE
    from .payment.reading import description
    from .payment.sla import SLA_CAPABILITY, SLA_GET_NODE, SLA_LIST_NODE

    register(
        ptr.CASES,
        commands=(ptr_reading.LIST_NODE,),
        refresh_commands=(ptr_reading.REFRESH_NODE,),
        groups=ptr_reading.GROUPS,
        description=ptr_reading.description,
        collector=ptr.collect_stable,
    )

    register(
        ptr_orders.ORDERS,
        commands=(ptr_orders_reading.LIST_NODE,),
        refresh_commands=(ptr_orders_reading.REFRESH_NODE,),
        groups=ptr_orders_reading.GROUPS,
        description=ptr_orders_reading.description,
        collector=ptr_orders.collect_stable,
        refresh_hint=lambda capability: capability.refresh_command,
    )

    for rule_cap in rules.CAPABILITIES:
        register(
            rule_cap,
            commands=(rules_reading.list_node(rule_cap),),
            refresh_commands=(rules_reading.refresh_node(rule_cap),),
            groups=rules_reading.groups(rule_cap),
            description=rules_reading.description,
        )

    # Refresh navigation predates query discovery and has a different order.
    # Reserve its slots so moving declarations does not reorder public help.
    for capability in (
        *CAPABILITIES,
        COLLECTION_COST_CAPABILITY,
        COLLECTION_SLA,
        COLLECTION_VA_RULES,
        COLLECTION_VA_CAPACITY,
    ):
        _REFRESH_COMMANDS[capability.name] = ()

    for capability in CAPABILITIES:
        register(
            capability,
            commands=(list_node(capability),),
            refresh_commands=(refresh_node(capability),),
            groups=(group_node(capability),),
            description=network_description,
        )
    register(
        COLLECTION_SLA,
        commands=(COLLECTION_SLA_LIST_NODE, COLLECTION_SLA_GET_NODE),
        refresh_commands=(sla_refresh,),
        description=sla_description,
    )
    register(
        COLLECTION_VA_RULES,
        commands=(COLLECTION_VA_RULE_LIST_NODE, COLLECTION_VA_RULE_GET_NODE),
        refresh_commands=(va_refresh,),
        description=va_rule_description,
    )
    register(
        COLLECTION_VA_CAPACITY,
        commands=(COLLECTION_VA_CAPACITY_LIST_NODE,),
        refresh_commands=(capacity_refresh,),
        description=va_capacity_description,
    )
    register(
        COLLECTION_COST_CAPABILITY,
        commands=(COLLECTION_COST_LIST_NODE,),
        refresh_commands=(cost_refresh,),
        description=collection_description,
    )
    register(CHANNEL_CAPABILITY, commands=(CHANNEL_LIST_NODE,), description=description)
    register(COST_CAPABILITY, commands=(COST_LIST_NODE,), description=description)
    register(
        SLA_CAPABILITY, commands=(SLA_LIST_NODE, SLA_GET_NODE), description=description
    )

    register(
        ACCOUNT_ISOLATION,
        commands=(isolation_list,),
        refresh_commands=(isolation_refresh,),
        groups=(isolation_group,),
        description=isolation_description,
    )

    from .liquidity import leaves as liquidity_leaves
    from .liquidity import reading as liquidity_reading

    # Peer liquidity plugin (ADR 0015): verified leaves plus deferred
    # discovery; the liquidity origin/auth routing lives in the capability.
    for leaf in liquidity_leaves.LIST_LEAVES.values():
        register(
            leaf.capability(leaf.variants[0]),
            commands=(liquidity_leaves.list_query_node(leaf),),
            refresh_commands=(liquidity_leaves.refresh_list_node(leaf),),
            groups=(),
            description=liquidity_reading.description,
        )
    for leaf in liquidity_leaves.DETAIL_LEAVES.values():
        register(
            leaf.capability,
            commands=(liquidity_leaves.detail_query_node(leaf),),
            refresh_commands=(),
            groups=(),
            description=liquidity_reading.description,
        )
    for leaf in liquidity_leaves.RETIRED_LEAVES.values():
        query, refresh = liquidity_leaves.retired_nodes(leaf)
        handle = liquidity_leaves.UnsupportedLeafHandle(query)
        handle.cache_enabled = False
        register(
            handle,
            commands=(query,),
            refresh_commands=(refresh,),
            description=liquidity_reading.description,
        )
    for leaf in liquidity_leaves.INTERNAL_LIST_LEAVES.values():
        register(leaf.capability(leaf.variants[0]))
    for leaf in liquidity_leaves.INTERNAL_DETAIL_LEAVES.values():
        register(leaf.capability)
    from dataclasses import replace

    for deferred in liquidity_leaves.DEFERRED:
        node = liquidity_leaves.unsupported_node(deferred)
        register(
            liquidity_leaves.UnsupportedLeafHandle(node),
            commands=(node,),
            refresh_commands=(
                replace(node, path=("refresh", "liquidity", *deferred.path[:-1])),
            )
            if deferred in liquidity_leaves.ACCOUNT_PENDING
            else (),
            groups=(),
            description=liquidity_reading.description,
        )
    refresh_paths = [
        node.path
        for node in refresh_nodes()
        if node.path[:2] == ("refresh", "liquidity")
    ]
    _GROUPS["liquidity"] = tuple(
        node
        for node in liquidity_leaves.group_nodes()
        if node.path[:1] != ("refresh",)
        or any(path[: len(node.path)] == node.path for path in refresh_paths)
    )

    from .fx.trade import FX_TRADE, TRADE_NODE
    from .fx.trade import description as fx_description

    register(
        FX_TRADE,
        commands=(TRADE_NODE,),
        description=fx_description,
    )


_load_builtins()
