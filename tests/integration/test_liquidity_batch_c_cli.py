"""Verified batch C structures through public CLI, fake CDP and real SQLite."""

from datetime import datetime, timezone

pytest_plugins = ["test_liquidity_cli_sit"]


def page(rows, total):
    return {
        "status": 200,
        "body": {"success": True, "data": {"data": rows, "totalCount": total}},
    }


def strategy(index, task_type="FUND_DECISION_TASK", **overrides):
    return {
        "id": f"synthetic-task-{index}",
        "taskType": task_type,
        "triggerDate": int(
            datetime(2026, 10, 2, tzinfo=timezone.utc).timestamp() * 1000
        ),
        "resultTime": None,
        "valueDate": "20261002",
        "expectedInvestStartDate": "20261002",
        "expectedInvestEndDate": "20261003",
        "fundDecisionStrategyId": "synthetic-fund",
        "investmentPortfolioStrategyId": "",
        "mainStrategyId": "synthetic-main",
        "investmentAmount": "12345678901234567890.0012300",
        "maximumExceptedIncome": "",
        "maximumExpectedRateOfReturn": "0",
        "taskStatus": "future-native-state",
        "adoptionStatus": "future-native-adoption",
        "triggerType": "source-type",
        **overrides,
    }


SCOPES = [
    *[
        (
            "strategy-results",
            [
                "--task-type",
                task,
                "--from-date",
                "20261001",
                "--to-date",
                "20261004",
            ],
            lambda index, task=task, **overrides: strategy(index, task, **overrides),
        )
        for task in ("FUND_DECISION_TASK", "PRODUCT_DECISION_TASK")
    ],
]


def args(leaf, options, *extra, refresh=False):
    return (
        (
            ["refresh", "liquidity", "investment", leaf]
            if refresh
            else ["liquidity", "investment", leaf, "list"]
        )
        + (
            options
            if refresh or "--live" in extra
            else options[:2]
            if options[:1] == ["--task-type"]
            else []
        )
        + list(extra)
    )


def listing(rows):
    def handle(body, index):
        offset = body["rowStart"]
        return page(rows[offset : offset + 10], len(rows))

    return handle
