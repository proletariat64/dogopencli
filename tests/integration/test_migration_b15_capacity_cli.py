"""VA capacity exercises SDK short-page acquisition through installed packages."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

pytest_plugins = ["integration.test_leaf_handbook"]
ROOT = Path(__file__).resolve().parents[2]
LEAF = "va.capacity"


@pytest.fixture
def sample_source():
    return ROOT / "leaf_packages/collection/va.capacity"


@pytest.fixture(autouse=True)
def collection_entry(handbook):
    handbook[1].href = "https://ifundbossportal.alipay.com/voucher/VARuleManage"


def records(count=102):
    return [
        {
            "ruleId": str(index),
            "bankAccountVaId": "BANK-ONE" if index % 2 else "BANK-TWO",
            "totalCount": 1000,
            "unknown": [None, False, Decimal("0.123456789012345678901")],
        }
        for index in range(count)
    ]


def reply(rows, page, total=None):
    body = {"success": True, "pageNo": page, "pageSize": 100, "resultDataList": rows}
    if total is not None:
        body["totalCount"] = total
    return {"status": 200, "body": body}


def pages(rows):
    # The first total is deliberately smaller than the first page's arrivals.
    return [
        reply(rows[:100], 1, 1),
        reply(rows[100:], 2, "backend-bug"),
        reply([], 3),
        reply([], 4),
    ]


def test_installed_capacity_live_refresh_offline_and_local_filters(handbook):
    cli, browser, _ = handbook
    cli("collection", "list", LEAF, "--help")
    description = cli("collection", "describe", LEAF)
    assert "short_page" in str(description)
    assert not browser.business_requests
    rows = records()
    browser.business_script.extend(pages(rows))
    live = cli(
        "collection", "list", LEAF, "--live", "--require-complete", "--limit", "0"
    )
    assert live["data"] == rows
    assert live["meta"]["reported_total"] is None
    assert live["meta"]["acquisition"]["coverage_basis"] == "qualified_short_page"
    assert live["meta"]["acquisition"]["arrivals"] == 102
    assert browser.business_requests == [
        {"pageNo": 1, "pageSize": 100},
        {"pageNo": 2, "pageSize": 100},
        {"pageNo": 3, "pageSize": 100},
        {"pageNo": 4, "pageSize": 100},
    ]
    browser.business_script.extend(pages(rows))
    cli("collection", "refresh", LEAF, "--require-complete")
    saved = cli("collection", "list", LEAF, "--limit", "0")
    assert saved["data"] == rows
    assert saved["meta"]["acquisition"]["coverage_basis"] == "qualified_short_page"
    calls = len(browser.business_requests)
    selected = cli(
        "collection",
        "list",
        LEAF,
        "--bank-va-rule-id",
        "BANK-ONE",
        "--va-rule-id",
        "1",
        "--va-rule-id",
        "2",
        "--limit",
        "0",
    )
    assert selected["data"] == [rows[1]]
    assert len(browser.business_requests) == calls
    browser.business_script.extend(pages(rows))
    selected_live = cli(
        "collection",
        "list",
        LEAF,
        "--live",
        "--bank-va-rule-id",
        "BANK-ONE",
        "--va-rule-id",
        "1",
        "--limit",
        "0",
    )
    assert selected_live["data"] == [rows[1]]
    after = cli("collection", "list", LEAF, "--limit", "0")
    assert after["data"] == saved["data"]
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert all(set(q) == {"pageNo", "pageSize"} for q in browser.business_requests)


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate",
        "conflict",
        "business",
        "auth",
        "echo",
        "missing-rows",
        "missing-id",
        "empty",
    ],
)
def test_failed_or_empty_capacity_refresh_preserves_snapshot(handbook, failure):
    cli, browser, _ = handbook
    rows = records()
    browser.business_script.extend(pages(rows))
    cli("collection", "refresh", LEAF)
    saved = cli("collection", "list", LEAF, "--limit", "0")
    first, last, *confirmations = pages(deepcopy(rows))
    if failure in {"duplicate", "conflict"}:
        last["body"]["resultDataList"] = [deepcopy(rows[0])]
        if failure == "conflict":
            last["body"]["resultDataList"][0]["totalCount"] = 999
    elif failure == "business":
        last["body"]["success"] = False
    elif failure == "auth":
        last["status"] = 401
    elif failure == "echo":
        last["body"]["pageNo"] = 1
    elif failure == "missing-rows":
        del last["body"]["resultDataList"]
    elif failure == "missing-id":
        del last["body"]["resultDataList"][0]["ruleId"]
    if failure == "empty":
        browser.business_script.extend([reply([], 1), reply([], 2)])
        assert cli("collection", "refresh", LEAF)["meta"]["published"] is False
    else:
        browser.business_script.extend([first, last, *confirmations])
        rejected = cli("collection", "refresh", LEAF, code=1)
        assert rejected["data"] is None
        assert rejected["error"]["code"] == (
            "INCOMPLETE_RESULT"
            if failure in {"duplicate", "conflict"}
            else "BUSINESS_QUERY_FAILED"
            if failure == "business"
            else "AUTH_REQUIRED"
            if failure == "auth"
            else "INVALID_RESPONSE"
        )
    after = cli("collection", "list", LEAF, "--limit", "0")
    assert after["data"] == saved["data"]
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_exact_multiple_queries_empty_terminal_page(handbook):
    cli, browser, _ = handbook
    rows = records(100)
    browser.business_script.extend(
        [reply(rows, 1, 0), reply([], 2, 0), reply([], 3, 0)]
    )
    result = cli(
        "collection", "list", LEAF, "--live", "--require-complete", "--limit", "0"
    )
    assert result["data"] == rows
    assert (
        result["meta"]["acquisition"]["attempts"][-1]["termination_reason"]
        == "two_empty_batches"
    )
    assert len(browser.business_requests) == 3
