"""Integration tests drive the public CLI fully offline: no network and no
browser process may be started."""

import socket
import subprocess
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def no_network_no_browser(monkeypatch: pytest.MonkeyPatch):
    def blocked(*args: Any, **kwargs: Any):
        raise AssertionError("network or browser access is forbidden in SIT")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
