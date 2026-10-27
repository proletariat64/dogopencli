"""Durable synchronization behavior through the storage boundary."""

from pathlib import Path

import duckdb

from dogopencli.sync_store import SyncStore


def database(tmp_path: Path) -> Path:
    path = tmp_path / "duckdog.duckdb"
    with duckdb.connect(str(path)) as db:
        db.execute("CREATE TABLE settings (_record VARCHAR)")
        db.execute(
            "CREATE TABLE _dogopencli_leaf_ownership "
            "(relation_name VARCHAR PRIMARY KEY, leaf_id VARCHAR UNIQUE NOT NULL)"
        )
        db.execute(
            "INSERT INTO _dogopencli_leaf_ownership VALUES ('settings', "
            "'test/settings')"
        )
    return path


def target(store, **extra):
    return store.save_target(
        {
            "leaf_id": "test/settings",
            "relation": "settings",
            "variant": "default",
            "namespace": {"environment": "test"},
            **extra,
        }
    )


def publish(store, item, rows, *, chunk=None, mode="settings", **kwargs):
    attempt = store.start_attempt(
        item["id"], chunk or {}, started_at="2026-10-25T12:00:00Z"
    )
    return store.publish(
        attempt,
        rows,
        key_fields=("id",),
        mode=mode,
        evidence={"complete": True, "authoritative": True},
        acquired_at="2026-10-25T12:01:00Z",
        **kwargs,
    )


def test_settings_replace_and_status_reads_without_creating_files(tmp_path):
    missing = tmp_path / "absent" / "missing.duckdb"
    assert SyncStore.status(missing) == {"targets": [], "coverage": [], "attempts": []}
    assert not missing.parent.exists()
    path = database(tmp_path)
    with SyncStore(path) as store:
        item = target(store)
        publish(store, item, [{"id": "a", "value": 1}, {"id": "b", "value": 2}])
        result = publish(store, item, [{"id": "b", "value": 3}])
        assert result["updated"] == 1
        assert store.records(item["id"]) == [{"id": "b", "value": 3}]
    report = SyncStore.status(path)
    assert report["targets"][0]["row_count"] == 1
    assert report["coverage"][0]["state"] == "complete_nonempty"
    with duckdb.connect(str(path), read_only=True) as db:
        assert db.execute("SELECT count(*) FROM settings").fetchone() == (1,)


def test_runtime_merges_windows_and_does_not_delete_history_on_empty(tmp_path):
    path = database(tmp_path)
    with SyncStore(path) as store:
        item = target(store)
        publish(
            store,
            item,
            [{"id": "a", "value": 1}],
            chunk={"date": "2026-10-23"},
            mode="runtime",
        )
        publish(
            store,
            item,
            [{"id": "b", "value": 2}],
            chunk={"date": "2026-10-25"},
            mode="runtime",
        )
        publish(store, item, [], chunk={"date": "2026-10-24"}, mode="runtime")
        assert store.records(item["id"]) == [
            {"id": "a", "value": 1},
            {"id": "b", "value": 2},
        ]
        assert [c["state"] for c in store.coverage(item["id"])] == [
            "complete_nonempty",
            "complete_empty",
            "complete_nonempty",
        ]


def test_runtime_version_order_and_equal_version_conflict_preserve_records(tmp_path):
    import pytest

    from dogopencli.errors import CliError

    with SyncStore(database(tmp_path)) as store:
        item = target(store)
        publish(
            store,
            item,
            [{"id": "a", "revision": 2, "value": "new"}],
            mode="runtime",
            version_field="revision",
        )
        result = publish(
            store,
            item,
            [{"id": "a", "revision": 1, "value": "old"}],
            mode="runtime",
            version_field="revision",
        )
        assert result["older"] == 1
        assert store.records(item["id"]) == [{"id": "a", "revision": 2, "value": "new"}]
        with pytest.raises(CliError, match="Equal source versions"):
            publish(
                store,
                item,
                [{"id": "a", "revision": 2, "value": "conflict"}],
                mode="runtime",
                version_field="revision",
            )
        assert store.records(item["id"])[0]["value"] == "new"


