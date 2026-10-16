"""Issue #89 discovery and refusal through the public CLI, without CDP."""

import sqlite3
from pathlib import Path

import pytest

from dogopencli.browser import cdp

TARGETS = [
    ("pricing", "valuations", ("fee-order", "semantics", "naming")),
    ("pricing", "bills", ("DEPOSIT", "currency", "period")),
]


@pytest.fixture
def disconnected_batch_c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache = tmp_path / "cache.sqlite3"
    with sqlite3.connect(cache) as connection:
        connection.execute("CREATE TABLE previous_capture (value TEXT)")
        connection.execute("INSERT INTO previous_capture VALUES ('preserve')")
    config = tmp_path / "config.toml"
    config.write_text(
        f'[cache]\npath = "{cache}"\n'
        f'[auth]\nprofile = "{tmp_path / "profile"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
        '[sources.liquidity]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))

    def reject_browser(*args, **kwargs):
        pytest.fail("unreleased batch C command contacted CDP")

    cdp.set_transport_factory(reject_browser)
    try:
        yield cache, cache.read_bytes()
    finally:
        cdp.set_transport_factory(None)
