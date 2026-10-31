"""Funding-demand latest-state selection through the installed public CLI."""

import pytest
from integration.leaves.liquidity.test_operations_cli import (
    installed as operations_installed,
)
from integration.leaves.liquidity.test_operations_cli import page, record

from dogopencli.jsonutil import parse

installed = operations_installed
pytestmark = pytest.mark.parametrize("installed", ["demands"], indirect=True)


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("newer_first", [False, True])
def test_latest_demand_version_preserves_whole_record_and_cache(
    installed, strict, newer_first
):
    case, cli, browser, _ = installed
    old = {**record(case), "gmtModified": "2026-04-02 01:02:03", "old_only": True}
    new = {
        **record(case),
        "gmtModified": "2026-04-02 01:02:04",
        "status": "FINAL",
        "nested": [False, None, "0.00001"],
    }
    other = {**record(case, 1), "gmtModified": "2026-03-30 23:59:59"}
    arrivals = [new, other, old] if newer_first else [old, other, new]
    browser.business_script.append(page(case, arrivals, 2))
    flags = ("--require-complete",) if strict else ()
    result = cli("refresh", *flags)
    assert result["error"] is None
    assert result["meta"]["complete"] is True
    assert result["meta"]["outcome"] == "warning"
    assert result["meta"]["warnings"]
    assert result["meta"]["published"] is True
    requests = len(browser.business_requests)
    offline = cli("list", "--limit", "0", *flags)
    assert offline["data"] == [new, other]
    assert "__dogopencli_demand_order" not in str(offline["data"])
    assert offline["meta"]["acquisition"] == result["meta"]["acquisition"]
    assert len(browser.business_requests) == requests


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        " ",
        1,
        True,
        "2026-02-30 12:00:00",
        "2026-04-02T12:00:00",
        "2026-04-02 12:00:00+08:00",
        "2026-04-02 12:00:00.000",
        "2026-4-2 12:00:00",
    ],
)
def test_invalid_singleton_modification_clock_preserves_cache(installed, value):
    case, cli, browser, _ = installed
    retained = record(case, 77)
    browser.business_script.append(page(case, [retained]))
    saved = cli("refresh", "--require-complete")
    candidate = {**record(case, 88), "gmtModified": value}
    browser.business_script.append(page(case, [candidate]))
    failed = cli("refresh", code=1)
    assert failed["error"]["code"] == "INVALID_RESPONSE"
    assert failed["meta"]["published"] is False
    offline = cli("list", "--limit", "0", "--require-complete")
    assert offline["data"] == [retained]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("change", ["missing", "collision"])
def test_missing_or_reserved_modification_order_is_rejected(installed, change):
    case, cli, browser, _ = installed
    candidate = record(case)
    if change == "missing":
        candidate.pop("gmtModified")
    else:
        candidate["__dogopencli_demand_order"] = 1
    browser.business_script.append(page(case, [candidate]))
    result = cli("list", "--live", code=1)
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("strict", [False, True])
def test_equal_modification_clock_keeps_last_whole_demand(installed, strict):
    case, cli, browser, _ = installed
    old = {**record(case), "old_only": True}
    new = {**record(case), "status": "FINAL", "unknown": [None, False, "0.0001"]}
    browser.business_script.append(page(case, [old, old, new], 1))
    flags = ("--require-complete",) if strict else ()
    result = cli("list", "--live", "--limit", "0", *flags)
    assert result["data"] == [new]
    assert result["error"] is None
    assert result["meta"]["complete"] is True
    assert result["meta"]["warnings"]


def test_demand_winner_does_not_hide_missing_distinct_identity(installed):
    case, cli, browser, _ = installed
    old = {**record(case), "gmtModified": "2026-04-02 01:02:03"}
    new = {**old, "gmtModified": "2026-04-02 01:02:04"}
    browser.business_script.append(page(case, [old, new], 2))
    result = cli("refresh", "--require-complete", code=1)
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["meta"]["complete"] is False
    assert result["meta"]["published"] is False


def test_demand_selection_proof_survives_export_and_preserve_import(installed, run_cli):
    case, _, browser, _ = installed
    old = {**record(case), "gmtModified": "2026-04-02 01:00:00"}
    new = {**old, "gmtModified": "2026-04-02 02:00:00", "status": "FINAL"}

    def workflow(*args):
        code, out, error = run_cli(["workflow", *args])
        assert code == 0, out + error
        return parse(out)["data"]

    plan = workflow(
        "plan",
        "create",
        "--leaf",
        "liquidity.operations.demands",
        "--parameters",
        '{"from-time":"2026-04-01T00:00:00","to-time":"2026-04-02T00:00:00"}',
    )
    browser.business_script.append(page(case, [old, new], 1))
    run = workflow("export", "create", "--plan", plan["id"])
    result = workflow("export", "run", "--run", run["id"])
    exported = workflow("export", "show", "--export", result["id"])
    assert exported["records"] == [new]
    assert "LATEST_BY_SELECTION" in str(exported)
    assert "__dogopencli_demand_order" not in str(exported["records"])
    prepared = workflow(
        "import", "plan", "--export", result["id"], "--action", "preserve"
    )
    requests = len(browser.business_requests)
    workflow("import", "apply", "--plan", prepared["id"])
    retained = workflow("observation", "show", "--export", result["id"])
    assert retained["records"] == [new]
    assert "LATEST_BY_SELECTION" in str(retained)
    assert len(browser.business_requests) == requests
