"""Observable local plugin and storage lifecycle acceptance."""

import json

import duckdb
import pytest


def install(root, name="sample", relation="sample_rows"):
    folder = root / "plugins" / "payment" / name
    folder.mkdir(parents=True)
    value = {
        "domain": "payment",
        "name": name,
        "operations": {"list": {"description": "List samples", "parameters": []}},
        "adapter": "adapter.py:adapter",
        "fields": [],
        "identity": [],
        "summary": "Samples",
        "purpose": "Inquiry",
        "identity_description": "Unknown",
        "limitations": [],
        "examples": [],
        "dataset": {"relation": relation},
    }
    (folder / "leaf.json").write_text(json.dumps(value))
    (folder / "adapter.py").write_text(
        "class Adapter:\n"
        "    def capability(self, parameters): pass\n"
        "    def scope(self, parameters): return 'all'\n"
        "    def collector(self, *args, **kwargs): pass\n"
        "    def filter(self, records, parameters): return records\n"
        "adapter = Adapter()\n"
    )
    return folder


def test_install_initializes_empty_owned_table_and_isolates_bad_leaf(tmp_path):
    from dogopencli.leaves.registry import Registry

    install(tmp_path)
    bad = install(tmp_path, "broken", "broken_rows")
    (bad / "leaf.json").write_text("{")
    registry = Registry(tmp_path / "config.toml").scan()
    assert set(registry.leaves) == {"payment.sample"}
    assert registry.diagnostics[0]["id"] == "payment.broken"
    with duckdb.connect(str(tmp_path / "duckdog.duckdb")) as db:
        assert db.execute("SELECT count(*) FROM sample_rows").fetchone() == (0,)
    assert not (tmp_path / "leaf-cache.sqlite3").exists()
    assert Registry(tmp_path / "config.toml").scan().diagnostics == registry.diagnostics


def test_uninstall_cleans_cache_preserves_dataset_and_reinstall(tmp_path):
    import shutil

    from dogopencli.cache import Cache, SnapshotMeta
    from dogopencli.leaves.registry import Registry

    folder = install(tmp_path)
    Registry(tmp_path / "config.toml").scan()
    cache = Cache(tmp_path / "leaf-cache.sqlite3")
    meta = SnapshotMeta(
        namespace="leaf:payment.sample",
        capability="sample",
        scope="all",
        source_kind="live",
        snapshot_id="one",
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at="2026-10-16T00:00:00Z",
        loaded_at="2026-10-16T00:00:00Z",
        source_observed_from=None,
        source_observed_to=None,
        row_count=1,
    )
    cache.publish(meta, [(1, '{"value":1}')])
    with duckdb.connect(str(tmp_path / "duckdog.duckdb")) as db:
        db.execute("INSERT INTO sample_rows VALUES ('synthetic')")
    # A repairable malformed leaf is still installed.
    (folder / "leaf.json").write_text("{")
    assert Registry(tmp_path / "config.toml").scan().diagnostics
    assert cache.current("leaf:payment.sample") is not None
    shutil.rmtree(folder)
    assert not Registry(tmp_path / "config.toml").scan().leaves
    assert cache.current("leaf:payment.sample") is None
    install(tmp_path)
    assert Registry(tmp_path / "config.toml").scan().diagnostics == []
    with duckdb.connect(str(tmp_path / "duckdog.duckdb")) as db:
        assert db.execute("SELECT * FROM sample_rows").fetchall() == [("synthetic",)]


def test_missing_registered_table_is_reported_without_repair(tmp_path):
    from dogopencli.leaves.registry import Registry

    install(tmp_path)
    Registry(tmp_path / "config.toml").scan()
    with duckdb.connect(str(tmp_path / "duckdog.duckdb")) as db:
        db.execute("DROP TABLE sample_rows")
    broken = Registry(tmp_path / "config.toml").scan()
    assert broken.leaves == {}
    assert broken.diagnostics[0]["code"] == "DATASET_ERROR"
    with duckdb.connect(str(tmp_path / "duckdog.duckdb")) as db:
        assert db.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name='sample_rows'"
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    "reserved", ["live", "version", "detail-identity", "explicit-parameters"]
)
def test_basic_schema_rejects_unsupported_and_reserved_controls(tmp_path, reserved):
    from dogopencli.errors import CliError
    from dogopencli.leaves.registry import validate_manifest

    folder = install(tmp_path)
    manifest = json.loads((folder / "leaf.json").read_text())
    manifest["operations"]["list"]["parameters"] = [
        {"name": reserved, "type": "boolean", "required": False, "description": "bad"}
    ]
    with pytest.raises(CliError, match="reserved"):
        validate_manifest(manifest)


