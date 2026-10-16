"""Rule-status run-overview public CLI, native request shape and cache safety."""

import json

pytest_plugins = ["test_liquidity_cli_sit"]

SCOPE = [
    "--trigger-from",
    "2026-01-01 00:00:00",
    "--trigger-to",
    "2026-01-31 23:59:59",
]
QUERY = ["liquidity", "operations", "rule-status", "list"]
REFRESH = ["refresh", "liquidity", "operations", "rule-status"]

# UTC epoch milliseconds for the inclusive scope bounds.
TRIGGER_MS = 1768478400000  # 2026-01-15 12:00:00 UTC


def record(index=0, **changes):
    return {
        "id": 9007199254740993 + index,  # beyond float-exact 2**53
        "ruleId": f"synthetic-rule-{index}",
        "ruleName": "excluded free text",
        "tntInstId": "GUAPW3SG",
        "executeStatus": "EXECUTED",
        "createdOrder": "Y",
        "bizNo": f"synthetic-biz-{index}",
        "orderStatus": "PAID",
        "expectTriggerTime": TRIGGER_MS + index * 1000,
        "realTriggerTime": TRIGGER_MS + index * 1000 + 1,
        "gmtCreate": TRIGGER_MS - 1000,
        "gmtModified": TRIGGER_MS - 999,
        "expectTriggerDate": "20260115",
        "debitAmount": "excluded-amount",
        "accountNo": "excluded-account",
        "aliasName": "excluded-alias",
        **changes,
    }


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "data": rows,
                "count": len(rows) if total is None else total,
            },
        },
    }


def listing(rows, start=SCOPE[1], end=SCOPE[3]):
    def answer(payload, index):
        assert set(payload) == {"tntInstId", "transferRuleRecordQueryRequesVO"}
        vo = json.loads(payload["transferRuleRecordQueryRequesVO"])
        assert vo["tntInstId"] == payload["tntInstId"] == "GUAPW3SG"
        assert vo["queryDetailed"] == "false"
        assert vo["executeStatusList"] == []
        assert vo["createdOrderList"] == []
        assert vo["orderStatusList"] == []
        assert vo["rowStart"] == 0
        assert vo["pageSize"] == 5000
        assert vo["triggerStartTime"] == start
        assert vo["triggerEndTime"] == end
        return response(rows)

    return answer


SCOPE_START_MS = 1767225600000  # 2026-01-01 00:00:00 UTC
SCOPE_END_MS = 1769903999000  # 2026-01-31 23:59:59 UTC


Z_SCOPE = [
    "--trigger-from",
    "2026-01-01T00:00:00Z",
    "--trigger-to",
    "2026-01-31T23:59:59Z",
]
# Explicit numeric offsets spelling the same instants (UTC/+08 day rollover).
OFFSET_SCOPE = [
    "--trigger-from",
    "2026-01-01T08:00:00+08:00",
    "--trigger-to",
    "2026-02-01T07:59:59+08:00",
]
