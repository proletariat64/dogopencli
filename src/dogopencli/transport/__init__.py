"""Shared transport boundary (ADR 0005).

Every backend access is a structured QueryRequest validated against the
registered endpoint contract before execution. CDP and snapshot are two
implementations of the same QueryTransport; both return an HTTP status,
a raw response body and independent origin metadata, and both feed the
formal plugin parsers.
"""

import json
from dataclasses import dataclass
from typing import Any, Protocol

from ..errors import REQUEST_NOT_ALLOWED, CliError
from ..plugins import EndpointContract


@dataclass(frozen=True)
class QueryRequest:
    capability: str
    method: str
    host: str
    path: str
    body: dict[str, Any]


@dataclass(frozen=True)
class OriginMetadata:
    """Source facts independent of the response body."""

    backend: str
    simulated: bool
    dataset_id: str | None
    dataset_complete: bool | None
    backend_complete: bool | None
    source_observed_from: str | None
    source_observed_to: str | None


@dataclass(frozen=True)
class TransportResponse:
    status: int
    body: bytes
    origin: OriginMetadata
    retry_after: str | None = None


class QueryTransport(Protocol):
    def execute(self, request: QueryRequest) -> TransportResponse:
        """Run one allowlisted request; never mutates business data."""
        ...


def validate_request(request: QueryRequest, contract: EndpointContract) -> None:
    """Default-deny allowlist: host, path, method and body keys."""
    if (
        request.method != contract.method
        or request.host != contract.host
        or request.path != contract.path
    ):
        raise CliError(
            REQUEST_NOT_ALLOWED,
            f"request endpoint is not registered for {request.capability}",
        )
    unknown = sorted(set(request.body) - contract.allowed_body_keys)
    if unknown:
        raise CliError(
            REQUEST_NOT_ALLOWED,
            f"request body keys are not registered: {unknown}",
        )

    for key, expected in contract.fixed_body_values:
        actual = request.body.get(key)
        if type(actual) is not type(expected) or actual != expected:
            raise CliError(
                REQUEST_NOT_ALLOWED,
                f"request field {key} must match its registered fixed value",
            )

    for key, allowed in contract.nested_body_keys:
        value = request.body.get(key)
        if not isinstance(value, dict) or set(value) - allowed:
            raise CliError(
                REQUEST_NOT_ALLOWED,
                f"request field {key} has an unregistered shape",
            )

    for key, allowed, fixed in contract.json_body_contracts:
        value = request.body.get(key)
        try:
            decoded = json.loads(value) if isinstance(value, str) else None
        except (ValueError, TypeError):
            decoded = None
        if not isinstance(decoded, dict) or set(decoded) != allowed:
            raise CliError(
                REQUEST_NOT_ALLOWED,
                f"request JSON field {key} has an unregistered shape",
            )
        for field, expected in fixed:
            actual = decoded.get(field)
            if type(actual) is not type(expected) or actual != expected:
                raise CliError(
                    REQUEST_NOT_ALLOWED,
                    f"request JSON field {key}.{field} must match its fixed value",
                )
