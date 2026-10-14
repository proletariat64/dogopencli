"""Current-query proof of the cash directory's single omitted native position.

Persisted hints accelerate discovery only. No account data enters hint state.
"""

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from ...collect import execute_bounded
from ...errors import TIMEOUT, CliError
from ...jsonutil import canonical
from .capability import LiquidityListCapability

_HINT_VERSION = 1
_HINT_MAX_AGE = 30 * 86400
_MAX_PROBES = 64


class _Unstable(Exception):
    """Successful responses contradict the single-hole hypothesis."""


def _fingerprint(capability: LiquidityListCapability, scope: str) -> str:
    descriptor = capability.descriptor
    body = capability.page_body(scope, 0, 1)
    contract = {
        "version": _HINT_VERSION,
        "host": capability.contract.host,
        "endpoint": descriptor.endpoint,
        "method": descriptor.method,
        "scope": scope,
        "body": body,
        "identity": descriptor.identity,
        "container": descriptor.container,
        "total": descriptor.total,
        "envelope": descriptor.envelope,
    }
    return hashlib.sha256(canonical(contract).encode()).hexdigest()


def _read_hints(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > 65536:
            return {}
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != _HINT_VERSION:
        return {}
    hints = data.get("hints")
    if not isinstance(hints, dict):
        return {}
    # Retain only recognized metadata; never copy arbitrary corrupt payloads.
    return {
        key: {"offset": value["offset"], "verified_at": value["verified_at"]}
        for key, value in hints.items()
        if isinstance(key, str)
        and len(key) == 64
        and all(char in "0123456789abcdef" for char in key)
        and isinstance(value, dict)
        and type(value.get("offset")) is int
        and type(value.get("verified_at")) in (int, float)
        and 0 <= time.time() - value["verified_at"] <= _HINT_MAX_AGE
    }


def _save_hint(path: Path, key: str, offset: int) -> bool:
    temporary: str | None = None
    try:
        hints = _read_hints(path)
        hints[key] = {"offset": offset, "verified_at": time.time()}
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False
        ) as stream:
            temporary = stream.name
            json.dump({"version": _HINT_VERSION, "hints": hints}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        return True
    except OSError:
        return False
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def verify_hole(
    capability: LiquidityListCapability,
    transport: Any,
    scope: str,
    records: list[dict[str, Any]],
    native_total: int,
    deadline: float,
    *,
    hint_path: Path,
) -> dict[str, Any] | None:
    """Verify a stable interior omission; return no exception for ambiguity.

    Malformed/native failed inquiries propagate their normal hard errors.
    The caller must additionally ensure acquisition arrivals had no duplicates
    or uncovered ranges before entering this narrow diagnostic.
    """
    if capability.descriptor.path != ("cash", "accounts"):
        return None
    if native_total < 3 or native_total - len(records) != 1:
        return None
    identities = [capability.identity_key(record) for record in records]
    if len(set(identities)) != len(identities):
        return None
    contents = [canonical(record) for record in records]
    deadline = min(deadline, time.monotonic() + 60)
    probes: list[dict[str, int]] = []
    requests = 0

    class ProbeTransport:
        def execute(self, request: Any, *, timeout: float) -> Any:
            nonlocal requests
            if requests >= _MAX_PROBES or time.monotonic() >= deadline:
                raise CliError(
                    TIMEOUT, "cash hole verification budget exhausted", retryable=True
                )
            requests += 1
            return transport.execute(request, timeout=timeout)

    bounded_transport = ProbeTransport()

    def probe(start: int, size: int) -> list[dict[str, Any]]:
        if len(probes) >= _MAX_PROBES or time.monotonic() >= deadline:
            raise CliError(
                TIMEOUT, "cash hole verification budget exhausted", retryable=True
            )
        body = capability.page_body(scope, start, size)
        response = execute_bounded(capability, bounded_transport, body, deadline)
        rows, total = capability.parse_rows(response.body)
        capability.validate_rows_scope(rows, scope)
        keys = [capability.identity_key(row) for row in rows]
        if total != native_total or len(rows) > size or len(set(keys)) != len(keys):
            raise _Unstable
        probes.append({"row_start": start, "page_size": size, "returned": len(rows)})
        return rows

    def equal(rows: list[dict[str, Any]], expected: list[str]) -> None:
        if [canonical(row) for row in rows] != expected:
            raise _Unstable

    def check(offset: int) -> bool:
        if not 0 < offset < native_total - 1:
            return False
        if probe(offset, 1):
            return False
        neighbors = contents[offset - 1 : offset + 1]
        for _ in range(2):
            equal(probe(offset - 1, 1), neighbors[:1])
            equal(probe(offset + 1, 1), neighbors[1:])
            equal(probe(offset, 1), [])
        equal(probe(offset - 1, 3), neighbors)
        return True

    key = _fingerprint(capability, scope)
    hint = _read_hints(hint_path).get(key, {})
    candidate = hint.get("offset", 2062)
    try:
        # A before/after first-position anchor rechecks totals and acquisition
        # ordering without redownloading the full directory.
        equal(probe(0, 1), contents[:1])
        if not check(candidate):
            low, high = 0, native_total
            while high - low > 1:
                middle = (low + high) // 2
                left = probe(low, middle - low)
                count = len(left)
                if count == middle - low - 1:
                    equal(left, contents[low : middle - 1])
                    high = middle
                elif count == middle - low:
                    equal(left, contents[low:middle])
                    low = middle
                else:
                    return None
            candidate = low
            if not check(candidate):
                return None
        equal(probe(0, 1), contents[:1])
        equal(probe(native_total - 1, 1), contents[-1:])
    except _Unstable:
        return None
    saved = _save_hint(hint_path, key, candidate)
    result: dict[str, Any] = {
        "code": "VERIFIED_BACKEND_HOLE",
        "native_total": native_total,
        "effective_total": native_total - 1,
        "hole_offset": candidate,
        "verification": {
            "probe_count": len(probes),
            "request_count": requests,
            "probes": probes,
        },
        "hint_saved": saved,
    }
    if not saved:
        result["hint_warning"] = "Verified cash hole hint could not be saved"
    return result
