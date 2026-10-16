"""Batch F F4 (#119): network routes stays deferred through the public CLI."""

from pathlib import Path

import pytest

from dogopencli.browser import cdp
from dogopencli.cache import Cache, SnapshotMeta

LIST_PATH = ("liquidity", "network", "routes", "list")
GET_PATH = ("liquidity", "network", "routes", "get")
# Named blocker from the #119 evidence (2026-10-06): RealTimeNetwork is a
# network configuration object (native network id; routeId values are
# references), and the discovered queryWhaleRouteDetail caller is a
# network-scoped per-route quota detail, not a global routes list.
LIST_BLOCKER = (
    "no native global routes-list caller",
    "RealTimeNetwork",
    "queryWhaleRouteDetail",
    "quota",
    "not a global routes list",
)
GET_BLOCKER = ("queryWhaleRouteDetail", "never executed")


@pytest.fixture(params=["sqlite", "missing", "corrupt"])
def disconnected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request):
    cache = tmp_path / "cache.sqlite3"
    if request.param == "sqlite":
        Cache(cache).publish(
            SnapshotMeta(
                namespace="preserved",
                capability="preserved",
                scope="all",
                source_kind="cdp",
                snapshot_id="previous-capture",
                dataset_id=None,
                simulated=True,
                backend_complete=True,
                dataset_complete=True,
                fetched_at="2026-10-01T00:00:00Z",
                loaded_at="2026-10-01T00:00:00Z",
                source_observed_from=None,
                source_observed_to=None,
                row_count=1,
            ),
            [(1, '{"sentinel":"preserved synthetic record"}')],
        )
    elif request.param == "corrupt":
        cache.write_bytes(b"unreadable previous cache must stay untouched")
    config = tmp_path / "config.toml"
    config.write_text(
        f'[cache]\npath = "{cache}"\n'
        f'[auth]\nprofile = "{tmp_path / "profile"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
        '[sources.liquidity]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))

    def reject_browser(*args, **kwargs):
        pytest.fail("deferred network routes command contacted CDP")

    cdp.set_transport_factory(reject_browser)
    try:
        yield cache, cache.read_bytes() if cache.exists() else None
    finally:
        cdp.set_transport_factory(None)
