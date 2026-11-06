"""Delivery exercises real local HTTP and isolated deployment directories."""

import hashlib
import importlib.util
import json
import threading
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(
        "delivery_" + name, ROOT / "tools/plugin-site" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


publisher, deployer, server = load("publish"), load("deploy"), load("server")


def test_publish_exact_bytes_retry_and_conflict(tmp_path, monkeypatch):
    package = tmp_path / "plugin.zip"
    with zipfile.ZipFile(package, "w") as archive:
        for path in (ROOT / "tools/leaf-dev/example").glob("*"):
            if path.is_file():
                archive.write(path, path.name)
    registry = server.make_server("127.0.0.1", 0, tmp_path / "data", "test-token")
    thread = threading.Thread(target=registry.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{registry.server_port}/plugins/"
    monkeypatch.setenv("PLUGIN_PUBLISH_TOKEN", "test-token")
    try:
        with pytest.raises(ValueError, match="HTTPS"):
            publisher.publish(package, url, "1.0.0")
        first = publisher.publish(package, url, "1.0.0", allow_http=True)
        assert first["sha256"] == hashlib.sha256(package.read_bytes()).hexdigest()
        assert publisher.publish(package, url, "1.0.0", allow_http=True) == first
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr("README.md", "Different valid archive")
        with pytest.raises(ValueError, match="differs"):
            publisher.publish(package, url, "1.0.0", allow_http=True)
        monkeypatch.setenv("PLUGIN_PUBLISH_TOKEN", "wrong")
        with pytest.raises(ValueError, match="401"):
            publisher.publish(package, url, "2.0.0", allow_http=True)
    finally:
        registry.shutdown()
        registry.server_close()
        thread.join()


def bundle(directory, version):
    directory.mkdir()
    for name in (
        "server.py",
        "deploy.py",
        "web/index.html",
        "runtime/dogopencli/__init__.py",
        "seed/plugin/1/package.zip",
    ):
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(version)
    files = {
        p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.rglob("*")
        if p.is_file()
    }
    (directory / "bundle.json").write_text(
        json.dumps({"version": version, "files": files})
    )
    return directory


def test_site_upgrade_rollback_and_preserved_publications(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    calls = []
    monkeypatch.setattr(deployer, "systemctl", lambda *args: calls.append(args))
    monkeypatch.setattr(deployer, "healthy", lambda *args: None)
    first = bundle(tmp_path / "one", "v1")
    root = tmp_path / "site"
    active = deployer.deploy(first, root)
    assert (root / "current").resolve() == active
    data = root / "data/plugin/1/package.zip"
    data.write_text("published by users")
    token = root / "publish.env"
    token.write_text("keep")
    second = bundle(tmp_path / "two", "v2")
    assert deployer.deploy(second, root) == root / "releases/v2"
    assert data.read_text() == "published by users"
    assert token.read_text() == "keep"

    def failed(*args):
        raise ValueError("unhealthy")

    monkeypatch.setattr(deployer, "healthy", failed)
    with pytest.raises(ValueError, match="unhealthy"):
        deployer.deploy(bundle(tmp_path / "three", "v3"), root)
    assert (root / "current").resolve() == root / "releases/v2"
    assert data.read_text() == "published by users"
    (second / "server.py").write_text("corrupt")
    with pytest.raises(ValueError, match="checksum"):
        deployer.deploy(second, root)
    assert (root / "current").resolve() == root / "releases/v2"
