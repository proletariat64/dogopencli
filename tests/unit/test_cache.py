"""Unit tests for the SQLite snapshot cache."""

import pytest

from dogopencli.cache import Cache, SnapshotMeta, namespace


def meta(ns: str, snapshot_id: str = "snap-1", row_count: int = 2) -> SnapshotMeta:
    return SnapshotMeta(
        namespace=ns,
        capability="payment.channel.list",
        scope="EXTERNAL",
        source_kind="snapshot",
        snapshot_id=snapshot_id,
        dataset_id="d" * 64,
        simulated=True,
        backend_complete=False,
        dataset_complete=True,
        fetched_at="2026-01-01T00:00:00+00:00",
        loaded_at="2026-01-02T00:00:00+00:00",
        source_observed_from="2026-01-01T00:00:00+00:00",
        source_observed_to="2026-01-01T01:00:00+00:00",
        row_count=row_count,
    )


ROWS = [(1, '{"seqid":1,"a":1}'), (2, '{"seqid":2,"a":2}')]


def test_publish_and_read_roundtrip(tmp_path):
    store = Cache(tmp_path / "db" / "cache.sqlite3")
    ns = namespace("payment.channel.list", "EXTERNAL", "snapshot")
    store.publish(meta(ns), ROWS)
    snapshot = store.current(ns)
    assert snapshot is not None
    assert snapshot.snapshot_id == "snap-1"
    assert snapshot.dataset_id == "d" * 64
    assert snapshot.backend_complete is False
    assert store.records(ns) == ROWS


def test_namespaces_are_isolated(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    ns_a = namespace("payment.channel.list", "EXTERNAL", "snapshot")
    ns_b = namespace("payment.channel.list", "EXTERNAL", "cdp")
    store.publish(meta(ns_a), ROWS)
    assert store.current(ns_b) is None
    assert store.records(ns_b) == []


def test_replace_keeps_single_current_snapshot(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    ns = namespace("payment.channel.list", "EXTERNAL", "snapshot")
    store.publish(meta(ns, snapshot_id="old"), ROWS)
    store.publish(meta(ns, snapshot_id="new", row_count=1), ROWS[:1])
    snapshot = store.current(ns)
    assert snapshot is not None
    assert snapshot.snapshot_id == "new"
    assert store.records(ns) == ROWS[:1]


def test_failed_publish_preserves_previous_snapshot(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    ns = namespace("payment.channel.list", "EXTERNAL", "snapshot")
    store.publish(meta(ns), ROWS)

    def broken():
        yield ROWS[0]
        raise RuntimeError("simulated import failure")

    with pytest.raises(RuntimeError):
        store.publish(meta(ns, snapshot_id="broken"), broken())
    snapshot = store.current(ns)
    assert snapshot is not None
    assert snapshot.snapshot_id == "snap-1"
    assert store.records(ns) == ROWS


def test_refresh_lock_conflicts(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    with store.refresh_lock():
        with pytest.raises(Exception) as caught:
            with store.refresh_lock():
                pass
        assert getattr(caught.value, "code", None) == "LOCKED"
    with store.refresh_lock():
        pass
