"""Local registry acceptance: no business API, browser auth or adapter execution."""

import concurrent.futures
import hashlib
import http.client
import importlib.util
import io
import json
import threading
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "plugin_site_server", ROOT / "tools/plugin-site/server.py"
)
site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(site)


def archive(extra=None):
    stream = io.BytesIO()
    example = ROOT / "tools/leaf-dev/example"
    with zipfile.ZipFile(stream, "w") as zipped:
        for source in example.iterdir():
            if source.is_file() and source.suffix != ".pyc":
                zipped.writestr(source.name, source.read_bytes())
        if extra:
            zipped.writestr(*extra)
    return stream.getvalue()


@pytest.fixture
def registry(tmp_path):
    server = site.make_server("127.0.0.1", 0, tmp_path / "data", "test-only-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, tmp_path / "data"
    server.shutdown()
    server.server_close()
    thread.join()


def request(server, method, path, body=None, token=None, headers=None):
    connection = http.client.HTTPConnection(*server.server_address, timeout=5)
    values = dict(headers or {})
    if token:
        values["Authorization"] = f"Bearer {token}"
    connection.request(method, path, body=body, headers=values)
    response = connection.getresponse()
    result = response.status, response.read(), dict(response.getheaders())
    connection.close()
    return result


def upload(server, payload=None, version="1.0.0", token="test-only-token"):
    return request(
        server,
        "PUT",
        f"/plugins/api/releases/{version}",
        archive() if payload is None else payload,
        token,
    )


def test_publish_download_persistence_and_immutable_versions(registry):
    server, data = registry
    payload = archive()
    status, body, _ = upload(server, payload)
    assert status == 201
    result = json.loads(body)
    assert result["validation"] == "static-only"
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert request(server, "GET", result["download"])[1] == payload
    assert upload(server, payload)[0] == 409
    assert upload(server, payload, version="2.0.0")[0] == 201
    records = site.catalog(data)
    assert [row["version"] for row in records] == ["2.0.0", "1.0.0"]
    assert request(server, "GET", result["download"])[1] == payload
    assert len(list(data.glob("*/*/release.json"))) == 2
    # A new server instance reads persisted publications without an index rebuild.
    restarted = site.make_server("127.0.0.1", 0, data)
    threading.Thread(target=restarted.serve_forever, daemon=True).start()
    try:
        catalog = json.loads(request(restarted, "GET", "/plugins/api/catalog")[1])
        assert len(catalog["releases"]) == 2
        assert catalog["publishing"] is False
        assert upload(restarted)[0] == 503
    finally:
        restarted.shutdown()
        restarted.server_close()


def test_authentication_and_limits(registry):
    server, data = registry
    assert upload(server, token=None)[0] == 401
    assert upload(server, token="wrong")[0] == 401
    assert upload(server, payload=b"")[0] == 413
    assert (
        request(
            server,
            "PUT",
            "/plugins/api/releases/1",
            b"",
            "test-only-token",
            {"Content-Length": str(site.MAX_ARCHIVE_BYTES + 1)},
        )[0]
        == 413
    )
    assert not data.exists()


@pytest.mark.parametrize(
    "extra",
    [
        ("../escape.py", "bad"),
        ("cookies.json", "{}"),
        ("nested/leaf.json", "{}"),
        ("leaf.json", "{}"),
    ],
)
def test_unsafe_packages_rejected_without_publication(registry, extra):
    server, data = registry
    assert upload(server, archive(extra))[0] == 400
    assert site.catalog(data) == []


def test_validation_never_executes_adapter(registry):
    server, data = registry
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipped:
        zipped.writestr(
            "leaf.json", (ROOT / "tools/leaf-dev/example/leaf.json").read_bytes()
        )
        zipped.writestr("adapter.py", "raise RuntimeError('must never execute')")
    assert upload(server, stream.getvalue())[0] == 201
    assert len(site.catalog(data)) == 1


def test_invalid_and_traversal_routes(registry):
    server, _ = registry
    for path in (
        "/",
        "/plugins/../server.py",
        "/plugins/%2e%2e/server.py",
        "/plugins/downloads/../../server.py",
        "/plugins/runtime/dogopencli/config.py",
    ):
        assert request(server, "GET", path)[0] == 404
    assert upload(server, version="../escape")[0] == 400
    assert upload(server, payload=b"not a zip")[0] == 400
    assert request(server, "GET", "/plugins")[0] == 308
    assert request(server, "HEAD", "/plugins/")[1] == b""


def test_concurrent_same_version_has_one_winner(registry):
    server, data = registry
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: upload(server)[0], range(2)))
    assert sorted(results) == [201, 409]
    assert len(site.catalog(data)) == 1


def test_pages_and_machine_entry_points(registry):
    server, _ = registry
    for path in ("", "docs", "llms.txt", "agent-guide.md", "app.js", "style.css"):
        status, body, headers = request(server, "GET", "/plugins/" + path)
        assert status == 200
        assert body
        assert headers["X-Content-Type-Options"] == "nosniff"
    assert json.loads(request(server, "GET", "/plugins/api/health")[1]) == {
        "status": "ok"
    }


def test_catalog_ignores_uncommitted_release_and_partial_json(registry):
    server, data = registry
    status, body, _ = upload(server)
    assert status == 201
    staging = data / ".release-pending" / "release"
    staging.mkdir(parents=True)
    metadata = staging / "release.json"
    metadata.write_bytes(body)
    assert (
        len(json.loads(request(server, "GET", "/plugins/api/catalog")[1])["releases"])
        == 1
    )
    metadata.write_text('{"incomplete":', encoding="utf-8")
    assert len(site.catalog(data)) == 1
    assert request(server, "GET", "/plugins/api/catalog")[0] == 200


@pytest.mark.parametrize("default", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_manifest_does_not_poison_catalog(registry, default):
    server, data = registry
    manifest = json.loads((ROOT / "tools/leaf-dev/example/leaf.json").read_text())
    manifest["operations"]["list"]["parameters"].append(
        {
            "name": "amount",
            "type": "number",
            "required": False,
            "description": "Number default",
            "default": default,
        }
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipped:
        zipped.writestr("leaf.json", json.dumps(manifest))
        zipped.writestr("adapter.py", "raise RuntimeError('must never execute')")
    assert upload(server, stream.getvalue())[0] == 400
    assert site.catalog(data) == []
    assert request(server, "GET", "/plugins/api/catalog")[0] == 200
