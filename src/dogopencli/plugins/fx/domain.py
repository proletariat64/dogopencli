"""Domain-owned navigation, leaf and cache declarations."""

from dataclasses import replace

from ...browser.environment import FX_STARTUP_URL as ENTRY_POINT
from ...helpspec import (
    BizNode,
)
from .. import DomainAuthPolicy, DomainComponent, LeafRegistration, leaf_registration
from .trade import GROUP_NODE as FX_GROUP

GROUPS = (
    BizNode(("refresh", "fx"), "Refresh FX temporary query caches."),
    FX_GROUP,
)


def component() -> DomainComponent:
    leaves: list[LeafRegistration] = []

    def register(capability, **declarations):
        leaves.append(leaf_registration(capability, **declarations))

    from .trade import FX_TRADE, TRADE_NODE
    from .trade import description as fx_description

    register(
        FX_TRADE,
        commands=(TRADE_NODE,),
        description=fx_description,
    )
    leaves = [
        replace(
            leaf,
            refresh_commands=(
                replace(
                    TRADE_NODE,
                    path=("refresh", "fx", "trade"),
                    handler="cmd_refresh_fx_trade",
                    cache_capability=FX_TRADE.name,
                    options=tuple(
                        option
                        for option in TRADE_NODE.options
                        if option.name not in ("live", "require_fresh")
                    ),
                ),
            ),
        )
        for leaf in leaves
    ]

    leaves = [
        replace(
            leaf,
            operations=(
                (("fx", "trade"), "list"),
                (("refresh", "fx", "trade"), "refresh"),
            ),
            cache_paths=(("fx", "trade"), ("refresh", "fx", "trade")),
        )
        for leaf in leaves
    ]

    return DomainComponent(
        id="fx",
        navigation_order=3,
        entry_point=ENTRY_POINT,
        leaves=tuple(leaves),
        groups=GROUPS,
        auth=DomainAuthPolicy(
            preserve_headed=True, document_completion=True, bounded_handoff=True
        ),
    )
