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
