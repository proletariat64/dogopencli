"""Public-CLI SIT for ``dogopencli logout`` (issue #8).

Drives ``dogopencli logout`` through dogopencli.cli.main with the browser/CDP
external boundary replaced by the scripted stand-ins in ``fake_cdp.py``: the
fake CDP transport records page-level cookie commands and decides what the
post-clearing verification probe observes. No real Chrome, network, company
authentication, or cookie database is involved.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_cdp import (
    IPAYBUSERVICE_LOGIN_URL,
    LOOKALIKE_COOKIE,
    PAYMENT_URL,
    SSO_URL,
    UNRELATED_COOKIE,
    FakeBrowser,
    seed_cookies,
)

import dogopencli.browser.logout as logout_mod
from dogopencli.browser import cdp
from dogopencli.browser.coordination import (
    CONTROL_LOCK_NAME,
    LOGIN_LOCK_NAME,
    acquire_browser_control,
    acquire_file_lock,
    acquire_login_lock,
)

CDP_URL = "http://127.0.0.1:9222"


@pytest.fixture
def logout_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    profile = tmp_path / "chrome-profile"
    (config_dir / "config.toml").write_text(
        f'[auth]\nprofile = "{profile}"\ncdp_url = "{CDP_URL}"\n'
    )
    state = FakeBrowser()
    monkeypatch.setattr(
        "dogopencli.browser.launcher._endpoint_process_args",
        lambda port: [["chrome", f"--user-data-dir={profile}"]],
    )
    seed_cookies(state)
    monkeypatch.setattr("dogopencli.browser.launcher.launch", state.launch)
    cdp.set_transport_factory(state.transport)
    yield SimpleNamespace(
        state=state,
        config_dir=config_dir,
        profile=profile,
        tmp_path=tmp_path,
        argv=["--config-dir", str(config_dir)],
    )
    cdp.set_transport_factory(None)


def invoke(run_cli, argv: list[str]) -> tuple[int, dict, str]:
    code, out, err = run_cli(argv)
    value = json.loads(out)
    assert "\x1b" not in out
    assert out.count("\n") == 1
    assert value["output_version"] == 1
    assert value["exit_code"] == code
    return code, value, err


def locks_released(profile: Path) -> bool:
    try:
        acquire_file_lock(profile / LOGIN_LOCK_NAME).release()
        acquire_file_lock(profile / CONTROL_LOCK_NAME).release()
    except BlockingIOError:
        return False
    return True


def remaining_domains(state: FakeBrowser) -> set[str]:
    return {cookie["domain"] for cookie in state.cookies}


# --- success: clear the applicable families and verify the SSO redirect ------


def test_logout_success_clears_and_verifies(run_cli, logout_setup):
    state = logout_setup.state
    state.href = SSO_URL  # without the session cookies the entry redirects
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 0
    assert value["command"] == "logout"
    assert value["error"] is None
    result = value["result"]
    assert result["authenticated"] is False
    assert result["verified"] is True
    assert result["cleared"] == "cdp"
    assert result["cookies_deleted"] == 5
    assert result["domains"] == [
        "antglobal-inc.com",
        "ifundcontrol.alipay.com",
        "iglobalfundcontrol.alipay.com",
        "alipay.com",
    ]
    assert result["cdp_url"] == CDP_URL
    assert result["profile"] == str(logout_setup.profile)
    assert result["mode"] == "headless"
    assert "remote company SSO session is not revoked" in result["note"]
    # Every family cookie deleted through page-level CDP; foreign cookies —
    # including the lookalike host — survive untouched.
    deleted = {(c["name"], c["domain"]) for c in state.deleted_cookies}
    assert ("SSO_GLOBAL_AUTHTOKEN", ".alipay.com") in deleted
    assert ("LOOKALIKE", ".notantglobal-inc.com") not in deleted
    assert remaining_domains(state) == {
        LOOKALIKE_COOKIE["domain"],
        UNRELATED_COOKIE["domain"],
    }
    # Local only: no launch/mode switch, no navigation but the payment-entry
    # verification probe, no remote logout endpoint, temporary targets closed.
    assert state.launches == []
    urls = [url for transport in state.transports for url in transport.created]
    assert set(urls) == {"about:blank", PAYMENT_URL}
    navigations = [
        url for transport in state.transports for url in transport.navigations
    ]
    assert navigations == [PAYMENT_URL]
    assert all("logout" not in url.lower() for url in urls + navigations)
    closed = [t for transport in state.transports for t in transport.closed]
    assert len(closed) == len(urls)
    assert locks_released(logout_setup.profile)


def test_logout_delayed_entry_redirect_still_verifies(
    run_cli, logout_setup, monkeypatch
):
    """UAT 2026-09-12: after clearing, the entry settles on its own URL and
    only redirects to the ipaybuservice login page seconds later; the probe's
    bounded stability window must catch it for the logout to verify."""
    state = logout_setup.state
    monkeypatch.setattr(cdp, "ENTRY_STABILITY_SECONDS", 2.0)
    state.href = PAYMENT_URL
    state.href_flip = (2, IPAYBUSERVICE_LOGIN_URL)
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 0
    result = value["result"]
    assert result["authenticated"] is False
    assert result["verified"] is True
    assert result["cookies_deleted"] == 5
    assert locks_released(logout_setup.profile)


def test_logout_idempotent_second_run(run_cli, logout_setup):
    state = logout_setup.state
    state.href = SSO_URL
    code, _, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 0
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 0
    assert value["result"]["cookies_deleted"] == 0
    assert value["result"]["verified"] is True


def test_logout_text_format_result(run_cli, logout_setup):
    logout_setup.state.href = SSO_URL
    code, out, _ = run_cli([*logout_setup.argv, "--format", "text", "logout"])
    assert code == 0
    assert "authenticated: False" in out
    assert "verified: True" in out


# --- verification failures: never a claimed logout ----------------------------


def test_logout_unverified_when_still_authenticated(run_cli, logout_setup):
    state = logout_setup.state
    state.href = PAYMENT_URL  # the entry stays authenticated after clearing
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 1
    assert value["result"] is None
    error = value["error"]
    assert error["code"] == "logout_unverified"
    assert error["retryable"] is False
    assert "NOT in effect" in error["message"]
    assert error["next"]
    assert state.deleted_cookies  # clearing ran; only verification failed
    assert locks_released(logout_setup.profile)


def test_logout_inconclusive_probe_is_service_failure(run_cli, logout_setup):
    logout_setup.state.href = "https://unrelated.example.com/error page"
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "service_failure"
    assert error["retryable"] is True


@pytest.mark.parametrize("unreachable_before_clear", [False, True])
def test_logout_invalidates_auth_only_after_reaching_cookie_clear(
    run_cli, logout_setup, unreachable_before_clear
):
    code, _, _ = invoke(
        run_cli, [*logout_setup.argv, "auth", "check", "--domain", "payment"]
    )
    assert code == 0
    logout_setup.state.running = not unreachable_before_clear
    logout_setup.state.href = "https://unexpected.example/"
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 1
    assert value["error"]["code"] == (
        "browser_unavailable" if unreachable_before_clear else "service_failure"
    )
    _, output, _ = run_cli([*logout_setup.argv, "domain", "show", "payment"])
    outcome = json.loads(output)["result"]["auth"]["outcome"]
    assert outcome == ("authenticated" if unreachable_before_clear else "unknown")
    assert bool(logout_setup.state.deleted_cookies) is not unreachable_before_clear


# --- CDP unavailable / clearing failure: explicit, cookie store untouched -----


def test_logout_cdp_unreachable_fails_without_touching_cookie_store(
    run_cli,
    logout_setup,
):
    state = logout_setup.state
    state.running = False
    profile = logout_setup.profile
    profile.mkdir(parents=True)
    cookie_store = profile / "Cookies"
    cookie_store.write_bytes(b"sentinel-cookie-store")
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "browser_unavailable"
    assert error["retryable"] is True
    assert "not changed" in error["message"]
    assert state.deleted_cookies == []
    assert cookie_store.read_bytes() == b"sentinel-cookie-store"
    assert state.launches == []  # logout never starts or repairs Chrome
    assert locks_released(profile)


def test_logout_clearing_failure_is_retryable(run_cli, logout_setup):
    logout_setup.state.probe_error = True  # page-level commands fail
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "browser_unavailable"
    assert error["retryable"] is True
    assert "partially cleared" in error["message"]
    assert locks_released(logout_setup.profile)


# --- coordination conflicts ----------------------------------------------------


def test_logout_concurrent_login_is_login_in_progress(run_cli, logout_setup):
    held = acquire_login_lock(logout_setup.profile)
    try:
        code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    finally:
        held.release()
    assert code == 1
    error = value["error"]
    assert error["code"] == "login_in_progress"
    assert error["retryable"] is True
    # The conflict aborts before any browser or authentication mutation.
    assert logout_setup.state.transports == []
    assert logout_setup.state.deleted_cookies == []


def test_logout_during_data_work_is_browser_busy(run_cli, logout_setup):
    held = acquire_browser_control(logout_setup.profile, shared=True)
    try:
        code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    finally:
        held.release()
    assert code == 1
    error = value["error"]
    assert error["code"] == "browser_busy"
    assert error["retryable"] is True
    assert logout_setup.state.transports == []
    assert logout_setup.state.deleted_cookies == []


# --- business data stays untouched ---------------------------------------------


def test_logout_never_touches_business_cache_or_cookie_store(
    run_cli,
    logout_setup,
):
    logout_setup.state.href = SSO_URL
    cache_file = logout_setup.tmp_path / "cache.sqlite3"
    cache_file.write_bytes(b"sentinel-business-cache")
    profile = logout_setup.profile
    profile.mkdir(parents=True)
    cookie_store = profile / "Cookies"
    cookie_store.write_bytes(b"sentinel-cookie-store")
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 0
    assert value["result"]["verified"] is True
    assert cache_file.read_bytes() == b"sentinel-business-cache"
    assert cookie_store.read_bytes() == b"sentinel-cookie-store"


# --- interruption ----------------------------------------------------------------


def test_logout_interrupt_exits_130_and_releases_locks(
    run_cli, logout_setup, monkeypatch
):
    def raise_sigint(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(logout_mod, "delete_domain_cookies", raise_sigint)
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 130
    assert value["result"] is None
    assert value["error"]["code"] == "interrupted"
    assert locks_released(logout_setup.profile)


# --- argument matrix and help ----------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    (
        ["logout", "extra"],  # no positional arguments
        ["logout", "--yes"],  # no confirmation bypass
        ["logout", "--force"],
        ["logout", "--format", "table"],  # auth supports json/text only
        ["logout", "--format", "markdown"],
        ["logout", "--timeout-seconds", "5"],  # login-only option
        ["logout", "--json"],  # hidden compatibility alias rejected
    ),
)
def test_logout_invalid_arguments(run_cli, logout_setup, argv):
    code, value, _ = invoke(run_cli, [*logout_setup.argv, *argv])
    assert code == 1
    assert value["result"] is None
    error = value["error"]
    assert error["code"] == "invalid_arguments"
    assert error["retryable"] is False
    assert error["next"]
    assert logout_setup.state.launches == []
    assert logout_setup.state.deleted_cookies == []


def test_logout_help_is_json_by_default(run_cli, logout_setup):
    code, out, _ = run_cli(["logout", "--help"])
    assert code == 0
    document = json.loads(out)["data"]
    assert document["command"] == "dogopencli logout"
    names = [option["name"] for option in document["options"]]
    assert "timeout_seconds" not in names
    assert "yes" not in names
    assert "force" not in names
    for global_name in (
        "config_dir",
        "format",
        "verbose",
        "quiet",
        "no_color",
        "help",
        "version",
    ):
        assert global_name in names
    assert document["output"]["formats"] == ["json", "text"]
    assert "logout_unverified" in document["errors"]


def test_logout_refuses_foreign_profile(run_cli, logout_setup, monkeypatch):
    state = logout_setup.state
    monkeypatch.setattr(
        "dogopencli.browser.launcher._endpoint_process_args",
        lambda port: [["chrome", "--user-data-dir=/unrelated-profile"]],
    )
    before = list(state.cookies)
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 1
    assert value["error"]["code"] == "browser_unavailable"
    assert state.cookies == before


def test_malformed_cookie_is_reported_before_family_deletion(run_cli, logout_setup):
    state = logout_setup.state
    state.cookies.append({"domain": ".antglobal-inc.com", "path": "/"})
    before = list(state.cookies)
    code, value, _ = invoke(run_cli, [*logout_setup.argv, "logout"])
    assert code == 1
    assert value["error"]["code"] == "browser_unavailable"
    assert state.cookies == before
