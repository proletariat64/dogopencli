"""Public-CLI SIT for the authentication commands (issue #3).

Drives ``dogopencli login`` / ``dogopencli auth check`` through
dogopencli.cli.main with the browser/CDP external boundary replaced by the
scripted stand-ins in ``fake_cdp.py``: the fake CDP transport decides what
each bounded probe observes, the fake launcher records mode switches, and the
human SSO action is a scripted href flip. No real Chrome, network, or company
authentication is involved.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_cdp import (
    IPAYBUSERVICE_LOGIN_URL,
    PAYMENT_ORIGIN,
    PAYMENT_URL,
    SSO_URL,
    FakeBrowser,
)

import dogopencli.browser.login as login_mod
from dogopencli import __version__
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
def auth_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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


@pytest.fixture
def fast_clock(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(login_mod, "POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(login_mod, "HANDOFF_SETTLE_SECONDS", 0)


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


# --- login: browser lifecycle ------------------------------------------------


def test_login_healthy_headless_reused_without_restart(run_cli, auth_setup):
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "login"])
    assert code == 0
    assert value["command"] == "login"
    assert value["error"] is None
    result = value["result"]
    assert result["authenticated"] is True
    assert result["mode"] == "headless"
    assert result["cdp_url"] == CDP_URL
    assert result["profile"] == str(auth_setup.profile)
    assert result["probe"]["startup_url"] == PAYMENT_URL
    assert result["probe"]["final_origin"] == PAYMENT_ORIGIN
    assert auth_setup.state.launches == []
    assert locks_released(auth_setup.profile)
    # Login never refreshes business caches.
    assert list(auth_setup.tmp_path.rglob("*.sqlite3")) == []


def test_login_absent_chrome_starts_headless(run_cli, auth_setup):
    auth_setup.state.running = False
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "login"])
    assert code == 0
    assert auth_setup.state.launches == ["headless"]
    assert value["result"]["authenticated"] is True


def test_login_headed_chrome_switches_to_headless(run_cli, auth_setup):
    auth_setup.state.mode = "headed"
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "login"])
    assert code == 0
    assert auth_setup.state.launches == ["headless"]
    assert value["result"]["mode"] == "headless"


def test_login_expired_session_enters_human_flow_and_succeeds(
    run_cli, auth_setup, fast_clock
):
    state = auth_setup.state
    state.href = SSO_URL  # expired: every probe sees the SSO redirect
    completed = {"done": False}

    def human_completes_sso(browser):
        browser.href = PAYMENT_URL
        completed["done"] = True
        return PAYMENT_URL

    # Probes: headless expiry, one still-waiting poll, then the human action.
    state.hrefs = [SSO_URL, SSO_URL, human_completes_sso]
    code, value, err = invoke(run_cli, [*auth_setup.argv, "login"])
    assert code == 0
    assert completed["done"] is True
    assert state.launches == ["headed", "headless"]
    assert state.mode == "headless"
    result = value["result"]
    assert result["authenticated"] is True
    assert result["mode"] == "headless"
    assert "headed mode" in err  # progress goes to stderr
    # Only initial expiry, headed verification, and headless verification
    # create targets. Both human-wait polls attach to the existing form.
    assert sum(len(t.created) for t in state.transports) == 3
    assert sum(len(t.navigations) for t in state.transports) == 3
    assert locks_released(auth_setup.profile)


def test_login_default_timeout_is_600_seconds(run_cli, auth_setup):
    code, out, _ = run_cli([*auth_setup.argv, "login", "--help"])
    assert code == 0
    document = json.loads(out)
    (option,) = [o for o in document["options"] if o["name"] == "timeout_seconds"]
    assert option["default"] == 600.0
    assert option["type"] == "positive"


def test_login_timeout_preserves_headed_chrome(
    run_cli, auth_setup, fast_clock, monkeypatch
):
    from dogopencli.browser import probe as probe_mod

    # Advance after one pending response, rather than racing a 50ms wall-clock
    # deadline during another CDP probe on a loaded machine.
    clock = [0.0]
    monkeypatch.setattr(login_mod, "monotonic", lambda: clock[0])
    monkeypatch.setattr(probe_mod, "monotonic", lambda: clock[0])
    monkeypatch.setattr(login_mod, "sleep", lambda _: clock.__setitem__(0, 0.05))
    auth_setup.state.href = SSO_URL  # the human never completes SSO
    code, value, err = invoke(
        run_cli, [*auth_setup.argv, "login", "--timeout-seconds", "0.05"]
    )
    assert code == 1
    error = value["error"]
    assert error["code"] == "auth_required"
    assert error["retryable"] is True
    assert error["details"]["profile"] == str(auth_setup.profile)
    assert any("dogopencli login" in step for step in error["next"])
    assert auth_setup.state.launches == ["headed"]
    assert auth_setup.state.mode == "headed"  # preserved for the next login
    assert locks_released(auth_setup.profile)


def test_login_interrupt_preserves_headed_and_exits_130(
    run_cli, auth_setup, monkeypatch
):
    auth_setup.state.href = SSO_URL

    def raise_sigint(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(login_mod, "sleep", raise_sigint)
    code, value, err = invoke(run_cli, [*auth_setup.argv, "login"])
    assert code == 130
    assert value["error"]["code"] == "interrupted"
    assert auth_setup.state.mode == "headed"
    assert "re-run dogopencli login" in err
    assert locks_released(auth_setup.profile)


def test_login_after_timeout_continues_from_headed(run_cli, auth_setup, fast_clock):
    state = auth_setup.state
    state.href = SSO_URL
    code, _, _ = invoke(
        run_cli, [*auth_setup.argv, "login", "--timeout-seconds", "0.05"]
    )
    assert code == 1
    assert state.mode == "headed"
    # Second login recovers the state it finds: the preserved headed Chrome is
    # switched to headless for the probe, and a healthy session succeeds.
    state.href = PAYMENT_URL
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "login"])
    assert code == 0
    assert value["result"]["authenticated"] is True


def test_login_headed_launch_failure_is_actionable(run_cli, auth_setup, fast_clock):
    auth_setup.state.href = SSO_URL
    auth_setup.state.fail_modes.add("headed")  # a host without a GUI
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "login"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "browser_unavailable"
    assert error["retryable"] is True
    assert "visible Chrome" in error["message"]
    assert "GUI" in error["message"]


def test_login_service_failure_never_enters_human_flow(run_cli, auth_setup, fast_clock):
    auth_setup.state.href = "https://unrelated.example.com/error page"
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "login"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "service_failure"
    assert error["details"]["expected_origin"] == PAYMENT_ORIGIN
    assert auth_setup.state.launches == []  # no headed switch, no human flow


def test_login_headless_handoff_failure_is_non_success(
    run_cli, auth_setup, fast_clock, monkeypatch
):
    monkeypatch.setattr(login_mod, "MAX_HANDOFF_ATTEMPTS", 2)

    def headed_only(browser):
        # Headed probes see a completed SSO; headless probes keep redirecting.
        return PAYMENT_URL if browser.mode == "headed" else SSO_URL

    auth_setup.state.href = headed_only
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "login"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "auth_required"
    assert error["details"]["handoff_attempts"] == 2
    assert auth_setup.state.launches == ["headed", "headless", "headed", "headless"]


def test_login_concurrent_login_is_login_in_progress(run_cli, auth_setup):
    held = acquire_login_lock(auth_setup.profile)
    try:
        code, value, _ = invoke(run_cli, [*auth_setup.argv, "login"])
    finally:
        held.release()
    assert code == 1
    error = value["error"]
    assert error["code"] == "login_in_progress"
    assert error["retryable"] is True
    assert auth_setup.state.launches == []  # conflict aborts before mutations


def test_login_during_data_work_is_browser_busy(run_cli, auth_setup):
    held = acquire_browser_control(auth_setup.profile, shared=True)
    try:
        code, value, _ = invoke(run_cli, [*auth_setup.argv, "login"])
    finally:
        held.release()
    assert code == 1
    error = value["error"]
    assert error["code"] == "browser_busy"
    assert error["retryable"] is True
    assert auth_setup.state.launches == []


# --- auth check: bounded read-only probe -------------------------------------


def test_auth_check_authenticated_headless(run_cli, auth_setup):
    code, value, err = invoke(run_cli, [*auth_setup.argv, "auth", "check"])
    assert code == 0
    assert err == ""
    assert value["command"] == "auth.check"
    result = value["result"]
    assert result["authenticated"] is True
    assert result["mode"] == "headless"
    assert result["cdp_url"] == CDP_URL
    assert result["profile"] == str(auth_setup.profile)
    assert result["probe"]["final_origin"] == PAYMENT_ORIGIN
    # Read-only: no launch, no mode switch, no lock files, no profile creation.
    assert auth_setup.state.launches == []
    assert not auth_setup.profile.exists()


def test_auth_check_headed_mode_is_also_verified(run_cli, auth_setup):
    auth_setup.state.mode = "headed"
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "auth", "check"])
    assert code == 0
    assert value["result"]["mode"] == "headed"
    assert auth_setup.state.mode == "headed"  # never switched or repaired


def test_auth_check_expired_session_is_auth_required(run_cli, auth_setup):
    auth_setup.state.href = SSO_URL
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "auth", "check"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "auth_required"
    assert error["retryable"] is True
    assert error["details"]["final_origin"] == "https://tonelogin.antglobal-inc.com"
    assert any("dogopencli login" in step for step in error["next"])
    # Credentials and ticket material never enter the output.
    assert "token" not in json.dumps(value)
    assert auth_setup.state.launches == []  # no human login initiated


def test_auth_check_ipaybuservice_login_is_auth_required(run_cli, auth_setup):
    # UAT 2026-09-12: the unauthenticated entry lands on ipaybuservice
    # /login.htm, not the company SSO origin.
    auth_setup.state.href = IPAYBUSERVICE_LOGIN_URL
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "auth", "check"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "auth_required"
    assert error["retryable"] is True
    assert error["details"]["final_origin"] == "https://ipaybuservice.alipay.com"
    assert any("dogopencli login" in step for step in error["next"])
    assert auth_setup.state.launches == []


def test_auth_check_delayed_entry_redirect_is_auth_required(
    run_cli, auth_setup, monkeypatch
):
    # UAT 2026-09-12: the cleared entry settles on its own URL first; the
    # JS-driven redirect to the ipaybuservice login page fires seconds later.
    state = auth_setup.state
    monkeypatch.setattr(cdp, "ENTRY_STABILITY_SECONDS", 2.0)
    state.href = PAYMENT_URL
    state.href_flip = (2, IPAYBUSERVICE_LOGIN_URL)
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "auth", "check"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "auth_required"
    assert error["details"]["final_origin"] == "https://ipaybuservice.alipay.com"
    assert auth_setup.state.launches == []


def test_auth_check_unreachable_browser_is_browser_unavailable(run_cli, auth_setup):
    auth_setup.state.running = False
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "auth", "check"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "browser_unavailable"
    assert error["retryable"] is True
    assert auth_setup.state.launches == []  # check never starts Chrome


def test_auth_check_probe_failure_is_browser_unavailable(run_cli, auth_setup):
    auth_setup.state.probe_error = True
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "auth", "check"])
    assert code == 1
    assert value["error"]["code"] == "browser_unavailable"


def test_auth_check_unexpected_origin_is_service_failure(run_cli, auth_setup):
    auth_setup.state.href = "https://unrelated.example.com/error page"
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "auth", "check"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "service_failure"
    assert error["retryable"] is True
    assert "inconclusive" in error["message"]


# --- dedicated endpoints, ports and paths ------------------------------------


def test_forbidden_cdp_port_is_rejected(run_cli, tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[auth]\ncdp_url = "http://127.0.0.1:9333"\n'
    )
    code, value, _ = invoke(run_cli, ["--config-dir", str(config_dir), "auth", "check"])
    assert code == 1
    error = value["error"]
    assert error["code"] == "config_invalid"
    assert "9330-9340" in error["message"]


def test_probe_targets_payment_entry_not_di(run_cli, auth_setup):
    code, _, _ = invoke(run_cli, [*auth_setup.argv, "auth", "check"])
    assert code == 0
    (transport,) = auth_setup.state.transports
    assert transport.created == [PAYMENT_URL]
    assert transport.closed == ["created-1"]  # temporary targets always close


# --- help, version, formats and the argument matrix --------------------------


def test_bare_auth_shows_help_and_exits_0(run_cli, auth_setup):
    code, out, _ = run_cli([*auth_setup.argv, "auth"])
    assert code == 0
    document = json.loads(out)
    assert document["help_version"] == 1
    assert document["command"] == "dogopencli auth"
    assert [child["name"] for child in document["children"]] == ["check"]
    assert document["output"]["help_default_format"] == "json"


def test_login_help_is_json_by_default(run_cli, auth_setup):
    code, out, _ = run_cli(["login", "--help"])
    assert code == 0
    document = json.loads(out)
    assert document["command"] == "dogopencli login"
    names = [option["name"] for option in document["options"]]
    assert "timeout_seconds" in names
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


def test_help_text_format(run_cli, auth_setup):
    code, out, _ = run_cli(["--format", "text", "login", "--help"])
    assert code == 0
    assert "--timeout-seconds" in out
    assert "default: 600.0" in out


def test_auth_check_help(run_cli, auth_setup):
    code, out, _ = run_cli(["auth", "check", "-h"])
    assert code == 0
    assert json.loads(out)["command"] == "dogopencli auth check"


def test_version_envelope(run_cli, auth_setup):
    for argv in (["login", "--version"], ["auth", "--version"]):
        code, value, _ = invoke(run_cli, argv)
        assert code == 0
        assert value["command"] == "version"
        assert value["result"] == {"version": __version__}


def test_text_format_result(run_cli, auth_setup):
    code, out, _ = run_cli([*auth_setup.argv, "--format", "text", "auth", "check"])
    assert code == 0
    assert "authenticated: True" in out


def test_text_format_error_goes_to_stderr(run_cli, auth_setup):
    auth_setup.state.href = SSO_URL
    code, out, err = run_cli([*auth_setup.argv, "--format", "text", "auth", "check"])
    assert code == 1
    assert out == ""
    assert err.startswith("auth_required: ")
    assert "Next:" in err


def test_globals_may_follow_the_command(run_cli, auth_setup):
    code, value, _ = invoke(
        run_cli, ["auth", "check", "--config-dir", str(auth_setup.config_dir)]
    )
    assert code == 0
    assert value["result"]["authenticated"] is True


def test_verbose_and_quiet_channels(run_cli, auth_setup):
    code, _, err = run_cli([*auth_setup.argv, "--verbose", "auth", "check"])
    assert code == 0
    assert "dogopencli: auth.check; config=" in err
    code, out, err = run_cli([*auth_setup.argv, "--quiet", "auth", "check"])
    assert code == 0
    assert err == ""


def test_no_color_accepted(run_cli, auth_setup):
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "--no-color", "auth", "check"])
    assert code == 0


@pytest.mark.parametrize(
    "argv",
    (
        ["auth", "check", "browser_context"],  # deprecated positional rejected
        ["login", "--json"],  # hidden compatibility alias rejected
        ["auth", "check", "--form", "json"],  # no option-name abbreviation
        ["login", "--verbose", "--quiet"],
        ["login", "--format", "table"],  # auth supports json/text only
        ["auth", "check", "--format", "markdown"],
        ["login", "--timeout-seconds", "abc"],
        ["login", "--timeout-seconds", "0"],
        ["login", "--timeout-seconds", "-5"],
        ["login", "--timeout-seconds", "nan"],
        ["login", "--timeout-seconds", "inf"],
        ["auth", "logout"],  # issue #8 scope; unknown for now
        ["auth", "check", "extra"],
        ["auth", "bogus"],
    ),
)
def test_invalid_arguments(run_cli, auth_setup, argv):
    code, value, _ = invoke(run_cli, [*auth_setup.argv, *argv])
    assert code == 1
    assert value["result"] is None
    error = value["error"]
    assert error["code"] == "invalid_arguments"
    assert error["retryable"] is False
    assert error["next"]
    assert auth_setup.state.launches == []


def test_empty_config_dir_is_invalid(run_cli, auth_setup):
    code, value, _ = invoke(run_cli, ["--config-dir", "", "login"])
    assert code == 1
    assert value["error"]["code"] == "invalid_arguments"
    assert "cannot be empty" in value["error"]["message"]


def test_login_refuses_foreign_profile(run_cli, auth_setup, monkeypatch):
    state = auth_setup.state
    monkeypatch.setattr(
        "dogopencli.browser.launcher._endpoint_process_args",
        lambda port: [["chrome", "--user-data-dir=/unrelated-profile"]],
    )
    before = list(state.launches)
    code, value, _ = invoke(run_cli, [*auth_setup.argv, "login"])
    assert code == 1
    assert value["error"]["code"] == "browser_unavailable"
    assert state.launches == before


def test_auth_uses_custom_config_filename(run_cli, auth_setup, monkeypatch):
    custom = auth_setup.tmp_path / "custom-name.toml"
    custom.write_text((auth_setup.config_dir / "config.toml").read_text())
    monkeypatch.delenv("DOGOPENCLI_CONFIG_DIR", raising=False)
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(custom))
    code, value, _ = invoke(run_cli, ["auth", "check"])
    assert code == 0
    assert value["result"]["profile"] == str(auth_setup.profile)
