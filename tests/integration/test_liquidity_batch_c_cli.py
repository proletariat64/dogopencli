"""Verified batch C structures through public CLI, fake CDP and real SQLite."""

from datetime import datetime, timezone

import pytest

from dogopencli.jsonutil import parse

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
                "--trigger-from",
                "20261001",
                "--trigger-to",
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
        + options
        + list(extra)
    )


def listing(rows):
    def handle(body, index):
        offset = body["rowStart"]
        return page(rows[offset : offset + 10], len(rows))

    return handle


@pytest.mark.parametrize("task", ["FUND_DECISION_TASK", "PRODUCT_DECISION_TASK"])
def test_strategy_variant_wire_scope_projection_and_offline_isolation(
    setup, run_cli, task
):
    options = [
        "--task-type",
        task,
        "--trigger-from",
        "20261001",
        "--trigger-to",
        "20261004",
    ]
    rows = [strategy(index, task) for index in range(12)]
    for index, value in enumerate((None, "", "0")):
        rows[index]["investmentAmount"] = value
    raw = [
        dict(
            row,
            decisionUser="SYNTHETIC PRIVATE",
            mainStrategyVo={"private": "SYNTHETIC"},
            unknownMemo="SYNTHETIC",
        )
        for row in rows
    ]

    def handle(body, index):
        assert body["taskType"] == task
        assert body["triggerStartDate"] == "2026-10-01 00:00:00"
        assert body["triggerEndDate"] == "2026-10-04 23:59:59"
        assert body["pageSize"] == 10
        return listing(raw)(body, index)

    setup.state.business_handler = handle
    code, out, err = run_cli(args("strategy-results", options, refresh=True))
    assert code == 0, err
    refreshed = parse(out)
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(args("strategy-results", options, "--live", "--all"))
    assert code == 0, err
    assert sorted(parse(out)["data"], key=lambda row: row["id"]) == sorted(
        rows, key=lambda row: row["id"]
    )
    assert setup.cache_path.read_bytes() == before
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(args("strategy-results", options, "--all"))
    assert code == 0, err
    cached = parse(out)
    assert sorted(cached["data"], key=lambda row: row["id"]) == sorted(
        rows, key=lambda row: row["id"]
    )
    assert cached["meta"]["scope"] == refreshed["meta"]["scope"]
    assert cached["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert len(setup.state.business_requests) == count
    other = (
        "PRODUCT_DECISION_TASK"
        if task == "FUND_DECISION_TASK"
        else "FUND_DECISION_TASK"
    )
    changed = [other if value == task else value for value in options]
    code, out, _ = run_cli(args("strategy-results", changed))
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert len(setup.state.business_requests) == count
    assert b"SYNTHETIC PRIVATE" not in setup.cache_path.read_bytes()
    setup.state.reachable = True
    other_rows = [strategy(0, other)]
    setup.state.business_handler = listing(other_rows)
    code, _, err = run_cli(args("strategy-results", changed, refresh=True))
    assert code == 0, err
    setup.state.reachable = False
    for scope, expected in ((options, rows), (changed, other_rows)):
        code, out, err = run_cli(args("strategy-results", scope, "--all"))
        assert code == 0, err
        assert sorted(parse(out)["data"], key=lambda row: row["id"]) == sorted(
            expected, key=lambda row: row["id"]
        )


@pytest.mark.parametrize("leaf,options,record", SCOPES)
def test_complete_empty_and_live_isolation(setup, run_cli, leaf, options, record):
    setup.state.business_handler = listing([])
    code, out, err = run_cli(args(leaf, options, "--live", "--all"))
    assert code == 0, err
    assert parse(out)["data"] == []
    assert parse(out)["meta"]["complete"] is True

    assert not setup.cache_path.exists()
    code, out, err = run_cli(args(leaf, options, "--require-complete", refresh=True))
    assert code == 0, err
    assert parse(out)["meta"]["published"] is True
    setup.state.reachable = False
    code, out, err = run_cli(args(leaf, options, "--all", "--require-complete"))
    assert code == 0, err
    assert parse(out)["data"] == []
    assert parse(out)["meta"]["complete"] is True


def test_offline_describe_declares_both_variants_and_source_units(setup, run_cli):
    setup.state.reachable = False
    code, out, err = run_cli(
        ["describe", "liquidity", "investment", "strategy-results", "list"]
    )
    assert code == 0, err
    description = parse(out)
    guide = description["read_guide"]
    assert guide["live_verified"] == "2026-10-04"
    assert guide["identity"] == ["taskType", "id"]
    assert guide["offline_profile"] == "history"
    variants = {item["selectors"]["task_type"]: item for item in guide["variants"]}
    assert set(variants) == {"FUND_DECISION_TASK", "PRODUCT_DECISION_TASK"}
    for task, item in variants.items():
        properties = item["data_schema"]["properties"]
        assert properties["investmentAmount"]["x-unit"] == "equivalent USD"
        assert properties["triggerDate"]["x-unit"] == "epoch milliseconds"
        assert (
            properties["maximumExpectedRateOfReturn"]["x-evidence"]["unit"] == "unknown"
        )
        assert "decisionUser" not in properties
        assert "mainStrategyVo" not in properties
        if task == "PRODUCT_DECISION_TASK":
            assert properties["maximumExceptedIncome"]["x-unit"] == "equivalent USD"
        else:
            assert "x-unit" not in properties["maximumExceptedIncome"]
    assert not setup.state.business_requests


@pytest.mark.parametrize(
    "leaf,options",
    [
        ("strategy-results", []),
        (
            "strategy-results",
            [
                "--task-type",
                "UNKNOWN",
                "--trigger-from",
                "20261001",
                "--trigger-to",
                "20261004",
            ],
        ),
        (
            "strategy-results",
            [
                "--task-type",
                "FUND_DECISION_TASK",
                "--trigger-from",
                "20261005",
                "--trigger-to",
                "20261004",
            ],
        ),
        (
            "strategy-results",
            [
                "--task-type",
                "FUND_DECISION_TASK",
                "--trigger-from",
                "20260230",
                "--trigger-to",
                "20261004",
            ],
        ),
    ],
)
def test_scope_rejected_before_transport(setup, run_cli, leaf, options):
    for refresh in (False, True):
        code, out, _ = run_cli(
            args(
                leaf,
                options,
                "--live" if not refresh else "--require-complete",
                refresh=refresh,
            )
        )
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert not setup.state.business_requests
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("leaf,options,record", SCOPES)
@pytest.mark.parametrize(
    "defect",
    [
        "total-drift",
        "identity-conflict",
        "business-envelope",
        "wrong-date",
        "wrong-type",
        "bad-number",
        "wrong-task-type",
        "wrong-tenant",
        "auth",
    ],
)
def test_hard_failures_preserve_complete_cache(
    setup, run_cli, leaf, options, record, defect
):
    setup.state.business_handler = listing([record(0)])
    code, _, err = run_cli(args(leaf, options, refresh=True))
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    def fail(body, index):
        if defect == "auth":
            return {"status": 401, "body": {"success": False}}
        if defect == "wrong-task-type":
            return page([record(0, taskType="UNVERIFIED")], 1)
        if defect == "wrong-tenant":
            return page([record(0, tntInstId="OTHER")], 1)
        if defect == "business-envelope":
            return {"status": 200, "body": {"success": False, "errorCode": "SYNTHETIC"}}
        if defect == "wrong-date":
            overrides = {"triggerDate": 0}
            return page([record(0, **overrides)], 1)
        if defect == "wrong-type":
            return page([record(0, id=True)], 1)
        if defect == "bad-number":
            field = "investmentAmount"
            return page([record(0, **{field: "NaN"})], 1)
        if body["rowStart"] == 0:
            return page([record(i) for i in range(10)], 12)
        if defect == "identity-conflict":
            field = "investmentAmount"
            return page([record(0, **{field: "999"}), record(10)], 12)
        return page([record(10), record(11)], 13)

    setup.state.business_handler = fail
    for refresh in (False, True):
        code, out, _ = run_cli(
            args(
                leaf,
                options,
                *([] if refresh else ["--live", "--all"]),
                refresh=refresh,
            )
        )
        assert code == 1
        assert parse(out)["data"] is None
        assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("leaf,options,record", SCOPES)
def test_overlap_warns_and_strict_refresh_does_not_publish(
    setup, run_cli, leaf, options, record
):
    setup.state.business_handler = listing([record(0)])
    code, _, err = run_cli(args(leaf, options, refresh=True))
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    def overlap(body, index):
        return page(
            [record(i) for i in range(10)]
            if body["rowStart"] == 0
            else [record(0), record(10)],
            12,
        )

    setup.state.business_handler = overlap
    code, out, err = run_cli(args(leaf, options, "--live", "--all"))
    result = parse(out)
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    assert result["meta"]["complete"] is False
    assert len(result["data"]) == 11
    assert result["meta"]["missing_count"] == 1
    assert setup.cache_path.read_bytes() == before
    for refresh in (False, True):
        code, out, _ = run_cli(
            args(
                leaf,
                options,
                "--require-complete",
                *([] if refresh else ["--live"]),
                refresh=refresh,
            )
        )
        assert code == 1
        assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
        assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(args(leaf, options, refresh=True))
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["published"] is True
    setup.state.reachable = False
    code, out, err = run_cli(args(leaf, options, "--all"))
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["complete"] is False
