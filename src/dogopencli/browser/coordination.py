"""Profile-level browser coordination for the dedicated dogopencli Chrome.

Ported from DI ``src/di_common/durable.py`` (flock primitives) and
``src/diauth/coordination.py`` at baseline commit
8eb163c6d140554ca167bd50349a85ca224ac342, with dogopencli lock names. flocks
die with the holding process: a crashed login never leaves a permanent
false-busy state.

- ``.dogopencli-login.lock`` — held exclusive for one whole login operation; a
  concurrent login fails immediately with ``login_in_progress``.
- ``.dogopencli-browser-control.lock`` — held shared by active data work and
  authentication checks (through observation persistence), and
  exclusive by browser mutations (login launch/restart/mode-switch, later
  logout). Either conflict is ``browser_busy``. Authentication checks never
  acquire the login lock or launch/switch Chrome.
"""

import contextlib
import fcntl
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import BROWSER_BUSY, LOGIN_IN_PROGRESS, AuthError

LOGIN_LOCK_NAME = ".dogopencli-login.lock"
CONTROL_LOCK_NAME = ".dogopencli-browser-control.lock"


@dataclass
class FileLock:
    fd: int
    path: Path

    def release(self) -> None:
        with contextlib.suppress(OSError):
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            os.close(self.fd)


def acquire_file_lock(path: Path, *, shared: bool = False) -> FileLock:
    """Hold ``path`` with LOCK_NB; LOCK_SH when ``shared``, else LOCK_EX."""
    path.touch(exist_ok=True)
    fd = os.open(str(path), os.O_RDWR)
    try:
        fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise
    return FileLock(fd=fd, path=path)


def acquire_login_lock(profile: Path) -> FileLock:
    """Take the exclusive login lock; ``login_in_progress`` when held."""
    profile.mkdir(parents=True, exist_ok=True)
    try:
        return acquire_file_lock(profile / LOGIN_LOCK_NAME)
    except BlockingIOError as exc:
        raise AuthError(
            LOGIN_IN_PROGRESS,
            "another dogopencli login operation is in progress for the dedicated "
            f"browser profile {profile}; retry after it finishes",
            details={"profile": str(profile)},
        ) from exc


def acquire_browser_control(profile: Path, *, shared: bool) -> FileLock:
    """Take the browser-control lock; ``browser_busy`` on either conflict."""
    profile.mkdir(parents=True, exist_ok=True)
    try:
        return acquire_file_lock(profile / CONTROL_LOCK_NAME, shared=shared)
    except BlockingIOError as exc:
        message = (
            "a login/logout browser mutation is in progress; retry after it finishes"
            if shared
            else "active data work is using the dedicated browser; "
            "retry after it finishes"
        )
        raise AuthError(
            BROWSER_BUSY, message, details={"profile": str(profile)}
        ) from exc
