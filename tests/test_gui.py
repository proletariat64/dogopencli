"""Public localhost HTTP behavior for the domain control interface."""

import json
import os
import re
import select
import signal
import socket
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from dogopencli import gui
from dogopencli.errors import CliError


class DomainInventory:
    """Small registration/service fixture; no browser or business transport."""

    enabled = True

    def inventory(self):
        return [
            {
                "id": "payment",
                "entry_point": "https://example.test/shared",
                "enabled": self.enabled,
                "auth": {"outcome": "unknown", "updated_at": None},
                "leaves": [
                    {
                        "id": "sample",
                        "enabled": True,
                        "effective_enabled": True,
                        "last_execution": {"outcome": "unknown", "updated_at": None},
                    }
                ],
            }
        ]

    def set_enabled(self, domain_id, enabled):
        if domain_id != "payment":
            raise CliError("INVALID_ARGUMENT", "Unknown domain")
        self.enabled = enabled
        return self.inventory()[0]


@pytest.fixture
def running_gui():
    server = gui.create_server(DomainInventory())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_offline_domain_inventory_and_local_page(running_gui):
    server, url = running_gui
    assert server.server_address[0] == "127.0.0.1"
    with urlopen(url + "/api/domains") as response:
        inventory = json.load(response)["domains"]
    assert inventory[0]["id"] == "payment"
    assert inventory[0]["leaves"][0]["id"] == "sample"
    with urlopen(url) as response:
        page = response.read().decode()
        assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "Domains" in page
    assert "textContent" in page
    with pytest.raises(HTTPError) as failure:
        urlopen(url + "/login")
    assert failure.value.code == 404


def page_token(url):
    with urlopen(url) as response:
        return re.search(r"const token='([^']+)'", response.read().decode())[1]


def post(url, path, payload, **headers):
    return urlopen(
        Request(
            url + path,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Dogopencli-Token": page_token(url),
                **headers,
            },
        )
    )


def test_domain_toggle_visible_on_next_inventory(running_gui):
    _, url = running_gui
    with post(url, "/api/domains/payment", {"enabled": False}) as response:
        assert json.load(response)["domain"]["enabled"] is False
    with urlopen(url + "/api/domains") as response:
        assert json.load(response)["domains"][0]["enabled"] is False
    with pytest.raises(HTTPError) as failure:
        post(url, "/api/domains/payment/leaves/sample", {"enabled": False})
    assert failure.value.code == 404


@pytest.mark.parametrize(
    "payload", [None, {}, {"enabled": 1}, {"enabled": False, "id": "fx"}]
)
def test_invalid_toggle_does_not_change_domain(running_gui, payload):
    _, url = running_gui
    with pytest.raises(HTTPError) as failure:
        post(url, "/api/domains/payment", payload)
    assert failure.value.code == 400
    with urlopen(url + "/api/domains") as response:
        assert json.load(response)["domains"][0]["enabled"] is True


def test_cross_origin_and_rebound_host_cannot_access_gui(running_gui):
    _, url = running_gui
    with pytest.raises(HTTPError) as failure:
        post(
            url, "/api/domains/payment", {"enabled": False}, Origin="https://evil.test"
        )
    assert failure.value.code == 403
    with pytest.raises(HTTPError) as failure:
        urlopen(Request(url + "/api/domains", headers={"Host": "evil.test"}))
    assert failure.value.code == 403
    with pytest.raises(HTTPError) as failure:
        urlopen(
            Request(
                url + "/api/domains/payment",
                data=b'{"enabled": false}',
                headers={"Content-Type": "application/json"},
            )
        )
    assert failure.value.code == 403


def test_failed_save_reports_error_and_preserves_state():
    class FailingSave(DomainInventory):
        def set_enabled(self, domain_id, enabled):
            raise CliError("STATE_ERROR", "Cannot save operational state")

    server = gui.create_server(FailingSave())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with pytest.raises(HTTPError) as failure:
            post(url, "/api/domains/payment", {"enabled": False})
        assert failure.value.code == 500
        assert json.load(failure.value)["error"]["code"] == "STATE_ERROR"
        with urlopen(url + "/api/domains") as response:
            assert json.load(response)["domains"][0]["enabled"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_gui_help_is_offline_and_supports_json_text(capsys):
    assert gui.main(["--help"]) == 0
    help_data = json.loads(capsys.readouterr().out)
    assert help_data["command"] == "dogopencli gui"
    assert help_data["help_version"] == 1
    assert gui.main(["--help", "--format", "text"]) == 0
    assert "--port" in capsys.readouterr().out


def test_cli_and_gui_share_durable_state_without_read_side_effects(
    monkeypatch, tmp_path, capsys
):
    from dogopencli import domain_cli, plugins
    from dogopencli.domains import DomainService

    domain = SimpleNamespace(
        id="payment", entry_point="https://example.test/", leaves=()
    )
    monkeypatch.setattr(plugins, "domain_plugins", lambda: (domain,), raising=False)
    service = DomainService(tmp_path / "config.toml")
    server = gui.create_server(service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(url + "/api/domains") as response:
            assert json.load(response)["domains"][0]["enabled"] is True
        assert list(tmp_path.iterdir()) == []
        with post(url, "/api/domains/payment", {"enabled": False}) as response:
            assert json.load(response)["domain"]["enabled"] is False
        assert domain_cli.main(["show", "payment", "--config-dir", str(tmp_path)]) == 0
        assert json.loads(capsys.readouterr().out)["result"]["enabled"] is False
        assert (
            domain_cli.main(["enable", "payment", "--config-dir", str(tmp_path)]) == 0
        )
        capsys.readouterr()
        with urlopen(url + "/api/domains") as response:
            assert json.load(response)["domains"][0]["enabled"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_foreground_gui_prints_reachable_url_and_releases_port_on_ctrl_c(tmp_path):
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; from dogopencli.gui import main; "
            "raise SystemExit(main(sys.argv[1:]))",
            "--config-dir",
            str(tmp_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    try:
        readable, _, _ = select.select([process.stdout], [], [], 10)
        assert readable, "GUI did not advertise readiness"
        url = process.stdout.readline().strip()
        assert url.startswith("http://127.0.0.1:"), url
        with urlopen(url + "/api/domains") as response:
            assert json.load(response)["domains"]
        assert list(tmp_path.iterdir()) == []
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stdout + stderr
        port = int(url.rsplit(":", 1)[1])
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
