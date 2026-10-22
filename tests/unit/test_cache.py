"""Unit tests for the SQLite snapshot cache."""

import threading
from dataclasses import replace

import pytest

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.jsonutil import canonical, parse


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


def test_partial_quality_survives_atomic_publication_and_offline_read(tmp_path):
    from dogopencli.result_policy import AcquisitionEvidence

    store = Cache(tmp_path / "cache.sqlite3")
    evidence = AcquisitionEvidence.for_collection(
        complete=False, reported_total=3, collected_total=2, arrivals=2
    )
    snapshot = replace(
        meta("partial"), dataset_complete=False, acquisition=evidence.record()
    )
    store.publish(snapshot, ROWS)
    loaded, rows = store.read("partial")
    assert loaded.acquisition == evidence.record()
    assert loaded.row_count == 2 and loaded.backend_complete is False
    assert rows == ROWS


def test_missing_cache_read_does_not_create_database(tmp_path):
    path = tmp_path / "absent" / "cache.sqlite3"
    assert Cache(path).read("missing") == (None, [])
    assert not path.parent.exists()


def test_publish_and_read_roundtrip(tmp_path):
    store = Cache(tmp_path / "db" / "cache.sqlite3")
    ns = "leaf:sample.rows"
    store.publish(meta(ns), ROWS)
    snapshot = store.current(ns)
    assert snapshot is not None
    assert snapshot.snapshot_id == "snap-1"
    assert snapshot.dataset_id == "d" * 64
    assert snapshot.backend_complete is False
    assert store.records(ns) == ROWS


def test_namespaces_are_isolated(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    ns_a = "leaf:sample.rows"
    ns_b = "leaf:sample.other"
    store.publish(meta(ns_a), ROWS)
    assert store.current(ns_b) is None
    assert store.records(ns_b) == []


def test_replace_keeps_single_current_snapshot(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    ns = "leaf:sample.rows"
    store.publish(meta(ns, snapshot_id="old"), ROWS)
    store.publish(meta(ns, snapshot_id="new", row_count=1), ROWS[:1])
    snapshot = store.current(ns)
    assert snapshot is not None
    assert snapshot.snapshot_id == "new"
    assert store.records(ns) == ROWS[:1]


def test_failed_publish_preserves_previous_snapshot(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    ns = "leaf:sample.rows"
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


def test_unsupported_cache_schema_requires_recreation(tmp_path):
    import sqlite3

    from dogopencli.cache import SCHEMA
    from dogopencli.errors import CliError

    path = tmp_path / "cache.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            SCHEMA.replace(",\n    source_path TEXT,\n    acquisition TEXT", "")
        )
    store = Cache(path)
    for read in (store.read, store.current):
        with pytest.raises(CliError) as caught:
            read("test")
        assert caught.value.code == "CACHE_ERROR"
    with pytest.raises(CliError) as caught:
        store.publish(meta("test"), ROWS)
    assert caught.value.code == "CACHE_ERROR"
    path.unlink()
    store.publish(meta("test"), ROWS)
    assert store.read("test")[1] == ROWS


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
            result = pool.submit(Cache(path).publish, meta("test"), ROWS)
            try:
                assert busy.wait(5)
            finally:
                if release_lock:
                    holder.rollback()
                    released.set()
            if release_lock:
                assert result.result(timeout=5) is None
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


def test_concurrent_reads_see_complete_snapshots(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")

    def snapshot(ns: str, rows: int, marker: str) -> SnapshotMeta:
        return SnapshotMeta(
            namespace=ns,
            capability="sample.rows",
            scope="sample",
            source_kind="cdp",
            snapshot_id=marker,
            dataset_id=None,
            simulated=False,
            backend_complete=True,
            dataset_complete=True,
            fetched_at="2026-09-11T00:00:00+00:00",
            loaded_at="2026-09-11T00:00:00+00:00",
            source_observed_from=None,
            source_observed_to=None,
            row_count=rows,
        )

    ns = "leaf:sample.rows"
    failures: list[str] = []
    writer_errors: list[BaseException] = []
    stop = threading.Event()
    first_checked = threading.Event()
    checks = 0

    def writer() -> None:
        try:
            for round_no in range(40):
                rows = 3 if round_no % 2 == 0 else 5
                keyed = [
                    (index, canonical({"seq": index, "round": round_no}))
                    for index in range(1, rows + 1)
                ]
                store.publish(snapshot(ns, rows, f"snap-{round_no}"), keyed)
                if round_no == 0 and not first_checked.wait(timeout=5):
                    raise AssertionError("reader did not check the first snapshot")
        except BaseException as error:
            writer_errors.append(error)
        finally:
            stop.set()

    def reader() -> None:
        nonlocal checks
        while not stop.is_set():
            meta, bodies = store.read(ns)
            if meta is None:
                continue
            try:
                if len(bodies) != meta.row_count:
                    failures.append(
                        f"row_count {meta.row_count} but {len(bodies)} records"
                    )
                    return
                if [seq for seq, _ in bodies] != list(range(1, meta.row_count + 1)):
                    failures.append("seqids are not continuous for one snapshot")
                    return
                rounds = {parse(body)["round"] for _, body in bodies}
                if len(rounds) != 1:
                    failures.append("records mix two published snapshots")
                    return
                checks += 1
            finally:
                first_checked.set()

    thread = threading.Thread(target=writer)
    thread.start()
    reader()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert writer_errors == []
    assert checks > 0
    assert failures == []
