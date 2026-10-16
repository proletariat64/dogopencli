"""Public risk detail CLI with native-shape, wholly synthetic fixture values."""

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


FIXTURE = Path(__file__).parents[1] / "fixtures/liquidity/risk_detail_sanitized.json"


def response(mode):
    doc = json.loads(FIXTURE.read_text())
    doc["data"]["riskMode"] = mode
    return doc


def command(resource, *, identity="synthetic-risk-001"):
    return ["liquidity", "risk", resource, "get", "--risk-event-id", identity]
