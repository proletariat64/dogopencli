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
    code, out, err = run_cli(
        ["fx", "trade", "--live", *SCOPE, "--fields", "amount,futureField"]
    )
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
    code, out, _ = run_cli(
        ["fx", "trade", "--live", *SCOPE, "--offset", "49", "--limit", "2"]
    )
    value = envelope(out)
    assert code == 0
    assert value["data"] == [{"uniqueId": "SYNTHETIC-49"}, {"uniqueId": "SYNTHETIC-50"}]
    assert value["meta"]["collected_total"] == 52
    assert value["meta"]["has_more"] is True
    assert [r["pageNo"] for r in fx_browser.business_requests] == [0, 1]


@pytest.mark.parametrize(
    "extra",
    [
        ["--trade-id", ""],
        ["--trade-id", "ANY"],
        ["--scene", "ANY"],
        ["--transact-from", "2026-10-03"],
        ["--transact-from", "2026-10-04", "--transact-to", "2026-10-03"],
        ["--transact-from", "2026-02-30", "--transact-to", "2026-10-03"],
        ["--transact-from", "2026-10-03T00:00:00", "--transact-to", "2026-10-03"],
        [*SCOPE, "--all", "--limit", "1"],
        [*SCOPE, "--offset", "-1"],
        [*SCOPE, "--fields", " , "],
    ],
)
def test_invalid_scope_has_no_browser_effect(run_cli, fx_browser, envelope, extra):
    code, out, _ = run_cli(["fx", "trade", "--live", *extra])
    assert code == 2 and envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert fx_browser.transports == []


def test_exact_trade_id_without_date_is_allowed(run_cli, fx_browser):
    fx_browser.business_script.append(page([{"uniqueId": "SYNTHETIC-ID"}]))
    assert run_cli(["fx", "trade", "--live", "--trade-id", "SYNTHETIC-ID"])[0] == 0
    assert fx_browser.business_requests[0]["queryRequest"] == {
        "uniqueIds": ["SYNTHETIC-ID"]
    }


def test_strict_withholds_unproven_candidate(run_cli, fx_browser, envelope):
    fx_browser.business_script.append(page([{"uniqueId": "SYNTHETIC-ID"}]))
    code, out, _ = run_cli(["fx", "trade", "--live", *SCOPE, "--require-complete"])
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
    code, out, err = run_cli(["fx", "trade", "--live", *SCOPE])
    assert code == 1 and envelope(out)["data"] is None
    assert "SECRET" not in out + err


def test_expired_fx_does_not_query_or_launch(run_cli, fx_browser, envelope):
    fx_browser.href = SSO_URL
    code, out, _ = run_cli(["fx", "trade", "--live", *SCOPE])
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


def test_fx_discovery_is_offline_and_cache_supported(run_cli, monkeypatch):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", "/does-not-exist/config.toml")
    for argv in (
        ["fx", "--help"],
        ["help", "fx", "trade"],
        ["describe", "fx", "trade"],
    ):
        code, out, err = run_cli(argv)
        assert code == 0 and json.loads(out) and not err
    code, out, err = run_cli(["snapshot", "fx", "--format", "json"])
    assert code == 1
    assert json.loads(out)["inspection_errors"][0]["code"] == "CONFIG_ERROR"


def test_http_auth_error_has_one_fx_selector(run_cli, fx_browser, envelope):
    fx_browser.business_script.append({"status": 401, "body": {}})
    code, out, _ = run_cli(["fx", "trade", "--live", *SCOPE])
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
    code, out, _ = run_cli(["fx", "trade", "--live", *SCOPE])
    assert (
        code == 0
        and "COUNT_SHORTFALL" in envelope(out)["meta"]["acquisition"]["reasons"]
    )
    monkeypatch.setattr(query, "MAX_PAGES", 1)
    fx_browser.business_script.append(
        page([{"uniqueId": str(n)} for n in range(50)], total=51)
    )
    code, out, _ = run_cli(["fx", "trade", "--live", *SCOPE])
    assert (
        code == 0
        and "PAGE_BUDGET_EXHAUSTED" in envelope(out)["meta"]["acquisition"]["reasons"]
    )


