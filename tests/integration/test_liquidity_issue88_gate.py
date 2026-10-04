"""Batch B's first-release gates through the public, disconnected CLI."""

from pathlib import Path

import pytest

from dogopencli.browser import cdp
from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.jsonutil import parse

TARGETS = (
    (("risk", "events"), "runtimes", "riskMode=RISK_EVENT"),
    (("risk", "anomalies"), "runtimes", "riskMode=RISK_ALERT"),
    (("rules", "monitoring"), "settings", "monitoring rule-type filter"),
)


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
        pytest.fail("unreleased batch B command contacted CDP")

    cdp.set_transport_factory(reject_browser)
    try:
        yield cache, cache.read_bytes() if cache.exists() else None
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize("path,kind,scope_evidence", TARGETS)
@pytest.mark.parametrize("command", ["help", "describe"])
def test_batch_b_discovery_explains_each_native_scope_and_release_blocker(
    disconnected, run_cli, path, kind, scope_evidence, command
):
    cache, before = disconnected
    code, out, err = run_cli([command, "liquidity", *path, "list"])
    assert code == 0, err
    document = parse(out)
    if command == "help":
        assert document["kind"] == kind
        assert document["errors"] == ["UNSUPPORTED_CAPABILITY"]
        assert document["options"] == []
        assert document["effects"]["network"] is False
        assert document["effects"]["browser_required"] is False
        reason = document["summary"]
    else:
        guide = document["read_guide"]
        assert guide["kind"] == kind
        assert guide["release_status"] == "deferred"
        assert guide["evidence_status"] == "empty-scope"
        assert guide["options"] == []
        assert not document["data_schema"].get("properties")
        reason = guide["reason"]
    assert scope_evidence in reason
    for blocker in ("nonempty", "identity", "complete acquisition", "production UAT"):
        assert blocker in reason
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize("path,kind,scope_evidence", TARGETS)
@pytest.mark.parametrize("mode", ["cached", "live", "strict", "refresh"])
def test_batch_b_queries_refuse_without_browser_or_cache_access(
    disconnected, run_cli, path, kind, scope_evidence, mode
):
    cache, before = disconnected
    args = ["liquidity", *path, "list"]
    if mode == "live":
        args.append("--live")
    elif mode == "strict":
        args.append("--require-complete")
    elif mode == "refresh":
        args = ["refresh", "liquidity", *path]
    code, out, _ = run_cli(args)
    envelope = parse(out)
    assert code == (1 if mode == "cached" else 2)
    assert envelope["data"] is None
    assert envelope["error"]["code"] == (
        "UNSUPPORTED_CAPABILITY" if mode == "cached" else "INVALID_ARGUMENT"
    )
    assert envelope["error"]["retryable"] is False
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize("path,kind,scope_evidence", TARGETS)
@pytest.mark.parametrize("action", ["get", "history"])
def test_batch_b_lists_cannot_release_detail_or_history(
    disconnected, run_cli, path, kind, scope_evidence, action
):
    cache, before = disconnected
    code, out, _ = run_cli(["liquidity", *path, action])
    envelope = parse(out)
    assert code == (1 if action == "get" else 2)
    assert envelope["data"] is None
    assert envelope["error"]["code"] == (
        "UNSUPPORTED_CAPABILITY" if action == "get" else "INVALID_ARGUMENT"
    )
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize("disconnected", ["missing"], indirect=True)
def test_batch_b_snapshot_reports_zero_enabled_targets(disconnected, run_cli):
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
        "dogopencli liquidity risk events list",
        "dogopencli liquidity risk anomalies list",
        "dogopencli liquidity rules monitoring list",
    }
    found = [node for node in leaves(document["tree"]) if node["command"] in targets]
    assert len(found) == 3
    assert all(node["availability"] == "unsupported" for node in found)
    assert all(node["cache"]["status"] == "not_applicable" for node in found)
    assert all("production UAT" in node["availability_reason"] for node in found)
    assert (cache.read_bytes() if cache.exists() else None) == before
