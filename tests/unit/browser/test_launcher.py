"""Unit tests for profile-level locks and the launcher argument construction."""

import pytest

from dogopencli.browser import launcher
from dogopencli.browser.coordination import (
    CONTROL_LOCK_NAME,
    LOGIN_LOCK_NAME,
    acquire_browser_control,
    acquire_file_lock,
    acquire_login_lock,
)
from dogopencli.browser.environment import BrowserEnvironment
from dogopencli.browser.errors import AuthError

PAYMENT_URL = (
    "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
)


def _environment(tmp_path, port: int = 9222) -> BrowserEnvironment:
    return BrowserEnvironment(
        cdp_url=f"http://127.0.0.1:{port}",
        profile=tmp_path / "chrome",
        startup_url=PAYMENT_URL,
        chrome_bin="google-chrome",
        log_path=tmp_path / "chrome.log",
    )


def test_login_lock_conflict(tmp_path):
    held = acquire_login_lock(tmp_path / "profile")
    try:
        with pytest.raises(AuthError) as caught:
            acquire_login_lock(tmp_path / "profile")
        assert caught.value.code == "login_in_progress"
        assert caught.value.retryable is True
    finally:
        held.release()
    acquire_login_lock(tmp_path / "profile").release()


def test_browser_control_conflicts_both_ways(tmp_path):
    profile = tmp_path / "profile"
    held = acquire_browser_control(profile, shared=True)
    try:
        with pytest.raises(AuthError) as caught:
            acquire_browser_control(profile, shared=False)
        assert caught.value.code == "browser_busy"
    finally:
        held.release()
    held = acquire_browser_control(profile, shared=False)
    try:
        with pytest.raises(AuthError) as caught:
            acquire_browser_control(profile, shared=True)
        assert caught.value.code == "browser_busy"
    finally:
        held.release()


def test_shared_control_allows_parallel_readers(tmp_path):
    profile = tmp_path / "profile"
    first = acquire_browser_control(profile, shared=True)
    second = acquire_browser_control(profile, shared=True)
    first.release()
    second.release()


def test_lock_names_are_dogopencli_specific():
    assert LOGIN_LOCK_NAME == ".dogopencli-login.lock"
    assert CONTROL_LOCK_NAME == ".dogopencli-browser-control.lock"
    assert "di-" not in LOGIN_LOCK_NAME + CONTROL_LOCK_NAME


def test_chrome_args_use_dedicated_profile_and_port(tmp_path):
    env = _environment(tmp_path)
    args = launcher._chrome_args(env, "headless")
    assert f"--user-data-dir={env.profile}" in args
    assert "--remote-debugging-port=9222" in args
    assert "--headless=new" in args
    assert "--ozone-platform=wayland" not in args
    joined = " ".join(args)
    assert "di-chrome" not in joined
    assert not any(str(port) in joined for port in range(9330, 9341))


