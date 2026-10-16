"""Domain-owned navigation, leaf and cache declarations."""

from dataclasses import replace

from ...browser.environment import LIQUIDITY_STARTUP_URL as ENTRY_POINT
from ...helpspec import (
    BizNode,
)
from .. import DomainAuthPolicy, DomainComponent, LeafRegistration, leaf_registration

GROUPS = (
    BizNode(("prune", "liquidity"), "Prune liquidity temporary caches."),
    BizNode(("prune", "liquidity", "forecast"), "Prune account forecast caches."),
    BizNode(("prune", "liquidity", "operations"), "Prune account strategy caches."),
    BizNode(
        ("liquidity",),
        "Read-only liquidity inquiries: cash, forecast, operations, investment,"
        " risk, rules, network, ledger, pricing and reference data. Every"
        " business leaf declares one kind: runtimes, settings or reference.",
        examples=("dogopencli liquidity investment holdings list",),
        next=("dogopencli help liquidity cash",),
    ),
    BizNode(
        ("refresh", "liquidity"),
        "Replace one temporary liquidity list acquisition.",
        next=("dogopencli help refresh liquidity investment",),
    ),
)


def component() -> DomainComponent:
    leaves: list[LeafRegistration] = []

    def register(capability, **declarations):
        leaves.append(leaf_registration(capability, **declarations))

    from . import leaves as liquidity_leaves
    from . import reading as liquidity_reading

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
            enabled=False,
            commands=(query,),
            refresh_commands=(refresh,),
            description=liquidity_reading.description,
        )
    for leaf in liquidity_leaves.INTERNAL_LIST_LEAVES.values():
        register(leaf.capability(leaf.variants[0]))
    for leaf in liquidity_leaves.INTERNAL_DETAIL_LEAVES.values():
        register(leaf.capability)
    for deferred in liquidity_leaves.DEFERRED:
        node = liquidity_leaves.unsupported_node(deferred)
        register(
            liquidity_leaves.UnsupportedLeafHandle(node),
            enabled=False,
            commands=(node,),
            refresh_commands=(
                replace(node, path=("refresh", "liquidity", *deferred.path[:-1])),
            )
            if deferred in liquidity_leaves.ACCOUNT_PENDING
            else (),
            groups=(),
            description=liquidity_reading.description,
        )
    refresh_paths = [node.path for leaf in leaves for node in leaf.refresh_commands]
    extra_groups = tuple(
        node
        for node in liquidity_leaves.group_nodes()
        if node.path[:1] != ("refresh",)
        or any(path[: len(node.path)] == node.path for path in refresh_paths)
    )

    r06 = {
        "account_t0",
        "account_hours_max",
        "account_daily_max",
        "account_demands_intraday",
        "account_t3",
        "account_demands",
        "account_cashflows",
        "account_strategies",
    }
    for index, leaf in enumerate(leaves):
        aliases = tuple(
            replace(
                node,
                path=("prune", *node.path[:-1]),
                summary="Delete this leaf temporary cache; idempotent and offline.",
                handler="cmd_prune" if leaf.enabled else node.handler,
                options=(),
                effects={
                    "mutates": True,
                    "network": False,
                    "browser_required": False,
                    "destructive": True,
                },
            )
            for node in leaf.commands
            if node.path[-1] == "list" and node.path[-2] in r06
        )
        if aliases:
            leaves[index] = replace(
                leaf, prune_commands=(*leaf.prune_commands, *aliases)
            )

    return DomainComponent(
        id="liquidity",
        navigation_order=2,
        entry_point=ENTRY_POINT,
        leaves=tuple(leaves),
        groups=GROUPS + extra_groups,
        auth=DomainAuthPolicy(
            preserve_headed=True, document_completion=True, bounded_handoff=True
        ),
    )
