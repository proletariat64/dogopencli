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


def test_dead_process_does_not_leave_refresh_locked(tmp_path):
    import os
    import signal

    store = Cache(tmp_path / "cache.sqlite3")
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        with store.refresh_lock():
            os.write(write_fd, b"ready")
            signal.pause()
        os._exit(0)
    os.close(write_fd)
    try:
        assert os.read(read_fd, 5) == b"ready"
    finally:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        os.close(read_fd)
    assert (tmp_path / "cache.sqlite3.refresh.lock").exists()
    with store.refresh_lock():
        pass


def test_sqlite_lock_error_is_not_hidden_by_rollback(tmp_path, monkeypatch):
    import sqlite3

    from dogopencli.errors import CliError

    path = tmp_path / "cache.sqlite3"
    store = Cache(path)
    store.publish(meta("test"), ROWS)
    connect = sqlite3.connect
    holder = connect(path, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")

    def fast_connect(*args, **kwargs):
        kwargs["timeout"] = 0.01
        return connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", fast_connect)
    try:
        with pytest.raises(CliError) as caught:
            store.publish(meta("test", "new"), ROWS)
        assert caught.value.code == "LOCKED"
        assert "rollback" not in str(caught.value)
    finally:
        holder.rollback()
        holder.close()
    assert store.current("test").snapshot_id == "snap-1"


def test_corrupt_cache_is_not_misreported_as_locked(tmp_path):
    from dogopencli.errors import CliError

    path = tmp_path / "cache.sqlite3"
    path.write_bytes(b"not a database")
    with pytest.raises(CliError) as caught:
        Cache(path).read("test")
    assert caught.value.code == "CACHE_ERROR"


def test_existing_cache_schema_preserves_records(tmp_path):
    import sqlite3

    from dogopencli.cache import SCHEMA

    path = tmp_path / "cache.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        SCHEMA.replace(
            "row_count INTEGER NOT NULL,\n    source_path TEXT",
            "row_count INTEGER NOT NULL",
        )
    )
    connection.execute("INSERT INTO records VALUES (?, ?, ?)", ("test", 1, "{}"))
    connection.commit()
    connection.close()

    store = Cache(path)
    assert store.records("test") == [(1, "{}")]
    connection = sqlite3.connect(path)
    assert "source_path" in [
        row[1] for row in connection.execute("PRAGMA table_info(snapshots)")
    ]
    connection.close()


def test_concurrent_old_schema_migration(tmp_path, monkeypatch):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from dogopencli.cache import SCHEMA

    path = tmp_path / "cache.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(
        SCHEMA.replace(
            "row_count INTEGER NOT NULL,\n    source_path TEXT",
            "row_count INTEGER NOT NULL",
        )
    )
    connection.execute("INSERT INTO records VALUES (?, ?, ?)", ("test", 1, "{}"))
    connection.commit()
    connection.close()
    barrier = Barrier(2, timeout=5)
    connect = sqlite3.connect

    class SynchronizedConnection(sqlite3.Connection):
        checked = False

        def execute(self, sql, *args, **kwargs):
            result = super().execute(sql, *args, **kwargs)
            if sql == "PRAGMA table_info(snapshots)" and not self.checked:
                self.checked = True
                rows = result.fetchall()
                barrier.wait()
                return rows
            return result

    def synchronized_connect(*args, **kwargs):
        return connect(*args, factory=SynchronizedConnection, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", synchronized_connect)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: Cache(path).records("test"), range(2)))
    assert results == [[(1, "{}")], [(1, "{}")]]


def test_refresh_lock_preserves_os_error_cause(tmp_path, monkeypatch):
    from dogopencli.errors import CliError

    error = OSError("lock unavailable")

    def fail_open(*args):
        raise error

    monkeypatch.setattr("dogopencli.cache.os.open", fail_open)
    with pytest.raises(CliError) as caught:
        with Cache(tmp_path / "cache.sqlite3").refresh_lock():
            pytest.fail("lock must not be acquired")
    assert caught.value.code == "IO_ERROR"
    assert caught.value.__cause__ is error


@pytest.mark.parametrize("release_lock", [True, False])
def test_wal_initialization_retries_only_within_deadline(
    tmp_path, monkeypatch, release_lock
):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from dogopencli.errors import CliError

    path = tmp_path / "cache.sqlite3"
    connect = sqlite3.connect
    holder = connect(path, isolation_level=None)
    holder.execute("CREATE TABLE existing (id INTEGER)")
    holder.execute("BEGIN")
    holder.execute("SELECT * FROM existing").fetchall()
    busy = Event()
    released = Event()

    class ObservedConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            try:
                return super().execute(sql, *args, **kwargs)
            except sqlite3.OperationalError:
                if sql == "PRAGMA journal_mode=WAL":
                    busy.set()
                    if release_lock:
                        assert released.wait(5)
                raise

    def observed_connect(*args, **kwargs):
        kwargs["timeout"] = 0.01
        return connect(*args, factory=ObservedConnection, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", observed_connect)
    if not release_lock:
        ticks = iter([0.0, 11.0])
        monkeypatch.setattr("dogopencli.cache.monotonic", lambda: next(ticks))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(Cache(path).read, "test")
            try:
                assert busy.wait(5)
            finally:
                if release_lock:
                    holder.rollback()
                    released.set()
            if release_lock:
                assert result.result(timeout=5) == (None, [])
            else:
                with pytest.raises(CliError) as caught:
                    result.result(timeout=5)
                assert caught.value.code == "LOCKED"
                assert caught.value.retryable is True
    finally:
        holder.close()
    with connect(path) as connection:
        assert connection.execute("SELECT * FROM existing").fetchall() == []
    assert path.stat().st_mode & 0o777 == 0o600
