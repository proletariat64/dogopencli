"""Static delivery contract, shared by installer and author helper."""

import io
import json
import stat
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from dogopencli.errors import CliError
from dogopencli.leaves import package as delivery
from dogopencli.leaves.package import prepare_package


def test_directory_is_snapshot_and_adapter_never_executes(tmp_path):
    source = tmp_path / "arbitrary"
    source.mkdir()
    manifest = json.loads(
        (
            Path(__file__).parents[1]
            / "src/dogopencli/leaf_packages/payment/sla.baselines/leaf.json"
        ).read_text()
    )
    (source / "leaf.json").write_text(json.dumps(manifest))
    (source / "adapter.py").write_text("raise RuntimeError('must not execute')")
    (source / "assets").mkdir()
    (source / "assets/readme.txt").write_text("resource")
    with prepare_package(source) as package:
        snapshot = package.path
        assert package.manifest["name"] == "sla.baselines"
        (source / "assets/readme.txt").write_text("edited")
        assert (snapshot / "assets/readme.txt").read_text() == "resource"
    assert not snapshot.exists()
    assert source.exists()


def archive_bytes(extra=None):
    source = (
        Path(__file__).parents[1] / "src/dogopencli/leaf_packages/payment/sla.baselines"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("leaf.json", (source / "leaf.json").read_bytes())
        archive.writestr("adapter.py", "raise RuntimeError('must not execute')")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return output.getvalue()


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/absolute",
        "C:/drive",
        "nested/leaf.json",
        "cache/response.json",
        "private.duckdb",
        "config.toml",
        "a\\b",
    ],
)
def test_zip_rejects_unsafe_or_runtime_payloads(tmp_path, name):
    path = tmp_path / "arbitrary.zip"
    path.write_bytes(archive_bytes({name: "payload"}))
    with pytest.raises(CliError):
        with prepare_package(path):
            pytest.fail("invalid payload accepted")
    assert path.exists()
    assert not (tmp_path / "outside").exists()


def test_zip_and_directory_symlinks_rejected(tmp_path):
    path = tmp_path / "archive.zip"
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(CliError):
        with prepare_package(path):
            pytest.fail("symlink accepted")
    source = tmp_path / "directory"
    source.mkdir()
    (source / "link").symlink_to(path)
    with pytest.raises(CliError):
        with prepare_package(source):
            pytest.fail("symlink accepted")


@pytest.mark.parametrize(
    "limit", ["MAX_ENTRIES", "MAX_EXPANDED_BYTES", "MAX_ARCHIVE_BYTES"]
)
def test_actual_package_limits(tmp_path, monkeypatch, limit):
    monkeypatch.setattr(delivery, limit, 1)
    path = tmp_path / "package.zip"
    path.write_bytes(archive_bytes())
    with pytest.raises(CliError):
        with prepare_package(path):
            pytest.fail("package limit ignored")


@pytest.fixture
def http_source():
    payload = archive_bytes()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            if self.path.startswith("/redirect"):
                self.send_response(302)
                self.send_header("Location", "/redirect")
                self.end_headers()
                return
            self.send_response(404 if self.path.split("?")[0] == "/missing" else 200)
            body = b"not zip" if self.path.split("?")[0] == "/invalid" else payload
            self.send_header(
                "Content-Length",
                str(len(body) + (1 if self.path.split("?")[0] == "/truncated" else 0)),
            )
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_http_without_suffix_and_cleanup(http_source, tmp_path, monkeypatch):
    url, requests = http_source
    monkeypatch.setattr(delivery.tempfile, "tempdir", str(tmp_path))
    with prepare_package(url + "/artifact?token=private") as package:
        assert package.manifest["domain"] == "payment"
        assert (package.path / "adapter.py").is_file()
    assert requests == ["/artifact?token=private"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("endpoint", ["missing", "invalid", "truncated", "redirect"])
def test_http_failures_clean_owned_temporary_files(
    http_source, tmp_path, monkeypatch, endpoint
):
    url, requests = http_source
    monkeypatch.setattr(delivery.tempfile, "tempdir", str(tmp_path))
    with pytest.raises(CliError) as error:
        with prepare_package(url + "/" + endpoint + "?secret=private"):
            pytest.fail("bad HTTP source accepted")
    assert "private" not in str(error.value)
    assert len(requests) == (6 if endpoint == "redirect" else 1)
    assert list(tmp_path.iterdir()) == []


def test_http_stream_limit(http_source, monkeypatch):
    monkeypatch.setattr(delivery, "MAX_ARCHIVE_BYTES", 1)
    with pytest.raises(CliError, match="HTTP ZIP download failed"):
        with prepare_package(http_source[0] + "/artifact"):
            pytest.fail("download limit ignored")
