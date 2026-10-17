"""Unit tests for dedicated environment resolution and the port guard."""

from pathlib import Path

import pytest

from dogopencli.browser.environment import (
    DEFAULT_CDP_URL,
    cdp_port,
    resolve_environment,
)
from dogopencli.browser.errors import AuthError
from dogopencli.domain_contracts import PAYMENT_STARTUP_URL


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for name in (
        "DOGOPENCLI_CHROME_PROFILE",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_BIN",
        "DOGOPENCLI_CHROME_LOG",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_use_dogopencli_locations(tmp_path: Path):
    env = resolve_environment(tmp_path / "no-config")
    assert env.cdp_url == DEFAULT_CDP_URL == "http://127.0.0.1:9222"
    assert env.profile == (
        tmp_path / "home" / ".local" / "share" / "dogopencli" / "chrome"
    )
    assert env.startup_url == PAYMENT_STARTUP_URL
    assert env.chrome_bin == "google-chrome"
    assert "di-chrome" not in str(env.profile)


def test_auth_section_overrides(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[auth]\nprofile = "/data/dogopencli/chrome"\n'
        'cdp_url = "http://127.0.0.1:9229"\n'
        'chrome_bin = "chromium"\n'
    )
    env = resolve_environment(config_dir)
    assert env.profile == Path("/data/dogopencli/chrome")
    assert env.cdp_url == "http://127.0.0.1:9229"
    assert env.chrome_bin == "chromium"


def test_environment_variables_win_over_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[auth]\ncdp_url = "http://127.0.0.1:9229"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CHROME_CDP_URL", "http://127.0.0.1:9228")
    monkeypatch.setenv("DOGOPENCLI_CHROME_PROFILE", str(tmp_path / "env-profile"))
    env = resolve_environment(config_dir)
    assert env.cdp_url == "http://127.0.0.1:9228"
    assert env.profile == tmp_path / "env-profile"


@pytest.mark.parametrize("port", (9330, 9333, 9340))
def test_forbidden_ports_rejected(port: int):
    with pytest.raises(AuthError) as caught:
        cdp_port(f"http://127.0.0.1:{port}")
    assert caught.value.code == "config_invalid"


@pytest.mark.parametrize("port", (9222, 9229, 9341))
def test_neighbouring_ports_allowed(port: int):
    assert cdp_port(f"http://127.0.0.1:{port}") == port


def test_missing_port_rejected():
    with pytest.raises(AuthError, match="explicit port"):
        cdp_port("http://127.0.0.1")


def test_unknown_auth_key_rejected(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text('[auth]\nprofile_x = "p"\n')
    with pytest.raises(AuthError) as caught:
        resolve_environment(config_dir)
    assert caught.value.code == "config_invalid"


def test_empty_auth_value_rejected(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text('[auth]\nprofile = "  "\n')
    with pytest.raises(AuthError) as caught:
        resolve_environment(config_dir)
    assert caught.value.code == "config_invalid"
