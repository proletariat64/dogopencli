"""Uniform command assembly from complete domain component declarations."""

from collections.abc import Iterable
from dataclasses import replace

from .auth.spec import SPECS as AUTH_SPECS
from .describe import description_nodes
from .helpspec import (
    FIELDS,
    FORMAT_TABLE,
    LIMIT,
    NO_EFFECTS,
    OFFSET,
    REQUIRE_COMPLETE,
    BizNode,
    contract,
    display_modes,
    opt,
)
from .management import DECLARATIONS as MANAGEMENT_DECLARATIONS
from .plugins import DomainPlugin, domain_plugins, validate_domains

AUTH_PATHS = frozenset(path for path in AUTH_SPECS if path)

ROOT_NODE = BizNode(
    (),
    "Inquiry-only, read-only payment, collection, liquidity and FX queries;"
    " all enabled lists default to temporary cache replay.",
    constraints=("Business queries never modify production business configuration.",),
    errors=("INVALID_ARGUMENT",),
    examples=(
        "dogopencli",
        "dogopencli help payment",
        "dogopencli help payment channel list",
    ),
    next=(
        "dogopencli help payment",
        "dogopencli help refresh",
        "dogopencli --format text",
    ),
)
REFRESH_NODE = BizNode(
    ("refresh",),
    "Explicitly rebuild local caches; never runs implicitly.",
    examples=("dogopencli refresh payment channel",),
    next=("dogopencli help refresh payment",),
)
SNAPSHOT_NODE = BizNode(
    ("snapshot",),
    "Inspect the installed command tree and local cache metadata offline.",
    options=(
        opt(
            "format",
            "Report format.",
            default="text",
            choices=("json", "text", "table"),
            argument_contract=contract("enum", modes=display_modes()),
        ),
    ),
    constraints=(
        "Optional command path selects a subtree; arguments remain in help.",
        "Offline, read-only metadata inspection; never refreshes or opens a browser.",
    ),
    output={
        "default_format": "text",
        "formats": ["json", "text", "table"],
        "help_default_format": "json",
        "help_formats": ["json", "text"],
    },
    errors=("INVALID_ARGUMENT", "CONFIG_ERROR", "CACHE_ERROR"),
    examples=(
        "dogopencli snapshot",
        "dogopencli snapshot liquidity cash --format json",
    ),
    handler="cmd_snapshot",
)


def build_catalog(declarations: Iterable[BizNode]) -> dict[tuple[str, ...], BizNode]:
    """Reject ambiguous/unreachable declarations and derive direct children."""
    nodes: dict[tuple[str, ...], BizNode] = {}
    for node in declarations:
        node = replace(
            node,
            options=tuple(option for option in node.options if option.name != "all"),
            examples=tuple(
                example.replace("--all", "--limit 0") for example in node.examples
            ),
            constraints=tuple(
                c.replace("--all", "--limit 0") for c in node.constraints
            ),
        )
        if node.path[:1] == ("refresh",) and node.handler is not None:
            existing = {option.name for option in node.options}
            node = replace(
                node,
                options=(
                    *node.options,
                    *(
                        option
                        for option in (LIMIT, OFFSET, FIELDS, FORMAT_TABLE)
                        if option.name not in existing
                    ),
                ),
            )
            if not any(option.name == "require_complete" for option in node.options):
                node = replace(node, options=(*node.options, REQUIRE_COMPLETE))
        if node.path in nodes or node.path in AUTH_PATHS:
            raise ValueError(f"duplicate command path: {node.path}")
        if node.children:
            raise ValueError(f"children must be derived: {node.path}")
        if node.handler is not None and (
            not isinstance(node.handler, str) or not node.handler.isidentifier()
        ):
            raise ValueError(f"invalid handler binding: {node.path}")
        nodes[node.path] = node
    if () not in nodes:
        raise ValueError("command catalog needs a root")
    all_nodes = {**nodes, **{path: AUTH_SPECS[path] for path in AUTH_SPECS if path}}
    for path in all_nodes:
        if path and path[:-1] not in all_nodes:
            raise ValueError(f"missing parent for command: {path}")
    for path, node in nodes.items():
        children = tuple(
            (child_path[-1], child.summary)
            for child_path, child in all_nodes.items()
            if child_path and child_path[:-1] == path
        )
        if not node.handler and not children:
            raise ValueError(f"command must be either group or executable: {path}")
        # An executable node may also be a parent: bare refresh collection va
        # runs its handler while refresh collection va capacity is its child.
        nodes[path] = replace(node, children=children)
    return nodes


