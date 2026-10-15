"""S01 public CLI, fake CDP and temporary SQLite acceptance."""

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "operations", "account_strategies"]


def strategy(alias="SYN-A", version=1, **changes):
    return {
        "aliasName": alias,
        "version": version,
        "entity": "SYN-ENTITY",
        "bankId": "SYN-BANK",
        "currency": "USD",
        "accountType": "CASH",
        "operationStrategy": "Self-Built Cash Pool,No Need,Self-Built Cash Pool",
        "coverAlgorithm": "N",
        "status": "Invalid",
        "processStatus": "APPROVED",
        "lastModifiedTime": "2026-10-15 12:30:00",
        **changes,
    }


def install(setup, rows):
    def answer(payload, index):
        start = payload["rowStart"]
        page = rows[start : start + payload["pageSize"]]
        return {
            "status": 200,
            "body": {"success": True, "data": {"data": page, "totalCount": len(rows)}},
        }

    setup.state.business_handler = answer


def test_default_view_preserves_invalid_and_native_versions_without_status(
    setup, run_cli
):
    rows = [strategy(), strategy(version=2, status="Valid", processStatus="SUBMITTED")]
    install(setup, rows)
    code, out, err = run_cli([*ROOT, "list", "--live", "--limit", "1"])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == rows[:1]
    assert result["meta"]["complete"] is True
    assert result["meta"]["collected_total"] == 2
    assert setup.state.business_requests == [
        {"rowStart": 0, "pageSize": 5000},
        {"rowStart": 2, "pageSize": 5000},
    ]
    assert not setup.cache_path.exists()
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions and all(
        "/strategyManage/queryList.json" in e for e in expressions
    )
    assert all("POST" in e for e in expressions)
