"""R06 public CLI, fake CDP and temporary SQLite acceptance."""

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]

ROOT = ["liquidity", "forecast", "account_demands"]
SCOPE = [
    "--alias",
    "SYN-A",
    "--entity",
    "SYN-E",
    "--bank",
    "SYN-B",
    "--from-date",
    "20261009",
    "--to-date",
    "20261015",
]


def test_account_demands_declared_and_missing_scope_rejected(setup, run_cli):
    code, out, err = run_cli(["help", *ROOT, "list"])
    assert code == 0, err
    assert "--alias" in out
    for scope in (
        [],
        SCOPE[:-2],
        [*SCOPE[:-4], "--from-date", "20261015", "--to-date", "20261009"],
    ):
        code, out, err = run_cli([*ROOT, "list", "--live", *scope])
        assert code == 2, err
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


def demand(index):
    return {
        "id": str(index),
        "aliasName": "SYN-A",
        "entity": "SYN-E",
        "bankID": "SYN-B",
        "amount": "123456789.123456789",
        "originalBizNo": f"BIZ-{index}",
        "expectValueDate": "20261012",
    }


def listing(rows):
    def answer(payload, index):
        start, size = payload["rowStart"], payload["pageSize"]
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": {
                    "data": rows[start : start + size],
                    "totalCount": len(rows),
                    "rowStart": start,
                    "pageSize": size,
                },
            },
        }

    return answer


def test_large_demands_full_collection_terminal_probe_and_offline(setup, run_cli):
    rows = [demand(index) for index in range(160029)]
    setup.state.business_handler = listing(rows)
    code, out, err = run_cli(["refresh", *ROOT, *SCOPE, "--require-complete"])
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["complete"] is True
    assert result["meta"]["collected_total"] == 160029
    requests = setup.state.business_requests
    assert [p["rowStart"] for p in requests] == [*range(0, 160001, 5000), 160029]
    assert all(p["pageSize"] == 5000 for p in requests)
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list", "--limit", "1", "--offset", "160028"])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == [rows[-1]]
    assert result["meta"]["complete"] is True


@pytest.mark.parametrize("alias", ["", " ", "ANY", "SYN-A,SYN-B"])
def test_account_validation_before_directory_or_browser(setup, run_cli, alias):
    code, out, _ = run_cli(
        [
            *ROOT,
            "list",
            "--live",
            "--alias",
            alias,
            "--from-date",
            "20261009",
            "--to-date",
            "20261015",
        ]
    )
    assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


def test_refresh_empty_failure_and_strict_partial_preserve_slot(setup, run_cli):
    setup.state.business_handler = listing([demand(1), demand(2)])
    assert run_cli(["refresh", *ROOT, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = listing([])
    code, out, err = run_cli(["refresh", *ROOT, *SCOPE])
    assert code == 0, err
    assert parse(out)["meta"]["published"] is False
    assert setup.cache_path.read_bytes() == before
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "data": [demand(1)] if payload["rowStart"] == 0 else [],
                "totalCount": 2,
            },
        },
    }
    code, out, _ = run_cli(["refresh", *ROOT, *SCOPE, "--require-complete"])
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli([*ROOT, "list", *SCOPE, "--live"])
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is False
    assert "INCOMPLETE_RESULT" in err
    assert setup.cache_path.read_bytes() == before


def test_demands_explicit_offline_filters_use_saved_scope_without_network(
    setup, run_cli
):
    setup.state.business_handler = listing([demand(1)])
    assert run_cli(["refresh", *ROOT, *SCOPE])[0] == 0
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list", *SCOPE])
    assert code == 0, err
    assert parse(out)["data"] == [demand(1)]
    assert parse(out)["meta"]["requested_scope_covered"] is True
    code, out, err = run_cli([*ROOT, "list", "--alias", "SYN-OTHER"])
    assert code == 0, err
    assert parse(out)["data"] == []
    assert parse(out)["meta"]["requested_scope_covered"] is False


def test_t3_native_forecast_day_scope_and_width(setup, run_cli):
    row = {
        "aliasName": "SYN-A",
        "forecastDate": "20261015",
        "expectValueDate": "20261019",
        "fundActionType": "PAYMENT",
        "entity": "SYN-E",
        "bankId": "SYN-B",
        "dateFlag": "T3",
        "currency": "USD",
        "amount": "1.000",
    }
    setup.state.business_handler = listing([row])
    command = [
        "liquidity",
        "forecast",
        "account_t3",
        "list",
        "--live",
        "--account-alias",
        "SYN-A",
        "--from-date",
        "20261015",
        "--to-date",
        "20261015",
    ]
    code, out, err = run_cli(command)
    assert code == 0, err
    assert parse(out)["data"] == [row]
    assert [p["rowStart"] for p in setup.state.business_requests] == [0, 1]
    assert all(p["pageSize"] == 10 for p in setup.state.business_requests)


