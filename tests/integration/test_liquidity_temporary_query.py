"""Temporary Liquidity acquisitions through CLI/fake CDP/temporary SQLite."""

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]


@pytest.mark.parametrize("reported_total", [2, 3])
@pytest.mark.parametrize("account", ["A", "B"])
@pytest.mark.parametrize("currencies", [["USD"], ["JPY"], ["USD", "EUR"]])
def test_filtered_waterlevels_preserve_source_completeness_and_scope(
    setup, run_cli, reported_total, account, currencies
):
    rows = [
        {"aliasName": "A", "currency": currency, "curAvlBal": "1.00"}
        for currency in ("USD", "EUR")
    ]
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": reported_total},
        },
    }
    code, out, err = run_cli(
        ["refresh", "liquidity", "cash", "waterlevels", "--account-alias", "A"]
    )
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    setup.state.transports.clear()
    command = ["liquidity", "cash", "waterlevels", "list", "--account-alias", account]
    for currency in currencies:
        command.extend(["--currency", currency])
    code, out, err = run_cli(command)
    assert code == 0, err
    result = parse(out)
    complete = reported_total == len(rows) and account == "A"
    assert result["meta"]["complete"] is complete
    assert result["meta"]["source_acquisition"]["scope_complete"] is (
        reported_total == len(rows)
    )
    assert result["meta"]["requested_scope_covered"] is (account == "A")
    assert result["data"] == [
        row for row in rows if account == "A" and row["currency"] in currencies
    ]
    code, out, err = run_cli([*command, "--require-complete"])
    if complete:
        assert code == 0, err
        assert parse(out)["meta"]["complete"] is True
    else:
        assert code == 1
        assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.state.transports == []
    assert setup.cache_path.read_bytes() == before


def test_cash_online_default_is_native_alipaygm(setup, run_cli):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"data": [], "totalCount": 0}},
    }
    code, out, err = run_cli(["liquidity", "cash", "balances", "list", "--live"])
    assert code == 0, err
    assert setup.state.business_requests[0]["entitys"] == ["ALIPAYGM"]
    assert not setup.cache_path.exists()


def test_refresh_replaces_leaf_and_offline_replays_without_defaults(setup, run_cli):
    def rows(entity):
        return [
            {
                "balId": entity,
                "entity": entity,
                "aliasName": "A",
                "currency": "USD",
                "curBalance": "1.00",
                "avlBalance": None,
            }
        ]

    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows(payload["entitys"][0]), "totalCount": 1},
        },
    }
    for entity in ("E1", "E2"):
        code, out, err = run_cli(
            ["refresh", "liquidity", "cash", "balances", "--entity", entity]
        )
        assert code == 0, err
    setup.state.transports.clear()
    code, out, err = run_cli(["liquidity", "cash", "balances", "list"])
    assert code == 0, err
    assert [r["account_holder_entity_id"] for r in parse(out)["data"]] == ["E2"]
    assert setup.state.transports == []


def test_empty_refresh_preserves_previous_and_reports_current_empty(setup, run_cli):
    row = {
        "balId": "B1",
        "entity": "E1",
        "aliasName": "A",
        "currency": "USD",
        "curBalance": "1",
        "avlBalance": None,
    }
    state = {"rows": [row]}
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": state["rows"], "totalCount": len(state["rows"])},
        },
    }
    command = ["refresh", "liquidity", "cash", "balances", "--entity", "E1"]
    assert run_cli(command)[0] == 0
    state["rows"] = []
    code, out, err = run_cli(command)
    assert code == 0, err
    assert parse(out)["meta"]["published"] is False
    assert parse(out)["meta"]["collected_total"] == 0
    code, out, err = run_cli(["liquidity", "cash", "balances", "list"])
    assert code == 0, err
    assert len(parse(out)["data"]) == 1


