"""Private, best-effort operational page-width preference for List acquisition.

Only contract fingerprints and observed complete page widths are persisted.
This file never stores scopes, rows, request bodies, authentication or responses.
"""

import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .jsonutil import canonical

MAX_BYTES = 65536
MAX_ENTRIES = 256


def state_key(leaf_id: str, capability: Any, scope: str, sizes: tuple[int, ...]) -> str:
    contract = capability.contract
    raw = canonical(
        {
            "leaf": leaf_id,
            "capability": capability.name,
            "method": contract.method,
            "host": contract.host,
            "path": contract.path,
            "scope": scope,
            "sizes": list(sizes),
        }
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read(path: Path) -> dict[str, int]:
    try:
        if path.stat().st_size > MAX_BYTES:
            return {}
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {}
    if not isinstance(document, dict) or not isinstance(
        document.get("preferences"), dict
    ):
        return {}
    result = {}
    for key, value in document["preferences"].items():
        if (
            isinstance(key, str)
            and len(key) == 64
            and all(c in "0123456789abcdef" for c in key)
            and type(value) is int
            and 0 < value <= 100000
        ):
            result[key] = value
    return dict(list(result.items())[-MAX_ENTRIES:])


def preferred_page_size(
    path: Path | None, key: str, allowed: tuple[int, ...]
) -> int | None:
    if path is None:
        return None
    value = _read(path).get(key)
    return value if value in allowed else None


def remember_page_size(path: Path | None, key: str, size: int) -> None:
    """Atomic, locked, best-effort optimization; never fail an inquiry."""
    if path is None:
        return
    temporary = None
    lock_fd = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        values = _read(path)
        values.pop(key, None)
        values[key] = size
        values = dict(list(values.items())[-MAX_ENTRIES:])
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = stream.name
            os.chmod(temporary, 0o600)
            json.dump({"preferences": values}, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError:
        return
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        if lock_fd is not None:
            os.close(lock_fd)
