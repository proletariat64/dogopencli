import sqlite3
from stat import S_IMODE

import pytest

from dogopencli.cache import Cache
from dogopencli.result_policy import AcquisitionEvidence
from dogopencli.temporary_query import prune_slot, publish_slot, read_slot


def test_single_slot_replacement_and_empty_preservation(tmp_path):
    store = Cache(tmp_path / "cache.sqlite")
    evidence = AcquisitionEvidence(
        scope_complete=True, dataset_complete=True, collected_total=1
    )
    first = publish_slot(
        store,
        "payment.channel",
        [{"id": "A"}],
        capability="channel",
        scope={"entity": "A"},
        evidence=evidence,
        fetched_at="2026-01-01T00:00:00+00:00",
    )
    assert (
        publish_slot(
            store,
            "payment.channel",
            [],
            capability="channel",
            scope={},
            evidence=evidence,
            fetched_at="2026-01-02T00:00:00+00:00",
        )
        is None
    )
    assert read_slot(store, "payment.channel") == (first, [{"id": "A"}])
    publish_slot(
        store,
        "payment.channel",
        [{"id": "B"}],
        capability="channel",
        scope={"entity": "B"},
        evidence=evidence,
        fetched_at="2026-01-03T00:00:00+00:00",
    )
    assert read_slot(store, "payment.channel")[1] == [{"id": "B"}]
    assert prune_slot(store, "payment.channel")
    assert not prune_slot(store, "payment.channel")


def test_missing_read_and_prune_do_not_initialize_storage(tmp_path):
    path = tmp_path / "absent" / "cache.sqlite"
    store = Cache(path)
    assert read_slot(store, "fx.trade") == (None, [])
    assert not prune_slot(store, "fx.trade")
    assert not path.parent.exists()


def test_enabled_list_catalog_has_uniform_display_and_prune():
    from dogopencli.catalog import NODES
    from dogopencli.plugins import domain_plugins

    cache_paths = {
        path
        for domain in domain_plugins()
        for leaf in domain.leaves
        if leaf.enabled
        for path in leaf.cache_paths
    }

    for path, node in NODES.items():
        if path not in cache_paths or path[:1] == ("refresh",):
            continue
        if path[-1] != "list" and path != ("fx", "trade"):
            continue
        options = {option.name: option for option in node.options}
        assert "all" not in options
        assert {"limit", "offset", "format"} <= options.keys()
        assert options["format"].default == "json"
        sibling = (*path[:-1], "prune") if path[-1] == "list" else (*path, "prune")
        assert NODES[sibling].handler == "cmd_prune"


@pytest.mark.parametrize("legacy_version", [None, 156])
def test_format_switch_discards_legacy_once_and_preserves_external_inputs(
    tmp_path, legacy_version
):
    store = Cache(tmp_path / "cache.sqlite")
    external = tmp_path / "duckdog.db"
    external.write_bytes(b"external source stays private")
    evidence = AcquisitionEvidence(
        scope_complete=True, dataset_complete=True, collected_total=1
    )
    publish_slot(
        store,
        "payment.channel",
        [{"id": "legacy"}],
        capability="channel",
        scope={},
        evidence=evidence,
        fetched_at="2026-01-01T00:00:00+00:00",
    )
    with sqlite3.connect(tmp_path / "cache.sqlite") as connection:
        if legacy_version is None:
            connection.execute("DROP TABLE cache_format")
        else:
            connection.execute("UPDATE cache_format SET version = ?", (legacy_version,))
        connection.execute("UPDATE snapshots SET namespace = 'legacy:list:cdp'")
        connection.execute("UPDATE records SET namespace = 'legacy:list:cdp'")
    assert read_slot(store, "payment.channel") == (None, [])
    publish_slot(
        store,
        "payment.channel",
        [{"id": "new"}],
        capability="channel",
        scope={},
        evidence=evidence,
        fetched_at="2026-01-02T00:00:00+00:00",
    )
    assert read_slot(store, "payment.channel")[1] == [{"id": "new"}]
    assert read_slot(store, "payment.channel")[1] == [{"id": "new"}]
    assert external.read_bytes() == b"external source stays private"


@pytest.fixture
def updated_slot(tmp_path):
    path = tmp_path / "cache" / "cache.sqlite"
    store = Cache(path)
    snapshot = publish_slot(
        store,
        "payment.channel",
        [{"id": "saved"}],
        capability="channel",
        scope={},
        evidence=AcquisitionEvidence.for_collection(
            complete=True, collected_total=1, reported_total=1
        ),
        fetched_at="2026-01-01T00:00:00+00:00",
    )
    return store, path, snapshot


def test_updated_slot_replays_without_write_access(updated_slot, monkeypatch):
    store, path, snapshot = updated_slot
    connection = sqlite3.connect(path)
    # No WAL sidecars need creating in this read-only-directory fixture.
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.close()
    before = path.read_bytes()
    path.chmod(0o444)
    path.parent.chmod(0o550)

    def deny_write_connection():
        raise PermissionError("cache is read-only")

    monkeypatch.setattr(store, "_connect", deny_write_connection)
    try:
        assert read_slot(store, "payment.channel") == (snapshot, [{"id": "saved"}])
        assert path.read_bytes() == before
        assert S_IMODE(path.stat().st_mode) == 0o444
        assert S_IMODE(path.parent.stat().st_mode) == 0o550
        assert list(path.parent.iterdir()) == [path]
    finally:
        path.parent.chmod(0o700)
        path.chmod(0o600)


def test_updated_slot_replays_while_writer_holds_lock(updated_slot, monkeypatch):
    store, path, snapshot = updated_slot
    connect = sqlite3.connect
    writer = connect(path, isolation_level=None)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("UPDATE records SET body = ?", ('{"id":"uncommitted"}',))

    def fast_connect(*args, **kwargs):
        kwargs["timeout"] = 0.01
        return connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", fast_connect)
    try:
        assert read_slot(store, "payment.channel") == (snapshot, [{"id": "saved"}])
    finally:
        writer.rollback()
        writer.close()
