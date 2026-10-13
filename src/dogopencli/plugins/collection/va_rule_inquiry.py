"""Native collection VA rule detail inquiry; no detail cache."""

from typing import Any

from ... import collect
from ...transport.cdp import CdpQueryTransport
from . import va_rule


def fetch_detail(transport: CdpQueryTransport, identity: str) -> dict[str, Any]:
    """Explicit live get is strict; refusal tolerance is private to refresh."""
    response = collect.execute_bounded(
        va_rule.COLLECTION_VA_RULES_DETAIL, transport, {"vaRuleId": identity}
    )
    return va_rule.parse_detail(response.body, identity)
