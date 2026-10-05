"""Issue #117 rule-status stays deferred behind its named Batch F blocker."""

from pathlib import Path

import pytest

from dogopencli.browser import cdp
from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.jsonutil import parse

PATH = ("operations", "rule-status")
COMMAND = "dogopencli liquidity operations rule-status list"
BLOCKER_PHRASES = (
    "no independent runtime-list caller",
    "configuration RUN/PAUSE is not one execution",
    "not renamed as rule status",
)


@pytest.fixture
def disconnected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache = tmp_path / "cache.sqlite3"
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
    config = tmp_path / "config.toml"
    config.write_text(
        f'[cache]\npath = "{cache}"\n'
        f'[auth]\nprofile = "{tmp_path / "profile"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
        '[sources.liquidity]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))

    def reject_browser(*args, **kwargs):
        pytest.fail("deferred rule-status command contacted CDP")

    cdp.set_transport_factory(reject_browser)
    try:
        yield cache, cache.read_bytes()
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize("command", ["help", "describe"])
def test_rule_status_discovery_exposes_named_batch_f_blocker(
    disconnected, run_cli, command
):
    cache, before = disconnected
    code, out, err = run_cli([command, "liquidity", *PATH, "list"])
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
        assert guide["evidence_status"] == "unverified"
        assert guide["options"] == []
        assert not document["data_schema"].get("properties")
        reason = guide["reason"]
    for phrase in BLOCKER_PHRASES:
        assert phrase in reason
    assert cache.read_bytes() == before


def test_rule_status_list_refuses_offline_without_cache_mutation(disconnected, run_cli):
    cache, before = disconnected
    code, out, _ = run_cli(["liquidity", *PATH, "list"])
    envelope = parse(out)
    assert code == 1
    assert envelope["data"] is None
    assert envelope["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert envelope["error"]["retryable"] is False
    message = envelope["error"]["message"]
    assert message.startswith("liquidity operations rule-status list is deferred: ")
    for phrase in BLOCKER_PHRASES:
        assert phrase in message
    assert cache.read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        ["liquidity", "operations", "rule-status", "list", "--live"],
        ["liquidity", "operations", "rule-status", "list", "--require-complete"],
        ["refresh", "liquidity", "operations", "rule-status"],
    ],
)
def test_rule_status_live_strict_and_refresh_cannot_execute(
    disconnected, run_cli, args
):
    cache, before = disconnected
    code, out, _ = run_cli(args)
    envelope = parse(out)
    assert code == 2
    assert envelope["data"] is None
    assert envelope["error"]["code"] == "INVALID_ARGUMENT"
    assert envelope["error"]["retryable"] is False
    assert cache.read_bytes() == before


def test_rule_status_snapshot_reports_named_deferred_blocker(disconnected, run_cli):
    cache, before = disconnected
    code, out, err = run_cli(["snapshot", "liquidity", "--format", "json"])
    assert code == 0, err
    document = parse(out)

    def leaves(node):
        if "availability" in node:
            yield node
        for child in node["children"]:
            yield from leaves(child)

    node = next(leaf for leaf in leaves(document["tree"]) if leaf["command"] == COMMAND)
    assert node["availability"] == "unsupported"
    assert node["cache"]["status"] == "not_applicable"
    for phrase in BLOCKER_PHRASES:
        assert phrase in node["availability_reason"]
    assert cache.read_bytes() == before
