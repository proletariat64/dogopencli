"""Private, best-effort operational page-width preference for List acquisition.

Only contract fingerprints and observed complete page widths are persisted.
This file never stores scopes, rows, request bodies, authentication or responses.
"""

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Callable
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
    def update(_document: dict) -> dict:
        values = _read(path)
        values.pop(key, None)
        values[key] = size
        return {"preferences": dict(list(values.items())[-MAX_ENTRIES:])}

    update_state(path, update)


def read_state(path: Path, *, limit: int = MAX_BYTES) -> dict:
    try:
        if path.stat().st_size > limit:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def update_state(path: Path | None, update: Callable[[dict], dict]) -> bool:
    """Atomic, locked, best-effort optimization; never fail an inquiry."""
    if path is None:
        return False
    temporary = None
    lock_fd = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        # A best-effort preference write must never block a successful read.
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        document = update(read_state(path, limit=2 * 1024 * 1024))
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = stream.name
            os.chmod(temporary, 0o600)
            json.dump(document, stream, separators=(",", ":"))
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
        if lock_fd is not None:
            os.close(lock_fd)


def _history_path(path: Path | None) -> Path | None:
    return path.with_name(path.stem + ".holes.json") if path is not None else None


def latest_holes(path: Path | None, key: str, policy: dict) -> list[dict]:
    """Only the latest query can supply hints; never search older FIFO entries."""
    path = _history_path(path)
    if path is None:
        return []
    histories = read_state(path, limit=2 * 1024 * 1024).get("histories", {})
    history = histories.get(key) if isinstance(histories, dict) else None
    if not isinstance(history, list) or not history:
        return []
    entry = history[-1]
    if (
        not isinstance(entry, dict)
        or entry.get("status") != "complete"
        or entry.get("policy") != policy
    ):
        return []
    holes = entry.get("holes")
    if not isinstance(holes, list) or len(holes) > 1000:
        return []
    previous_end = 0
    for hole in holes:
        if not isinstance(hole, dict):
            return []
        lo, hi = hole.get("start"), hole.get("end")
        if (
            type(lo) is not int
            or type(hi) is not int
            or not previous_end <= lo < hi <= 2**53
            or hole.get("kind") not in ("empty", "error")
            or not isinstance(hole.get("fingerprint"), str)
        ):
            return []
        for side in ("left", "right"):
            position, fingerprint = hole.get(side + "_position"), hole.get(side)
            if position is None and fingerprint is None:
                continue
            if (
                type(position) is not int
                or not 0 <= position < 2**53
                or (position >= lo if side == "left" else position < hi)
                or not isinstance(fingerprint, str)
                or len(fingerprint) != 64
                or any(c not in "0123456789abcdef" for c in fingerprint)
            ):
                return []
        previous_end = hi
    return holes


def remember_holes(path: Path | None, key: str, policy: dict, entry: dict) -> bool:
    """Five queries per scoped key, including no-hole and failed acquisitions."""
    from datetime import datetime, timezone

    def update(document: dict) -> dict:
        histories = document.get("histories", {})
        if not isinstance(histories, dict):
            histories = {}
        history = histories.pop(key, [])
        if not isinstance(history, list):
            history = []
        histories[key] = [
            *history[-4:],
            {
                **entry,
                "policy": policy,
                "observed_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        histories = dict(list(histories.items())[-MAX_ENTRIES:])
        # Evict oldest other scopes first; retain the current query's FIFO.
        while len(histories) > 1 and len(json.dumps(histories)) > 2 * 1024 * 1024:
            del histories[next(iter(histories))]
        return {"histories": histories}

    return update_state(_history_path(path), update)
