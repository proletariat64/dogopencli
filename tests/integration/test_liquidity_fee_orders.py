"""Native-shape sanitized fees through public CLI, fake CDP and SQLite."""

import json
from pathlib import Path

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
ROW = json.loads(
    (Path(__file__).parents[1] / "fixtures/liquidity_fee_orders.json").read_text()
)["result"]["data"][0]


def args(*extra, refresh=False, start="20260801", end="20260831"):
    cmd = (
        ["refresh", "liquidity", "pricing", "fee-orders"]
        if refresh
        else ["liquidity", "pricing", "fee-orders", "list"]
    )
    return cmd + ["--from-date", start, "--to-date", end, *extra]


def page(rows, total):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": total,
            "result": {"success": True, "count": total, "data": rows},
        },
    }


def listing(rows):
    def handle(body, index):
        assert set(body) == {"tntInstId", "feeOrderListQueryVO"}
        assert body["tntInstId"] == "GUAPW3SG"
        vo = json.loads(body["feeOrderListQueryVO"])
        assert vo == {
            "tntInstId": "GUAPW3SG",
            "timeZone": "GMT+08",
            "beginDate": "20260801",
            "endDate": "20260831",
            "rowStart": vo["rowStart"],
            "pageSize": 10,
        }
        return page(rows[vo["rowStart"] : vo["rowStart"] + 10], len(rows))

    return handle


def test_pagination_projection_offline_live_coverage(setup, run_cli):
    rows = [dict(ROW, id=f"test-{i}") for i in range(12)]
    rows[0].update(feeAmount=None, transAmount="", status="future-native-status")
    rows[1]["feeAmount"] = "0"
    setup.state.business_handler = listing(
        [dict(row, unknownPrivate="TEST PRIVATE") for row in rows]
    )
    code, out, err = run_cli(args(refresh=True))
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is True
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(args("--live", "--all"))
    assert code == 0, err
    assert sorted(parse(out)["data"], key=lambda r: r["id"]) == sorted(
        rows, key=lambda r: r["id"]
    )
    assert setup.cache_path.read_bytes() == before
    assert b"TEST PRIVATE" not in before
    setup.state.reachable = False
    for start, end in (("20260801", "20260831"), ("20260804", "20260804")):
        code, out, err = run_cli(args("--all", start=start, end=end))
        assert code == 0, err
        assert len(parse(out)["data"]) == 12
    code, out, _ = run_cli(args(start="20260701", end="20260731"))
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize(
    "start,end",
    [("20260801", "20260901"), ("20260802", "20260801"), ("20260230", "20260301")],
)
def test_invalid_bounds_no_browser(setup, run_cli, start, end):
    code, _, _ = run_cli(args("--live", start=start, end=end))
    assert code != 0
    assert not setup.state.business_requests


def test_empty_partial_and_strict(setup, run_cli):
    setup.state.business_handler = listing([])
    code, out, err = run_cli(args(refresh=True))
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is True
    setup.state.business_handler = lambda body, index: page([ROW], 2)
    before = setup.cache_path.read_bytes()
    code, out, _ = run_cli(args("--require-complete", refresh=True))
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(args(refresh=True))
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is False
    setup.state.reachable = False
    code, out, err = run_cli(args("--all"))
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is False
    assert parse(out)["data"] == [ROW]


@pytest.mark.parametrize(
    "changes",
    [
        {"tntInstId": "OTHER"},
        {"serviceDate": "20260901"},
        {"id": 1},
        {"serviceDate": "20260230"},
        {"feeAmount": 1.2},
        {"serviceTime": "2026-08-04T11:00:00Z"},
    ],
)
def test_invalid_rows_preserve_cache(setup, run_cli, changes):
    setup.state.business_handler = listing([ROW])
    code, _, err = run_cli(args(refresh=True))
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = listing([dict(ROW, **changes)])
    code, out, _ = run_cli(args(refresh=True))
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == before


def test_identity_conflict(setup, run_cli):
    setup.state.business_handler = listing([ROW, dict(ROW, feeAmount="2")])
    code, out, _ = run_cli(args(refresh=True))
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"


def test_describe_and_valuation_distinct(setup, run_cli):
    setup.state.reachable = False
    code, out, err = run_cli(["describe", "liquidity", "pricing", "fee-orders", "list"])
    assert code == 0, err
    assert parse(out)["read_guide"]["identity"] == ["id"]
    assert "31 calendar days" in out
    assert parse(out)["read_guide"]["live_verified"] == "2026-10-04"
    properties = parse(out)["data_schema"]["properties"]
    assert properties["feeAmount"]["x-currency-field"] == "pricingCurrency"
    assert properties["transAmount"]["x-currency-field"] == "currency"
    assert "no inferred UTC offset" in properties["serviceTime"]["description"]
    code, out, _ = run_cli(["liquidity", "pricing", "valuations", "list"])
    assert code == 1
    assert parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert not setup.state.business_requests


@pytest.mark.parametrize("inner,outer", [(False, True), (True, False)])
def test_business_failure_is_not_empty_success(setup, run_cli, inner, outer):
    response = page([], 0)
    response["body"]["resultFlag"] = outer
    response["body"]["result"]["success"] = inner
    setup.state.business_handler = lambda body, index: response
    code, out, _ = run_cli(args(refresh=True))
    assert code == 1
    assert parse(out)["data"] is None


def test_previous_cache_not_migrated_or_deleted(setup, run_cli):
    import sqlite3

    with sqlite3.connect(setup.cache_path) as connection:
        connection.execute("CREATE TABLE previous_valuation_capture (value TEXT)")
        connection.execute("INSERT INTO previous_valuation_capture VALUES ('preserve')")
    before = setup.cache_path.read_bytes()
    code, out, _ = run_cli(args())
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.cache_path.read_bytes() == before
    setup.state.business_handler = listing([ROW])
    code, _, err = run_cli(args(refresh=True))
    assert code == 0, err
    with sqlite3.connect(setup.cache_path) as connection:
        assert connection.execute(
            "SELECT value FROM previous_valuation_capture"
        ).fetchall() == [("preserve",)]


@pytest.mark.parametrize(
    "amount,currency", [("feeAmount", "pricingCurrency"), ("transAmount", "currency")]
)
@pytest.mark.parametrize("unit", [None, "", "dollars", "missing"])
def test_populated_zero_requires_currency_and_preserves_cache(
    setup, run_cli, amount, currency, unit
):
    setup.state.business_handler = listing([ROW])
    assert run_cli(args(refresh=True))[0] == 0
    prior = setup.cache_path.read_bytes()
    row = dict(ROW, **{amount: "0", currency: unit})
    if unit == "missing":
        del row[currency]
    setup.state.business_handler = listing([row])
    code, out, _ = run_cli(args(refresh=True))
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == prior
