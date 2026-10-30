"""Transfer business calendar and version selection through the public CLI."""

import json
from pathlib import Path

import pytest
from integration.leaves.liquidity.test_operations_cli import (
    installed as operations_installed,
)
from integration.leaves.liquidity.test_operations_cli import (
    page,
    record,
)

from dogopencli.jsonutil import parse

installed = operations_installed

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize(
    "start,end,wire_start,wire_end",
    [
        ("2026-01-15", "2026-01-15", "2026-01-14 08:00:00", "2026-01-15 07:59:59"),
        ("2026-07-15", "2026-07-15", "2026-07-14 09:00:00", "2026-07-15 08:59:59"),
        ("2026-03-08", "2026-03-08", "2026-03-07 08:00:00", "2026-03-08 08:59:59"),
        ("2025-11-02", "2025-11-02", "2025-11-01 09:00:00", "2025-11-02 07:59:59"),
        ("2026-03-07", "2026-03-09", "2026-03-06 08:00:00", "2026-03-09 08:59:59"),
        ("2025-11-01", "2025-11-03", "2025-10-31 09:00:00", "2025-11-03 07:59:59"),
    ],
)
def test_calendar_plan_converts_each_endpoint_independently(
    run_cli, start, end, wire_start, wire_end
):
    code, out, error = run_cli(
        [
            "plugins",
            "install",
            str(ROOT / "leaf_packages/liquidity/operations.transfers"),
        ]
    )
    assert code == 0, out + error
    code, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity.operations.transfers",
            "--mode",
            "history",
            "--parameters",
            json.dumps({"from-date": start, "to-date": end}),
        ]
    )
    assert code == 0, out + error
    plan = json.loads(out)["data"]
    assert plan["desired_range"] == {"from": start, "to": end}
    assert plan["contract"]["time_basis"] == "gmtCreate"
    assert plan["contract"]["timezone"] == "GMT+08"
    assert plan["contract"]["cross_range_equivalence"] is False
    assert plan["native_scope"]["transactionStartDate"] == wire_start
    assert plan["native_scope"]["transactionEndDate"] == wire_end


@pytest.mark.parametrize("installed", ["transfers"], indirect=True)
@pytest.mark.parametrize("newer_first", [False, True])
@pytest.mark.parametrize("strict", [False, True])
def test_versions_return_latest_complete_native_record(installed, newer_first, strict):
    case, cli, browser, _ = installed
    old = {**record(case), "gmtModified": "2026-09-30 01:00:00（GMT+08）"}
    new = {
        **old,
        "gmtModified": "2026-09-30 02:00:00（GMT+08）",
        "orderStatus": "UPDATED_NATIVE_STATE",
        "transFerOrderLogVoList": [{"nested": [None, "0.00000001", False]}],
    }
    other = {**record(case, 1), "gmtModified": "2026-09-30 00:00:00（GMT+08）"}
    arrivals = [new, other, old] if newer_first else [old, other, new]
    browser.business_script.append(page(case, arrivals, 2))
    flags = ("--require-complete",) if strict else ()
    result = cli("refresh", *flags)
    assert result["error"] is None
    assert result["meta"]["complete"] is True
    assert result["meta"]["outcome"] == "warning"
    assert result["meta"]["warnings"]
    assert result["meta"]["published"] is True
    offline = cli("list", "--limit", "0", *flags)
    assert offline["data"] == [new, other]
    assert offline["meta"]["acquisition"] == result["meta"]["acquisition"]


@pytest.mark.parametrize("installed", ["transfers"], indirect=True)
@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "2026-09-30 01:00:00",
        "2026-02-30 01:00:00（GMT+08）",
        "2026-09-30 01:00:00（GMT+00）",
        1,
    ],
)
def test_invalid_version_clock_fails_without_publication(installed, value):
    case, cli, browser, _ = installed
    browser.business_script.append(page(case, [{**record(case), "gmtModified": value}]))
    result = cli("refresh", code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result["meta"]["published"] is False


@pytest.mark.parametrize("installed", ["transfers"], indirect=True)
def test_reserved_ordering_field_cannot_replace_native_value(installed):
    case, cli, browser, _ = installed
    browser.business_script.append(
        page(
            case,
            [
                {
                    **record(case),
                    "gmtModified": "2026-09-30 01:00:00（GMT+08）",
                    "__dogopencli_transfer_order": 1,
                }
            ],
        )
    )
    assert cli("refresh", code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("installed", ["transfers"], indirect=True)
def test_equal_order_uses_last_arrival_without_merging_fields(installed):
    case, cli, browser, _ = installed
    old = {
        **record(case),
        "gmtModified": "2026-09-30 01:00:00（GMT+08）",
        "old_only": 1,
    }
    new = {key: value for key, value in old.items() if key != "old_only"}
    new["unknown"] = [None, False, "0.001"]
    browser.business_script.append(page(case, [old, old, new], 1))
    result = cli("list", "--live", "--limit", "0", "--require-complete")
    assert result["data"] == [new]
    assert result["error"] is None
    assert result["meta"]["complete"] is True
    assert result["meta"]["warnings"]


@pytest.mark.parametrize("installed", ["transfers"], indirect=True)
def test_valid_winner_cannot_repair_missing_business_identity(installed):
    case, cli, browser, _ = installed
    old = {**record(case), "gmtModified": "2026-09-30 01:00:00（GMT+08）"}
    new = {**old, "gmtModified": "2026-09-30 02:00:00（GMT+08）"}
    browser.business_script.append(page(case, [old, new], 2))
    result = cli("refresh", "--require-complete", code=1)
    assert result["meta"]["complete"] is False
    assert result["meta"]["published"] is False
    assert result["error"]["code"] == "INCOMPLETE_RESULT"


@pytest.mark.parametrize("installed", ["transfers"], indirect=True)
def test_selected_version_evidence_survives_exact_preserve_import(installed, run_cli):
    case, _, browser, _ = installed
    old = {**record(case), "gmtModified": "2026-09-30 01:00:00（GMT+08）"}
    new = {
        **old,
        "gmtModified": "2026-09-30 02:00:00（GMT+08）",
        "orderStatus": "FINAL",
    }

    def workflow(*args):
        code, out, error = run_cli(["workflow", *args])
        assert code == 0, out + error
        return parse(out)["data"]

    plan = workflow(
        "plan",
        "create",
        "--leaf",
        "liquidity.operations.transfers",
        "--mode",
        "history",
        "--parameters",
        '{"from-date":"2026-09-30","to-date":"2026-09-30"}',
    )
    browser.business_script.append(page(case, [old, new], 1))
    run = workflow("export", "create", "--plan", plan["id"])
    result = workflow("export", "run", "--run", run["id"])
    export_id = result["packages"][0]["export_id"]
    exported = workflow("export", "show", "--export", export_id)
    assert exported["records"] == [new]
    assert "LATEST_BY_SELECTION" in str(exported)
    assert "__dogopencli_transfer_order" not in str(exported["records"])
    prepared = workflow("import", "plan", "--export", export_id, "--action", "preserve")
    requests = len(browser.business_requests)
    workflow("import", "apply", "--plan", prepared["id"])
    retained = workflow("observation", "show", "--export", export_id)
    assert retained["records"] == exported["records"]
    assert "LATEST_BY_SELECTION" in str(retained)
    assert len(browser.business_requests) == requests
