"""Quality policy against real SQLite, independent of domain row projections."""

from datetime import datetime, timedelta, timezone

import pytest

from dogopencli.cache import Cache, SnapshotMeta, namespace
from dogopencli.cached_query import read_cached_query
from dogopencli.config import Config, SourceConfig
from dogopencli.errors import CliError


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
    Cache(config.cache_path).publish(snapshot, [(1, '{"id":1}'), (2, '{"id":2}')])
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


def test_identity_mismatch_precedes_quality(cached_scope):
    config, source, now = cached_scope
    foreign = SourceConfig(source.kind, source.path, "other-dataset")
    with pytest.raises(CliError) as caught:
        read((config, foreign, now), require_fresh=True, require_complete=True)
    assert caught.value.code == "CACHE_MISS"
    assert "source identity" in caught.value.message
    assert "run: dogopencli refresh fixture" in caught.value.message


def test_exact_ttl_boundary_is_fresh(cached_scope):
    config, source, now = cached_scope
    result = read((config, source, now - timedelta(hours=1)), require_fresh=True)
    assert result.stale is False
