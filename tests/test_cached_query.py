"""Quality policy against real SQLite, independent of domain row projections."""

from datetime import datetime, timedelta, timezone

import pytest

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.cached_query import read_cached_query
from dogopencli.config import Config, SourceConfig
from dogopencli.errors import CliError
from dogopencli.temporary_query import publish_candidate
from dogopencli.temporary_query import query_namespace as namespace


@pytest.fixture
def cached_scope(tmp_path):
    source = SourceConfig("snapshot", tmp_path / "absent-source", "fixture")
    config = Config(tmp_path / "cache.sqlite3", 72, {"fixture": source})
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    snapshot = SnapshotMeta(
        namespace=namespace("fixture.list", "EXTERNAL", source.kind),
        capability="fixture.list",
        scope="EXTERNAL",
        source_kind=source.kind,
        snapshot_id="snapshot",
        dataset_id="fixture",
        simulated=True,
        backend_complete=False,
        dataset_complete=True,
        fetched_at=(now - timedelta(hours=73)).isoformat(),
        loaded_at=now.isoformat(),
        source_observed_from=None,
        source_observed_to=None,
        row_count=2,
        source_path=str(source.path),
    )
    publish_candidate(
        Cache(config.cache_path), snapshot, [(1, '{"id":1}'), (2, '{"id":2}')]
    )
    return config, source, now


def read(scope, **overrides):
    config, source, now = scope
    options = dict(
        refresh_command="refresh fixture",
        require_fresh=False,
        require_complete=False,
        now=now,
    )
    options.update(overrides)
    return read_cached_query(config, source, "fixture.list", "EXTERNAL", **options)


def test_partial_mock_remains_usable_without_source_files(cached_scope):
    cached = read(cached_scope)
    assert len(cached.stored) == 2
    meta = cached.meta(2, 1)
    assert meta["stale"] is True
    assert meta["complete"] is False
    assert meta["dataset_complete"] is True
    assert meta["simulated"] is True
    assert meta["has_more"] is True
    assert cached.meta(2, 1, offset=1)["has_more"] is False


@pytest.mark.parametrize(
    "fresh, complete, code",
    [
        (True, False, "CACHE_STALE"),
        (False, True, "INCOMPLETE_RESULT"),
        (True, True, "CACHE_STALE"),
    ],
)
def test_quality_requirements_and_error_precedence(cached_scope, fresh, complete, code):
    with pytest.raises(CliError) as caught:
        read(cached_scope, require_fresh=fresh, require_complete=complete)
    assert caught.value.code == code


def test_configured_source_change_does_not_hide_saved_slot(cached_scope):
    config, source, now = cached_scope
    foreign = SourceConfig(source.kind, source.path, "other-dataset")
    assert len(read((config, foreign, now)).stored) == 2


def test_exact_ttl_boundary_is_fresh(cached_scope):
    config, source, now = cached_scope
    result = read((config, source, now - timedelta(hours=1)), require_fresh=True)
    assert result.stale is False


@pytest.mark.parametrize(
    "mode",
    ["valid", "duplicate", "missing", "invalid", "malformed_json", "seqid_gap"],
)
def test_validated_snapshot_records(cached_scope, mode):
    """Read-time integrity uses real stored data and preserves domain failures."""
    import sqlite3

    config, _, _ = cached_scope
    with sqlite3.connect(config.cache_path) as connection:
        if mode == "duplicate":
            connection.execute("UPDATE records SET body = '{\"id\":1}'")
        elif mode == "missing":
            connection.execute("DELETE FROM records WHERE seqid = 2")
        elif mode == "invalid":
            connection.execute("UPDATE records SET body = 'null' WHERE seqid = 2")
        elif mode == "malformed_json":
            connection.execute(
                "UPDATE records SET body = '{BROKEN-PRIVATE}' WHERE seqid = 2"
            )
        elif mode == "seqid_gap":
            connection.execute("UPDATE records SET seqid = 3 WHERE seqid = 2")

    def validate(record):
        if not isinstance(record, dict):
            raise CliError("INVALID_RESPONSE", "invalid fixture row")

    cached = read(cached_scope)
    if mode == "valid":
        assert cached.validated_records(
            validate, lambda row: row["id"], coverage_error="invalid coverage"
        ) == [{"id": 1}, {"id": 2}]
    else:
        with pytest.raises(CliError) as caught:
            cached.validated_records(
                validate, lambda row: row["id"], coverage_error="invalid coverage"
            )
        assert caught.value.code == (
            "INVALID_RESPONSE"
            if mode in ("invalid", "malformed_json")
            else "INCOMPLETE_RESULT"
        )
        assert "BROKEN-PRIVATE" not in caught.value.message
