"""Bounded native composition through public CLI, fake CDP and real SQLite."""

import hashlib
import json

import pytest

from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.forecast_accuracy import METRIC_FIELDS

pytest_plugins = ["test_liquidity_cli_sit"]
ACCOUNT = "TEST-ACCOUNT"
ROW = {
    "id": "TEST-RECORD-1",
    "bankAccountAliasName": ACCOUNT,
    "currency": "USD",
    "valueDate": "20260930",
    "baseValueDate": "20260929",
    "recordCreateTime": "2026-10-05 01:02:03",
    "forecastBalance": "0.00",
    "cashFlowTransIn": "-10.00000000000001",
    "cashFlowTransOut": "",
    "forecastTaskId": 0,
    "forecastBatchNo": None,
    "forecastRuleId": "unknown",
    "accountNo": "TEST-PRIVATE-NUMBER",
    "instId": "TEST-INST",
    "bankId": "TEST-BANK",
    "operator": "TEST-PERSON",
    "memo": "TEST-PRIVATE-MEMO",
}
METRICS = {
    field: str(index) + ".000000000000001" for index, field in enumerate(METRIC_FIELDS)
}
METRICS.update(
    cashFlowAccuracy="", inflowAccuracy="0", outflowAccuracy="-2", realizedBalance=None
)


def args(*extra, refresh=False, account=None, day=None):
    command = (
        ["refresh", "liquidity", "forecast", "accuracy"]
        if refresh
        else ["liquidity", "forecast", "accuracy", "list"]
    )
    online = refresh or "--live" in extra
    flags = []
    if online or account is not None:
        flags.extend(["--account-alias", ACCOUNT if account is None else account])
    if online or day is not None:
        flags.extend(["--record-date", "2026-10-05" if day is None else day])
    return command + flags + list(extra)


def base_page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "count": len(rows) if total is None else total,
                "dataValue": rows,
            },
        },
    }


def metric_page(metrics=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "bankAccountDetailDayVO": METRICS if metrics is None else metrics,
            },
        },
    }


def handler(rows, *, total=None, metric=None):
    by_id = {row["id"]: row for row in rows}

    def answer(body, index):
        assert body["tntInstId"] == "GUAPW3SG"
        if "bankCashForecastRecordQueryVo" in body:
            assert set(body) == {"tntInstId", "bankCashForecastRecordQueryVo"}
            assert json.loads(body["bankCashForecastRecordQueryVo"]) == {
                "tntInstId": "GUAPW3SG",
                "rowStart": 0,
                "pageSize": 5000,
                "aliasName": [ACCOUNT],
                "valueStartDay": "20261005",
                "valueEndDay": "20261005",
                "recordStartTime": "000000",
                "recordEndTime": "235959",
            }
            return base_page(rows, total)
        assert set(body) == {"tntInstId", "bankAccountDetailCashFlowQueryVO"}
        vo = parse(body["bankAccountDetailCashFlowQueryVO"])
        row = by_id[vo["forecastRecordId"]]
        assert vo == {
            "valueDate": row["valueDate"],
            "accountNo": row["accountNo"],
            "instId": row["instId"],
            "currency": row["currency"],
            "bankId": row["bankId"],
            "forecastRecordId": row["id"],
            "aliasName": ACCOUNT,
            "forecastBalance": "0"
            if row["forecastBalance"] in ("0.0", "0.00")
            else row["forecastBalance"],
        }
        return metric_page() if metric is None else metric(vo, index)

    return answer


def digest(setup):
    return hashlib.sha256(setup.cache_path.read_bytes()).hexdigest()


def seed(setup, run_cli):
    setup.state.business_handler = handler([ROW])
    code, out, err = run_cli(args("--require-complete", refresh=True))
    assert code == 0, err
    return parse(out), digest(setup)


@pytest.mark.parametrize("kind", ["host", "path", "method", "extra", "tenant", "vo"])
def test_bound_shared_transport_default_deny(setup, kind):
    from dogopencli.errors import CliError
    from dogopencli.plugins.liquidity.forecast_accuracy import BoundInquiry, metric_body
    from dogopencli.transport import QueryRequest, validate_request

    body = metric_body(ROW, ACCOUNT)
    cap = BoundInquiry("accuracy.test", "/cashFlowDetailDay.json", body)
    values = {
        "capability": cap.name,
        "method": "GET",
        "host": "iliquidity.alipay.com",
        "path": cap.contract.path,
        "body": dict(body),
    }
    if kind in {"host", "path", "method"}:
        values[kind] = "OTHER"
    elif kind == "extra":
        values["body"]["unverified"] = "value"
    elif kind == "tenant":
        values["body"]["tntInstId"] = "OTHER"
    else:
        vo = json.loads(body["bankAccountDetailCashFlowQueryVO"])
        vo["forecastRecordId"] = "OTHER-ROW"
        values["body"]["bankAccountDetailCashFlowQueryVO"] = json.dumps(vo)
    with pytest.raises(CliError) as error:
        validate_request(QueryRequest(**values), cap.contract)
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not setup.state.business_requests