def test_daily_no_argument_replay_and_local_entity_filter(setup, run_cli):
    def answer(payload, index):
        if "wallet" in payload:
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": 2,
                    "result": {
                        "bankAccountPropertyVOList": [
                            {"aliasName": "A1", "instId": "E1", "currency": "USD"},
                            {"aliasName": "A2", "instId": "E2", "currency": "USD"},
                        ]
                    },
                },
            }
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": [
                    {
                        "id": "D",
                        "data": alias,
                        "statisticalDate": "2026-10-01",
                        "balance": "12.00",
                    }
                    for alias in payload["aliasNames"]
                ],
            },
        }

    setup.state.business_handler = answer
    code, out, err = run_cli(
        [
            "refresh",
            "liquidity",
            "cash",
            "balances",
            "--entity",
            "E1",
            "--entity",
            "E2",
            "--from-date",
            "2026-10-01",
            "--to-date",
            "2026-10-02",
        ]
    )
    assert code == 0, err
    for options, count in (([], 2), (["--entity", "E1"], 1), (["--entity", "E3"], 0)):
        code, out, err = run_cli(["liquidity", "cash", "balances", "list", *options])
        assert code == 0, err
        assert len(parse(out)["data"]) == count
        assert parse(out)["meta"]["variant"] == "/balStatisticalQuery.json"
    code, out, err = run_cli(
        [
            "liquidity",
            "cash",
            "balances",
            "list",
            "--from-date",
            "2026-10-03",
            "--to-date",
            "2026-10-04",
            "--require-complete",
        ]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"


def test_any_freezes_duckdog_native_ids_then_replays_offline(setup, run_cli):
    duckdb = pytest.importorskip("duckdb")

    database = setup.tmp_path / "selector.duckdb"
    connection = duckdb.connect(str(database))
    connection.execute("CREATE TABLE entities(instId VARCHAR)")
    connection.execute("INSERT INTO entities VALUES ('E2'), ('E1'), ('E1')")
    connection.close()
    config = setup.tmp_path / "config.toml"
    with config.open("a") as target:
        target.write(
            f'\n[duckdog]\npath = "{database}"\n[duckdog.selectors]\n'
            '"liquidity/reference/entities" = "entities"\n'
        )
    rows = [
        {
            "balId": f"B{index}",
            "entity": "E1" if index % 2 else "E2",
            "aliasName": f"A{index}",
            "currency": "USD",
            "curBalance": "1.00",
            "avlBalance": None,
        }
        for index in range(102)
    ]

    def answer(payload, index):
        assert payload["entitys"] == ["E1", "E2"]
        if payload["rowStart"] == 0:
            connection = duckdb.connect(str(database))
            connection.execute("DELETE FROM entities")
            connection.execute("INSERT INTO entities VALUES ('OTHER')")
            connection.close()
        start = payload["rowStart"]
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": {
                    "data": rows[start : start + payload["pageSize"]],
                    "totalCount": 102,
                },
            },
        }

    setup.state.business_handler = answer
    code, out, err = run_cli(
        ["refresh", "liquidity", "cash", "balances", "--entity", "ANY"]
    )
    assert code == 0, err
    assert parse(out)["meta"]["selection"]["values"] == ["E1", "E2"]
    database.unlink()
    setup.state.transports.clear()
    code, out, err = run_cli(
        ["liquidity", "cash", "balances", "list", "--entity", "ANY", "--limit", "0"]
    )
    assert code == 0, err
    assert len(parse(out)["data"]) == 102
    assert setup.state.transports == []


def test_prune_is_leaf_local_idempotent_and_offline(setup, run_cli):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "data": [
                    {
                        "balId": "B",
                        "entity": "E1",
                        "aliasName": "A",
                        "currency": "USD",
                        "curBalance": "1",
                        "avlBalance": None,
                    }
                ],
                "totalCount": 1,
            },
        },
    }
    assert (
        run_cli(["refresh", "liquidity", "cash", "balances", "--entity", "E1"])[0] == 0
    )
    setup.state.transports.clear()
    for _ in range(2):
        code, out, err = run_cli(["liquidity", "cash", "balances", "prune"])
        assert code == 0, err
    code, out, err = run_cli(["liquidity", "cash", "balances", "list"])
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []


def test_native_get_is_online_without_cache_or_live_flag(setup, run_cli):
    native = {
        "inquiryTaskId": "SYN-CHILD",
        "inquiryType": "TARGET_RFQ",
        "currency": "USD",
        "ticketSize": "1.2300",
        "inquiryOrderListVOList": [],
    }
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": native},
    }
    code, out, err = run_cli(
        ["liquidity", "investment", "rfqs", "get", "--inquiry-sub-task-id", "SYN-CHILD"]
    )
    assert code == 0, err
    assert parse(out)["data"] == native
    assert setup.state.business_requests == [{"inquiryTaskId": "SYN-CHILD"}]
    assert not setup.cache_path.exists()


def test_cached_native_corruption_rejected_before_filter_or_display(setup, run_cli):
    from dogopencli.cache import Cache
    from dogopencli.result_policy import AcquisitionEvidence
    from dogopencli.temporary_query import publish_slot

    store = Cache(setup.cache_path)
    rows = [
        {
            "balId": "B",
            "entity": "E1",
            "aliasName": "A",
            "currency": "USD",
            "curBalance": "NaN",
        }
    ]
    with store.refresh_lock():
        publish_slot(
            store,
            "liquidity.cash.balances",
            rows,
            capability="liquidity.cash.balances.list",
            scope={"entitys": ["E1"], "timeZone": "GMT+08"},
            variant="/latestBalanceQuery.json",
            evidence=AcquisitionEvidence.for_collection(
                complete=True, reported_total=1, collected_total=1
            ),
            fetched_at="2026-10-13T00:00:00+00:00",
        )
    code, out, err = run_cli(
        [
            "liquidity",
            "cash",
            "balances",
            "list",
            "--entity",
            "OTHER",
            "--offset",
            "100",
        ]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.state.transports == []
