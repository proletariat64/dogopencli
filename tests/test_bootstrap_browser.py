"""Isolation and non-interference checks for worktree browser setup."""

import runpy
import socket
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/bootstrap_browser.py"


@pytest.fixture
def bootstrap(monkeypatch):
    namespace = runpy.run_path(str(SCRIPT))
    setup = namespace["setup"]
    launcher = setup.__globals__["launcher"]
    monkeypatch.setattr(launcher, "_cdp_metadata", lambda url: "")
    monkeypatch.setattr(launcher, "launch", lambda env, mode: mode)
    return setup


def test_setup_ignores_shared_auth_and_reuses_local_identity(
    tmp_path, monkeypatch, bootstrap
):
    monkeypatch.setenv("DOGOPENCLI_CHROME_PROFILE", "/foreign/profile")
    monkeypatch.setenv("DOGOPENCLI_CHROME_CDP_URL", "http://127.0.0.1:9222")
    first = bootstrap(tmp_path)
    second = bootstrap(tmp_path)
    assert first == second
    assert first.profile.is_relative_to(tmp_path)
    assert first.startup_url == "about:blank"
    directory = first.profile.parent
    text = (directory / "config.toml").read_text()
    assert str(directory / "cache.sqlite3") in text
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / "config.toml").stat().st_mode & 0o777 == 0o600
    other = bootstrap(tmp_path / "other-worktree")
    assert other.profile != first.profile


def test_setup_preserves_headed_mode(tmp_path, monkeypatch, bootstrap):
    launcher = bootstrap.__globals__["launcher"]
    monkeypatch.setattr(launcher, "_cdp_metadata", lambda url: '{"Browser":"Chrome"}')
    calls = []
    monkeypatch.setattr(launcher, "launch", lambda env, mode: calls.append(mode))
    bootstrap(tmp_path)
    assert calls == ["headed"]


def test_setup_refuses_occupied_non_cdp_port(tmp_path, monkeypatch, bootstrap):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        monkeypatch.setitem(
            bootstrap.__globals__, "available_port", lambda: listener.getsockname()[1]
        )
        launcher = bootstrap.__globals__["launcher"]
        monkeypatch.setattr(launcher, "launch", lambda *args: pytest.fail("launched"))
        with pytest.raises(RuntimeError, match="occupied"):
            bootstrap(tmp_path)
        assert listener.fileno() >= 0


def test_setup_refuses_copied_worktree_config(tmp_path, bootstrap):
    bootstrap(tmp_path)
    other = tmp_path / "copy/tmp/bootstrap-browser"
    other.mkdir(parents=True)
    original = tmp_path / "tmp/bootstrap-browser/config.toml"
    (other / "config.toml").write_text(original.read_text())
    with pytest.raises(RuntimeError, match="another worktree"):
        bootstrap(tmp_path / "copy")
