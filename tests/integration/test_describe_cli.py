"""Offline discovery and rejection through the public CLI."""

import socket
import sqlite3

import pytest

from dogopencli import cli

PATHS = [
    ["payment", "channel", "list"],
    ["payment", "cost", "list"],
    ["payment", "sla", "baselines", "list"],
    ["payment", "sla", "baselines", "get"],
]


@pytest.fixture
def offline(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("description attempted business/environment access")

    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "invalid.toml"))
    (tmp_path / "invalid.toml").write_text("not valid = [ TOML")
    monkeypatch.setattr(cli.config_mod, "load", forbidden)
    monkeypatch.setattr(cli, "Cache", forbidden)
    monkeypatch.setattr(cli, "inquiry_session", forbidden)
    monkeypatch.setattr(cli, "load_dataset", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    from dogopencli.auth import cli as auth_cli
    from dogopencli.browser import cdp

    monkeypatch.setattr(auth_cli, "main", forbidden)
    monkeypatch.setattr(cdp, "make_transport", forbidden)
    for name in ("cmd_channel_list", "cmd_cost_list", "cmd_sla_list", "cmd_sla_get"):
        monkeypatch.setattr(cli, name, forbidden)
    return tmp_path
