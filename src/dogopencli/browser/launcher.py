"""Launcher for the one Chrome process allowed to own the dedicated profile.

Python port of DI ``scripts/launch_di_chrome.sh`` at baseline commit
8eb163c6d140554ca167bd50349a85ca224ac342, with dogopencli profile, locks,
owner record and CDP port. Repeating the active mode is idempotent; a mode
switch stops only the verified owned PID (never a broad process kill); an
externally managed Chrome holding the profile or CDP endpoint is refused with
guidance. ``dogopencli login`` drives the launcher while holding the profile
browser-control lock and passes ``control_held=True`` so the launcher mutates
under that hold instead of taking the lock itself (flocks conflict across
fds, even within one process tree).
"""

import os
import re
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

from . import coordination
from .cdp import CdpError, HttpCdpTransport
from .environment import BrowserEnvironment, cdp_port

OWNER_FILE_NAME = ".dogopencli-chrome-owner"
LAUNCH_LOCK_NAME = ".dogopencli-launch.lock"

#: Bound on waiting for CDP readiness after spawn and for a stopped Chrome.
READY_WAIT_SECONDS = 10.0

_HEADLESS_ARGS = ("--headless=new",)
_COMMON_ARGS = (
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
)


class LauncherError(Exception):
    """A bounded launcher failure; the login layer maps it to browser_unavailable."""


def _chrome_args(environment: BrowserEnvironment, mode: str) -> list[str]:
    args = [
        f"--user-data-dir={environment.profile}",
        f"--remote-debugging-port={cdp_port(environment.cdp_url)}",
        *_COMMON_ARGS,
    ]
    if mode == "headed":
        if os.environ.get("WAYLAND_DISPLAY") or Path("/mnt/wslg/runtime-dir").is_dir():
            args.append("--ozone-platform=wayland")
    else:
        args.extend(_HEADLESS_ARGS)
    return args


def _cdp_metadata(cdp_url: str) -> str:
    try:
        url = cdp_url.rstrip("/") + "/json/version"
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _metadata_mode(metadata: str) -> str:
    return "headless" if "HeadlessChrome/" in metadata else "headed"


def _proc_state_ticks(pid: int) -> tuple[str, str] | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    # field 3 (state) and field 22 (start_ticks) follow the parenthesised comm
    fields = stat.rsplit(")", 1)[1].split()
    if len(fields) < 20:
        return None
    return fields[0], fields[19]


