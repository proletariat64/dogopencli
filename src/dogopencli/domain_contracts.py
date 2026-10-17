"""Side-effect-free domain identity and authentication declarations.

Installed manifests own leaf identity, operation discovery and documentation.
Domain declarations never import or register business implementations.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

PAYMENT_STARTUP_URL = (
    "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
)
FX_STARTUP_URL = "https://app-ipay-qk.alipay.com/ifxriskweb/RiskStandardTrade"
LIQUIDITY_STARTUP_URL = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"


@dataclass(frozen=True)
class DomainAuthPolicy:
    """Behavior consumed by the shared browser authentication lifecycle."""

    preserve_headed: bool = False
    document_completion: bool = False
    bounded_handoff: bool = False
    probe: Callable[..., Any] | None = None


@dataclass(frozen=True)
class DomainDeclaration:
    """One domain's verified entry point and authentication policy."""

    id: str
    entry_point: str
    auth: DomainAuthPolicy = DomainAuthPolicy()


_DOMAINS = (
    DomainDeclaration(
        "payment",
        PAYMENT_STARTUP_URL,
    ),
    DomainDeclaration(
        "collection",
        PAYMENT_STARTUP_URL,
    ),
    DomainDeclaration(
        "fx",
        FX_STARTUP_URL,
        DomainAuthPolicy(
            preserve_headed=True, document_completion=True, bounded_handoff=True
        ),
    ),
    DomainDeclaration(
        "liquidity",
        LIQUIDITY_STARTUP_URL,
        DomainAuthPolicy(
            preserve_headed=True, document_completion=True, bounded_handoff=True
        ),
    ),
)


def domain_declarations() -> tuple[DomainDeclaration, ...]:
    """Return built-in domain metadata without loading business runtimes."""
    return _DOMAINS


STARTUP_URLS = {domain.id: domain.entry_point for domain in domain_declarations()}
