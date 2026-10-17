"""Plugin lifecycle acceptance through the public command boundary."""

import json
import sqlite3
from pathlib import Path

import duckdb
import pytest


def package(tmp_path, name="sample", relation="sample_rows"):
    from test_leaf_registry import install

    root = tmp_path / ("source-" + name)
    return install(root, name, relation)


def call(run_cli, *args):
    code, output, _ = run_cli(list(args))
    return code, json.loads(output)


def test_directory_snapshot_duplicate_and_retained_data(run_cli, tmp_path, monkeypatch):
    scope = tmp_path / "scope"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    source = package(tmp_path)
    code, result = call(run_cli, "plugins", "install", str(source))
    assert code == 0, result
    installed = scope / "plugins/payment/sample"
    assert (installed / "leaf.json").read_bytes() == (source / "leaf.json").read_bytes()
    source.joinpath("adapter.py").write_text("raise RuntimeError('source changed')")
    assert "source changed" not in installed.joinpath("adapter.py").read_text()
    installed.joinpath("leaf.json").write_text(
        installed.joinpath("leaf.json")
        .read_text()
        .replace('"Samples"', '"Local edits"')
    )
    before = installed.joinpath("leaf.json").read_bytes()
    code, result = call(run_cli, "plugins", "install", str(source))
    assert code != 0 and result["error"]["code"] == "PLUGIN_EXISTS"
    assert installed.joinpath("leaf.json").read_bytes() == before
    with duckdb.connect(str(scope / "duckdog.duckdb")) as database:
        database.execute("INSERT INTO sample_rows VALUES ('retained synthetic')")
    code, result = call(run_cli, "plugins", "uninstall", "payment.sample")
    assert code == 0 and not installed.exists(), result
    assert call(run_cli, "plugins", "uninstall", "payment.sample")[0] == 0
    with duckdb.connect(str(scope / "duckdog.duckdb")) as database:
        assert database.execute("SELECT * FROM sample_rows").fetchall() == [
            ("retained synthetic",)
        ]
    with sqlite3.connect(scope / "leaf-registry.sqlite3") as database:
        assert database.execute("SELECT leaf_id,active FROM bindings").fetchall() == [
            ("payment.sample", 0)
        ]


def test_disabled_unknown_and_invalid_adapter_leave_no_executable_install(
    run_cli, tmp_path, monkeypatch
):
    scope = tmp_path / "scope"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    source = package(tmp_path)
    assert call(run_cli, "domain", "disable", "payment")[0] == 0
    code, result = call(run_cli, "plugins", "install", str(source))
    assert code == 1 and result["error"]["code"] == "DOMAIN_DISABLED"
    assert not (scope / "plugins/payment/sample").exists()
    assert call(run_cli, "domain", "enable", "payment")[0] == 0
    manifest = json.loads(source.joinpath("leaf.json").read_text())
    manifest["domain"] = "unknown"
    source.joinpath("leaf.json").write_text(json.dumps(manifest))
    assert call(run_cli, "plugins", "install", str(source))[0] != 0
    manifest["domain"] = "payment"
    source.joinpath("leaf.json").write_text(json.dumps(manifest))
    source.joinpath("adapter.py").write_text("adapter = object()\n")
    assert call(run_cli, "plugins", "install", str(source))[0] != 0
    assert not (scope / "plugins/payment/sample").exists()
    if (scope / "duckdog.duckdb").exists():
        with duckdb.connect(str(scope / "duckdog.duckdb")) as database:
            assert database.execute("SHOW TABLES").fetchall() == []


def test_broken_disabled_uninstall_does_not_execute_adapter(
    run_cli, tmp_path, monkeypatch
):
    scope = tmp_path / "scope"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    source = package(tmp_path)
    assert call(run_cli, "plugins", "install", str(source))[0] == 0
    assert call(run_cli, "domain", "disable", "payment")[0] == 0
    installed = scope / "plugins/payment/sample"
    installed.joinpath("leaf.json").write_text("{")
    marker = tmp_path / "adapter-executed"
    installed.joinpath("adapter.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).touch()\nraise RuntimeError()\n"
    )
    assert call(run_cli, "plugins", "uninstall", "payment.sample")[0] == 0
    assert not marker.exists() and not installed.exists()


def test_reinstall_rejects_incompatible_retained_table(run_cli, tmp_path, monkeypatch):
    scope = tmp_path / "scope"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    source = package(tmp_path)
    assert call(run_cli, "plugins", "install", str(source))[0] == 0
    assert call(run_cli, "plugins", "uninstall", "payment.sample")[0] == 0
    with duckdb.connect(str(scope / "duckdog.duckdb")) as database:
        database.execute("DROP TABLE sample_rows")
        database.execute("CREATE TABLE sample_rows (native_amount INTEGER)")
        database.execute("INSERT INTO sample_rows VALUES (42)")
    code, result = call(run_cli, "plugins", "install", str(source))
    assert code == 1 and result["error"]["code"] == "DATASET_ERROR"
    assert not (scope / "plugins/payment/sample").exists()
    with duckdb.connect(str(scope / "duckdog.duckdb")) as database:
        assert database.execute("SELECT * FROM sample_rows").fetchall() == [(42,)]


