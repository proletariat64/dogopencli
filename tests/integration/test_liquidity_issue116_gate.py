"""Batch F issue #116: wallet leaves stay deferred with their named blockers."""

from pathlib import Path

import pytest

from dogopencli.browser import cdp
from dogopencli.cache import Cache, SnapshotMeta

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