@pytest.mark.parametrize(
    ("instant", "start", "end"),
    [
        ("2026-01-01T00:00:00+08:00", 1767110400000, 1767196799999),
        ("2024-03-01T00:00:00+08:00", 1709136000000, 1709222399999),
        ("2026-10-01T00:00:00+08:00", 1790697600000, 1790783999999),
    ],
)
def test_online_default_previous_complete_gmt8_day(
    run_cli, fx_browser, monkeypatch, instant, start, end
):
    from datetime import datetime

    from dogopencli.plugins.fx import trade

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(instant).astimezone(tz)

    monkeypatch.setattr(trade, "datetime", Clock)
    fx_browser.business_script.append(page([]))
    assert run_cli(["fx", "trade", "--live"])[0] == 0
    assert fx_browser.business_requests[0]["queryRequest"] == {
        "transactTimeRange": {"start": start, "end": end}
    }


def test_offline_fx_cache_miss_does_not_open_browser(run_cli, fx_browser, envelope):
    code, out, _ = run_cli(["fx", "trade"])
    assert code == 1 and envelope(out)["error"]["code"] == "CACHE_MISS"
    assert not fx_browser.transports


def test_fx_refresh_replay_prune_and_empty_preservation(run_cli, fx_browser, envelope):
    fx_browser.allows_cache = True
    fx_browser.business_script.append(page([{"uniqueId": "first", "extra": None}]))
    code, out, _ = run_cli(["refresh", "fx", "trade", "--trade-id", "first"])
    assert code == 0 and envelope(out)["meta"]["published"] is True
    count = len(fx_browser.business_requests)
    code, out, _ = run_cli(["fx", "trade", "--limit", "0"])
    cached = envelope(out)
    assert code == 0 and cached["data"] == [{"uniqueId": "first", "extra": None}]
    assert cached["meta"]["complete"] is False
    assert len(fx_browser.business_requests) == count
    fx_browser.business_script.append(page([]))
    code, out, _ = run_cli(["refresh", "fx", "trade", "--trade-id", "empty"])
    empty = envelope(out)
    assert code == 0 and empty["data"] == []
    assert empty["meta"]["published"] is False
    code, out, _ = run_cli(["fx", "trade"])
    assert code == 0 and envelope(out)["data"] == cached["data"]
    assert envelope(out)["meta"]["fetched_at"] == cached["meta"]["fetched_at"]
    for _ in range(2):
        assert run_cli(["fx", "trade", "prune"])[0] == 0
    code, out, _ = run_cli(["fx", "trade"])
    assert code == 1 and envelope(out)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize(
    "contender",
    [
        ["fx", "trade", "prune"],
        ["refresh", "fx", "trade", "--trade-id", "competing"],
    ],
)
def test_fx_refresh_blocks_competing_commands_during_fetch(
    run_cli, fx_browser, envelope, contender
):
    fx_browser.allows_cache = True
    fx_browser.business_handler = lambda payload, index: page([{"uniqueId": "saved"}])
    assert run_cli(["refresh", "fx", "trade", "--trade-id", "saved"])[0] == 0
    request_count = len(fx_browser.business_requests)
    observed = []

    def answer(payload, index):
        trade_id = payload["queryRequest"]["uniqueIds"][0]
        if trade_id == "outer":
            transport_count = len(fx_browser.transports)
            code, out, _ = run_cli(contender)
            observed.append((code, envelope(out)))
            assert len(fx_browser.transports) == transport_count
        return page([{"uniqueId": trade_id}])

    fx_browser.business_handler = answer
    code, out, _ = run_cli(["refresh", "fx", "trade", "--trade-id", "outer"])
    assert code == 0 and envelope(out)["meta"]["published"] is True
    assert len(observed) == 1
    assert observed[0][0] == 1
    assert observed[0][1]["error"]["code"] == "LOCKED"
    assert len(fx_browser.business_requests) == request_count + 1
    code, out, _ = run_cli(["fx", "trade"])
    assert code == 0 and envelope(out)["data"] == [{"uniqueId": "outer"}]
    assert run_cli(["fx", "trade", "prune"])[0] == 0
    assert run_cli(["fx", "trade"])[0] == 1