def test_case_insensitive_relation_collision_isolates_later_leaf(tmp_path):
    from dogopencli.leaves.registry import Registry

    install(tmp_path, "first", "Rows")
    install(tmp_path, "second", "rows")
    registry = Registry(tmp_path / "config.toml").scan()
    assert set(registry.leaves) == {"payment.first"}
    assert registry.diagnostics[0]["id"] == "payment.second"


def test_update_replaces_adapter_source_even_with_same_timestamp_and_size(tmp_path):
    import os

    from dogopencli.leaves.registry import Registry

    folder = install(tmp_path)
    path = folder / "adapter.py"
    before = path.stat()
    assert (
        Registry(tmp_path / "config.toml")
        .scan()
        .get("payment", "sample")
        .adapter.scope({})
        == "all"
    )
    path.write_text(path.read_text().replace("'all'", "'new'"))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert (
        Registry(tmp_path / "config.toml")
        .scan()
        .get("payment", "sample")
        .adapter.scope({})
        == "new"
    )


def test_replaced_folder_is_diagnostic_and_preserves_cache(tmp_path):
    import shutil

    from dogopencli.cache import Cache, SnapshotMeta
    from dogopencli.leaves.registry import Registry

    folder = install(tmp_path)
    Registry(tmp_path / "config.toml").scan()
    cache = Cache(tmp_path / "leaf-cache.sqlite3")
    meta = SnapshotMeta(
        namespace="leaf:payment.sample",
        capability="sample",
        scope="all",
        source_kind="live",
        snapshot_id="one",
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at="2026-10-16T00:00:00Z",
        loaded_at="2026-10-16T00:00:00Z",
        source_observed_from=None,
        source_observed_to=None,
        row_count=1,
    )
    cache.publish(meta, [(1, "{}")])
    shutil.rmtree(folder)
    folder.write_text("broken installation")
    registry = Registry(tmp_path / "config.toml").scan()
    assert registry.diagnostics[0]["id"] == "payment.sample"
    assert cache.current("leaf:payment.sample") is not None


def test_domain_replaced_with_file_preserves_managed_cache(tmp_path):
    import shutil

    from dogopencli.cache import Cache, SnapshotMeta
    from dogopencli.leaves.registry import Registry

    folder = install(tmp_path)
    Registry(tmp_path / "config.toml").scan()
    cache = Cache(tmp_path / "leaf-cache.sqlite3")
    cache.publish(
        SnapshotMeta(
            namespace="leaf:payment.sample",
            capability="sample",
            scope="all",
            source_kind="live",
            snapshot_id="one",
            dataset_id=None,
            simulated=False,
            backend_complete=True,
            dataset_complete=True,
            fetched_at="2026-10-16T00:00:00Z",
            loaded_at="2026-10-16T00:00:00Z",
            source_observed_from=None,
            source_observed_to=None,
            row_count=1,
        ),
        [(1, "{}")],
    )
    shutil.rmtree(folder.parent)
    folder.parent.write_text("broken domain")
    registry = Registry(tmp_path / "config.toml").scan()
    assert registry.diagnostics
    assert cache.current("leaf:payment.sample") is not None


def test_unreadable_domain_does_not_disable_healthy_domain(tmp_path, monkeypatch):
    from pathlib import Path

    from dogopencli.leaves.registry import Registry

    install(tmp_path)
    bad = tmp_path / "plugins/fx"
    bad.mkdir()
    real_iterdir = Path.iterdir

    def iterdir(path):
        if path == bad:
            raise PermissionError("unavailable domain")
        return real_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    registry = Registry(tmp_path / "config.toml").scan()
    assert set(registry.leaves) == {"payment.sample"}
    assert registry.diagnostics[0]["id"] == "fx"