def _pid_is_live(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    state_ticks = _proc_state_ticks(pid)
    return state_ticks is not None and state_ticks[0] != "Z"


class _Owner:
    """The recorded Chrome process started by this launcher."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self.pid = 0
        self.mode = ""
        self.profile = ""
        self.start_ticks = ""

    def load(self) -> bool:
        try:
            lines = self._path.read_text().splitlines()
        except OSError:
            return False
        values = {}
        for line in lines:
            key, _, value = line.partition("=")
            values[key] = value
        try:
            self.pid = int(values.get("pid", ""))
        except ValueError:
            return False
        self.mode = values.get("mode", "")
        self.profile = values.get("profile", "")
        self.start_ticks = values.get("start_ticks", "")
        return True

    def is_valid(self, profile: Path) -> bool:
        if not self.load():
            return False
        if self.profile != str(profile) or self.mode not in ("headed", "headless"):
            return False
        if not _pid_is_live(self.pid):
            return False
        state_ticks = _proc_state_ticks(self.pid)
        if state_ticks is None or state_ticks[1] != self.start_ticks:
            return False
        # Chrome rewrites its argv after startup, so match the flattened
        # cmdline; the trailing space guards against prefix profiles.
        try:
            raw = Path(f"/proc/{self.pid}/cmdline").read_bytes()
        except OSError:
            return False
        cmdline = raw.replace(b"\0", b" ").decode("utf-8", "replace") + " "
        return f"--user-data-dir={profile} " in cmdline

    def remove(self) -> None:
        self._path.unlink(missing_ok=True)

    def remove_if_matches(self, pid: int) -> None:
        if self.load() and self.pid == pid:
            self.remove()


def _profile_lock_pid(profile: Path) -> int | None:
    link = profile / "SingletonLock"
    if not link.is_symlink():
        return None
    try:
        target = os.readlink(link)
    except OSError:
        return None
    pid_text = target.rsplit("-", 1)[-1]
    if not pid_text.isdigit():
        return None
    pid = int(pid_text)
    return pid if _pid_is_live(pid) else None


def _stop_owned_chrome(
    owner: _Owner, *, environment: BrowserEnvironment | None = None
) -> None:
    if environment is not None:
        if not owner.is_valid(environment.profile):
            raise LauncherError("cannot verify owned Chrome before closing it")
        require_profile(environment)
        session = None
        try:
            transport = HttpCdpTransport(environment.cdp_url)
            session = transport.open_session(
                transport.version()["webSocketDebuggerUrl"]
            )
            # Flush cookies and closed-tab records before the mode switch.
            session.command("Browser.close", {}, 2.0)
        except (CdpError, KeyError):
            pass  # Chrome can disconnect while completing Browser.close.
        finally:
            if session is not None:
                session.close()
    else:
        # Recovery when CDP was unavailable; signal only the recorded child.
        try:
            os.kill(owner.pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + READY_WAIT_SECONDS
    while time.monotonic() < deadline:
        if not _pid_is_live(owner.pid):
            owner.remove_if_matches(owner.pid)
            return
        time.sleep(0.1)
    raise LauncherError(
        f"owned Chrome pid {owner.pid} did not stop; close it manually before "
        "switching mode"
    )


def _acquire_control(profile: Path, control_held: bool) -> coordination.FileLock | None:
    """Mutations require the exclusive browser-control lock.

    ``dogopencli login`` already holds the lock for its whole operation and
    passes ``control_held=True``; the pass-through is trusted only when the
    lock really is held — if an exclusive acquisition succeeds here, no
    operation holds it and the caller is trying to bypass browser_busy
    protection.
    """
    path = profile / coordination.CONTROL_LOCK_NAME
    if control_held:
        try:
            probe = coordination.acquire_file_lock(path)
        except BlockingIOError:
            return None  # really held by the caller's operation
        probe.release()
        raise LauncherError(
            "control_held is set but no login/logout holds the browser-control "
            "lock; refusing to bypass browser_busy protection"
        )
    try:
        return coordination.acquire_file_lock(path)
    except BlockingIOError as exc:
        raise LauncherError(
            "browser_busy: active data work is using the dedicated browser; "
            f"retry after it finishes (profile {profile})"
        ) from exc


def _endpoint_process_args(
    port: int, proc_root: Path = Path("/proc")
) -> list[list[str]]:
    """Resolve local listening sockets to their owning processes, fail closed."""
    inodes = set()
    for table in ("tcp", "tcp6"):
        for line in (proc_root / "net" / table).read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] == "0A" and int(fields[1].rsplit(":", 1)[1], 16) == port:
                inodes.add(f"socket:[{fields[9]}]")
    owners = []
    for process in proc_root.iterdir():
        if not process.name.isdigit():
            continue
        try:
            if not any(os.readlink(fd) in inodes for fd in (process / "fd").iterdir()):
                continue
            args = process.joinpath("cmdline").read_bytes().split(b"\0")
            decoded = [arg.decode("utf-8", "strict") for arg in args if arg]
            # Chrome can rewrite argv as one space-joined process title.
            # This is not shell syntax: spaces and quotes inside values are
            # literal. Split at Chrome switch boundaries, not every space.
            # Ambiguous trailing positional text remains part of the value
            # and therefore cannot pass the exact profile check below.
            if len(decoded) == 1:
                decoded = re.split(
                    r" (?=--[a-zA-Z0-9][a-zA-Z0-9-]*(?:=| |$))", decoded[0]
                )
            owners.append(decoded)
        except (OSError, UnicodeError, ValueError):
            continue  # Unreadable processes cannot establish ownership.
    return owners


def require_profile(environment: BrowserEnvironment) -> None:
    """Prove the CDP listener belongs to the configured profile before reuse."""
    try:
        owners = _endpoint_process_args(cdp_port(environment.cdp_url))
        expected = f"--user-data-dir={environment.profile}"
        if len(owners) == 1:
            profiles = [arg for arg in owners[0] if arg.startswith("--user-data-dir")]
            if profiles == [expected]:
                return
    except (OSError, ValueError, IndexError):
        pass
    raise LauncherError(
        f"cannot verify that CDP {environment.cdp_url} belongs to dedicated "
        f"profile {environment.profile}; refusing to reuse or alter that Chrome"
    )


def launch(
    environment: BrowserEnvironment, mode: str, *, control_held: bool = False
) -> str:
    """Ensure the dedicated Chrome runs in ``mode``; return a readiness note."""
    if mode not in ("headed", "headless"):
        raise ValueError(f"unknown Chrome mode: {mode}")
    profile = environment.profile
    profile.mkdir(parents=True, exist_ok=True)
    try:
        launch_lock = coordination.acquire_file_lock(profile / LAUNCH_LOCK_NAME)
    except BlockingIOError as exc:
        raise LauncherError(
            f"another Chrome launcher operation is active for profile {profile}; "
            "retry after it finishes"
        ) from exc
    control: coordination.FileLock | None = None
    try:
        owner = _Owner(profile / OWNER_FILE_NAME)
        metadata = _cdp_metadata(environment.cdp_url)
        if '"webSocketDebuggerUrl"' in metadata:
            require_profile(environment)
            running_mode = _metadata_mode(metadata)
            if running_mode == mode:
                return (
                    f"Chrome already ready | mode {mode} | CDP "
                    f"{environment.cdp_url} | profile {profile}"
                )
            if not owner.is_valid(profile):
                raise LauncherError(
                    f"Chrome on {environment.cdp_url} is mode {running_mode} but is "
                    f"not owned by this launcher; close it before requesting {mode} "
                    f"with dedicated profile {profile}"
                )
            control = _acquire_control(profile, control_held)
            _stop_owned_chrome(owner, environment=environment)
        if owner.is_valid(profile):
            if owner.mode == mode:
                raise LauncherError(
                    f"owned Chrome pid {owner.pid} is running in {mode} mode but "
                    f"CDP is not ready at {environment.cdp_url}; inspect "
                    f"{environment.log_path}"
                )
            if control is None:
                control = _acquire_control(profile, control_held)
            _stop_owned_chrome(owner)
        else:
            owner.remove()
        lock_pid = _profile_lock_pid(profile)
        if lock_pid is not None:
            raise LauncherError(
                f"profile {profile} is in use by unowned pid {lock_pid}; close "
                f"that Chrome before launching {mode}"
            )
        if control is None:
            control = _acquire_control(profile, control_held)
        return _spawn(environment, mode, owner)
    finally:
        if control is not None:
            control.release()
        launch_lock.release()


def _spawn(environment: BrowserEnvironment, mode: str, owner: _Owner) -> str:
    profile = environment.profile
    environment.log_path.parent.mkdir(parents=True, exist_ok=True)
    env_vars = dict(os.environ)
    if Path("/mnt/wslg/runtime-dir").is_dir():
        env_vars.setdefault("WAYLAND_DISPLAY", "wayland-0")
        env_vars.setdefault("XDG_RUNTIME_DIR", "/mnt/wslg/runtime-dir")
    command = [
        environment.chrome_bin,
        *_chrome_args(environment, mode),
    ]
    with environment.log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env_vars,
            start_new_session=True,
        )
    state_ticks = _proc_state_ticks(process.pid)
    if state_ticks is None:
        raise LauncherError(
            f"Chrome exited before ownership could be recorded; inspect "
            f"{environment.log_path}"
        )
    tmp = owner._path.with_name(f"{OWNER_FILE_NAME}.tmp.{process.pid}")
    tmp.write_text(
        f"pid={process.pid}\nmode={mode}\nprofile={profile}\n"
        f"start_ticks={state_ticks[1]}\n"
    )
    tmp.replace(owner._path)
    # Startup-error cleanup must target this child, never an unloaded PID 0.
    owner.pid = process.pid
    note = (
        f"Chrome mode {mode} | pid {process.pid} | CDP {environment.cdp_url} "
        f"| profile {profile}"
    )
    deadline = time.monotonic() + READY_WAIT_SECONDS
    while time.monotonic() < deadline:
        metadata = _cdp_metadata(environment.cdp_url)
        if '"webSocketDebuggerUrl"' in metadata:
            ready_mode = _metadata_mode(metadata)
            if ready_mode != mode:
                _stop_owned_chrome(owner)
                raise LauncherError(
                    f"CDP became ready in {ready_mode} mode, expected {mode}"
                )
            require_profile(environment)
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CdpError("startup deadline exhausted")
                _open_single_entry(environment, deadline=deadline)
            except CdpError as exc:
                try:
                    _stop_owned_chrome(owner, environment=environment)
                except LauncherError:
                    pass
                raise LauncherError(
                    f"Chrome could not open its entry page: {exc}; inspect "
                    f"{environment.log_path}"
                ) from exc
            return note
        if not _pid_is_live(process.pid):
            owner.remove_if_matches(process.pid)
            lock_pid = _profile_lock_pid(profile)
            if lock_pid is not None:
                raise LauncherError(
                    f"Chrome could not open profile {profile} because it is in "
                    f"use by pid {lock_pid}; close that Chrome and retry"
                )
            raise LauncherError(
                f"Chrome exited before CDP became ready; inspect {environment.log_path}"
            )
        time.sleep(0.1)
    try:
        _stop_owned_chrome(owner)
    except LauncherError:
        pass  # the readiness timeout is the reported failure
    raise LauncherError(
        f"CDP did not become ready at {environment.cdp_url} in requested "
        f"{mode} mode; inspect {environment.log_path}"
    )


def _open_single_entry(environment: BrowserEnvironment, *, deadline: float) -> None:
    """Reuse Chrome's startup page; normalize only this newly started browser.

    With no positional URL Chrome creates/restores its window itself. Creating
    another target would trigger delayed restore and duplicate that window.
    This runs under the launch/control locks, before the human-wait phase.
    """
    transport = HttpCdpTransport(environment.cdp_url, timeout=1.0)

    def remaining() -> float:
        budget = deadline - time.monotonic()
        if budget <= 0:
            raise CdpError("entry-page startup deadline exhausted")
        return budget

    def pages() -> list[dict]:
        return [
            t
            for t in transport.list_targets(timeout=remaining())
            if t.get("type") == "page"
        ]

    targets = pages()
    while not targets:
        time.sleep(min(0.1, remaining()))
        targets = pages()
    keep = targets[0]
    if not keep.get("id") or not keep.get("webSocketDebuggerUrl"):
        raise CdpError("startup page has no target/session identifier")
    session = transport.open_session(keep["webSocketDebuggerUrl"], timeout=remaining())
    try:
        session.navigate(environment.startup_url, remaining())
    finally:
        session.close()
    stable = 0
    while stable < 2:
        targets = pages()
        if not any(t.get("id") == keep["id"] for t in targets):
            raise CdpError("startup entry page disappeared")
        extra = [t for t in targets if t.get("id") != keep["id"]]
        for target in extra:
            remaining()
            transport.close_target(target["id"])
        stable = 0 if extra else stable + 1
        time.sleep(min(0.1, remaining()))
