"""Holdings query dates scope snapshots without filtering native row dates."""

from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp


@pytest.fixture
def source(tmp_path: Path, monkeypatch):
    cache = tmp_path / "cache.sqlite3"
    config = tmp_path / "config.toml"
    config.write_text(
        f'[cache]\npath = "{cache}"\n'
        f'[auth]\nprofile = "{tmp_path / "profile"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
        '[sources.liquidity]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    browser = FakeBrowser(
        href="https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    )
    cdp.set_transport_factory(browser.transport)
    yield browser, cache
    cdp.set_transport_factory(None)


def mixed_rows():
    return [
        {"investmentNo": "H1", "valueDate": "20220815", "amount": "10.00"},
        {"investmentNo": "H2", "valueDate": "20260930", "amount": "20.00"},
        {"investmentNo": "H3", "valueDate": "20261001", "amount": "30.00"},
    ]


def query(day=None):
    return [
        "liquidity",
        "investment",
        "holdings",
        "list",
        *(["--date", day] if day else []),
        "--limit",
        "0",
    ]


def refresh(day="20261001"):
    return ["refresh", "liquidity", "investment", "holdings", "--date", day]


def install(browser, rows):
    def answer(payload, index):
        assert payload["pageSize"] == 500
        assert payload["date"] in ("20261001", "20260930")
        return {
            "status": 200,
            "body": {"success": True, "data": {"data": rows, "totalCount": len(rows)}},
        }

    browser.business_handler = answer
