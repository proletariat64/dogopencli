"""Decision history keeps native versions and verifies their source lineage."""

from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp

LIQUIDITY_URL = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
QUERY = ["liquidity", "operations", "decisions", "history", "--id", "7"]


@pytest.fixture
def history_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[cache]\n"
        f'path = "{tmp_path / "cache.sqlite3"}"\n'
        "ttl_hours = 72\n"
        "[auth]\n"
        f'profile = "{tmp_path / "chrome-profile"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
        "[sources.liquidity]\n"
        'kind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config_path))
    state = FakeBrowser(href=LIQUIDITY_URL)
    cdp.set_transport_factory(state.transport)
    yield state
    cdp.set_transport_factory(None)
    assert not (tmp_path / "cache.sqlite3").exists()


def parent():
    return {
        "id": 7,
        "reportId": "report-a",
        "groupId": "group-a",
        "tntInstId": "GUAPW3SG",
    }


def versions():
    return [dict(parent(), id=6, version=2), dict(parent(), id=5, version=1)]


def script(state, rows, current=None):
    from collections import deque

    state.business_script = deque(
        {"status": 200, "body": {"success": True, "data": data}}
        for data in (parent() if current is None else current, rows)
    )
