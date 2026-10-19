"""Executable handbook samples for qualified responses and independent sources."""

from decimal import Decimal
from pathlib import Path

import pytest

pytest_plugins = ["integration.test_leaf_handbook"]
ROOT = Path(__file__).resolve().parents[2]
LEFT = [
    {
        "id": "left-one",
        "parentRef": "one",
        "amount": Decimal("0.123456789012345678901"),
    },
    {"id": "left-two", "parentRef": "one", "unknown": [None, False, "1.0000"]},
]
RIGHT = [
    {"id": "right-one", "parentRef": "two", "native": {"nested": []}},
    {"id": "right-two", "parentRef": "one", "amount": "2.0000"},
]
FLAGS = ("--left-scope", "L", "--right-scope", "R")


def reply(rows, *, total=None, success=True):
    value = {"success": success, "rows": rows}
    if total is not None:
        value["total"] = total
    return {"status": 200, "body": value}


@pytest.mark.parametrize(
    "sample_source", [ROOT / "tools/leaf-dev/example-single-response"], indirect=True
)
def test_single_response_sample_help_live_refresh_offline_and_empty_preservation(
    handbook,
):
    cli, browser, _ = handbook
    cli("collection", "list", "sample.response", "-h")
    cli("collection", "describe", "sample.response")
    assert not browser.business_requests
    rows = [{"id": str(index), "native": [False, None, "0.0000"]} for index in range(3)]
    browser.business_script.append(reply(rows))
    live = cli(
        "collection",
        "list",
        "sample.response",
        "--live",
        "--require-complete",
        "--limit",
        "0",
    )
    assert live["data"] == rows
    assert browser.business_requests == [{"scope": "all", "rowStart": 0, "pageSize": 2}]
    assert live["meta"]["reported_total"] is None
    assert live["meta"]["complete"] is True
    assert live["meta"]["acquisition"]["coverage_basis"] == "qualified_single_response"
    browser.business_script.append(reply(rows))
    cli("collection", "refresh", "sample.response", "--require-complete")
    before = cli("collection", "list", "sample.response", "--limit", "0")
    count = len(browser.business_requests)
    assert before["data"] == rows
    assert before["meta"]["acquisition"] == live["meta"]["acquisition"] | {
        "attempts": before["meta"]["acquisition"]["attempts"]
    }
    browser.business_script.append(reply([]))
    empty = cli("collection", "refresh", "sample.response", "--require-complete")
    assert empty["meta"]["published"] is False
    after = cli("collection", "list", "sample.response", "--limit", "0")
    assert after["data"] == before["data"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]
    assert len(browser.business_requests) == count + 1


@pytest.mark.parametrize(
    "sample_source", [ROOT / "tools/leaf-dev/example-single-response"], indirect=True
)
def test_single_response_sample_rejects_duplicate_coverage(handbook):
    cli, browser, _ = handbook
    browser.business_script.append(reply([{"id": "same"}] * 2))
    result = cli(
        "collection", "list", "sample.response", "--live", "--require-complete", code=1
    )
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["data"] is None
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize(
    "sample_source", [ROOT / "tools/leaf-dev/example-sources"], indirect=True
)
def test_sources_sample_keeps_native_children_and_source_evidence_offline(handbook):
    cli, browser, _ = handbook
    cli("collection", "list", "sample.sources", "-h")
    cli("collection", "describe", "sample.sources")
    assert not browser.business_requests
    browser.business_script.extend([reply(LEFT, total=2), reply(RIGHT, total=2)])
    result = cli(
        "collection",
        "list",
        "sample.sources",
        *FLAGS,
        "--live",
        "--require-complete",
        "--limit",
        "0",
    )
    expected = [
        {"parentRef": "one", "left": LEFT, "right": [RIGHT[1]]},
        {"parentRef": "two", "left": [], "right": [RIGHT[0]]},
    ]
    assert result["data"] == expected
    assert browser.business_requests == [
        {"scope": "L", "rowStart": 0, "pageSize": 2},
        {"scope": "R", "rowStart": 0, "pageSize": 2},
    ]
    evidence = result["meta"]["acquisition"]
    assert evidence["reported_total"] is None
    assert evidence["coverage_basis"] == "validated_sources"
    assert evidence["sources"]["left"]["scope"] == "L"
    assert evidence["sources"]["right"]["scope"] == "R"
    assert evidence["sources"]["left"]["acquisition"]["reported_total"] == 2
    assert evidence["sources"]["right"]["acquisition"]["reported_total"] == 2
    browser.business_script.extend([reply(LEFT, total=2), reply(RIGHT, total=2)])
    saved = cli("collection", "refresh", "sample.sources", *FLAGS, "--require-complete")
    count = len(browser.business_requests)
    offline = cli("collection", "list", "sample.sources", "--limit", "0")
    assert offline["data"] == expected
    assert offline["meta"]["acquisition"] == saved["meta"]["acquisition"]
    assert len(browser.business_requests) == count


@pytest.mark.parametrize(
    "sample_source", [ROOT / "tools/leaf-dev/example-sources"], indirect=True
)
def test_sources_sample_never_replaces_failed_source_with_empty_children(handbook):
    cli, browser, _ = handbook
    browser.business_script.extend([reply(LEFT, total=2), reply([], success=False)])
    result = cli("collection", "list", "sample.sources", *FLAGS, "--live", code=1)
    assert result["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert result["data"] is None
    assert result["meta"]["source"] == "right"
