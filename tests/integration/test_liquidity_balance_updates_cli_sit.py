"""Readable balance exports and normal statement updates at the CLI boundary."""

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
QUERY = ["liquidity", "cash", "balances", "list", "--entity", "E1", "--limit", "0"]
REFRESH = ["refresh", "liquidity", "cash", "balances", "--entity", "E1"]


def balance(record_id="B1", time="09:00:00", amount="10.00"):
    return {
        "balId": record_id,
        "entity": "E1",
        "aliasName": "A1",
        "currency": "USD",
        "curBalance": amount,
        "avlBalance": "8.00",
        "statementCreateTime": f"2026-10-01 {time}",
        "timeZone": "GMT+08",
        "leastDaytimeBalVo": {
            "valueDate": "2026-10-01",
            "instradayBalance": amount,
            "instradayAvlBalance": "8.00",
            "statementCreateTime": f"2026-10-01 {time}",
            "updateTime": f"2026-10-01 {time}",
        },
    }


def install(setup, rows):
    def answer(payload, index):
        start = payload["rowStart"]
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": {
                    "data": rows[start : start + payload["pageSize"]],
                    "totalCount": len(rows),
                },
            },
        }

    setup.state.business_handler = answer


def test_latest_export_uses_readable_names_and_fields(setup, run_cli):
    install(setup, [balance()])
    code, out, err = run_cli([*QUERY, "--live"])
    assert code == 0, err
    record = parse(out)["data"][0]
    assert record["balance_record_id"] == "B1"
    assert record["account_holder_entity_id"] == "E1"
    assert record["account_alias"] == "A1"
    assert record["current_balance"] == "10.00"
    assert record["intraday_balance"]["current_available_balance"] == "8.00"
    assert record["intraday_balance"]["value_date"] == "2026-10-01"
    assert "curBalance" not in record
    assert "leastDaytimeBalVo" not in record
    code, out, err = run_cli(
        [*QUERY, "--live", "--fields", "balance_record_id,current_balance"]
    )
    assert code == 0, err
    assert parse(out)["data"] == [
        {"balance_record_id": "B1", "current_balance": "10.00"}
    ]


@pytest.mark.parametrize("changed", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_same_day_statement_updates_are_successful_live_refresh_offline(
    setup, run_cli, changed, reverse
):
    newer = balance("B2", "10:00:00", "12.00" if changed else "10.0")
    rows = [balance(), newer]
    if reverse:
        rows.reverse()
    install(setup, rows)
    code, out, err = run_cli(
        [*QUERY, "--live", "--require-complete", "--page-size", "1"]
    )
    assert code == 0, err
    live = parse(out)
    assert len(live["data"]) == 1
    assert live["data"][0]["balance_record_id"] == "B2"
    assert live["data"][0]["current_balance"] == newer["curBalance"]
    assert live["meta"]["complete"] is True
    assert live["meta"]["collected_total"] == 2
    assert live["meta"]["matched_total"] == 1
    notices = live["meta"].get("warnings", [])
    assert [warning["code"] for warning in notices] == (
        ["BANK_STATEMENT_UPDATED"] if changed else []
    )
    if changed:
        assert notices[0]["level"] == "info"
        assert "Normal bank statement update/adjustment" in err
    else:
        assert "warning:" not in err
    assert not setup.cache_path.exists()

    code, out, err = run_cli([*REFRESH, "--require-complete", "--page-size", "1"])
    assert code == 0, err
    refreshed = parse(out)
    assert refreshed["data"]["row_count"] == 2  # native source records retained
    assert refreshed["meta"]["published"] is True
    assert refreshed["meta"].get("warnings", []) == notices
    before = setup.cache_path.read_bytes()
    requests = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, "--require-complete"])
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == live["data"]
    assert cached["meta"].get("warnings", []) == notices
    assert cached["meta"]["complete"] is True
    assert len(setup.state.business_requests) == requests
    assert setup.cache_path.read_bytes() == before


def test_balance_describe_documents_exported_names_and_native_identity(run_cli):
    code, out, err = run_cli(["describe", "liquidity", "cash", "balances", "list"])
    assert code == 0, err
    description = parse(out)
    guide = description["read_guide"]
    assert guide["identity"] == ["balance_record_id"]
    assert guide["native_identity"] == ["balId"]
    properties = description["data_schema"]["properties"]
    assert properties["current_balance"]["x-native-field"] == "curBalance"
    assert "intraday_balance.current_balance" in properties
    assert "leastDaytimeBalVo.instradayBalance" not in properties
    daily = guide["variants"][1]
    assert daily["series_time"] == "statistical_date"
    assert "source_id" in daily["data_schema"]["properties"]
    assert "data" not in daily["data_schema"]["properties"]


def test_thousands_formatted_equal_amounts_are_silent(setup, run_cli):
    install(setup, [balance(amount="1000.00"), balance("B2", "10:00:00", "1,000.00")])
    code, out, err = run_cli([*QUERY, "--live", "--require-complete"])
    assert code == 0, err
    result = parse(out)
    assert result["data"][0]["current_balance"] == "1,000.00"
    assert result["meta"].get("warnings", []) == []
    assert "warning:" not in err


@pytest.mark.parametrize("field", ["aliasName", "currency"])
@pytest.mark.parametrize("bad", [None, "", "  ", [], {"invalid": "value"}, 1, "absent"])
def test_malformed_account_attributes_never_merge_or_publish(
    setup, run_cli, field, bad
):
    install(setup, [balance()])
    assert run_cli(REFRESH)[0] == 0
    before = setup.cache_path.read_bytes()
    old = balance()
    new = balance("B2", "10:00:00")
    if bad == "absent":
        old.pop(field)
        new.pop(field)
    else:
        old[field] = bad
        new[field] = bad
    install(setup, [old, new])
    for command in ([*QUERY, "--live"], REFRESH):
        code, out, err = run_cli(command)
        assert code == 1, err
        result = parse(out)
        assert result["error"]["code"] == "INVALID_RESPONSE"
        assert result["data"] is None
        assert setup.cache_path.read_bytes() == before
