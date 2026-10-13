"""Native-shaped synthetic task details through CLI, fake CDP and SQLite."""

import json
from pathlib import Path

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]


@pytest.fixture(autouse=True)
def native_details_do_not_create_cache(setup, request):
    yield
    if request.node.originalname not in {
        "test_populated_parent_list_does_not_substitute_native_get",
        "test_native_get_does_not_touch_parent_list_cache",
        "test_asset_list_cache_cannot_satisfy_or_be_changed_by_native_get",
    }:
        assert not setup.cache_path.exists()


TYPES = ("FUND_DECISION_TASK", "PRODUCT_DECISION_TASK")


def fixture(task_type):
    variant = "fund" if task_type == TYPES[0] else "product"
    path = Path(__file__).parents[1] / "fixtures" / "liquidity" / "issue97"
    return json.loads((path / f"strategy-{variant}.json").read_text())


def command(task_type=TYPES[0], *, task_id="synthetic-task-1"):
    return [
        "liquidity",
        "investment",
        "strategy-results",
        "get",
        "--task-id",
        task_id,
        "--task-type",
        task_type,
    ]


def answer(setup, document):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": document,
    }


@pytest.mark.parametrize("task_type", TYPES)
def test_native_strategy_projection_and_variant_identity(setup, run_cli, task_type):
    answer(setup, fixture(task_type))
    code, out, err = run_cli(command(task_type))
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
    code, out, err = run_cli(command(task_type))
    assert code == 0, (out, err)
    result = parse(out)
    assert result["meta"]["source"] == "live"
    assert result["meta"]["kind"] == "runtimes"
    assert result["meta"]["fetched_at"]
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
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert len(setup.state.business_requests) == 3


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
def test_native_strategy_mismatch_and_malformed_response_refuse(
    setup, run_cli, field, value
):
    native = fixture(TYPES[0])
    answer(setup, native)
    assert run_cli(command())[0] == 0
    assert not setup.cache_path.exists()
    native["data"][field] = value
    code, out, _ = run_cli(command())
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()
    assert parse(out)["data"] is None


def test_native_get_does_not_publish_or_replay_when_browser_unavailable(setup, run_cli):
    answer(setup, fixture(TYPES[1]))
    code, out, err = run_cli(command(TYPES[1]))
    assert code == 0, (out, err)
    assert parse(out)["data"]["investableFundResultVo"] is None
    assert not setup.cache_path.exists()
    setup.state.running = False
    code, out, _ = run_cli(command(TYPES[1]))
    assert code == 1 and parse(out)["error"]["code"] == "BROWSER_UNAVAILABLE"
    assert parse(out)["data"] is None


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


def test_same_task_id_requests_each_native_variant_without_cache(setup, run_cli):
    for task_type in TYPES:
        answer(setup, fixture(task_type))
        code, out, err = run_cli(command(task_type))
        assert code == 0, (out, err)
        assert parse(out)["data"]["taskType"] == task_type
    assert len(setup.state.business_requests) == 2
    assert not setup.cache_path.exists()


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
def test_monetary_and_dated_anchors_refuse_invalid_response(
    setup, run_cli, target, field, value
):
    native = fixture(TYPES[0])
    answer(setup, native)
    assert run_cli(command())[0] == 0
    assert not setup.cache_path.exists()
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
    code, out, _ = run_cli(command())
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


def test_nullable_money_and_blank_optional_fields_preserved(setup, run_cli):
    native = fixture(TYPES[0])
    total = native["data"]["investableFundResultVo"]["currencyFundResultVoList"][0]
    total["safetyBufferAmount"] = None
    total["tenor"] = ""
    total["amount"]["amount"] = 0
    del total["amount"]["currencyValue"]
    answer(setup, native)
    code, out, err = run_cli(command())
    assert code == 0, (out, err)
    code, out, err = run_cli(command())
    assert code == 0, (out, err)
    result = parse(out)["data"]["investableFundResultVo"]["currencyFundResultVoList"][0]
    assert result["safetyBufferAmount"] is None
    assert result["tenor"] == ""
    assert result["amount"]["amount"] == 0
    assert result["amount"]["currency"] == "USD"
    assert "currencyValue" not in result["amount"]
