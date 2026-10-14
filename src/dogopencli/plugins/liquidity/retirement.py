"""Bounded B01/R01 business retirement policy, independent of source URLs."""

from ...errors import UNSUPPORTED_CAPABILITY, CliError

B01_PATHS = frozenset(
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


R01_REASONS = {
    ("cash", "groups"): (
        "Selected obsolete cash grouping configuration; dated source "
        "evidence is historical."
    ),
    ("investment", "strategies"): (
        "Selected obsolete investment strategy configuration; dated "
        "source evidence is historical."
    ),
    ("rules", "notification"): (
        "Selected discontinued notification configuration; dated source "
        "evidence is historical."
    ),
    ("ledger", "customers"): (
        "Ledger model confirmed unused by business decision; recent "
        "source timestamps do not revoke retirement."
    ),
    ("ledger", "accounts"): (
        "Both INNER and OUTER ledger models confirmed unused by business "
        "decision; recent source timestamps do not revoke retirement."
    ),
    ("reference", "business-lines"): (
        "Selected obsolete business-line directory; dated source evidence "
        "is historical."
    ),
    ("reference", "calendars"): (
        "Selected historical calendar coverage; dated coverage does not "
        "establish current support."
    ),
}
RETIRED_PATHS = B01_PATHS | R01_REASONS.keys()


def retirement_reason(path: tuple[str, ...]) -> str:
    """Describe the owning decision without asserting source-system shutdown."""
    if path[:2] in (("refresh", "liquidity"), ("prune", "liquidity")):
        path = path[2:]
    elif path[:1] == ("liquidity",):
        path = path[1:-1]
    if path in R01_REASONS:
        return (
            "Capability retired (R01/#167): "
            + R01_REASONS[path]
            + " Historical data is preserved; new acquisition is unavailable."
        )
    return RETIREMENT_REASON


def refuse_retired(path: tuple[str, ...]) -> None:
    """Gate capability ownership without blocking shared endpoint contracts."""
    if path in RETIRED_PATHS:
        raise CliError(UNSUPPORTED_CAPABILITY, retirement_reason(path))


def retired_command(path: tuple[str, ...]) -> bool:
    if path[:2] in (("refresh", "liquidity"), ("prune", "liquidity")):
        return path[2:] in RETIRED_PATHS
    return (
        path[:1] == ("liquidity",)
        and path[-1:] == ("list",)
        and path[1:-1] in RETIRED_PATHS
    )