def test_control_held_pass_through_requires_a_real_hold(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(launcher, "_cdp_metadata", lambda url: "")
    with pytest.raises(launcher.LauncherError, match="bypass browser_busy"):
        launcher.launch(_environment(tmp_path), "headless", control_held=True)


def test_control_held_pass_through_when_lock_held(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    env = _environment(tmp_path)
    monkeypatch.setattr(launcher, "_cdp_metadata", lambda url: "")
    monkeypatch.setattr(launcher, "_spawn", lambda e, mode, owner: f"spawned {mode}")
    env.profile.mkdir(parents=True, exist_ok=True)
    held = acquire_file_lock(env.profile / CONTROL_LOCK_NAME)
    try:
        note = launcher.launch(env, "headless", control_held=True)
    finally:
        held.release()
    assert note == "spawned headless"


def test_metadata_mode():
    assert launcher._metadata_mode('{"User-Agent": "HeadlessChrome/128"}') == "headless"
    assert launcher._metadata_mode('{"User-Agent": "Chrome/128"}') == "headed"


@pytest.mark.parametrize("mode", ["headed", "headless"])
def test_same_mode_foreign_browser_is_not_reused(tmp_path, monkeypatch, mode):
    env = _environment(tmp_path)
    agent = "HeadlessChrome/128" if mode == "headless" else "Chrome/128"
    monkeypatch.setattr(
        launcher,
        "_cdp_metadata",
        lambda url: (
            '{"webSocketDebuggerUrl":"ws://local", "User-Agent":"' + agent + '"}'
        ),
    )
    monkeypatch.setattr(
        launcher,
        "_endpoint_process_args",
        lambda port: [["chrome", "--user-data-dir=/foreign"]],
    )
    with pytest.raises(launcher.LauncherError, match="cannot verify"):
        launcher.launch(env, mode)


@pytest.mark.parametrize("separator", ["\0", " "])
@pytest.mark.parametrize(
    "profile_name", ["dedicated", "dedicated profile", "it's mine"]
)
def test_endpoint_process_args_uses_actual_listener(tmp_path, separator, profile_name):
    net = tmp_path / "net"
    net.mkdir()
    (net / "tcp").write_text(
        "header\n0: 0100007F:2406 00000000:0000 0A 0 0 0 1000 0 42\n"
    )
    (net / "tcp6").write_text("header\n")
    for pid, inode, profile in [(100, 42, f"/{profile_name}"), (101, 43, "/foreign")]:
        process = tmp_path / str(pid)
        (process / "fd").mkdir(parents=True)
        (process / "fd" / "1").symlink_to(f"socket:[{inode}]")
        (process / "cmdline").write_bytes(
            f"chrome{separator}--user-data-dir={profile}"
            f"{separator}--remote-debugging-port=9222\0".encode()
        )
    assert launcher._endpoint_process_args(9222, tmp_path) == [
        ["chrome", f"--user-data-dir=/{profile_name}", "--remote-debugging-port=9222"]
    ]


@pytest.mark.parametrize(
    "owners", [[], [["chrome", "--user-data-dir=/foreign"]], [["chrome"], ["chrome"]]]
)
def test_require_profile_fails_closed(tmp_path, monkeypatch, owners):
    monkeypatch.setattr(launcher, "_endpoint_process_args", lambda port: owners)
    with pytest.raises(launcher.LauncherError):
        launcher.require_profile(_environment(tmp_path))


@pytest.mark.parametrize("suffix", ["-other", " other", " extra/profile"])
def test_require_profile_rejects_profile_prefix(tmp_path, monkeypatch, suffix):
    env = _environment(tmp_path)
    monkeypatch.setattr(
        launcher,
        "_endpoint_process_args",
        lambda port: [["chrome", f"--user-data-dir={env.profile}{suffix}"]],
    )
    with pytest.raises(launcher.LauncherError):
        launcher.require_profile(env)


@pytest.mark.parametrize("other", ["--user-data-dir=/foreign", "--user-data-dir"])
def test_require_profile_rejects_multiple_profile_switches(
    tmp_path, monkeypatch, other
):
    env = _environment(tmp_path)
    monkeypatch.setattr(
        launcher,
        "_endpoint_process_args",
        lambda port: [["chrome", f"--user-data-dir={env.profile}", other]],
    )
    with pytest.raises(launcher.LauncherError):
        launcher.require_profile(env)


def test_chrome_keeps_sandbox_and_origin_protection(tmp_path):
    args = launcher._chrome_args(_environment(tmp_path), "headless")
    assert "--no-sandbox" not in args
    assert not any(arg.startswith("--remote-allow-origins") for arg in args)


@pytest.mark.parametrize("mode", ["headless", "headed"])
def test_spawn_opens_one_entry_only_after_profile_verification(
    tmp_path, monkeypatch, mode
):
    env = _environment(tmp_path)
    env.profile.mkdir()
    events = []
    commands = []

    class Process:
        pid = 12345

    class Session:
        def navigate(self, url, timeout):
            events.append("entry")
            assert url == env.startup_url
            assert 0 < timeout <= launcher.READY_WAIT_SECONDS

        def close(self):
            pass

    class Transport:
        def __init__(self, url, **kwargs):
            assert url == env.cdp_url
            self.targets = [
                {"type": "page", "id": "entry", "webSocketDebuggerUrl": "ws://entry"},
                {"type": "page", "id": "old-probe"},
            ]

        def list_targets(self, **kwargs):
            return self.targets

        def open_session(self, url, **kwargs):
            assert url == "ws://entry"
            return Session()

        def close_target(self, target_id):
            assert target_id == "old-probe"
            events.append("closed-probe")
            self.targets = self.targets[:1]

    def popen(command, **kwargs):
        commands.append(command)
        return Process()

    agent = "HeadlessChrome/128" if mode == "headless" else "Chrome/128"
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    monkeypatch.setattr(launcher, "_proc_state_ticks", lambda pid: ("S", "1234"))
    monkeypatch.setattr(
        launcher,
        "_cdp_metadata",
        lambda url: (
            '{"webSocketDebuggerUrl":"ws://local", "User-Agent":"' + agent + '"}'
        ),
    )
    monkeypatch.setattr(
        launcher, "require_profile", lambda e: events.append("verified")
    )
    monkeypatch.setattr(launcher, "HttpCdpTransport", Transport, raising=False)
    owner = launcher._Owner(env.profile / launcher.OWNER_FILE_NAME)
    launcher._spawn(env, mode, owner)
    assert env.startup_url not in commands[0]
    assert "--no-startup-window" not in commands[0]
    assert events == ["verified", "entry", "closed-probe"]


def test_spawn_entry_failure_is_not_reported_as_ready(tmp_path, monkeypatch):
    from dogopencli.browser.cdp import CdpError

    env = _environment(tmp_path)
    env.profile.mkdir()
    stopped = []

    class Process:
        pid = 12345

    class Transport:
        def __init__(self, url, **kwargs):
            pass

        def list_targets(self, **kwargs):
            raise CdpError("entry discovery failed")

    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **kw: Process())
    monkeypatch.setattr(launcher, "_proc_state_ticks", lambda pid: ("S", "1234"))
    monkeypatch.setattr(
        launcher,
        "_cdp_metadata",
        lambda url: (
            '{"webSocketDebuggerUrl":"ws://local", "User-Agent":"HeadlessChrome/128"}'
        ),
    )
    monkeypatch.setattr(launcher, "require_profile", lambda e: None)
    monkeypatch.setattr(launcher, "HttpCdpTransport", Transport, raising=False)
    monkeypatch.setattr(
        launcher, "_stop_owned_chrome", lambda owner, **kw: stopped.append(owner.pid)
    )
    owner = launcher._Owner(env.profile / launcher.OWNER_FILE_NAME)
    with pytest.raises(launcher.LauncherError, match="entry"):
        launcher._spawn(env, "headless", owner)
    assert stopped == [12345]


@pytest.mark.parametrize("disconnect", [False, True])
def test_mode_stop_flushes_browser_without_sigterm(tmp_path, monkeypatch, disconnect):
    from dogopencli.browser.cdp import CdpError

    env = _environment(tmp_path)
    owner = launcher._Owner(tmp_path / "owner")
    owner.pid = 12345
    events = []
    monkeypatch.setattr(owner, "is_valid", lambda profile: profile == env.profile)
    monkeypatch.setattr(
        owner, "remove_if_matches", lambda pid: events.append("removed")
    )
    monkeypatch.setattr(
        launcher, "require_profile", lambda e: events.append("verified")
    )
    monkeypatch.setattr(launcher, "_pid_is_live", lambda pid: False)

    def forbidden_signal(*args):
        pytest.fail("mode switch must not replace Browser.close with SIGTERM")

    monkeypatch.setattr(launcher.os, "kill", forbidden_signal)

    class Session:
        def command(self, method, params, timeout):
            assert (method, params) == ("Browser.close", {})
            events.append("browser-close")
            if disconnect:
                raise CdpError("closed websocket")

        def close(self):
            events.append("session-close")

    class Transport:
        def __init__(self, url):
            assert url == env.cdp_url

        def version(self):
            return {"webSocketDebuggerUrl": "ws://browser"}

        def open_session(self, url):
            assert url == "ws://browser"
            return Session()

    monkeypatch.setattr(launcher, "HttpCdpTransport", Transport)
    launcher._stop_owned_chrome(owner, environment=env)
    assert events == ["verified", "browser-close", "session-close", "removed"]


def test_mode_stop_refuses_unverified_owner(tmp_path, monkeypatch):
    owner = launcher._Owner(tmp_path / "owner")
    monkeypatch.setattr(owner, "is_valid", lambda profile: False)
    monkeypatch.setattr(
        launcher, "HttpCdpTransport", lambda url: pytest.fail("foreign CDP")
    )
    with pytest.raises(launcher.LauncherError, match="cannot verify"):
        launcher._stop_owned_chrome(owner, environment=_environment(tmp_path))
