"""Public FX CLI through real shared inquiry/transport and synthetic CDP."""

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.browser.environment import FX_STARTUP_URL
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical
from dogopencli.plugins.fx.trade import FX_TRADE
from dogopencli.transport import QueryRequest, validate_request
from dogopencli.transport.cdp import _fetch_expression

SCOPE = [
    "--transact-from",
    "2026-10-03",
    "--transact-to",
    "2026-10-03",
    "--bcode",
    "SYNTHETIC-BCODE",
    "--scene",
    "A+前报价",
    "--transaction-type",
    "SALE",
    "--fulfilled",
    "1",
    "--symbol",
    "USD/PHP",
]


def page(rows, number=0, total=None, **extra):
    return {
        "status": 200,
        "body": {
            "success": True,
            "result": {
                "success": True,
                "fvCode": None,
                "value": {
                    "items": rows,
                    "totalCount": len(rows) if total is None else total,
                    "currentPage": number,
                    "pageSize": 50,
                    **extra,
                },
            },
        },
    }


@pytest.fixture
def fx_browser(tmp_path, monkeypatch):
    state = FakeBrowser(href=FX_STARTUP_URL)
    profile = tmp_path / "profile"
    config = tmp_path / "config.toml"
    config.write_text(
        f'[auth]\nprofile = "{profile}"\ncdp_url = "http://127.0.0.1:9222"\n'
        f'[cache]\npath = "{tmp_path / "query.sqlite3"}"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    cdp.set_transport_factory(state.transport)
    yield state
    cdp.set_transport_factory(None)
    assert all(len(t.closed) == len(t.created) for t in state.transports)
    if not getattr(state, "allows_cache", False):
        # Execution observations are separate from the business query cache.
        assert not (tmp_path / "query.sqlite3").exists()


@pytest.mark.parametrize(
    "body",
    [
        {"queryRequest": {"save": True}},
        {"queryRequest": []},
        {"queryRequest": {}, "delete": True},
    ],
)
def test_nested_allowlist_rejects_unregistered_request(body):
    c = FX_TRADE.contract
    request = QueryRequest(FX_TRADE.name, c.method, c.host, c.path, body)
    with pytest.raises(CliError, match="unregistered|not registered"):
        validate_request(request, c)


def test_json_array_does_not_change_existing_json_encoding():
    c = FX_TRADE.contract
    request = QueryRequest(
        FX_TRADE.name, c.method, c.host, c.path, {"queryRequest": {}}
    )
    assert "JSON.stringify(payload)" in _fetch_expression(request, 1)
    assert "JSON.stringify([payload])" in _fetch_expression(
        request, 1, encoding="json-array"
    )


@pytest.mark.parametrize(
    "value",
    [
        {"totalCount": True},
        {"currentPage": -1},
        {"pageSize": 0},
        {"items": [None]},
    ],
)
def test_invalid_response_shape(value):
    document = page([])["body"]
    document["result"]["value"].update(value)
    with pytest.raises(CliError):
        FX_TRADE.parse_page(canonical(document).encode())
