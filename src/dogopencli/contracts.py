"""Side-effect-free endpoint, page and acquisition contracts.

Leaf packages own business requests and parsers. Shared collection and restricted
transport consume these protocols without importing leaf implementations.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class EndpointContract:
    """Verified inquiry endpoint; the shared allowlist rejects anything else."""

    method: str
    host: str
    path: str
    page_size: int
    one_based: bool
    allowed_body_keys: frozenset[str]
    # Verified larger capacity allowing one full-candidate rebuild on
    # business-success coverage gaps. None means no rebuild clause.
    rebuild_page_size: int | None = None
    # Explicitly verified widths for opt-in List collection; zero extra assumptions.
    allowed_page_sizes: tuple[int, ...] = ()
    scope_field: str | None = None
    # A repeated business identifier with differing content prevents proof of
    # completeness without making that identifier a deduplication key.
    consistency_field: str | None = None
    # Exact required request values for capabilities with a fixed acquisition.
    fixed_body_values: tuple[tuple[str, str | int], ...] = ()
    # A running estimate acquires until the first short page and validates
    # completeness against the final converged total. False keeps the
    # verified fixed-total contract.
    running_total: bool = False
    # Wire encoding of the validated body: ``json`` posts a JSON body,
    # ``form`` posts application/x-www-form-urlencoded, ``query`` serializes
    # into the URL query. GET always uses ``query`` regardless of this
    # declaration; ``json`` is the default POST encoding.
    encoding: str = "json"
    # RPC inquiries wrap the validated object in a one-element JSON array.
    # Nested inquiry fields remain default-deny at the shared boundary.
    nested_body_keys: tuple[tuple[str, frozenset[str]], ...] = ()
    # Only one response is verified for fixed-page inquiries. A reported
    # total beyond its capacity becomes a coverage gap, never a new request.
    single_page: bool = False
    # Native list identity is the counting unit for these paginated contracts.
    # No existing capability permits repeated arrivals to prove completeness.
    total_semantics: str = "unique_objects"
    duplicate_policy: str = "conservative"
    has_identity: bool = True
    # Business keys and versions do not establish native row identity.
    # Distinct content under an unverified key leaves consistency unproven.
    consistency_version_field: str | None = None
    # Named GET sources can carry an exact inquiry object as a JSON string.
    # Its keys, fixed scope and optional page widths are validated before execution.
    json_body_contracts: tuple[
        tuple[str, frozenset[str], tuple[tuple[str, str | int], ...], frozenset[int]],
        ...,
    ] = ()


@dataclass(frozen=True)
class ParsedPage:
    records: list[dict[str, Any]]
    page_num: int
    page_size: int
    total_count: int
    total_pages: int


class TransportCapability(Protocol):
    """The narrow transport-facing seam: one named, allowlisted endpoint.

    Detail inquiries are single allowlisted requests without pagination,
    filters or sorting; they still pass the same default-deny validation.
    """

    @property
    def name(self) -> str: ...

    @property
    def contract(self) -> EndpointContract: ...


class Capability(TransportCapability, Protocol):
    """A leaf-owned request builder, page parser and native identity policy."""

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        """Build one page's allowlisted inquiry object."""
        ...

    def identity_key(self, record: dict[str, Any]) -> Any:
        """Native row identity for a candidate with a proven identity contract."""
        ...

    def parse_page(self, body: bytes) -> ParsedPage:
        """Parse and validate the native envelope without changing field values."""
        ...


# A fixed built-in provider catalogue; no Domain SDK registration or versioning.
_COLLECTION_PROVIDERS: dict[str, str | None] = {
    "general": None,
    "payment.collection": "payment",
    "collection.collection": "collection",
    "fx.collection": "fx",
    "liquidity.collection": "liquidity",
}


def resolve_collection_provider(domain: str, name: str) -> str:
    """Resolve a single trusted provider and enforce its owner-domain boundary."""
    from .errors import CliError

    if name not in _COLLECTION_PROVIDERS:
        raise CliError("COLLECTION_PROVIDER_NOT_FOUND", "unknown List collection provider")
    owner = _COLLECTION_PROVIDERS[name]
    if owner is not None and owner != domain:
        raise CliError(
            "COLLECTION_PROVIDER_DOMAIN_MISMATCH",
            "List collection provider does not belong to the leaf domain",
        )
    return name
