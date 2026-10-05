"""Batch F (#118) investment leaves stay deferred through the public CLI."""

from pathlib import Path

import pytest

from dogopencli.browser import cdp
from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.jsonutil import parse

TARGETS = (
    (
        ("investment", "offers"),
        "unverified",
        (
            "#118",
            "ProductPoolView",
            "RFQMgmt",
            "QuotationGroupMgmt",
            "must not be renamed",
        ),
    ),
    (
        ("investment", "quote-sessions"),
        "unverified",
        (
            "#118",
            "session granularity",
            "identity",
            "must not be renamed",
        ),
    ),
    (
        ("investment", "investable-funds"),
        "empty-scope",
        (
            "#118",
            "queryInvestableFundList.json",
            "28",
            "totalCount=0",
            "positive sample",
            "identity",
            "production UAT",
        ),
    ),
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
                fetched_at="2026-10-06T00:00:00Z",
                loaded_at="2026-10-06T00:00:00Z",
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
        pytest.fail("deferred batch F3 command contacted CDP")

    cdp.set_transport_factory(reject_browser)
    try:
        yield cache, cache.read_bytes() if cache.exists() else None
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize("path,status,blockers", TARGETS)
@pytest.mark.parametrize("command", ["help", "describe"])
def test_batch_f3_discovery_explains_each_named_blocker(
    disconnected, run_cli, path, status, blockers, command
):
    cache, before = disconnected
    code, out, err = run_cli([command, "liquidity", *path, "list"])
    assert code == 0, err
    document = parse(out)
    if command == "help":
        assert document["kind"] == "runtimes"
        assert document["errors"] == ["UNSUPPORTED_CAPABILITY"]
        assert document["options"] == []
        assert document["effects"]["network"] is False
        assert document["effects"]["browser_required"] is False
        reason = document["summary"]
    else:
        guide = document["read_guide"]
        assert guide["kind"] == "runtimes"
        assert guide["release_status"] == "deferred"
        assert guide["evidence_status"] == status
        assert guide["options"] == []
        assert not document["data_schema"].get("properties")
        reason = guide["reason"]
    for blocker in blockers:
        assert blocker in reason
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize("path,status,blockers", TARGETS)
@pytest.mark.parametrize("mode", ["cached", "live", "strict", "refresh"])
def test_batch_f3_queries_refuse_without_browser_or_cache_access(
    disconnected, run_cli, path, status, blockers, mode
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
    if mode == "cached":
        message = envelope["error"]["message"]
        prefix = f"liquidity {' '.join(path)} list is deferred: "
        assert message.startswith(prefix)
        for blocker in blockers:
            assert blocker in message
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize("path,status,blockers", TARGETS)
def test_batch_f3_get_remains_unavailable(
    disconnected, run_cli, path, status, blockers
):
    cache, before = disconnected
    code, out, _ = run_cli(["liquidity", *path, "get"])
    envelope = parse(out)
    assert code == 2
    assert envelope["data"] is None
    assert envelope["error"]["code"] == "INVALID_ARGUMENT"
    assert envelope["error"]["retryable"] is False
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize("disconnected", ["missing"], indirect=True)
def test_batch_f3_snapshot_reports_all_three_leaves_as_unsupported(
    disconnected, run_cli
):
    cache, before = disconnected
    code, out, err = run_cli(["snapshot", "liquidity", "--format", "json"])
    assert code == 0, err
    document = parse(out)

    def leaves(node):
        if "availability" in node:
            yield node
        for child in node["children"]:
            yield from leaves(child)

    by_blockers = {blockers: path for path, _, blockers in TARGETS}
    found = [
        node
        for node in leaves(document["tree"])
        if node["command"].startswith("dogopencli liquidity investment ")
        and node["command"].endswith(" list")
        and any(
            node["command"] == f"dogopencli liquidity {' '.join(path)} list"
            for path in by_blockers.values()
        )
    ]
    assert len(found) == 3
    for node in found:
        assert node["availability"] == "unsupported"
        assert node["cache"]["status"] == "not_applicable"
        blockers = next(
            terms
            for terms, path in by_blockers.items()
            if node["command"] == f"dogopencli liquidity {' '.join(path)} list"
        )
        for blocker in blockers:
            assert blocker in node["availability_reason"]
    assert (cache.read_bytes() if cache.exists() else None) == before
