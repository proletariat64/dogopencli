"""Batch F F4 (#119): network routes stays deferred through the public CLI."""

from pathlib import Path

import pytest

from dogopencli.browser import cdp
from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.jsonutil import parse

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


@pytest.mark.parametrize("command", ["help", "describe"])
def test_batch_f4_discovery_explains_the_named_routes_blocker(
    disconnected, run_cli, command
):
    cache, before = disconnected
    code, out, err = run_cli([command, *LIST_PATH])
    assert code == 0, err
    document = parse(out)
    if command == "help":
        assert document["kind"] == "settings"
        assert document["errors"] == ["UNSUPPORTED_CAPABILITY"]
        assert document["options"] == []
        assert document["effects"]["network"] is False
        assert document["effects"]["browser_required"] is False
        reason = document["summary"]
    else:
        guide = document["read_guide"]
        assert guide["kind"] == "settings"
        assert guide["release_status"] == "deferred"
        assert guide["evidence_status"] == "unverified"
        assert guide["options"] == []
        assert not document["data_schema"].get("properties")
        reason = guide["reason"]
    for fragment in LIST_BLOCKER:
        assert fragment in reason
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize("mode", ["cached", "live", "strict", "refresh"])
def test_batch_f4_routes_queries_refuse_without_browser_or_cache_access(
    disconnected, run_cli, mode
):
    cache, before = disconnected
    args = list(LIST_PATH)
    if mode == "live":
        args.append("--live")
    elif mode == "strict":
        args.append("--require-complete")
    elif mode == "refresh":
        args = ["refresh", *LIST_PATH[:-1]]
    code, out, _ = run_cli(args)
    envelope = parse(out)
    assert code == (1 if mode == "cached" else 2)
    assert envelope["data"] is None
    assert envelope["error"]["code"] == (
        "UNSUPPORTED_CAPABILITY" if mode == "cached" else "INVALID_ARGUMENT"
    )
    assert envelope["error"]["retryable"] is False
    if mode == "cached":
        message = envelope["error"]["message"]
        assert message.startswith("liquidity network routes list is deferred: ")
        for fragment in LIST_BLOCKER:
            assert fragment in message
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize(
    "action,code,error",
    [("get", 1, "UNSUPPORTED_CAPABILITY"), ("history", 2, "INVALID_ARGUMENT")],
)
def test_batch_f4_route_detail_and_history_refuse(
    disconnected, run_cli, action, code, error
):
    cache, before = disconnected
    exit_code, out, _ = run_cli(["liquidity", "network", "routes", action])
    envelope = parse(out)
    assert exit_code == code
    assert envelope["data"] is None
    assert envelope["error"]["code"] == error
    assert envelope["error"]["retryable"] is False
    if action == "get":
        message = envelope["error"]["message"]
        assert message.startswith("liquidity network routes get is deferred: ")
        for fragment in GET_BLOCKER:
            assert fragment in message
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize("disconnected", ["missing"], indirect=True)
def test_batch_f4_snapshot_reports_the_routes_blocker(disconnected, run_cli):
    cache, before = disconnected
    code, out, err = run_cli(["snapshot", "liquidity", "--format", "json"])
    assert code == 0, err
    document = parse(out)

    def leaves(node):
        if "availability" in node:
            yield node
        for child in node["children"]:
            yield from leaves(child)

    targets = {
        "dogopencli liquidity network routes list",
        "dogopencli liquidity network routes get",
    }
    found = [node for node in leaves(document["tree"]) if node["command"] in targets]
    assert len(found) == 2
    for node in found:
        assert node["availability"] == "unsupported"
        assert node["cache"]["status"] == "not_applicable"
    routes_list = next(node for node in found if node["command"].endswith("list"))
    routes_get = next(node for node in found if node["command"].endswith("get"))
    for fragment in LIST_BLOCKER:
        assert fragment in routes_list["availability_reason"]
    for fragment in GET_BLOCKER:
        assert fragment in routes_get["availability_reason"]
    assert (cache.read_bytes() if cache.exists() else None) == before
