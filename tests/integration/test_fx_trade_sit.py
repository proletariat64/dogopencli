"""Public FX CLI through real shared inquiry/transport and synthetic CDP."""

import json
from decimal import Decimal

import pytest
from fake_cdp import SSO_URL, FakeBrowser

from dogopencli.browser import cdp
from dogopencli.browser.environment import FX_STARTUP_URL
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical
from dogopencli.plugins.fx import query
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
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    cdp.set_transport_factory(state.transport)
    yield state
    cdp.set_transport_factory(None)
    assert all(len(t.closed) == len(t.created) for t in state.transports)
    assert not list(tmp_path.rglob("*.sqlite3"))


def test_fx_scope_wire_precision_and_projection(run_cli, fx_browser, envelope):
    fx_browser.business_script.append(
        page(
            [
                {
                    "uniqueId": "SYNTHETIC-TRADE",
                    "amount": Decimal("0.1234567890123456789"),
                    "futureField": {"keep": True},
                }
            ]
        )
    )
    code, out, err = run_cli(["fx", "trade", *SCOPE, "--fields", "amount,futureField"])
    value = envelope(out)
    assert code == 0 and value["error"] is None
    assert value["data"] == [
        {"amount": Decimal("0.1234567890123456789"), "futureField": {"keep": True}}
    ]
    assert value["meta"]["reported_total"] == 1
    assert value["meta"]["complete"] is False
    assert value["meta"]["coverage_ratio"] is None
    assert "INCOMPLETE_RESULT" in err
    request = fx_browser.business_requests[0]
    assert request["queryRequest"] == {
        "p5Bcodes": ["SYNTHETIC-BCODE"],
        "quoteOperationScene": "A+前报价",
        "quoteSymbolList": ["USD/PHP"],
        "transactionTypeList": ["SALE"],
        "p5TimeOverDue": 1,
        "transactTimeRange": {"start": 1790956800000, "end": 1791043199999},
    }
    assert request["pageNo"] == 0
    assert all(
        url == FX_STARTUP_URL for t in fx_browser.transports for url in t.created
    )
    expression = next(
        expr
        for t in fx_browser.transports
        for expr in t.expressions
        if "fetch(" in expr
    )
    assert "body: JSON.stringify([payload])" in expression


def test_zero_based_acquisition_precedes_display_window(run_cli, fx_browser, envelope):
    fx_browser.business_script.extend(
        [
            page([{"uniqueId": f"SYNTHETIC-{n}"} for n in range(50)], total=52),
            page(
                [{"uniqueId": "SYNTHETIC-50"}, {"uniqueId": "SYNTHETIC-51"}],
                number=1,
                total=52,
            ),
        ]
    )
    code, out, _ = run_cli(["fx", "trade", *SCOPE, "--offset", "49", "--limit", "2"])
    value = envelope(out)
    assert code == 0
    assert value["data"] == [{"uniqueId": "SYNTHETIC-49"}, {"uniqueId": "SYNTHETIC-50"}]
    assert value["meta"]["collected_total"] == 52
    assert value["meta"]["has_more"] is True
    assert [r["pageNo"] for r in fx_browser.business_requests] == [0, 1]


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--bcode", "B"],
        ["--trade-id", ""],
        ["--transact-from", "2026-10-03"],
        ["--transact-from", "2026-10-04", "--transact-to", "2026-10-03"],
        ["--transact-from", "2026-02-30", "--transact-to", "2026-10-03"],
        ["--transact-from", "2026-10-03T00:00:00", "--transact-to", "2026-10-03"],
        [*SCOPE, "--all", "--limit", "1"],
        [*SCOPE, "--limit", "0"],
        [*SCOPE, "--offset", "-1"],
        [*SCOPE, "--fields", " , "],
    ],
)
def test_invalid_scope_has_no_browser_effect(run_cli, fx_browser, envelope, extra):
    code, out, _ = run_cli(["fx", "trade", *extra])
    assert code == 2 and envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert fx_browser.transports == []


