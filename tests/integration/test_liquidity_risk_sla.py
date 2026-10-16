"""Issue #109 public CLI, fake CDP and real SQLite; synthetic records only."""

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
QUERY = ["liquidity", "risk", "sla", "list", "--limit", "0"]
REFRESH = ["refresh", "liquidity", "risk", "sla"]


def row(identity="SYN-SLA"):
    return {
        "slaConfigId": identity,
        "riskEventType": "UNKNOWN-EVENT",
        "effectiveStatus": "UNKNOWN-STATE",
        "processStatus": "",
        "version": "0007.0100",
        "tntInstId": "GUAPW3SG",
        "gmtCreate": None,
        "gmtModified": "unknown-native-time",
        "slaRuleVOList": [{"notificationRecipients": ["SYN-PRIVATE"]}],
        "creator": "SYN-PRIVATE",
        "detailUrl": "https://example.invalid/private",
        "processId": "SYN-PRIVATE",
    }


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


def seed(setup, run_cli, rows=None):
    setup.state.business_handler = lambda payload, index: response(
        [row()] if rows is None else rows
    )
    code, out, err = run_cli([*REFRESH, "--require-complete"])
    assert code == 0, (out, err)
    return parse(out)
