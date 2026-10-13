"""Returns count deficits publish usable rows with durable quality evidence."""

from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ENTRY = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"


@pytest.fixture
def returns_source(tmp_path: Path, monkeypatch):
    cache = tmp_path / "cache.sqlite3"
    config = tmp_path / "config.toml"
    config.write_text(
        f'[cache]\npath = "{cache}"\n'
        f'[auth]\nprofile = "{tmp_path / "profile"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
        '[sources.liquidity]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    browser = FakeBrowser(href=ENTRY)
    cdp.set_transport_factory(browser.transport)
    yield browser, cache
    cdp.set_transport_factory(None)


@pytest.mark.parametrize("basis", ["accrual", "cash"])
def test_returns_partial_contract_publishes_truthful_offline_capture(
    returns_source, run_cli, basis
):
    browser, cache = returns_source
    scope = ["--basis", basis, "--from-date", "20261001", "--to-date", "20261001"]
    query = ["liquidity", "investment", "returns", "list", *scope]
    refresh = ["refresh", "liquidity", "investment", "returns", *scope]
    records = [
        {
            "transactionId": f"T{i}",
            "investmentNo": f"I{i}",
            "transactionDate": "20261001",
            "settlementDate": "20261001",
            "currency": "USD",
        }
        for i in range(2)
    ]
    total = 2
    requests = []

    def answer(payload, index):
        requests.append(payload)
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": {"data": records, "totalCount": total, "pageSize": 0},
            },
        }

    browser.business_handler = answer
    code, out, err = run_cli(refresh)
    assert code == 0, err
    assert parse(out)["data"]["published"] is True
    before = cache.read_bytes()
    total = 3

    code, out, err = run_cli([*query, "--live", "--limit", "0"])
    assert code == 0
    result = parse(out)
    assert result["data"] == records
    assert result["error"] is None
    assert result["meta"]["complete"] is False
    assert result["meta"]["reported_total"] == 3
    assert result["meta"]["collected_total"] == 2
    assert result["meta"]["warnings"][0]["code"] == "INCOMPLETE_RESULT"
    assert "warning: INCOMPLETE_RESULT" in err
    assert cache.read_bytes() == before

    code, out, _ = run_cli([*query, "--live", "--limit", "0", "--require-complete"])
    assert code == 1
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"

    code, out, _ = run_cli(refresh)
    assert code == 0
    result = parse(out)
    assert result["data"]["published"] is True
    assert result["meta"]["published"] is True
    assert result["meta"]["complete"] is False
    assert result["meta"]["reported_total"] == 3
    assert result["meta"]["collected_total"] == 2
    assert cache.read_bytes() != before
    before = cache.read_bytes()
    assert all(r["rowStart"] == 0 and r["pageSize"] == 5000 for r in requests)

    def disconnected(*args, **kwargs):
        pytest.fail("offline returns query contacted the browser")

    cdp.set_transport_factory(disconnected)
    code, out, _ = run_cli([*query, "--limit", "0"])
    assert code == 0
    assert parse(out)["data"] == records
    assert parse(out)["meta"]["complete"] is False
    assert cache.read_bytes() == before
