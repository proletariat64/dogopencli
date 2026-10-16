"""Readable balance exports and normal statement updates at the CLI boundary."""

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
