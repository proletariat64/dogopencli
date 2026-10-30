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
    # Explicitly verified widths for List collection; zero extra assumptions.
    allowed_page_sizes: tuple[int, ...] = ()
    scope_field: str | None = None
    # Exact required request values for capabilities with a fixed acquisition.
    fixed_body_values: tuple[tuple[str, str | int], ...] = ()
    # Wire encoding of the validated body: ``json`` posts a JSON body,
    # ``form`` posts application/x-www-form-urlencoded, ``query`` serializes
    # into the URL query. GET always uses ``query`` regardless of this
    # declaration; ``json`` is the default POST encoding.
    encoding: str = "json"
    # RPC inquiries wrap the validated object in a one-element JSON array.
    # Nested inquiry fields remain default-deny at the shared boundary.
    nested_body_keys: tuple[tuple[str, frozenset[str]], ...] = ()
    # Native list identity is the counting unit for these paginated contracts.
    # No existing capability permits repeated arrivals to prove completeness.
    total_semantics: str = "unique_objects"
    duplicate_policy: str = "conservative"
    # Explicit adapter scratch fields removed after SDK selection, before storage.
    internal_fields: tuple[str, ...] = ()
    has_identity: bool = True
    # Named GET sources can carry an exact inquiry object as a JSON string.
    # Its keys, fixed scope and optional page widths are validated before execution.
    json_body_contracts: tuple[
        tuple[
            str,
            frozenset[str],
            tuple[tuple[str, str | int | list[str] | None], ...],
            frozenset[int],
        ],
        ...,
    ] = ()


@dataclass(frozen=True)
class ParsedPage:
    records: list[dict[str, Any]]
    page_num: int
    page_size: int
    # Short-page acquisition does not require native total metadata.
    total_count: int | None
    total_pages: int | None


class TransportCapability(Protocol):
    """The narrow transport-facing seam: one named, allowlisted endpoint.

    Detail inquiries are single allowlisted requests without pagination,
    filters or sorting; they still pass the same default-deny validation.
    """

    @property
    def name(self) -> str: ...

    @property
    def contract(self) -> EndpointContract: ...


class DetailCapability(TransportCapability, Protocol):
    """Pure native detail mapping; the host owns all execution."""

    page_url: str

    def request_body(
        self, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]: ...

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any] | list[dict[str, Any]]: ...


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
        raise CliError(
            "COLLECTION_PROVIDER_NOT_FOUND", "unknown List collection provider"
        )
    owner = _COLLECTION_PROVIDERS[name]
    if owner is not None and owner != domain:
        raise CliError(
            "COLLECTION_PROVIDER_DOMAIN_MISMATCH",
            "List collection provider does not belong to the leaf domain",
        )
    return name