@pytest.mark.parametrize("refresh", [True, False])
def test_fx_locked_refresh_rejects_before_browser_but_live_proceeds(
    run_cli, fx_browser, envelope, refresh
):
    from dogopencli.cache import Cache

    store = Cache(query.config_mod.load([]).cache_path)
    fx_browser.business_script.append(page([]))
    args = ["refresh", "fx", "trade"] if refresh else ["fx", "trade", "--live"]
    with store.refresh_lock():
        code, out, _ = run_cli([*args, "--trade-id", "empty"])
    if refresh:
        assert code == 1 and envelope(out)["error"]["code"] == "LOCKED"
        assert not fx_browser.transports
        assert not fx_browser.business_requests
    else:
        assert code == 0 and envelope(out)["data"] == []
        assert len(fx_browser.business_requests) == 1


@pytest.mark.parametrize("offset", [0, 99])
def test_fx_cached_strict_rejects_incomplete_before_display(
    run_cli, fx_browser, envelope, offset
):
    fx_browser.allows_cache = True
    rows = [{"uniqueId": "saved"}]
    fx_browser.business_script.append(page(rows, total=2))
    assert run_cli(["refresh", "fx", "trade", "--trade-id", "saved"])[0] == 0
    request_count = len(fx_browser.business_requests)
    transport_count = len(fx_browser.transports)

    code, out, _ = run_cli(
        ["fx", "trade", "--require-complete", "--offset", str(offset)]
    )
    strict = envelope(out)
    assert code == 1
    assert strict["error"]["code"] == "INCOMPLETE_RESULT"
    assert strict["data"] is None

    code, out, err = run_cli(["fx", "trade"])
    cached = envelope(out)
    assert code == 0 and cached["data"] == rows
    assert cached["meta"]["complete"] is False
    assert "COUNT_SHORTFALL" in cached["meta"]["acquisition"]["reasons"]
    assert "INCOMPLETE_RESULT" in err
    assert len(fx_browser.business_requests) == request_count
    assert len(fx_browser.transports) == transport_count


def test_fx_refresh_keeps_full_rows_when_display_empty_and_replaces_scope(
    run_cli, fx_browser, envelope
):
    fx_browser.allows_cache = True
    rows = [{"uniqueId": f"row-{n}", "keep": None} for n in range(101)]
    fx_browser.business_script.extend(
        [
            page(rows[:50], total=101),
            page(rows[50:100], number=1, total=101),
            page(rows[100:], number=2, total=101),
        ]
    )
    code, out, _ = run_cli(
        [
            "refresh",
            "fx",
            "trade",
            *SCOPE,
            "--limit",
            "1",
            "--offset",
            "200",
            "--fields",
            "uniqueId",
        ]
    )
    value = envelope(out)
    assert code == 0 and value["data"] == []
    assert value["meta"]["published"] is True
    assert value["meta"]["collected_total"] == 101
    code, out, _ = run_cli(["fx", "trade"])
    assert code == 0 and envelope(out)["data"] == rows[:100]
    assert envelope(out)["meta"]["has_more"] is True
    code, out, _ = run_cli(["fx", "trade", "--limit", "0", "--offset", "99"])
    assert code == 0 and envelope(out)["data"] == rows[99:]
    fx_browser.business_script.append(page([{"uniqueId": "replacement"}]))
    assert run_cli(["refresh", "fx", "trade", "--trade-id", "replacement"])[0] == 0
    code, out, _ = run_cli(["fx", "trade", "--limit", "0"])
    assert code == 0 and envelope(out)["data"] == [{"uniqueId": "replacement"}]