def test_exact_trade_id_without_date_is_allowed(run_cli, fx_browser):
    fx_browser.business_script.append(page([{"uniqueId": "SYNTHETIC-ID"}]))
    assert run_cli(["fx", "trade", "--trade-id", "SYNTHETIC-ID"])[0] == 0
    assert fx_browser.business_requests[0]["queryRequest"] == {
        "uniqueIds": ["SYNTHETIC-ID"]
    }


def test_strict_withholds_unproven_candidate(run_cli, fx_browser, envelope):
    fx_browser.business_script.append(page([{"uniqueId": "SYNTHETIC-ID"}]))
    code, out, _ = run_cli(["fx", "trade", *SCOPE, "--require-complete"])
    value = envelope(out)
    assert code == 1 and value["data"] is None
    assert value["error"]["code"] == "INCOMPLETE_RESULT"


@pytest.mark.parametrize(
    "fault", ["business", "outer", "http", "echo", "total", "network"]
)
def test_hard_failure_withholds_all_rows(run_cli, fx_browser, envelope, fault):
    first = page([{"uniqueId": f"SYNTHETIC-{n}"} for n in range(50)], total=51)
    second = page([{"uniqueId": "SYNTHETIC-50"}], number=1, total=51)
    if fault == "business":
        second["body"]["result"] = {
            "success": False,
            "fvCode": "IPAY_RS_520000500",
            "fvMessage": "SECRET SQL token=secret",
        }
    elif fault == "outer":
        second["body"]["success"] = False
    elif fault == "http":
        second["status"] = 503
    elif fault == "echo":
        second["body"]["result"]["value"]["currentPage"] = 0
    elif fault == "total":
        second["body"]["result"]["value"]["totalCount"] = 52
    else:
        second = {"error": "SECRET network response"}
    fx_browser.business_script.extend([first, second])
    code, out, err = run_cli(["fx", "trade", *SCOPE])
    assert code == 1 and envelope(out)["data"] is None
    assert "SECRET" not in out + err


def test_expired_fx_does_not_query_or_launch(run_cli, fx_browser, envelope):
    fx_browser.href = SSO_URL
    code, out, _ = run_cli(["fx", "trade", *SCOPE])
    assert code == 1 and envelope(out)["error"]["code"] == "AUTH_REQUIRED"
    assert "login --domain fx" in envelope(out)["error"]["message"]
    assert not fx_browser.business_requests and not fx_browser.launches


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


def test_fx_discovery_is_offline_and_cache_inapplicable(run_cli, monkeypatch):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", "/does-not-exist/config.toml")
    for argv in (
        ["fx", "--help"],
        ["help", "fx", "trade"],
        ["describe", "fx", "trade"],
    ):
        code, out, err = run_cli(argv)
        assert code == 0 and json.loads(out) and not err
    code, out, err = run_cli(["snapshot", "fx", "--format", "json"])
    assert code == 0 and not err
    assert json.loads(out)["tree"]["children"][0]["cache"]["status"] == "not_applicable"


def test_http_auth_error_has_one_fx_selector(run_cli, fx_browser, envelope):
    fx_browser.business_script.append({"status": 401, "body": {}})
    code, out, _ = run_cli(["fx", "trade", *SCOPE])
    assert code == 1
    message = envelope(out)["error"]["message"]
    assert "login --domain fx;" in message
    assert "login --domain fx --domain fx" not in message


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


def test_partial_short_page_and_page_budget(run_cli, fx_browser, envelope, monkeypatch):
    fx_browser.business_script.append(page([{"uniqueId": "SYNTHETIC-ID"}], total=2))
    code, out, _ = run_cli(["fx", "trade", *SCOPE])
    assert (
        code == 0
        and "COUNT_SHORTFALL" in envelope(out)["meta"]["acquisition"]["reasons"]
    )
    monkeypatch.setattr(query, "MAX_PAGES", 1)
    fx_browser.business_script.append(
        page([{"uniqueId": str(n)} for n in range(50)], total=51)
    )
    code, out, _ = run_cli(["fx", "trade", *SCOPE])
    assert (
        code == 0
        and "PAGE_BUDGET_EXHAUSTED" in envelope(out)["meta"]["acquisition"]["reasons"]
    )
