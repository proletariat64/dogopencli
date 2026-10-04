"""Native-shaped synthetic task details through CLI, fake CDP and SQLite."""

import json
from pathlib import Path

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
TYPES = ("FUND_DECISION_TASK", "PRODUCT_DECISION_TASK")


def fixture(task_type):
    variant = "fund" if task_type == TYPES[0] else "product"
    path = Path(__file__).parents[1] / "fixtures" / "liquidity" / "issue97"
    return json.loads((path / f"strategy-{variant}.json").read_text())


def command(task_type=TYPES[0], *, refresh=False, task_id="synthetic-task-1"):
    path = ["liquidity", "investment", "strategy-results"]
    if refresh:
        path = ["refresh", *path, "detail"]
    return [*path, "get", "--task-id", task_id, "--task-type", task_type]


def answer(setup, document):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": document,
    }


@pytest.mark.parametrize("task_type", TYPES)
def test_refresh_offline_projection_and_variant_isolation(setup, run_cli, task_type):
    answer(setup, fixture(task_type))
    code, out, err = run_cli(command(task_type, refresh=True))
    assert code == 0, (out, err)
    assert setup.state.business_requests == [{"taskId": "synthetic-task-1"}]
    expressions = [
        expression
        for transport in setup.state.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert any("application/x-www-form-urlencoded" in e for e in expressions)
    assert any("/api/increment/decision/task/taskDetail.json" in e for e in expressions)
    setup.state.reachable = False
    code, out, err = run_cli(command(task_type))
    assert code == 0, (out, err)
    result = parse(out)
    assert result["meta"]["source"] == "cache"
    assert result["meta"]["kind"] == "runtimes"
    assert result["meta"]["detail_fetched_at"]
    data = result["data"]
    assert data["taskType"] == task_type
    assert "decisionUser" not in data
    assert "unknownSecret" not in out
    assert "synthetic-private" not in out
    assert "synthetic-free-text" not in out
    if task_type == TYPES[0]:
        money = data["investableFundResultVo"]["currencyFundResultVoList"][0]["amount"]
        assert money == {
            "amount": 12.5,
            "cent": 1250,
            "centFactor": 100,
            "currency": "USD",
            "currencyCode": "USD",
            "currencyValue": "840",
        }
    else:
        assert data["investableFundResultVo"] is None
    other = TYPES[1] if task_type == TYPES[0] else TYPES[0]
    code, out, _ = run_cli(command(other))
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert "refresh liquidity investment strategy-results detail get" in out
    assert len(setup.state.business_requests) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("taskId", "wrong"),
        ("taskId", 1),
        ("taskType", TYPES[1]),
        ("taskType", None),
        ("investableFundResultVo", []),
    ],
)
def test_mismatch_and_malformed_refresh_preserve_prior(setup, run_cli, field, value):
    native = fixture(TYPES[0])
    answer(setup, native)
    assert run_cli(command(refresh=True))[0] == 0
    prior = setup.cache_path.read_bytes()
    native["data"][field] = value
    code, out, _ = run_cli(command(refresh=True))
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == prior
    setup.state.reachable = False
    code, out, _ = run_cli(command())
    assert code == 0
    assert parse(out)["data"]["taskId"] == "synthetic-task-1"


def test_live_does_not_publish_and_offline_miss_never_connects(setup, run_cli):
    code, out, _ = run_cli(command())
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    answer(setup, fixture(TYPES[1]))
    code, out, err = run_cli([*command(TYPES[1]), "--live"])
    assert code == 0, (out, err)
    assert parse(out)["data"]["investableFundResultVo"] is None
    assert run_cli(command(TYPES[1]))[0] == 1


def test_task_type_required_and_discoverable(setup, run_cli):
    for args in (command()[:-2], command("unverified")):
        code, out, _ = run_cli(args)
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.business_requests == []
    code, out, err = run_cli(
        ["help", "liquidity", "investment", "strategy-results", "get"]
    )
    assert code == 0, err
    assert "task-type" in out
    assert "FUND_DECISION_TASK" in out
    code, out, err = run_cli(
        ["describe", "liquidity", "investment", "strategy-results", "get"]
    )
    assert code == 0, err
    assert "PRODUCT_DECISION_TASK" in out


def test_same_task_id_in_two_variants_keeps_independent_records(setup, run_cli):
    for task_type in TYPES:
        answer(setup, fixture(task_type))
        assert run_cli(command(task_type, refresh=True))[0] == 0
    setup.state.reachable = False
    for task_type in TYPES:
        code, out, _ = run_cli(command(task_type))
        assert code == 0
        assert parse(out)["data"]["taskType"] == task_type


@pytest.mark.parametrize(
    "target,field,value",
    [
        ("money", "amount", "missing"),
        ("money", "currency", "missing"),
        ("money", "currency", None),
        ("money", "currency", ""),
        ("money", "currency", "dollars"),
        ("date", "valueDate", "missing"),
        ("date", "valueDate", "20260230"),
        ("date", "valueDate", "not-a-date"),
        ("date", "currency", "EUR"),
        ("date", "sumAmount", "missing"),
        ("date", "sumAmount", {}),
    ],
)
def test_monetary_and_dated_anchors_preserve_prior(
    setup, run_cli, target, field, value
):
    native = fixture(TYPES[0])
    answer(setup, native)
    assert run_cli(command(refresh=True))[0] == 0
    prior = setup.cache_path.read_bytes()
    fund = native["data"]["investableFundResultVo"]
    if target == "money":
        item = fund["currencyFundResultVoList"][0]["amount"]
        item["amount"] = 0
    else:
        item = fund["investableInvestableFundDetailMap"]["USD"][0]
    if value == "missing":
        del item[field]
    else:
        item[field] = value
    code, out, _ = run_cli(command(refresh=True))
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == prior


def test_nullable_money_and_blank_optional_fields_preserved(setup, run_cli):
    native = fixture(TYPES[0])
    total = native["data"]["investableFundResultVo"]["currencyFundResultVoList"][0]
    total["safetyBufferAmount"] = None
    total["tenor"] = ""
    total["amount"]["amount"] = 0
    del total["amount"]["currencyValue"]
    answer(setup, native)
    code, out, err = run_cli(command(refresh=True))
    assert code == 0, (out, err)
    setup.state.reachable = False
    code, out, err = run_cli(command())
    assert code == 0, (out, err)
    result = parse(out)["data"]["investableFundResultVo"]["currencyFundResultVoList"][0]
    assert result["safetyBufferAmount"] is None
    assert result["tenor"] == ""
    assert result["amount"]["amount"] == 0
    assert result["amount"]["currency"] == "USD"
    assert "currencyValue" not in result["amount"]
