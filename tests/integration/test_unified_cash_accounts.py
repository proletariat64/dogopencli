"""Unified account inquiry through public CLI, fake CDP and temporary SQLite."""

import json

pytest_plugins = ["test_liquidity_cli_sit"]


def account(alias="A", **fields):
    return {
        "aliasName": alias,
        "currency": "USD",
        "bankId": "B",
        "instId": "E",
        **fields,
    }


def native_handler(cash, baselines, details=None):
    details = details or {row["aliasName"]: row for row in baselines}

    def answer(payload, index):
        if "bankAccountQueryVO" in payload:
            request = json.loads(payload["bankAccountQueryVO"])
            rows, container = cash, "bankAccountPropertyVOList"
        elif "bankAccountBaseLineQuery" in payload:
            request = json.loads(payload["bankAccountBaseLineQuery"])
            rows, container = baselines, "data"
        else:
            detail = details[payload["aliasName"]]
            if detail is False:
                return {
                    "status": 200,
                    "body": {
                        "resultFlag": True,
                        "errorCode": "ACCOUNT_REFUSED",
                        "errorMessage": "secret",
                        "result": {"success": False},
                    },
                }
            return {
                "status": 200,
                "body": {"resultFlag": True, "result": {"data": detail}},
            }
        start, size = request["rowStart"], request["pageSize"]
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": len(rows),
                "result": {container: rows[start : start + size]},
            },
        }

    return answer


def hole_handler(hole=3, refused=False):
    native = [
        account(f"A{i}", accountType="CA", status="Norm") if i != hole else None
        for i in range(8)
    ]
    baselines = [
        account(row["aliasName"], accountType="OA", status="NORMAL")
        for row in native
        if row
    ]
    normal = native_handler(
        [row for row in native if row],
        baselines,
        {
            row["aliasName"]: False if refused and row["aliasName"] == "A0" else row
            for row in baselines
        },
    )

    def answer(payload, index):
        if "bankAccountQueryVO" not in payload:
            return normal(payload, index)
        request = json.loads(payload["bankAccountQueryVO"])
        start, size = request["rowStart"], request["pageSize"]
        rows = [row for row in native[start : start + size] if row]
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": 8,
                "result": {"bankAccountPropertyVOList": rows},
            },
        }

    return answer