def test_incompatible_registered_table_is_diagnosed_without_repair(tmp_path):
    from dogopencli.leaves.registry import Registry

    install(tmp_path)
    Registry(tmp_path / "config.toml").scan()
    with duckdb.connect(str(tmp_path / "duckdog.duckdb")) as database:
        database.execute("DROP TABLE sample_rows")
        database.execute("CREATE TABLE sample_rows (native_amount INTEGER)")
        database.execute("INSERT INTO sample_rows VALUES (42)")
    registry = Registry(tmp_path / "config.toml").scan()
    assert registry.leaves == {}
    assert registry.diagnostics[0]["code"] == "DATASET_ERROR"
    with duckdb.connect(str(tmp_path / "duckdog.duckdb")) as database:
        assert database.execute("SELECT * FROM sample_rows").fetchall() == [(42,)]


def test_existing_binding_validates_while_external_reader_is_open(tmp_path):
    import subprocess
    import sys

    from dogopencli.leaves.registry import Registry

    install(tmp_path)
    Registry(tmp_path / "config.toml").scan()
    reader = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            "import duckdb,sys; database=duckdb.connect(sys.argv[1],read_only=True); "
            'print("ready",flush=True); sys.stdin.readline()',
            str(tmp_path / "duckdog.duckdb"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert reader.stdout.readline().strip() == "ready"
        registry = Registry(tmp_path / "config.toml").scan()
        assert set(registry.leaves) == {"payment.sample"}
        assert registry.diagnostics == []
    finally:
        reader.communicate("\n", timeout=10)


@pytest.mark.parametrize(
    "installation_point", ["registry_lock", "cache_lock", "root_unavailable"]
)
def test_scan_preserves_cache_when_leaf_appears_during_cleanup(
    tmp_path, monkeypatch, installation_point
):
    import dataclasses
    import shutil
    from contextlib import contextmanager

    import dogopencli.leaves.registry as module
    from dogopencli.cache import Cache, SnapshotMeta

    folder = install(tmp_path)
    registry = module.Registry(tmp_path / "config.toml")
    registry.scan()
    cache = Cache(registry.cache_path)
    meta = SnapshotMeta(
        namespace="leaf:payment.sample",
        capability="sample",
        scope="all",
        source_kind="live",
        snapshot_id="concurrent",
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at="2026-10-16T00:00:00Z",
        loaded_at="2026-10-16T00:00:00Z",
        source_observed_from=None,
        source_observed_to=None,
        row_count=1,
    )
    cache.publish(meta, [(1, '{"value":1}')])
    shutil.rmtree(folder)
    if installation_point == "registry_lock":
        original = module.fcntl.flock

        def install_before_lock(fd, operation):
            if operation & module.fcntl.LOCK_EX and not folder.exists():
                install(tmp_path)
            return original(fd, operation)

        monkeypatch.setattr(module.fcntl, "flock", install_before_lock)
    else:
        original = Cache.refresh_lock

        @contextmanager
        def install_before_cleanup(self, *args, **kwargs):
            with original(self, *args, **kwargs):
                if installation_point == "root_unavailable":
                    (tmp_path / "plugins").rename(tmp_path / "plugins-unavailable")
                else:
                    install(tmp_path)
                yield

        monkeypatch.setattr(Cache, "refresh_lock", install_before_cleanup)
    registry.scan()
    if installation_point == "root_unavailable":
        assert registry.diagnostics
        (tmp_path / "plugins-unavailable").rename(tmp_path / "plugins")
        install(tmp_path)
    else:
        assert registry.diagnostics == []
    assert dataclasses.asdict(
        cache.current("leaf:payment.sample")
    ) == dataclasses.asdict(meta)
    monkeypatch.undo()
    assert module.Registry(tmp_path / "config.toml").scan().diagnostics == []
    assert cache.current("leaf:payment.sample") is not None


def test_inventory_of_new_scope_does_not_create_configuration(tmp_path):
    from dogopencli.domains import DomainService

    scope = tmp_path / "new-scope"
    DomainService(scope / "config.toml").inventory()
    assert not scope.exists()
