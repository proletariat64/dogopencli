"""System metadata remains offline, read-only and separate from business records."""

import json
import shutil
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import duckdb
import pytest
from test_leaf_editor import editor as editor
from test_leaf_registry import install

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.leaves.registry import Registry
from dogopencli.system_info import read_system_info


def files(root):
    # mode=ro can maintain SQLite coordination files. Nonempty WAL payloads and
    # all application stores still participate in the byte-for-byte comparison.
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
        and not p.name.endswith("-shm")
        and not (p.name.endswith("-wal") and p.stat().st_size == 0)
    }


@pytest.fixture
def system_scope(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('[cache]\nttl_hours = 12\n[private]\nsecret = "hidden-secret"\n')
    install(tmp_path)
    retained = install(tmp_path, "retired", "retired_rows")
    assert not Registry(config).scan().diagnostics
    shutil.rmtree(retained)
    assert not Registry(config).scan().diagnostics
    with duckdb.connect(str(tmp_path / "duckdog.duckdb")) as database:
        database.execute("INSERT INTO sample_rows VALUES ('private-business-record')")
        database.execute("INSERT INTO retired_rows VALUES ('retained-private-record')")
        database.execute(
            "CREATE TABLE unrelated AS SELECT 'unrelated-private-record' AS secret"
        )
    now = datetime.now(timezone.utc)
    meta = SnapshotMeta(
        namespace="leaf:payment.sample",
        capability="sample",
        scope="secret-scope",
        source_kind="live",
        snapshot_id="one",
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at=(now - timedelta(hours=20)).isoformat(),
        loaded_at=now.isoformat(),
        source_observed_from=None,
        source_observed_to=None,
        row_count=1,
    )
    Cache(tmp_path / "leaf-cache.sqlite3").publish(
        meta, [(1, '{"secret":"cached-private-record"}')]
    )
    return config, meta


def test_new_scope_does_not_create_config_or_storage(tmp_path):
    path = tmp_path / "absent" / "config.toml"
    result = read_system_info(path)
    assert not path.parent.exists()
    assert result["cache"]["snapshot_count"] == 0
    assert result["duckdog"]["dataset_count"] == 0
    assert result["configuration"]["ttl_hours"] == 72
    assert result["installation"]["python_version"]


def test_populated_system_is_metadata_only_and_read_only(system_scope, monkeypatch):
    config, _ = system_scope
    original = files(config.parent)

    def forbidden(*args, **kwargs):
        raise AssertionError("System must not load adapters or initialize storage")

    monkeypatch.setattr(Registry, "scan", forbidden)
    monkeypatch.setattr(Registry, "_load", forbidden)
    monkeypatch.setattr(Registry, "_storage", forbidden)
    result = read_system_info(config)
    assert files(config.parent) == original
    assert result["leaf_count"] == 1
    assert result["cache"]["snapshot_count"] == 1
    assert result["cache"]["row_count"] == 1
    assert result["cache"]["leaves"][0]["freshness"] == "stale"
    db = result["duckdog"]["databases"][0]
    assert db["state"] == "available"
    assert [
        (d["leaf_id"], d["association"], d["estimated_rows"]) for d in db["datasets"]
    ] == [("payment.retired", "retained", 1), ("payment.sample", "installed", 1)]
    serialized = json.dumps(result)
    for forbidden_value in [
        "hidden-secret",
        "private-business-record",
        "retained-private-record",
        "cached-private-record",
        "unrelated-private-record",
        "secret-scope",
        "unrelated",
    ]:
        assert forbidden_value not in serialized


def test_busy_database_remains_usable_by_existing_writer(system_scope):
    config, _ = system_scope
    with duckdb.connect(str(config.parent / "duckdog.duckdb")) as writer:
        result = read_system_info(config)
        db = result["duckdog"]["databases"][0]
        assert db["state"] == "busy"
        assert all(d["estimated_rows"] is None for d in db["datasets"])
        assert writer.execute("SELECT count(*) FROM sample_rows").fetchone() == (1,)
    assert read_system_info(config)["duckdog"]["databases"][0]["state"] == "available"


def test_bad_binding_store_does_not_hide_other_sections(system_scope):
    config, _ = system_scope
    (config.parent / "leaf-registry.sqlite3").write_bytes(b"not sqlite")
    original = files(config.parent)
    result = read_system_info(config)
    assert result["duckdog"]["state"] == "unavailable"
    assert result["duckdog"]["dataset_count"] is None
    assert result["cache"]["snapshot_count"] == 1
    assert result["installation"]["version"]
    assert files(config.parent) == original


def test_missing_dataset_is_not_repaired_or_counted_as_empty(system_scope):
    config, _ = system_scope
    with duckdb.connect(str(config.parent / "duckdog.duckdb")) as database:
        database.execute("DROP TABLE sample_rows")
    result = read_system_info(config)
    dataset = next(
        d
        for d in result["duckdog"]["databases"][0]["datasets"]
        if d["leaf_id"] == "payment.sample"
    )
    assert dataset["state"] == "unavailable"
    assert dataset["estimated_rows"] is None


def test_bad_config_and_unknown_capture_time_do_not_invent_freshness(system_scope):
    config, meta = system_scope
    cache = Cache(config.parent / "leaf-cache.sqlite3")
    cache.publish(replace(meta, fetched_at="not-a-time"), [(1, "{}")])
    config.write_text("not valid TOML")
    result = read_system_info(config)
    assert result["configuration"]["state"] == "unavailable"
    assert result["configuration"]["ttl_hours"] is None
    assert result["cache"]["leaves"][0]["freshness"] == "unknown"
    assert result["cache"]["row_count"] == 1


@pytest.mark.parametrize("profile", ["1", '"~dogopencli_missing_user_593687/chrome"'])
def test_invalid_browser_configuration_does_not_hide_other_sections(
    system_scope, profile
):
    config, _ = system_scope
    config.write_text(f"[auth]\nprofile = {profile}\n")
    result = read_system_info(config)
    assert result["configuration"]["state"] == "unavailable"
    assert result["configuration"]["cdp_url"] is None
    assert result["installation"]["version"]
    assert result["cache"]["snapshot_count"] == 1
    assert result["duckdog"]["dataset_count"] == 2


@pytest.mark.parametrize("host", ["127.0.0.1", "[::1]"])
def test_browser_endpoint_displays_only_origin_without_credentials(system_scope, host):
    config, _ = system_scope
    config.write_text(
        '[auth]\ncdp_url = "http://user:secret-password@'
        + host
        + ':9222/secret-path?token=secret-token#secret-fragment"\n'
    )
    result = read_system_info(config)
    assert result["configuration"]["cdp_url"] == f"http://{host}:9222"
    serialized = json.dumps(result)
    for private in [
        "user:",
        "secret-password",
        "secret-path",
        "secret-token",
        "secret-fragment",
    ]:
        assert private not in serialized


def test_missing_cdp_port_is_confined_to_configuration(system_scope):
    config, _ = system_scope
    config.write_text('[auth]\ncdp_url = "http://127.0.0.1"\n')
    result = read_system_info(config)
    assert result["configuration"]["state"] == "unavailable"
    assert result["installation"]["version"]
    assert result["cache"]["snapshot_count"] == 1


def test_unresolvable_database_path_does_not_hide_other_sections(system_scope):
    config, _ = system_scope
    config.write_text(
        '[duckdog]\npath = "~dogopencli_missing_user_593687/data.duckdb"\n'
    )
    result = read_system_info(config)
    assert result["duckdog"]["state"] == "unavailable"
    assert result["duckdog"]["dataset_count"] is None
    assert result["installation"]["version"]
    assert result["cache"]["snapshot_count"] == 1


def test_mixed_case_owned_table_has_catalog_estimate(system_scope):
    config, _ = system_scope
    with duckdb.connect(str(config.parent / "duckdog.duckdb")) as database:
        database.execute('ALTER TABLE sample_rows RENAME TO "Sample_Rows"')
    result = read_system_info(config)
    database = result["duckdog"]["databases"][0]
    assert database["state"] == "available"
    dataset = next(d for d in database["datasets"] if d["relation"] == "sample_rows")
    assert dataset["estimated_rows"] == 1


def test_non_text_capture_time_remains_serializable_and_unknown(system_scope):
    config, _ = system_scope
    with sqlite3.connect(config.parent / "leaf-cache.sqlite3") as database:
        database.execute("UPDATE snapshots SET fetched_at=x'00'")
    result = read_system_info(config)
    snapshot = result["cache"]["leaves"][0]
    assert snapshot["fetched_at"] is None
    assert snapshot["freshness"] == "unknown"
    assert result["cache"]["snapshot_count"] == 1
    assert result["installation"]["version"]
    json.dumps(result)


@pytest.mark.parametrize("replacement_view", [False, True])
def test_missing_snapshot_table_is_unknown_without_repair(
    system_scope, replacement_view
):
    config, _ = system_scope
    with sqlite3.connect(config.parent / "leaf-cache.sqlite3") as database:
        database.execute("DROP TABLE snapshots")
        if replacement_view:
            database.execute("CREATE VIEW snapshots AS SELECT * FROM records")
    original = files(config.parent)
    result = read_system_info(config)
    assert result["cache"]["state"] == "unavailable"
    assert result["cache"]["snapshot_count"] is None
    assert result["cache"]["row_count"] is None
    assert result["installation"]["version"]
    assert files(config.parent) == original


def test_system_http_has_existing_origin_and_method_restrictions(editor):
    url, _, manifest = editor
    original = files(manifest.parents[3])
    with urlopen(url + "/api/system") as response:
        result = json.load(response)["system"]
        assert response.headers["Cache-Control"] == "no-store"
    assert result["leaf_count"] == 1
    assert files(manifest.parents[3]) == original
    for headers in [{"Host": "evil.test"}, {"Origin": "https://evil.test"}]:
        with pytest.raises(HTTPError) as failure:
            urlopen(Request(url + "/api/system", headers=headers))
        assert failure.value.code == 403
