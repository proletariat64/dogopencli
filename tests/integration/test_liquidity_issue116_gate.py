"""Batch F issue #116: wallet leaves stay deferred with their named blockers."""

from pathlib import Path

import pytest

from dogopencli.browser import cdp
from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.jsonutil import parse

WALLETS_REASON = (
    "Wallets: wallet=true/false returned identical ordered account rows at"
    " pageSize 1000/5000; wallet membership is not established."
)
WALLET_GET_REASON = "Wallet detail: wallet membership is not established."
WALLET_BALANCES_REASON = (
    "Wallet balances: no verified independent native wallet-balance caller"
    " bound to wallet membership; normal-account balances are not renamed."
)
LIST_TARGETS = (
    (("cash", "wallets"), "reference", "filter-unverified", WALLETS_REASON),
    (("cash", "wallet-balances"), "runtimes", "unverified", WALLET_BALANCES_REASON),
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
        pytest.fail("deferred issue #116 wallet command contacted CDP")

    cdp.set_transport_factory(reject_browser)
    try:
        yield cache, cache.read_bytes() if cache.exists() else None
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize("path,kind,status,reason", LIST_TARGETS)
@pytest.mark.parametrize("command", ["help", "describe"])
def test_batch_f1_wallet_discovery_explains_each_named_blocker(
    disconnected, run_cli, path, kind, status, reason, command
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
        assert document["summary"] == "Disabled inquiry."
    else:
        guide = document["read_guide"]
        assert guide["kind"] == kind
        assert guide["release_status"] == "deferred"
        assert guide["evidence_status"] == status
        assert not document["data_schema"].get("properties")
        assert guide["reason"] == reason
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize("path,kind,status,reason", LIST_TARGETS)
def test_batch_f1_wallet_lists_refuse_cached_without_touching_cache(
    disconnected, run_cli, path, kind, status, reason
):
    cache, before = disconnected
    code, out, _ = run_cli(["liquidity", *path, "list"])
    envelope = parse(out)
    assert code == 1
    assert envelope["data"] is None
    assert envelope["error"]["code"] == "LEAF_DISABLED"
    assert envelope["error"]["message"].startswith("Leaf is disabled:")
    assert envelope["error"]["retryable"] is False
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize("path,kind,status,reason", LIST_TARGETS)
@pytest.mark.parametrize("mode", ["live", "strict", "refresh"])
def test_batch_f1_wallet_live_strict_and_refresh_cannot_execute(
    disconnected, run_cli, path, kind, status, reason, mode
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
    assert code == 2
    assert envelope["data"] is None
    assert envelope["error"]["code"] == "INVALID_ARGUMENT"
    assert envelope["error"]["retryable"] is False
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize(
    "extra,exit_code,error_code",
    [
        ([], 1, "LEAF_DISABLED"),
        (["--live"], 2, "INVALID_ARGUMENT"),
    ],
)
def test_batch_f1_wallet_get_refuses_without_touching_cache(
    disconnected, run_cli, extra, exit_code, error_code
):
    cache, before = disconnected
    code, out, _ = run_cli(["liquidity", "cash", "wallets", "get", *extra])
    envelope = parse(out)
    assert code == exit_code
    assert envelope["data"] is None
    assert envelope["error"]["code"] == error_code
    if error_code == "LEAF_DISABLED":
        assert envelope["error"]["message"].startswith("Leaf is disabled:")
    assert envelope["error"]["retryable"] is False
    assert (cache.read_bytes() if cache.exists() else None) == before


@pytest.mark.parametrize("disconnected", ["sqlite", "missing"], indirect=True)
def test_batch_f1_wallet_snapshot_marks_all_leaves_unsupported(disconnected, run_cli):
    cache, before = disconnected
    code, out, err = run_cli(["snapshot", "liquidity", "--format", "json"])
    assert code == 0, err
    document = parse(out)

    def leaves(node):
        if "availability" in node:
            yield node
        for child in node["children"]:
            yield from leaves(child)

    expected = {
        "dogopencli liquidity cash wallets list": WALLETS_REASON,
        "dogopencli liquidity cash wallets get": WALLET_GET_REASON,
        "dogopencli liquidity cash wallet-balances list": WALLET_BALANCES_REASON,
    }
    found = [node for node in leaves(document["tree"]) if node["command"] in expected]
    assert len(found) == 3
    for node in found:
        assert node["availability"] == "unsupported"
        assert node["availability_reason"] == expected[node["command"]]
        assert node["cache"]["status"] == "not_applicable"
        assert node["rows"] is None
    assert (cache.read_bytes() if cache.exists() else None) == before
