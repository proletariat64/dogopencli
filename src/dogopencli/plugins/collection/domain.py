"""Domain-owned navigation, leaf and cache declarations."""

from ...browser.environment import PAYMENT_STARTUP_URL as ENTRY_POINT
from ...helpspec import BizNode
from .. import DomainAuthPolicy, DomainComponent, LeafRegistration, leaf_registration

GROUPS = (
    BizNode(
        ("collection",),
        "Read-only collection cost, SLA, VA and network configuration queries.",
        next=("dogopencli help collection cost",),
    ),
    BizNode(
        ("collection", "sla"),
        "Collection SLA configuration queries.",
        next=("dogopencli help collection sla configs",),
    ),
    BizNode(
        ("collection", "sla", "configs"),
        "Collection SLA list and true detail queries.",
        next=(
            "dogopencli help collection sla configs list",
            "dogopencli help collection sla configs get",
        ),
    ),
    BizNode(
        ("collection", "cost"),
        "Collection transaction-cost configuration queries.",
        next=("dogopencli help collection cost list",),
    ),
    BizNode(
        ("collection", "va"),
        "Collection VA rule and capacity monitoring queries.",
        next=("dogopencli help collection va rules",),
    ),
    BizNode(
        ("collection", "va", "rules"),
        "Collection VA rule list and true detail queries.",
        next=(
            "dogopencli help collection va rules list",
            "dogopencli help collection va rules get",
        ),
    ),
    BizNode(
        ("collection", "va", "capacity"),
        "Collection VA capacity monitoring queries.",
        next=("dogopencli help collection va capacity list",),
    ),
    BizNode(
        ("refresh", "collection"),
        "Rebuild collection product caches.",
        next=("dogopencli help refresh collection cost",),
    ),
)


def component() -> DomainComponent:
    leaves: list[LeafRegistration] = []

    def register(capability, **declarations):
        leaves.append(leaf_registration(capability, **declarations))

    from .account_isolation import (
        ACCOUNT_ISOLATION,
    )
    from .account_isolation import (
        GROUP_NODE as isolation_group,
    )
    from .account_isolation import (
        LIST_NODE as isolation_list,
    )
    from .account_isolation import (
        REFRESH_NODE as isolation_refresh,
    )
    from .account_isolation_reading import (
        description as isolation_description,
    )
    from .cost import COLLECTION_COST_CAPABILITY, COLLECTION_COST_LIST_NODE
    from .cost import REFRESH_NODE as cost_refresh
    from .network_config import (
        CAPABILITIES,
        group_node,
        list_node,
        refresh_node,
    )
    from .network_reading import description as network_description
    from .reading import description as collection_description
    from .sla import (
        COLLECTION_SLA,
        COLLECTION_SLA_GET_NODE,
        COLLECTION_SLA_LIST_NODE,
    )
    from .sla import REFRESH_NODE as sla_refresh
    from .sla_reading import description as sla_description
    from .va_capacity import (
        COLLECTION_VA_CAPACITY,
        COLLECTION_VA_CAPACITY_LIST_NODE,
    )
    from .va_capacity import REFRESH_NODE as capacity_refresh
    from .va_capacity_reading import (
        description as va_capacity_description,
    )
    from .va_rule import (
        COLLECTION_VA_RULE_GET_NODE,
        COLLECTION_VA_RULE_LIST_NODE,
        COLLECTION_VA_RULES,
    )
    from .va_rule import REFRESH_NODE as va_refresh
    from .va_rule_reading import description as va_rule_description

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
    register(
        ACCOUNT_ISOLATION,
        commands=(isolation_list,),
        refresh_commands=(isolation_refresh,),
        groups=(isolation_group,),
        description=isolation_description,
    )
    return DomainComponent(
        id="collection",
        navigation_order=1,
        entry_point=ENTRY_POINT,
        leaves=tuple(leaves),
        groups=GROUPS,
        auth=DomainAuthPolicy(),
        refresh_order=(
            *[cap.name for cap in CAPABILITIES],
            COLLECTION_COST_CAPABILITY.name,
            COLLECTION_SLA.name,
            COLLECTION_VA_RULES.name,
            COLLECTION_VA_CAPACITY.name,
            ACCOUNT_ISOLATION.name,
        ),
    )