def test_observations_keep_generations_but_only_latest_current_view(tmp_path):
    path = database(tmp_path)
    with SyncStore(path) as store:
        item = target(store)
        publish(store, item, [{"id": "a", "value": 1}], mode="observation")
        publish(store, item, [{"id": "a", "value": 2}], mode="observation")
        assert store.records(item["id"]) == [{"id": "a", "value": 2}]
        assert sorted(
            row["value"] for row in store.records(item["id"], observations=True)
        ) == [1, 2]


def test_rejects_untracked_existing_records_in_owned_relation(tmp_path):
    import pytest

    from dogopencli.errors import CliError

    path = database(tmp_path)
    with duckdb.connect(str(path)) as db:
        db.execute('INSERT INTO settings VALUES (\'{"id":"external"}\')')
    with SyncStore(path) as store:
        item = target(store)
        with pytest.raises(CliError, match="existing records"):
            publish(store, item, [{"id": "a"}])
        assert store.coverage(item["id"]) == []
    with duckdb.connect(str(path), read_only=True) as db:
        assert db.execute("SELECT _record FROM settings").fetchall() == [
            ('{"id":"external"}',)
        ]


def test_failed_refresh_preserves_data_coverage_and_reports_attempt(tmp_path):
    import pytest

    from dogopencli.errors import CliError

    path = database(tmp_path)
    with SyncStore(path) as store:
        item = target(store)
        publish(store, item, [{"id": "a", "value": 1}])
        failed = store.start_attempt(item["id"], {}, started_at="2026-10-26T12:00:00Z")
        with pytest.raises(CliError, match="complete authoritative"):
            store.publish(
                failed,
                [],
                key_fields=("id",),
                mode="settings",
                evidence={"complete": False, "authoritative": True},
                acquired_at="2026-10-26T12:01:00Z",
            )
        store.fail_attempt(
            failed,
            {"code": "INCOMPLETE_RESULT", "reason_codes": ["missing_page"]},
            finished_at="2026-10-26T12:01:00Z",
        )
        assert store.records(item["id"]) == [{"id": "a", "value": 1}]
        assert store.coverage(item["id"])[0]["acquired_at"] == "2026-10-25T12:01:00Z"
    report = SyncStore.status(path)["targets"][0]
    assert report["last_attempt"]["state"] == "failed"
    assert report["last_success"]["state"] == "complete"


def test_settings_scope_replacement_preserves_other_scope_and_decimals(tmp_path):
    from decimal import Decimal

    path = database(tmp_path)
    with SyncStore(path) as store:
        first = target(store, namespace={"account": "a"})
        second = target(store, namespace={"account": "b"})
        publish(
            store, first, [{"id": "same", "value": Decimal("1234567890.0123456789")}]
        )
        publish(
            store, second, [{"id": "same", "value": Decimal("1234567890.0123456789")}]
        )
        publish(store, first, [])
        assert store.records(first["id"]) == []
        assert store.records(second["id"])[0]["value"] == Decimal(
            "1234567890.0123456789"
        )
        assert store.coverage(first["id"])[0]["state"] == "complete_empty"
    with duckdb.connect(str(path), read_only=True) as db:
        assert db.execute("SELECT count(*) FROM settings").fetchone() == (1,)
        assert [
            (r[1], r[2]) for r in db.execute("PRAGMA table_info(settings)").fetchall()
        ] == [("_record", "VARCHAR")]


def test_interrupted_row_stream_rolls_back_and_restart_succeeds(tmp_path):
    import pytest

    path = database(tmp_path)
    with SyncStore(path) as store:
        item = target(store)
        publish(store, item, [{"id": "old"}])

        def interrupted():
            yield from ({"id": str(i)} for i in range(1001))
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            publish(store, item, interrupted())
        assert store.records(item["id"]) == [{"id": "old"}]
        assert not list(tmp_path.glob(".sync-stage-*"))
    with SyncStore(path) as store:
        publish(store, item, [{"id": "new"}])
        assert store.records(item["id"]) == [{"id": "new"}]


