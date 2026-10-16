"""Issue #82 release refusal stays offline until native evidence exists."""

from pathlib import Path

import pytest

from dogopencli.browser import cdp


@pytest.fixture
def disconnected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache = tmp_path / "cache.sqlite3"
    cache.write_bytes(b"previous capture must stay untouched")
    config = tmp_path / "config.toml"
    config.write_text(
        f'[cache]\npath = "{cache}"\n'
        f'[auth]\nprofile = "{tmp_path / "profile"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
        '[sources.liquidity]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))

    def reject_browser(*args, **kwargs):
        pytest.fail("deferred investable-funds command contacted CDP")

    cdp.set_transport_factory(reject_browser)
    yield cache, cache.read_bytes()
    cdp.set_transport_factory(None)
