"""R06 public CLI, fake CDP and temporary SQLite acceptance."""

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