def test_cashflow_retains_real_money_and_time_fields(setup, run_cli):
    row = {
        "bankAccountAliasName": "SYN-A",
        "entity": "SYN-E",
        "bankId": "SYN-B",
        "bankAccountFlowDateSourceType": None,
        "bankAccountFlowDateSourceTypeStr": "SETTLE_INSTRUCTION",
        "originalBizNo": "BIZ-1",
        "expectValueDate": "20261012",
        "expectValueTime": "2026-10-12 12:00:00",
        "expectValueDateTime": "",
        "currency": "USD",
        "gmtCreate": None,
        "fundDirection": "inflow",
        "gmtCreateStr": "2026-10-12 11:00:00",
        "amountStr": "10.1200",
        "amount": {"amount": 10, "cent": 1000, "currency": "USD"},
    }
    setup.state.business_handler = listing([row])
    code, out, err = run_cli(
        ["liquidity", "forecast", "account_cashflows", "list", "--live", *SCOPE]
    )
    assert code == 0, err
    assert parse(out)["data"] == [row]
    assert "receivedTime" not in parse(out)["data"][0]
    assert (
        run_cli(["refresh", "liquidity", "forecast", "account_cashflows", *SCOPE])[0]
        == 0
    )
    setup.state.reachable = False
    code, out, err = run_cli(["liquidity", "forecast", "account_cashflows", "list"])
    assert code == 0, err
    assert parse(out)["data"] == [row]


@pytest.mark.parametrize(
    "leaf", ["account_t3", "account_cashflows", "account_strategies"]
)
@pytest.mark.parametrize("terminal", [False, True])
@pytest.mark.parametrize(
    ("field", "value"),
    [("rowStart", 999), ("pageSize", 999), ("rowStart", True), ("pageSize", "5000")],
)
def test_native_paging_echo_conflicts_are_hard_errors(
    setup, run_cli, leaf, terminal, field, value
):
    row = {
        "aliasName": "SYN-A",
        "bankAccountAliasName": "SYN-A",
        "entity": "SYN-E",
        "bankId": "SYN-B",
        "currency": "USD",
        "version": 1,
        "forecastDate": "20261012",
        "expectValueDate": "20261012",
        "expectValueTime": "12:00:00",
        "fundActionType": "PAYMENT",
        "dateFlag": "T3",
        "bankAccountFlowDateSourceTypeStr": "SETTLE_INSTRUCTION",
        "originalBizNo": "BIZ-1",
    }

    def answer(payload, index):
        response = listing([row])(payload, index)
        data = response["body"]["data"]
        data.update(rowStart=payload["rowStart"], pageSize=payload["pageSize"])
        if bool(payload["rowStart"]) == terminal:
            data[field] = value
        return response

    setup.state.business_handler = answer
    if leaf == "account_strategies":
        command = ["refresh", "liquidity", "operations", leaf]
    elif leaf == "account_t3":
        command = [
            "refresh",
            "liquidity",
            "forecast",
            leaf,
            "--account-alias",
            "SYN-A",
            *SCOPE[-4:],
        ]
    else:
        command = ["refresh", "liquidity", "forecast", leaf, *SCOPE]
    code, out, _ = run_cli(command)
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


def test_demands_native_zero_offset_echo_remains_supported(setup, run_cli):
    def answer(payload, index):
        response = listing([demand(1)])(payload, index)
        response["body"]["data"].update(rowStart=0, pageSize=5000)
        return response

    setup.state.business_handler = answer
    code, out, err = run_cli(["refresh", *ROOT, *SCOPE, "--require-complete"])
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is True
    assert [p["rowStart"] for p in setup.state.business_requests] == [0, 1]


@pytest.mark.parametrize(
    "leaf",
    [
        "account_t0",
        "account_hours_max",
        "account_daily_max",
        "account_demands_intraday",
    ],
)
def test_unqualified_sources_are_discoverable_but_never_execute(setup, run_cli, leaf):
    root = ["liquidity", "forecast", leaf]
    assert run_cli(["help", *root, "list"])[0] == 0
    assert run_cli(["describe", *root, "list"])[0] == 0
    for command in ([*root, "list"], ["refresh", *root], ["prune", *root]):
        code, out, _ = run_cli(command)
        assert code == 1
        assert parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert setup.state.transports == []
    assert not setup.cache_path.exists()


def test_page_budget_safe_partial_and_strict_rejection_preserve_cache(
    setup, run_cli, monkeypatch
):
    from dogopencli.plugins.liquidity import account_collection

    setup.state.business_handler = listing([demand(1)])
    assert run_cli(["refresh", *ROOT, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()
    monkeypatch.setattr(account_collection, "MAX_PAGES", 1)
    code, out, err = run_cli([*ROOT, "list", "--live", *SCOPE, "--fields", "id"])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == [{"id": "1"}]
    assert result["meta"]["complete"] is False
    assert "PAGE_BUDGET_EXHAUSTED" in result["meta"]["acquisition"]["reasons"]
    assert setup.cache_path.read_bytes() == before
    code, out, _ = run_cli(["refresh", *ROOT, *SCOPE, "--require-complete"])
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