def test_writer_lock_survives_acquisition_readonly_selector(tmp_path):
    import pytest

    from dogopencli.errors import CliError

    path = database(tmp_path)
    with SyncStore(path) as store:
        with pytest.raises(CliError, match="Another sync writer"):
            with SyncStore(path):
                pass
        with store.acquisition():
            with duckdb.connect(str(path), read_only=True) as reader:
                assert reader.execute("SELECT count(*) FROM settings").fetchone() == (
                    0,
                )
            with pytest.raises(CliError, match="Another sync writer"):
                with SyncStore(path):
                    pass
        item = target(store)
        publish(store, item, [{"id": "after"}])


def test_duplicate_conflict_rejects_chunk_and_optional_native_empty_identity(tmp_path):
    import pytest

    from dogopencli.errors import CliError

    with SyncStore(database(tmp_path)) as store:
        item = target(store)
        with pytest.raises(CliError, match="Conflicting native identities"):
            publish(store, item, [{"id": "a", "v": 1}, {"id": "a", "v": 2}])
        assert store.records(item["id"]) == []
        with pytest.raises(CliError, match="missing native identity"):
            publish(store, item, [{"id": None}])
        publish(store, item, [{"id": None}], allow_empty_key_components=True)
        assert store.records(item["id"]) == [{"id": None}]


def test_datetime_versions_compare_instants_not_offset_strings(tmp_path):
    with SyncStore(database(tmp_path)) as store:
        item = target(store)
        publish(
            store,
            item,
            [{"id": "a", "modified": "2026-10-25T09:00:00+08:00", "v": "new"}],
            mode="runtime",
            version_field="modified",
            version_kind="datetime",
        )
        result = publish(
            store,
            item,
            [{"id": "a", "modified": "2026-10-25T00:30:00Z", "v": "old"}],
            mode="runtime",
            version_field="modified",
            version_kind="datetime",
        )
        assert result["older"] == 1
        assert store.records(item["id"])[0]["v"] == "new"


def test_target_identity_updates_without_duplicate_enrollment(tmp_path):
    with SyncStore(database(tmp_path)) as store:
        first = target(
            store, identity={"leaf": "settings", "scope": "all"}, end="2026-10-25"
        )
        second = target(
            store, identity={"leaf": "settings", "scope": "all"}, end="2026-10-26"
        )
        assert first["id"] == second["id"]
        assert len(store.targets()) == 1
        assert store.targets()[0]["end"] == "2026-10-26"


def test_publication_storage_failure_rolls_back_records_and_coverage(tmp_path):
    import pytest

    from dogopencli.errors import CliError

    path = database(tmp_path)
    with duckdb.connect(str(path)) as db:
        db.execute("DROP TABLE settings")
        db.execute(
            "CREATE TABLE settings (_record VARCHAR CHECK (_record NOT LIKE "
            "'%blocked%'))"
        )
    with SyncStore(path) as store:
        item = target(store)
        publish(store, item, [{"id": "safe"}])
        with pytest.raises(CliError, match="transaction failed"):
            publish(store, item, [{"id": "blocked"}])
        assert store.records(item["id"]) == [{"id": "safe"}]
        assert len(store.coverage(item["id"])) == 1
    with duckdb.connect(str(path), read_only=True) as db:
        assert db.execute("SELECT _record FROM settings").fetchall() == [
            ('{"id":"safe"}',)
        ]


def test_restart_marks_unfinished_attempt_without_claiming_coverage(tmp_path):
    path = database(tmp_path)
    with SyncStore(path) as store:
        item = target(store)
        store.start_attempt(
            item["id"], {"date": "2026-10-24"}, started_at="2026-10-25T00:00:00Z"
        )
    with SyncStore(path) as store:
        assert store.coverage(item["id"]) == []
    attempt = SyncStore.status(path)["attempts"][0]
    assert attempt["state"] == "interrupted"
    assert attempt["diagnostic"]["code"] == "INTERRUPTED"
