"""Cash balance date/selection contracts at the public CLI seam."""

import json

import pytest

pytest_plugins = ["test_liquidity_cli_sit"]

QUERY = ["liquidity", "cash", "balances", "list"]
REFRESH = ["refresh", "liquidity", "cash", "balances"]
DATES = ["--from-date", "2026-10-01", "--to-date", "2026-10-02"]


def roster(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": len(rows) if total is None else total,
            "result": {"bankAccountPropertyVOList": rows},
        },
    }


def daily(rows):
    return {"status": 200, "body": {"success": True, "data": rows}}


def entities(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": len(rows) if total is None else total,
            "result": {"entityMaintVOList": rows},
        },
    }


def directory():
    return [{"id": "row1", "instId": "E1", "instCode": "NOT-AN-ID"}]


def account(alias="A1", entity="E1", currency="USD"):
    return {"aliasName": alias, "instId": entity, "currency": currency}


def observation(alias="A1", day="2026-10-01", balance="12.00"):
    return {
        "id": "repeated-native-id",
        "data": alias,
        "statisticalDate": day,
        "balance": balance,
    }


def install_daily(setup, *, accounts=None, directory_rows=None, total=None, rows=None):
    accounts = [account()] if accounts is None else accounts
    directory_rows = directory() if directory_rows is None else directory_rows
    rows = [observation()] if rows is None else rows

    def answer(payload, index):
        if "entityMaintQueryVO" in payload:
            return entities(directory_rows)
        if "wallet" in payload:
            return roster(accounts, total)
        return daily(rows)

    setup.state.business_handler = answer


def synthetic_balance_id(row):
    account = [row.get(field) for field in ("entity", "aliasName", "currency")]
    return f"synthetic:{json.dumps(account, separators=(',', ':'), ensure_ascii=True)}"


def latest(rows):
    native_rows = [
        row if "balId" in row else {**row, "balId": synthetic_balance_id(row)}
        for row in rows
    ]
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": native_rows, "totalCount": len(native_rows)},
        },
    }


def test_daily_allowlist_rejects_export_mutation_and_latest_fields(setup):
    from dataclasses import replace

    from dogopencli.errors import CliError
    from dogopencli.plugins.liquidity.cash_forecast import CASH_DAILY_BALANCES
    from dogopencli.plugins.liquidity.leaves import list_leaf
    from dogopencli.transport import QueryRequest, validate_request
    from dogopencli.transport.cdp import CdpQueryTransport

    leaf = list_leaf(("cash", "balances"))
    capability = leaf.capability(CASH_DAILY_BALANCES)
    request = QueryRequest(
        capability=capability.name,
        method="POST",
        host="iliquidity.alipay.com",
        path="/balStatisticalQuery.json",
        body={
            "tntInstId": "GUAPW3SG",
            "balanceType": "day",
            "aliasNames": ["A1"],
            "queryStartDate": "20261001",
            "queryDate": "20261002",
        },
    )
    validate_request(request, capability.contract)
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url=capability.page_url,
    )
    invalid = [
        replace(request, path="/dayEndBalanceExport.json"),
        replace(request, path="/updateBalance.json"),
        replace(request, method="GET"),
        replace(request, host="ifundcontrol.alipay.com"),
    ]
    invalid.extend(
        replace(request, body={**request.body, field: value})
        for field, value in [
            ("entitys", ["E1"]),
            ("timeZone", "GMT+08"),
            ("rowStart", 0),
            ("pageSize", 100),
            ("arbitrary", "code"),
            ("balanceType", "month"),
            ("tntInstId", "OTHER"),
        ]
    )
    for changed in invalid:
        with pytest.raises(CliError) as error:
            transport.execute(changed)
        assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
    assert not any(t.created for t in setup.state.transports)
