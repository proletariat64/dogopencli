"""Native-shaped synthetic task details through CLI, fake CDP and SQLite."""

import json
from pathlib import Path

import pytest

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
