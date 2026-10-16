"""Domain-owned navigation, leaf and cache declarations."""

from dataclasses import replace
from typing import Any

from ...browser.environment import PAYMENT_STARTUP_URL as ENTRY_POINT
from ...helpspec import (
    REFRESH_CDP_CONSTRAINTS,
    REFRESH_CDP_EFFECTS,
    REFRESH_CDP_ERRORS,
    BizNode,
    scope_opt,
)
from ...helpspec import REFRESH_OUTPUT as _REFRESH_OUTPUT
from .. import DomainAuthPolicy, DomainComponent, LeafRegistration, leaf_registration
from .channel import CHANNEL_CAPABILITY
from .cost import COST_CAPABILITY
from .sla import SLA_CAPABILITY

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
    "effects": dict(REFRESH_CDP_EFFECTS),
}
_REFRESH_CHANNEL_NODE = BizNode(
    ("refresh", "payment", "channel"),
    "Import the configured channel source into the local cache.",
    options=(
        scope_opt(
            "payout_type",
            "Payout scope.",
            "str",
            value_type="enum",
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
    cache_capability=CHANNEL_CAPABILITY.name,
)
_REFRESH_COST_NODE = BizNode(
    ("refresh", "payment", "cost"),
    "Rebuild the payment cost cache through the existing CDP session.",
    constraints=REFRESH_CDP_CONSTRAINTS,
    effects=dict(REFRESH_CDP_EFFECTS),
    output=dict(_REFRESH_OUTPUT),
    errors=REFRESH_CDP_ERRORS,
    examples=("dogopencli refresh payment cost",),
    next=("dogopencli help payment cost list",),
    handler="cmd_refresh_cost",
    cache_capability=COST_CAPABILITY.name,
)
_REFRESH_SLA_NODE = BizNode(
    ("refresh", "payment", "sla"),
    "Rebuild the payment SLA baseline cache through the existing CDP session"
    " (list only).",
    constraints=REFRESH_CDP_CONSTRAINTS,
    effects=dict(REFRESH_CDP_EFFECTS),
    output=dict(_REFRESH_OUTPUT),
    errors=REFRESH_CDP_ERRORS,
    examples=("dogopencli refresh payment sla",),
    next=("dogopencli help payment sla baselines list",),
    handler="cmd_refresh_sla",
    cache_capability=SLA_CAPABILITY.name,
)

GROUPS = (
    BizNode(
        ("payment",),
        "Payment product queries: channels, costs, SLA baselines and rules.",
        examples=("dogopencli payment channel list",),
        next=("dogopencli help payment channel",),
    ),
    BizNode(
        ("payment", "channel"),
        "Payment channel queries.",
        examples=("dogopencli payment channel list",),
        next=("dogopencli help payment channel list",),
    ),
    BizNode(
        ("payment", "cost"),
        "Payment channel cost configuration queries.",
        examples=("dogopencli payment cost list",),
        next=("dogopencli help payment cost list",),
    ),
    BizNode(
        ("payment", "sla"),
        "Payment SLA baseline queries.",
        examples=("dogopencli payment sla baselines list",),
        next=("dogopencli help payment sla baselines",),
    ),
    BizNode(
        ("payment", "sla", "baselines"),
        "SLA baseline list and detail queries.",
        examples=("dogopencli payment sla baselines list",),
        next=(
            "dogopencli help payment sla baselines list",
            "dogopencli help payment sla baselines get",
        ),
    ),
    BizNode(
        ("refresh", "payment"),
        "Rebuild payment product caches.",
        examples=("dogopencli refresh payment channel",),
        next=("dogopencli help refresh payment channel",),
    ),
)


def component() -> DomainComponent:
    leaves: list[LeafRegistration] = []

    def register(capability, **declarations):
        leaves.append(leaf_registration(capability, **declarations))

    from . import (
        ptr,
        ptr_orders,
        ptr_orders_reading,
        ptr_reading,
        rules,
        rules_reading,
    )
    from .channel import CHANNEL_CAPABILITY, CHANNEL_LIST_NODE
    from .cost import COST_CAPABILITY, COST_LIST_NODE
    from .reading import description
    from .sla import SLA_CAPABILITY, SLA_GET_NODE, SLA_LIST_NODE

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
    register(CHANNEL_CAPABILITY, commands=(CHANNEL_LIST_NODE,), description=description)
    register(COST_CAPABILITY, commands=(COST_LIST_NODE,), description=description)
    register(
        SLA_CAPABILITY, commands=(SLA_LIST_NODE, SLA_GET_NODE), description=description
    )
    refreshes = {
        CHANNEL_CAPABILITY.name: _REFRESH_CHANNEL_NODE,
        COST_CAPABILITY.name: _REFRESH_COST_NODE,
        SLA_CAPABILITY.name: _REFRESH_SLA_NODE,
    }
    leaves = [
        replace(
            leaf,
            refresh_commands=(refreshes[leaf.id],),
            operations=(*leaf.operations, (refreshes[leaf.id].path, "refresh")),
            cache_paths=(*leaf.cache_paths, refreshes[leaf.id].path),
        )
        if leaf.id in refreshes
        else leaf
        for leaf in leaves
    ]

    return DomainComponent(
        id="payment",
        navigation_order=0,
        entry_point=ENTRY_POINT,
        leaves=tuple(leaves),
        groups=GROUPS,
        auth=DomainAuthPolicy(),
        refresh_order=(
            CHANNEL_CAPABILITY.name,
            COST_CAPABILITY.name,
            *[leaf.id for leaf in leaves if leaf.id not in refreshes],
            SLA_CAPABILITY.name,
        ),
    )
