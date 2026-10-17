"""Portable source acceptance through the public plugin CLI."""

import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import duckdb
import pytest

from dogopencli.cache import Cache, SnapshotMeta

_CREATE_CONNECTION = socket.create_connection
_SOCKET_CONNECT = socket.socket.connect
_POPEN = subprocess.Popen


def invoke(run_cli, *arguments):
    code, output, _ = run_cli(list(arguments))
    return code, json.loads(output)


@pytest.fixture
def delivered_source(tmp_path):
    from test_leaf_registry import install

    source = install(tmp_path / "author", "sample", "sample_rows")
    (source / "resources").mkdir()
    (source / "resources/guide.txt").write_text("synthetic resource")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in source.rglob("*"):
            if path.is_file():
                archive.writestr(path.relative_to(source).as_posix(), path.read_bytes())
    archive = tmp_path / "unrelated-delivery-name.zip"
    archive.write_bytes(buffer.getvalue())
    return source, archive


@pytest.fixture
def delivery_server(delivered_source, monkeypatch, tmp_path):
    payload = delivered_source[1].read_bytes()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            endpoint = self.path.split("?")[0]
            self.send_response(404 if endpoint == "/missing" else 200)
            body = b"invalid ZIP" if endpoint == "/invalid" else payload
            self.send_header(
                "Content-Length",
                str(len(body) + (1 if endpoint == "/truncated" else 0)),
            )
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    allowed = ("127.0.0.1", server.server_port)

    def connect(stream, address):
        assert address == allowed, "Only task-owned loopback HTTP server is allowed"
        return _SOCKET_CONNECT(stream, address)

    # The downloader runs in a cancellable interpreter. Apply the same single
    # loopback destination restriction there before any package code imports.
    startup = tmp_path / "download-startup"
    startup.mkdir()
    (startup / "sitecustomize.py").write_text(
        "import socket\n"
        "original_connect = socket.socket.connect\n"
        "original_resolve = socket.getaddrinfo\n"
        "def connect(stream, address):\n"
        f"    assert address == {allowed!r}\n"
        "    return original_connect(stream, address)\n"
        "def resolve(host, port, *args, **kwargs):\n"
        f"    assert (host, port) == {allowed!r}\n"
        "    return original_resolve(host, port, *args, **kwargs)\n"
        "socket.socket.connect = connect\n"
        "socket.getaddrinfo = resolve\n"
    )

    def download_process(arguments, **kwargs):
        assert arguments[:2] == [sys.executable, "-c"]
        assert len(arguments) == 3 and "package._download_transfer(" in arguments[2]
        assert "http://" not in arguments[2] and "https://" not in arguments[2]
        environment = dict(os.environ, PYTHONPATH=str(startup))
        return _POPEN(arguments, env=environment, **kwargs)

    # Only the downloader process and this loopback port cross SIT guards.
    monkeypatch.setattr(subprocess, "Popen", download_process)
    monkeypatch.setattr(socket, "create_connection", _CREATE_CONNECTION)
    monkeypatch.setattr(socket.socket, "connect", connect)
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("source_kind", ["zip", "http"])
def test_portable_source_installs_snapshot_and_empty_binding(
    run_cli, tmp_path, monkeypatch, delivered_source, delivery_server, source_kind
):
    scope = tmp_path / "operator"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    source, archive = delivered_source
    original = archive.read_bytes()
    argument = (
        str(archive) if source_kind == "zip" else delivery_server[0] + "/artifact"
    )
    code, result = invoke(run_cli, "plugins", "install", argument)
    assert code == 0, result
    installed = scope / "plugins/payment/sample"
    assert (
        installed.joinpath("leaf.json").read_bytes()
        == source.joinpath("leaf.json").read_bytes()
    )
    assert installed.joinpath("resources/guide.txt").read_text() == "synthetic resource"
    assert archive.read_bytes() == original
    source.joinpath("resources/guide.txt").write_text("source edited")
    assert installed.joinpath("resources/guide.txt").read_text() == "synthetic resource"
    with sqlite3.connect(scope / "leaf-registry.sqlite3") as database:
        assert database.execute("SELECT leaf_id, active FROM bindings").fetchall() == [
            ("payment.sample", 1)
        ]
    with duckdb.connect(str(scope / "duckdog.duckdb")) as database:
        assert database.execute("SELECT * FROM sample_rows").fetchall() == []
    assert not (scope / "leaf-cache.sqlite3").exists()
    code, listing = invoke(run_cli, "plugins", "list")
    assert code == 0, listing
    declaration = next(
        row for row in listing["data"]["plugins"] if row["identity"] == "payment.sample"
    )
    assert declaration["state"] == "installed"
    assert declaration["bundled"] is False
    assert declaration["diagnostics"] == []
    assert delivery_server[1] == ([] if source_kind == "zip" else ["/artifact"])


@pytest.mark.parametrize(
    ("endpoint", "expected_error"),
    [
        ("missing", "DOWNLOAD_FAILED"),
        ("invalid", "INVALID_PACKAGE"),
        ("truncated", "DOWNLOAD_FAILED"),
        ("artifact", "PLUGIN_EXISTS"),
    ],
)
def test_http_failure_preserves_installed_documentation_cache_and_binding(
    run_cli,
    tmp_path,
    monkeypatch,
    delivered_source,
    delivery_server,
    endpoint,
    expected_error,
):
    scope = tmp_path / "operator"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    assert invoke(run_cli, "plugins", "install", str(delivered_source[0]))[0] == 0
    installed = scope / "plugins/payment/sample"
    manifest_path = installed / "leaf.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["summary"] = "Operator documentation edit"
    manifest_path.write_text(json.dumps(manifest))
    before_files = {
        path.relative_to(installed): path.read_bytes()
        for path in installed.rglob("*")
        if path.is_file()
    }
    cache = Cache(scope / "leaf-cache.sqlite3")
    snapshot = SnapshotMeta(
        namespace="leaf:payment.sample",
        capability="payment.sample",
        scope="all",
        source_kind="live",
        snapshot_id="synthetic",
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at="2026-10-17T00:00:00Z",
        loaded_at="2026-10-17T00:00:00Z",
        source_observed_from=None,
        source_observed_to=None,
        row_count=1,
    )
    rows = [(1, '{"id":"cached synthetic"}')]
    cache.publish(snapshot, rows)
    with sqlite3.connect(scope / "leaf-registry.sqlite3") as database:
        bindings = database.execute("SELECT * FROM bindings").fetchall()
    with duckdb.connect(str(scope / "duckdog.duckdb")) as database:
        database.execute("INSERT INTO sample_rows VALUES ('retained synthetic')")
    code, result = invoke(
        run_cli,
        "plugins",
        "install",
        delivery_server[0] + "/" + endpoint + "?token=private",
    )
    assert code == 1 and result["error"]["code"] == expected_error, result
    assert "private" not in json.dumps(result)
    assert {
        path.relative_to(installed): path.read_bytes()
        for path in installed.rglob("*")
        if path.is_file()
    } == before_files
    assert cache.read(snapshot.namespace) == (snapshot, rows)
    with sqlite3.connect(scope / "leaf-registry.sqlite3") as database:
        assert database.execute("SELECT * FROM bindings").fetchall() == bindings
    with duckdb.connect(str(scope / "duckdog.duckdb")) as database:
        assert database.execute("SELECT * FROM sample_rows").fetchall() == [
            ("retained synthetic",)
        ]
    assert list(scope.glob(".leaf-install-*")) == []
    assert delivery_server[1] == ["/" + endpoint + "?token=private"]
