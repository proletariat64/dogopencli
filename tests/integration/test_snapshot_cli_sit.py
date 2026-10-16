"""Issue #80 acceptance through the public CLI and synthetic SQLite caches."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.jsonutil import canonical


@pytest.fixture
def snapshot_setup(tmp_path, monkeypatch):
    path = tmp_path / "cache.sqlite3"
    config = tmp_path / "config.toml"
    config.write_text(f'[cache]\npath = "{path}"\nttl_hours = 72\n')
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    monkeypatch.delenv("DOGOPENCLI_CONFIG_DIR", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("snapshot must not initialize browser/auth/transport")

    from dogopencli.browser import cdp, environment

    monkeypatch.setattr(cdp, "make_transport", forbidden)
    monkeypatch.setattr(environment, "resolve_environment", forbidden)
    return path, config


def publish(
    path, capability, scope="scope", *, count=2, complete=True, age=0, source="cdp"
):
    acquired = datetime.now(timezone.utc) - timedelta(hours=age)
    timestamp = acquired.isoformat()
    name = "temporary-query:" + capability.removesuffix(".list")
    meta = SnapshotMeta(
        namespace=name,
        capability=capability,
        scope=canonical(
            {"query": {"scope": scope}, "variant": source, "selection": None}
        ),
        source_kind=source,
        snapshot_id="PRIVATE-SNAPSHOT-ID",
        dataset_id=None,
        simulated=False,
        backend_complete=complete,
        dataset_complete=True,
        fetched_at=timestamp,
        loaded_at=timestamp,
        source_observed_from=None,
        source_observed_to=None,
        row_count=count,
    )
    # Snapshot counts storage records; it must not parse the business bodies.
    Cache(path).publish(
        meta,
        [(i, "PRIVATE-BUSINESS-ROW") for i in range(1, count + 1)],
    )
    return name, timestamp


def leaves(node):
    if "availability" in node:
        yield node
    for child in node.get("children", []):
        yield from leaves(child)


def report(run_cli, *path):
    code, out, err = run_cli(["snapshot", *path, "--format", "json"])
    return code, json.loads(out), err