def build_domain_catalog(
    domains: Iterable[DomainPlugin],
) -> dict[tuple[str, ...], BizNode]:
    """Build the complete catalog; omitting a component removes every projection."""
    domains = tuple(sorted(domains, key=lambda domain: domain.navigation_order))
    validate_domains(domains)
    queries = tuple(
        _execution_effects(node, leaf.enabled)
        for domain in domains
        for leaf in domain.leaves
        for node in leaf.commands
    )
    refreshes = []
    for domain in domains:
        leaves = {leaf.id: leaf for leaf in domain.leaves}
        for name in (
            *domain.refresh_order,
            *(name for name in leaves if name not in domain.refresh_order),
        ):
            refreshes.extend(
                _execution_effects(node, leaves[name].enabled)
                for node in leaves[name].refresh_commands
            )
    described = tuple(
        description_nodes(
            (
                *queries,
                *(
                    node
                    for domain in domains
                    for leaf in domain.leaves
                    if leaf.describe_refresh
                    for node in leaf.refresh_commands
                ),
            )
        )
    )
    domain_groups = [node for domain in domains for node in domain.groups]
    first_root = next((node for node in domain_groups if len(node.path) == 1), None)
    if first_root is not None:
        domain_groups.insert(domain_groups.index(first_root) + 1, REFRESH_NODE)
    elif refreshes:
        domain_groups.insert(0, REFRESH_NODE)
    declarations = [
        SNAPSHOT_NODE,
        *MANAGEMENT_DECLARATIONS,
        *(node for domain in domains for leaf in domain.leaves for node in leaf.groups),
        *domain_groups,
        ROOT_NODE,
        *(node for node in described if node.path[:1] != ("refresh",)),
        *(
            node
            for domain in domains
            for leaf in domain.leaves
            for node in leaf.prune_commands
        ),
        BizNode(("prune",), "Prune temporary query caches."),
        *refreshes,
    ]
    # Shared projection roots only exist when they contain domain contributions.
    has_refresh = bool(refreshes)
    if not has_refresh:
        declarations = [node for node in declarations if node.path != ("refresh",)]
    if not any(
        node.path[:1] == ("prune",) and len(node.path) > 1 for node in declarations
    ):
        declarations = [node for node in declarations if node.path != ("prune",)]
    return build_catalog(declarations)


def _execution_effects(node: BizNode, enabled: bool) -> BizNode:
    """Describe the local observation write shared by executable leaf handlers."""
    if not enabled:
        return replace(node, effects=dict(NO_EFFECTS), effects_variants=())
    return replace(
        node,
        effects={**node.effects, "mutates": True},
        effects_variants=tuple(
            {
                **variant,
                "effects": {**variant["effects"], "mutates": True},
            }
            for variant in node.effects_variants
        ),
        constraints=(
            *node.constraints,
            "Writes local execution observations; never mutates production business "
            "configuration. Observation storage is separate from the query cache.",
        ),
    )


NODES = build_domain_catalog(domain_plugins())


def resolve_child(path: tuple[str, ...], word: str) -> tuple[str, ...] | None:
    candidate = (*path, word)
    return candidate if candidate in NODES or candidate in AUTH_PATHS else None
