"""Swap latest complete document selection through the installed public CLI."""

import pytest
from integration.leaves.liquidity.test_operations_cli import (
    installed as operations_installed,
)
from integration.leaves.liquidity.test_operations_cli import page, record

from dogopencli.jsonutil import parse

installed = operations_installed


@pytest.mark.parametrize("installed", ["swaps"], indirect=True)
@pytest.mark.parametrize("newer_first", [False, True])
@pytest.mark.parametrize("strict", [False, True])
def test_versions_return_latest_complete_swap_record(installed, newer_first, strict):
    case, cli, browser, _ = installed
    old = {**record(case), "gmtModified": 100, "old_only": "retired"}
    new = {key: value for key, value in old.items() if key != "old_only"}
    new.update(
        gmtModified=200,
        orderStatus="FINAL_NATIVE_STATE",
        unknown={"native": [None, False, "0.000000000000000001"]},
    )
    other = {**record(case, 1), "gmtModified": 150}
    arrivals = [new, other, old] if newer_first else [old, other, new]
    browser.business_script.append(page(case, arrivals, 2))
    flags = ("--require-complete",) if strict else ()
    saved = cli("refresh", *flags)
    assert saved["error"] is None
    assert saved["meta"]["complete"] is True
    assert saved["meta"]["published"] is True
    acquisition = saved["meta"]["acquisition"]
    assert acquisition["arrivals"] == 3
    assert acquisition["reported_total"] == 2
    assert acquisition["collected_total"] == 2
    assert acquisition["selection"]["latest_by"] == "gmtModified"
    assert saved["meta"]["outcome"] == "warning"
    assert "LATEST_BY_SELECTION" in str(saved["meta"]["warnings"])
    before = len(browser.business_requests)
    offline = cli("list", "--limit", "0", *flags)
    assert offline["data"] == [new, other]
    assert offline["meta"]["acquisition"] == saved["meta"]["acquisition"]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == before


@pytest.mark.parametrize("installed", ["swaps"], indirect=True)
@pytest.mark.parametrize("strict", [False, True])
def test_equal_order_ties_keep_last_whole_row_and_duplicate_evidence(installed, strict):
    case, cli, browser, _ = installed
    first = {**record(case), "gmtModified": 200, "old_only": "not merged"}
    last = {key: value for key, value in first.items() if key != "old_only"}
    last["unknown"] = {"last": [False, None, "1.000000000000000001"]}
    browser.business_script.append(page(case, [first, first, last], 1))
    flags = ("--require-complete",) if strict else ()
    result = cli("list", "--live", "--limit", "0", *flags)
    assert result["data"] == [last]
    assert result["error"] is None
    assert result["meta"]["complete"] is True
    selection = result["meta"]["acquisition"]["selection"]
    assert selection["resolved_version_count"] == 1
    assert selection["equal_order_count"] == 1
    assert selection["identical_duplicate_count"] == 1
    assert "LATEST_BY_SELECTION" in str(result["meta"]["warnings"])


@pytest.mark.parametrize("installed", ["swaps"], indirect=True)
@pytest.mark.parametrize(
    "value", [None, "", "200", True, False, 1.0, [], {}, "missing"]
)
def test_required_integer_order_rejects_singleton_and_preserves_cache(installed, value):
    case, cli, browser, _ = installed
    original = {**record(case), "gmtModified": 100}
    browser.business_script.append(page(case, [original]))
    saved = cli("refresh", "--require-complete")
    invalid = {**original, "gmtModified": value}
    if value == "missing":
        invalid.pop("gmtModified")
    browser.business_script.append(page(case, [invalid]))
    rejected = cli("refresh", code=1)
    assert rejected["error"]["code"] == "INVALID_RESPONSE"
    assert rejected["data"] is None
    assert rejected["meta"]["published"] is False
    offline = cli("list", "--limit", "0", "--require-complete")
    assert offline["data"] == [original]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("installed", ["swaps"], indirect=True)
def test_latest_winner_cannot_hide_a_missing_distinct_swap(installed):
    case, cli, browser, _ = installed
    original = {**record(case), "gmtModified": 100}
    browser.business_script.append(page(case, [original]))
    saved = cli("refresh", "--require-complete")
    latest = {**original, "gmtModified": 200, "orderStatus": "UPDATED"}
    browser.business_script.append(page(case, [original, latest], 2))
    rejected = cli("refresh", "--require-complete", code=1)
    assert rejected["error"]["code"] == "INCOMPLETE_RESULT"
    assert rejected["meta"]["complete"] is False
    assert rejected["meta"]["published"] is False
    assert rejected["meta"]["acquisition"]["reported_total"] == 2
    assert rejected["meta"]["acquisition"]["collected_total"] == 1
    offline = cli("list", "--limit", "0")
    assert offline["data"] == [original]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("installed", [("swaps", "zip")], indirect=True)
def test_version_selection_survives_exact_export_preserve_import(installed, run_cli):
    case, _, browser, _ = installed
    old = {**record(case), "gmtModified": 100}
    latest = {**old, "gmtModified": 200, "orderStatus": "FINAL"}

    def workflow(*args):
        code, out, error = run_cli(["workflow", *args])
        assert code == 0, out + error
        return parse(out)["data"]

    plan = workflow(
        "plan",
        "create",
        "--leaf",
        "liquidity.operations.swaps",
        "--mode",
        "history",
        "--parameters",
        '{"from-date":"2026-09-30","to-date":"2026-09-30"}',
    )
    browser.business_script.append(page(case, [old, latest], 1))
    run = workflow("export", "create", "--plan", plan["id"])
    exported_run = workflow("export", "run", "--run", run["id"])
    export_id = exported_run["packages"][0]["export_id"]
    exported = workflow("export", "show", "--export", export_id)
    assert exported["records"] == [latest]
    assert "LATEST_BY_SELECTION" in str(exported)
    import_plan = workflow(
        "import", "plan", "--export", export_id, "--action", "preserve"
    )
    before = len(browser.business_requests)
    workflow("import", "apply", "--plan", import_plan["id"])
    retained = workflow("observation", "show", "--export", export_id)
    assert retained["records"] == exported["records"]
    assert "LATEST_BY_SELECTION" in str(retained)
    assert retained["scope"] == exported["metadata"]["scope"]
    assert len(browser.business_requests) == before
