"""Bounded B01 business retirement policy, independent of source URLs."""

from ...errors import UNSUPPORTED_CAPABILITY, CliError

RETIRED_PATHS = frozenset(
    ("pricing", resource)
    for resource in (
        "factors",
        "factor-values",
        "cost-prices",
        "strategies",
        "client-prices",
        "fee-orders",
    )
)
RETIREMENT_REASON = (
    "Capability retired: the cost/revenue business was discontinued"
    " by business decision "
    "(B01/#164). Historical data is preserved; new acquisition is unavailable."
)


def refuse_retired(path: tuple[str, ...]) -> None:
    """Gate capability ownership without blocking shared endpoint contracts."""
    if path in RETIRED_PATHS:
        raise CliError(UNSUPPORTED_CAPABILITY, RETIREMENT_REASON)


def retired_command(path: tuple[str, ...]) -> bool:
    if path[:2] in (("refresh", "liquidity"), ("prune", "liquidity")):
        return path[2:] in RETIRED_PATHS
    return (
        path[:1] == ("liquidity",)
        and path[-1:] == ("list",)
        and path[1:-1] in RETIRED_PATHS
    )