@pytest.mark.parametrize("failure", ["strict", "hard", "live"])
def test_fx_nonpublication_preserves_original_quality_and_timestamp(
    run_cli, fx_browser, envelope, failure
):
    fx_browser.allows_cache = True
    fx_browser.business_script.append(page([{"uniqueId": "saved"}], total=2))
    assert run_cli(["refresh", "fx", "trade", "--trade-id", "saved"])[0] == 0
    _, saved, _ = run_cli(["fx", "trade"])
    original = envelope(saved)
    if failure == "hard":
        fx_browser.business_script.append({"status": 500, "body": {}})
        args = ["refresh", "fx", "trade", "--trade-id", "new"]
    else:
        fx_browser.business_script.append(page([{"uniqueId": "new"}]))
        args = (
            ["fx", "trade", "--live"]
            if failure == "live"
            else ["refresh", "fx", "trade", "--require-complete"]
        )
        args += ["--trade-id", "new"]
    code, out, _ = run_cli(args)
    assert code == (0 if failure == "live" else 1)
    if failure == "strict":
        assert envelope(out)["meta"]["published"] is False
    _, cached, _ = run_cli(["fx", "trade"])
    assert envelope(cached)["data"] == original["data"]
    for key in ("fetched_at", "acquisition", "complete"):
        assert envelope(cached)["meta"][key] == original["meta"][key]


def test_fx_cached_explicit_filters_fail_without_browser(run_cli, fx_browser, envelope):
    code, out, _ = run_cli(["fx", "trade", "--trade-id", "an-id"])
    assert code == 2 and envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert "--live" in envelope(out)["error"]["message"]
    assert not fx_browser.transports


def test_fx_prune_absent_does_not_create_database(run_cli, fx_browser):
    for _ in range(2):
        assert run_cli(["fx", "trade", "prune"])[0] == 0
    assert not fx_browser.transports


@pytest.mark.parametrize("outcome", ["empty", "strict", "hard"])
def test_fx_no_candidate_does_not_create_slot(run_cli, fx_browser, envelope, outcome):
    response = page([] if outcome == "empty" else [{"uniqueId": "rejected"}])
    if outcome == "hard":
        response = {"status": 500, "body": {}}
    fx_browser.business_script.append(response)
    args = ["refresh", "fx", "trade", "--trade-id", "rejected"]
    if outcome == "strict":
        args.append("--require-complete")
    code, out, _ = run_cli(args)
    assert code == (0 if outcome == "empty" else 1)
    if outcome != "hard":
        assert envelope(out)["meta"]["published"] is False
    code, out, _ = run_cli(["fx", "trade"])
    assert code == 1 and envelope(out)["error"]["code"] == "CACHE_MISS"


def test_fx_ordinary_online_and_replay_ignore_missing_duckdog(
    run_cli, fx_browser, envelope, monkeypatch
):
    import os
    import sys
    from pathlib import Path

    fx_browser.allows_cache = True
    configuration = Path(os.environ["DOGOPENCLI_CONFIG"])
    configuration.write_text(
        configuration.read_text() + '[duckdog]\npath = "absent.duckdb"\n'
    )
    monkeypatch.setitem(sys.modules, "duckdb", None)
    fx_browser.business_script.append(page([{"uniqueId": "saved"}]))
    assert run_cli(["refresh", "fx", "trade", "--trade-id", "saved"])[0] == 0
    fx_browser.href = SSO_URL
    count = len(fx_browser.transports)
    code, out, _ = run_cli(["fx", "trade"])
    assert code == 0 and envelope(out)["data"] == [{"uniqueId": "saved"}]
    assert len(fx_browser.transports) == count
    assert not (configuration.parent / "absent.duckdb").exists()
