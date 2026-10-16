"""Funding-demand public CLI, native request shape and cache safety."""

import json

pytest_plugins = ["test_liquidity_cli_sit"]

SCOPE = ["--execute-from", "2026-04-01 00:00:00", "--execute-to", "2026-04-02 00:00:00"]
QUERY = ["liquidity", "operations", "demands", "list"]
REFRESH = ["refresh", "liquidity", "operations", "demands"]


def demand(index=0, **changes):
    return {
        "taskId": f"synthetic-demand-{index}",
        "tntInstId": "GUAPW3SG",
        "source": "FUND_REQUIRE",
        "sourceId": "synthetic-source",
        "instId": "synthetic-entity",
        "bankId": "synthetic-bank",
        "currency": "USD",
        "amount": "123456789012345678.123400",
        "executeTime": "2026-04-01 12:34:56",
        "status": "unknown-native-state",
        "accountNo": "excluded-account",
        "aliasName": "excluded-alias",
        "fundsRiskActionResult": {"private": "excluded"},
        **changes,
    }


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "dataValue": rows,
                "count": len(rows) if total is None else total,
            },
        },
    }


def listing(rows):
    def answer(payload, index):
        assert set(payload) == {"tntInstId", "riskActionTaskQueryVO"}
        vo = json.loads(payload["riskActionTaskQueryVO"])
        assert vo["tntInstId"] == payload["tntInstId"] == "GUAPW3SG"
        assert vo["source"] == ["FUND_REQUIRE"]
        assert vo["pageSize"] == 5000
        assert vo["startExecuteTime"] == SCOPE[1]
        assert vo["endExecuteTime"] == SCOPE[3]
        return response(rows[vo["rowStart"] : vo["rowStart"] + 5000], len(rows))

    return answer


T_SCOPE = [
    "--execute-from",
    "2026-04-01T00:00:00",
    "--execute-to",
    "2026-04-02T00:00:00",
]
