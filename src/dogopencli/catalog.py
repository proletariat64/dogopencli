"""Static command assembly shared by navigation and execution.

Plugin registration supplies query declarations, including handler bindings.
Group children are derived from paths. Building this catalog requires no
configuration, authentication, cache, browser, or network access.
"""

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from .auth.spec import SPECS as AUTH_SPECS
from .describe import description_nodes
from .helpspec import REFRESH_OUTPUT as _REFRESH_OUTPUT
from .helpspec import BizNode, opt
from .plugins import command_nodes, group_nodes, refresh_nodes

# The shared root is business-owned; auth retains its own help protocol.
AUTH_PATHS = frozenset(path for path in AUTH_SPECS if path)

_REFRESH_EFFECTS_BASE = {
    "mutates": True,
    "network": False,
    "browser_required": False,
    "destructive": False,
}
_REFRESH_SNAPSHOT_VARIANT: dict[str, Any] = {
    "when": "the configured source is a snapshot dataset",
    "summary": "imports the local dataset; no network and no browser",
    "effects": {
        "mutates": True,
        "network": False,
        "browser_required": False,
        "destructive": False,
    },
}
_REFRESH_CDP_VARIANT: dict[str, Any] = {
    "when": "the configured source is cdp",
    "summary": "queries the backend through the existing CDP session and"
    " rebuilds the cache",
    "effects": {
        "mutates": True,
        "network": True,
        "browser_required": True,
        "destructive": False,
    },
}
_REFRESH_CDP_EFFECTS: dict[str, Any] = {
    "mutates": True,
    "network": True,
    "browser_required": True,
    "destructive": False,
}

_REFRESH_CHANNEL_NODE = BizNode(
    ("refresh", "payment", "channel"),
    "Import the configured channel source into the local cache.",
    options=(
        opt(
            "payout_type",
            "Payout scope.",
            "str",
            default="EXTERNAL",
            choices=("EXTERNAL", "LIQUIDITY", "MANUAL", "SETTLEMENT"),
        ),
    ),
    constraints=(
        "The source branch is decided by configuration; both branches are"
        " listed statically in effects_variants.",
        "Progress diagnostics go to stderr; the result envelope goes to stdout.",
    ),
    effects=dict(_REFRESH_EFFECTS_BASE),
    effects_variants=(_REFRESH_SNAPSHOT_VARIANT, _REFRESH_CDP_VARIANT),
    output=dict(_REFRESH_OUTPUT),
    errors=(
        "INVALID_ARGUMENT",
        "CONFIG_ERROR",
        "SOURCE_DATA_MISSING",
        "SOURCE_DATA_INVALID",
        "SOURCE_SCOPE_UNAVAILABLE",
        "INVALID_RESPONSE",
        "AUTH_REQUIRED",
        "BROWSER_UNAVAILABLE",
        "LOCKED",
        "TIMEOUT",
        "BUSINESS_QUERY_FAILED",
    ),
    examples=(
        "dogopencli refresh payment channel",
        "dogopencli refresh payment channel --payout-type EXTERNAL",
    ),
    next=("dogopencli help payment channel list",),
    handler="cmd_refresh_channel",
)

_REFRESH_COST_NODE = BizNode(
    ("refresh", "payment", "cost"),
    "Rebuild the payment cost cache through the existing CDP session.",
    constraints=(
        "Requires the CDP source and an existing authenticated browser session.",
        "Progress diagnostics go to stderr; the result envelope goes to stdout.",
    ),
    effects=dict(_REFRESH_CDP_EFFECTS),
    output=dict(_REFRESH_OUTPUT),
    errors=(
        "INVALID_ARGUMENT",
        "CONFIG_ERROR",
        "INVALID_RESPONSE",
        "AUTH_REQUIRED",
        "BROWSER_UNAVAILABLE",
        "LOCKED",
        "TIMEOUT",
        "BUSINESS_QUERY_FAILED",
    ),
    examples=("dogopencli refresh payment cost",),
    next=("dogopencli help payment cost list",),
    handler="cmd_refresh_cost",
)

_REFRESH_SLA_NODE = BizNode(
    ("refresh", "payment", "sla"),
    "Rebuild the payment SLA baseline cache through the existing CDP session"
    " (full list, then every detail).",
    constraints=(
        "Requires the CDP source and an existing authenticated browser session.",
        "Progress diagnostics go to stderr; the result envelope goes to stdout.",
    ),
    effects=dict(_REFRESH_CDP_EFFECTS),
    output=dict(_REFRESH_OUTPUT),
    errors=(
        "INVALID_ARGUMENT",
        "CONFIG_ERROR",
        "INVALID_RESPONSE",
        "AUTH_REQUIRED",
        "BROWSER_UNAVAILABLE",
        "LOCKED",
        "TIMEOUT",
        "BUSINESS_QUERY_FAILED",
    ),
    examples=("dogopencli refresh payment sla",),
    next=("dogopencli help payment sla baselines list",),
    handler="cmd_refresh_sla",
)