@pytest.mark.parametrize("failure", ["publication", "sqlite"])
def test_install_failure_rolls_back_owned_storage_and_preserves_other_leaf(
    run_cli, tmp_path, monkeypatch, failure
):
    scope = tmp_path / "scope"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    source = package(tmp_path)
    other = package(tmp_path, "other", "other_rows")
    assert call(run_cli, "plugins", "install", str(other))[0] == 0
    with duckdb.connect(str(scope / "duckdog.duckdb")) as database:
        database.execute("INSERT INTO other_rows VALUES ('keep')")
    if failure == "publication":
        original = Path.rename

        def reject(source_path, target):
            if Path(target) == scope / "plugins/payment/sample":
                raise OSError("synthetic rename failure")
            return original(source_path, target)

        monkeypatch.setattr(Path, "rename", reject)
    else:
        with sqlite3.connect(scope / "leaf-registry.sqlite3") as database:
            database.execute(
                "CREATE TRIGGER reject_sample BEFORE INSERT ON bindings "
                "WHEN NEW.leaf_id='payment.sample' "
                "BEGIN SELECT RAISE(ABORT, 'synthetic database failure'); END"
            )
    assert call(run_cli, "plugins", "install", str(source))[0] == 1
    assert not (scope / "plugins/payment/sample").exists()
    assert (scope / "plugins/payment/other/leaf.json").is_file()
    with duckdb.connect(str(scope / "duckdog.duckdb")) as database:
        assert database.execute("SELECT * FROM other_rows").fetchall() == [("keep",)]
        assert (
            database.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name='sample_rows'"
            ).fetchall()
            == []
        )
    with sqlite3.connect(scope / "leaf-registry.sqlite3") as database:
        assert database.execute("SELECT leaf_id FROM bindings").fetchall() == [
            ("payment.other",)
        ]
    assert list(scope.glob(".leaf-install-*")) == []


def test_lifecycle_lock_contention_and_unavailable_root_are_errors(
    run_cli, tmp_path, monkeypatch
):
    import fcntl

    scope = tmp_path / "scope"
    scope.mkdir()
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    source = package(tmp_path)
    with (scope / "leaf-registry.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        code, result = call(run_cli, "plugins", "install", str(source))
        assert code == 1 and result["error"]["code"] == "LOCKED"
        code, result = call(run_cli, "plugins", "uninstall", "payment.sample")
        assert code == 1 and result["error"]["code"] == "LOCKED"
    (scope / "plugins").write_text("Unavailable root")
    code, result = call(run_cli, "plugins", "uninstall", "payment.sample")
    assert code == 1 and result["error"]["code"] == "IO_ERROR"


def test_uninstall_owned_cache_preserves_unrelated_cache_and_reinstall(
    run_cli, tmp_path, monkeypatch
):
    from dataclasses import replace

    from dogopencli.cache import Cache, SnapshotMeta

    scope = tmp_path / "scope"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    source = package(tmp_path)
    assert call(run_cli, "plugins", "install", str(source))[0] == 0
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
    cache.publish(snapshot, [(1, '{"id":"owned"}')])
    other = replace(snapshot, namespace="leaf:collection.other", capability="other")
    cache.publish(other, [(1, '{"id":"keep"}')])
    code, result = call(run_cli, "plugins", "uninstall", "payment.sample")
    assert code == 0 and result["data"]["cache_removed"] is True
    assert cache.current(snapshot.namespace) is None
    assert cache.read(other.namespace) == (other, [(1, '{"id":"keep"}')])
    assert call(run_cli, "plugins", "install", str(source))[0] == 0
    assert cache.current(snapshot.namespace) is None
    assert cache.current(other.namespace) == other


def test_stale_refresh_after_removal_cannot_publish_or_query(
    run_cli, tmp_path, monkeypatch
):
    from contextlib import contextmanager

    from dogopencli.cache import Cache
    from dogopencli.leaves.lifecycle import install, uninstall

    scope = tmp_path / "scope"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    source = package(tmp_path)
    assert call(run_cli, "plugins", "install", str(source))[0] == 0
    original = Cache.refresh_lock
    changed = False

    @contextmanager
    def remove_before_refresh_lock(cache):
        nonlocal changed
        if not changed:
            changed = True
            uninstall(scope / "config.toml", "payment.sample")
            install(scope / "config.toml", str(source))
        with original(cache):
            yield

    monkeypatch.setattr(Cache, "refresh_lock", remove_before_refresh_lock)
    code, result = call(run_cli, "payment", "refresh", "sample")
    assert code == 1 and result["error"]["code"] == "LEAF_NOT_FOUND"
    assert result["meta"]["published"] is False
    assert Cache(scope / "leaf-cache.sqlite3").current("leaf:payment.sample") is None
    assert (scope / "plugins/payment/sample/leaf.json").is_file()
