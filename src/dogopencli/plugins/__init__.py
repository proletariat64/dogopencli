"""Query capability plugin interface and registry (ADR 0001).

A capability declares its endpoint contract, request body shape, local
filter semantics and response parser. Core transport, cache and output do
not carry domain knowledge; new capabilities register here without
modifying the core layers.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
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


@dataclass(frozen=True)
class DomainAuthPolicy:
    """Domain declarations consumed by the shared browser lifecycle."""

    preserve_headed: bool = False
    document_completion: bool = False
    bounded_handoff: bool = False
    probe: Callable[..., Any] | None = None


@dataclass(frozen=True)
class LeafRegistration:
    """One stable leaf identity and its public operation contributions."""

    id: str
    capability: NamedCapability
    commands: tuple[BizNode, ...] = ()
    refresh_commands: tuple[BizNode, ...] = ()
    groups: tuple[BizNode, ...] = ()
    enabled: bool = True
    description: Callable[[BizNode], dict[str, Any]] | None = None
    collector: ScopeCollector[Any] | None = None
    refresh_hint: Callable[..., str] | None = None
    prune_commands: tuple[BizNode, ...] = ()
    operations: tuple[tuple[tuple[str, ...], str], ...] = ()
    cache_paths: tuple[tuple[str, ...], ...] = ()
    describe_refresh: bool = False


class DomainPlugin(Protocol):
    """Business domain integration contract; shared portal URLs are valid."""

    @property
    def id(self) -> str: ...

    @property
    def entry_point(self) -> str: ...

    @property
    def leaves(self) -> tuple[LeafRegistration, ...]: ...

    @property
    def groups(self) -> tuple[BizNode, ...]: ...

    @property
    def auth(self) -> DomainAuthPolicy: ...

    @property
    def refresh_order(self) -> tuple[str, ...]: ...

    @property
    def navigation_order(self) -> int: ...

    @property
    def handlers(self) -> Mapping[str, Callable[..., int]]: ...


@dataclass(frozen=True)
class DomainComponent:
    """Static implementation of the domain interface used by built-ins."""

    id: str
    entry_point: str
    leaves: tuple[LeafRegistration, ...]
    groups: tuple[BizNode, ...] = ()
    auth: DomainAuthPolicy = DomainAuthPolicy()
    refresh_order: tuple[str, ...] = ()
    navigation_order: int = 0
    handlers: Mapping[str, Callable[..., int]] = field(default_factory=dict)


def leaf_registration(
    capability: NamedCapability,
    *,
    commands: tuple[BizNode, ...] = (),
    refresh_commands: tuple[BizNode, ...] = (),
    groups: tuple[BizNode, ...] = (),
    enabled: bool = True,
    description: Callable[[BizNode], dict[str, Any]] | None = None,
    collector: ScopeCollector[Any] | None = None,
    refresh_hint: Callable[..., str] | None = None,
) -> LeafRegistration:
    """Adapt the existing leaf protocol into explicit operation metadata."""
    commands = tuple(
        replace(
            node,
            options=tuple(
                option for option in node.options if option.name != "require_fresh"
            ),
            effects={
                "mutates": False,
                "network": True,
                "browser_required": True,
                "destructive": False,
            },
            effects_variants=(),
            summary="Online native detail inquiry; never reads or writes query cache.",
        )
        if node.path[-1] == "get" and enabled
        else node
        for node in commands
    )
    if not enabled:
        commands = tuple(
            replace(node, summary="Disabled inquiry.") for node in commands
        )
        refresh_commands = tuple(
            replace(node, summary="Disabled refresh.") for node in refresh_commands
        )
    operations = tuple(
        (node.path, "get" if node.path[-1] == "get" else "list") for node in commands
    ) + tuple((node.path, "refresh") for node in refresh_commands)
    cache_paths = tuple(
        node.path
        for node in (*commands, *refresh_commands)
        if enabled
        and getattr(capability, "cache_enabled", True)
        and node.path[-1] != "get"
    )
    prune_commands = tuple(
        BizNode(
            (*node.path[:-1], "prune")
            if node.path[-1] == "list"
            else (*node.path, "prune"),
            "Delete this leaf's temporary query cache; idempotent and offline.",
            handler="cmd_prune",
            effects={
                "mutates": True,
                "network": False,
                "browser_required": False,
                "destructive": True,
            },
        )
        for node in commands
        if node.path in cache_paths and node.path[-1] in ("list", "trade")
    )
    return LeafRegistration(
        id=capability.name,
        capability=capability,
        commands=commands,
        refresh_commands=refresh_commands,
        groups=groups,
        enabled=enabled,
        description=description,
        collector=collector,
        refresh_hint=refresh_hint,
        prune_commands=prune_commands,
        operations=operations,
        cache_paths=cache_paths,
        describe_refresh=not enabled,
    )


_DOMAINS: tuple[DomainPlugin, ...] = ()


def domain_plugins() -> tuple[DomainPlugin, ...]:
    """Return ordered installed domain declarations without external work."""
    return _DOMAINS


def handler_for(name: str) -> Callable[..., int] | None:
    """Resolve a domain binding; validation reserves core execution names."""
    return next(
        (domain.handlers[name] for domain in _DOMAINS if name in domain.handlers), None
    )


def validate_domains(domains: tuple[DomainPlugin, ...]) -> None:
    """Reject invalid whole contributions before registry publication."""
    from ..auth.spec import SPECS
    from ..handler_contract import CORE_HANDLER_NAMES

    domain_ids: set[str] = set()
    leaf_ids: set[str] = set()
    handler_names: set[str] = set()
    paths: set[tuple[str, ...]] = set()
    reserved = {
        "auth",
        "login",
        "logout",
        "help",
        "snapshot",
        "domain",
        "gui",
        "refresh",
        "describe",
        "prune",
    }
    for domain in domains:
        if (
            not domain.id
            or not domain.id.isidentifier()
            or domain.id in reserved
            or domain.id in domain_ids
        ):
            raise ValueError(f"invalid or duplicate domain ID: {domain.id}")
        domain_ids.add(domain.id)
        for name, callback in domain.handlers.items():
            if (
                not isinstance(name, str)
                or not name.isidentifier()
                or not callable(callback)
                or name in handler_names
                or name in CORE_HANDLER_NAMES
            ):
                raise ValueError(f"invalid or duplicate handler binding: {name}")
            handler_names.add(name)
        if not domain.entry_point.startswith("https://"):
            raise ValueError(f"invalid domain entry point: {domain.id}")
        owned_ids = {leaf.id for leaf in domain.leaves}
        if (
            len(set(domain.refresh_order)) != len(domain.refresh_order)
            or set(domain.refresh_order) - owned_ids
        ):
            raise ValueError(f"invalid refresh order: {domain.id}")
        declarations = list(domain.groups)
        for leaf in domain.leaves:
            if not leaf.id or leaf.id != leaf.capability.name or leaf.id in leaf_ids:
                raise ValueError(f"invalid or duplicate leaf ID: {leaf.id}")
            leaf_ids.add(leaf.id)
            if type(leaf.enabled) is not bool:
                raise ValueError(f"invalid enabled state: {leaf.id}")
            executable = (*leaf.commands, *leaf.refresh_commands, *leaf.prune_commands)
            if any(node.handler is None for node in executable):
                raise ValueError(f"missing executable binding: {leaf.id}")
            operation_paths = {
                node.path for node in (*leaf.commands, *leaf.refresh_commands)
            }
            if set(leaf.cache_paths) - operation_paths or any(
                node.cache_capability not in (None, leaf.id) for node in executable
            ):
                raise ValueError(f"inconsistent cache binding: {leaf.id}")
            declarations.extend((*leaf.groups, *executable))
        for node in declarations:
            if node.handler is not None and (
                not isinstance(node.handler, str)
                or node.handler not in CORE_HANDLER_NAMES | domain.handlers.keys()
            ):
                raise ValueError(f"missing executable handler binding: {node.path}")
            owner = (
                node.path[1:2]
                if node.path[:1] in (("refresh",), ("prune",))
                else node.path[:1]
            )
            if owner != (domain.id,):
                raise ValueError(f"invalid domain ownership: {node.path}")
            if node.path in paths or node.path in SPECS:
                raise ValueError(f"duplicate command path: {node.path}")
            paths.add(node.path)
    parents = paths | {(), ("refresh",), ("prune",)}
    for path in paths:
        if path[:-1] not in parents:
            raise ValueError(f"missing parent for command: {path}")


def register_domains(domains: tuple[DomainPlugin, ...]) -> None:
    """Publish one validated replacement set atomically; dormant state survives."""
    global _DOMAINS
    validate_domains(domains)
    registry = {}
    collectors = {}
    hints = {}
    commands = {}
    refreshes = {}
    groups = {}
    descriptions = {}
    for domain in domains:
        groups[domain.id] = domain.groups
        for leaf in domain.leaves:
            registry[leaf.id] = leaf.capability
            commands[leaf.id] = leaf.commands
            groups[leaf.id] = leaf.groups
            if leaf.collector is not None:
                collectors[leaf.id] = leaf.collector
            if leaf.refresh_hint is not None:
                hints[leaf.id] = leaf.refresh_hint
            if leaf.description is not None:
                for node in (*leaf.commands, *leaf.refresh_commands):
                    descriptions[node.path] = leaf.description
        by_id = {leaf.id: leaf for leaf in domain.leaves}
        for name in (
            *domain.refresh_order,
            *(name for name in by_id if name not in domain.refresh_order),
        ):
            refreshes[name] = by_id[name].refresh_commands
    _REGISTRY.clear()
    _REGISTRY.update(registry)
    _COLLECTORS.clear()
    _COLLECTORS.update(collectors)
    _REFRESH_HINTS.clear()
    _REFRESH_HINTS.update(hints)
    _COMMANDS.clear()
    _COMMANDS.update(commands)
    _REFRESH_COMMANDS.clear()
    _REFRESH_COMMANDS.update(refreshes)
    _GROUPS.clear()
    _GROUPS.update(groups)
    _DESCRIPTIONS.clear()
    _DESCRIPTIONS.update(descriptions)
    _DOMAINS = domains


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
    from .collection.domain import component as collection
    from .fx.domain import component as fx
    from .liquidity.domain import component as liquidity
    from .payment.domain import component as payment

    register_domains((payment(), collection(), fx(), liquidity()))


_load_builtins()