_GROUPS: dict[tuple[str, ...], BizNode] = {
    (): BizNode(
        (),
        "Inquiry-only, read-only payment and collection operations queries; the default"
        " reads the local cache.",
        constraints=(
            "Business queries never modify production business configuration.",
        ),
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
    ),
    ("payment",): BizNode(
        ("payment",),
        "Payment product queries: channels, costs, and SLA baselines.",
        examples=("dogopencli payment channel list",),
        next=("dogopencli help payment channel",),
    ),
    ("payment", "channel"): BizNode(
        ("payment", "channel"),
        "Payment channel queries.",
        examples=("dogopencli payment channel list",),
        next=("dogopencli help payment channel list",),
    ),
    ("payment", "cost"): BizNode(
        ("payment", "cost"),
        "Payment channel cost configuration queries.",
        examples=("dogopencli payment cost list",),
        next=("dogopencli help payment cost list",),
    ),
    ("payment", "sla"): BizNode(
        ("payment", "sla"),
        "Payment SLA baseline queries.",
        examples=("dogopencli payment sla baselines list",),
        next=("dogopencli help payment sla baselines",),
    ),
    ("payment", "sla", "baselines"): BizNode(
        ("payment", "sla", "baselines"),
        "SLA baseline list and detail queries.",
        examples=("dogopencli payment sla baselines list",),
        next=(
            "dogopencli help payment sla baselines list",
            "dogopencli help payment sla baselines get",
        ),
    ),
    ("refresh",): BizNode(
        ("refresh",),
        "Explicitly rebuild local caches; never runs implicitly.",
        examples=("dogopencli refresh payment channel",),
        next=("dogopencli help refresh payment",),
    ),
    ("refresh", "payment"): BizNode(
        ("refresh", "payment"),
        "Rebuild payment product caches.",
        examples=("dogopencli refresh payment channel",),
        next=("dogopencli help refresh payment channel",),
    ),
    ("collection",): BizNode(
        ("collection",),
        "Read-only collection cost, SLA and VA queries.",
        next=("dogopencli help collection cost",),
    ),
    ("collection", "sla"): BizNode(
        ("collection", "sla"),
        "Collection SLA configuration queries.",
        next=("dogopencli help collection sla configs",),
    ),
    ("collection", "sla", "configs"): BizNode(
        ("collection", "sla", "configs"),
        "Collection SLA list and true detail queries.",
        next=(
            "dogopencli help collection sla configs list",
            "dogopencli help collection sla configs get",
        ),
    ),
    ("collection", "cost"): BizNode(
        ("collection", "cost"),
        "Collection transaction-cost configuration queries.",
        next=("dogopencli help collection cost list",),
    ),
    ("collection", "va"): BizNode(
        ("collection", "va"),
        "Collection VA rule and capacity monitoring queries.",
        next=("dogopencli help collection va rules",),
    ),
    ("collection", "va", "rules"): BizNode(
        ("collection", "va", "rules"),
        "Collection VA rule list and true detail queries.",
        next=(
            "dogopencli help collection va rules list",
            "dogopencli help collection va rules get",
        ),
    ),
    ("collection", "va", "capacity"): BizNode(
        ("collection", "va", "capacity"),
        "Collection VA capacity monitoring queries.",
        next=("dogopencli help collection va capacity list",),
    ),
    ("refresh", "collection"): BizNode(
        ("refresh", "collection"),
        "Rebuild collection product caches.",
        next=("dogopencli help refresh collection cost",),
    ),
}


def build_catalog(declarations: Iterable[BizNode]) -> dict[tuple[str, ...], BizNode]:
    """Reject ambiguous/unreachable declarations and derive direct children."""
    nodes: dict[tuple[str, ...], BizNode] = {}
    for node in declarations:
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


NODES = build_catalog(
    (
        *group_nodes(),
        *_GROUPS.values(),
        *description_nodes(command_nodes()),
        _REFRESH_CHANNEL_NODE,
        _REFRESH_COST_NODE,
        *refresh_nodes(),
        _REFRESH_SLA_NODE,
    )
)


def resolve_child(path: tuple[str, ...], word: str) -> tuple[str, ...] | None:
    candidate = (*path, word)
    return candidate if candidate in NODES or candidate in AUTH_PATHS else None
