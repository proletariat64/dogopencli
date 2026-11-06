"""Plan-driven preservation of qualified incomplete full List exports."""

import json
import os
import shutil
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fake_cdp import FakeBrowser
from leaves.liquidity.test_cash_accounts_cli import account, failed_detail, scripted
from test_workflow_cli import call, payment_page

pytest_plugins = ["integration.test_leaf_pilots_cli"]

RunCli = Callable[[list[str]], tuple[int, str, str]]


def standard_leaf(
    run_cli: RunCli,
    pilots: FakeBrowser,
    tmp_path: Path,
    *,
    rules: list[dict[str, Any]] | None = None,
    qualified: bool = True,
) -> dict[str, Any]:
    pilots.href = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    source = tmp_path / "qualified"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "leaf_packages/liquidity/reference.banks",
        source,
    )
    manifest = json.loads((source / "leaf.json").read_text())
    manifest["name"] = "synthetic.qualified"
    manifest["dataset"]["relation"] = "synthetic_qualified"
    contract = {
        "version": 1,
        "rules": rules
        if rules is not None
        else [
            {
                "id": "count-shortfall",
                "action": "preserve",
                "reason_codes": [
                    "SHORT_NATIVE_PAGE",
                    "COUNT_MISMATCH",
                    "COUNT_SHORTFALL",
                ],
                "retained_errors": [],
            }
        ],
    }
    if qualified:
        manifest["operations"]["list"]["import_qualification"] = contract
    (source / "leaf.json").write_text(json.dumps(manifest))
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 0, output
    return contract


def short_page(rows: list[dict[str, Any]], *, total: int = 2) -> dict[str, Any]:
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": total,
            "result": {"bankVoList": rows},
        },
    }


def test_standard_reason_rule_preserves_exact_qualified_incomplete_observation(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    contract = standard_leaf(run_cli, pilots, tmp_path)
    plan = call(run_cli, "plan", "create", "--leaf", "liquidity.synthetic.qualified")
    assert plan["import_qualification"] == contract
    rows = [{"bankId": "one", "nested": [False, {"amount": "1.0000"}]}]
    pilots.business_script.append(short_page(rows))
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    assert exported["state"] == "incomplete"
    saved = call(run_cli, "export", "show", "--export", exported["id"])
    assert saved["import_qualification"] == contract
    assert saved["metadata"]["complete"] is False
    assert saved["metadata"]["acquisition"]["reasons"] == [
        "SHORT_NATIVE_PAGE",
        "COUNT_MISMATCH",
        "COUNT_SHORTFALL",
    ]

    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    assert prepared["input_quality"] == "incomplete"
    assert prepared["qualification"] == {
        "contract_version": 1,
        "rule_id": "count-shortfall",
        "action": "preserve",
        "reason_codes": ["SHORT_NATIVE_PAGE", "COUNT_MISMATCH", "COUNT_SHORTFALL"],
        "retained_diagnostics": [],
        "retained_diagnostic_count": 0,
    }
    applied = call(run_cli, "import", "apply", "--plan", prepared["id"])
    assert applied["input_quality"] == "incomplete"
    assert applied["qualification"] == prepared["qualification"]
    observation = call(run_cli, "observation", "show", "--export", exported["id"])
    assert observation["records"] == rows
    assert observation["metadata"] == saved["metadata"]
    assert observation["receipt"]["input_quality"] == "incomplete"
    assert observation["receipt"]["qualification"] == prepared["qualification"]
    replayed = call(run_cli, "import", "apply", "--plan", prepared["id"])
    assert replayed["replayed"] is True
    status = call(run_cli, "status")
    assert status["last_successful_export"] is None
    assert status["current_publications"] == []
    assert len(status["committed_observations"]) == 1


def standard_export(
    run_cli: RunCli,
    pilots: FakeBrowser,
    tmp_path: Path,
    *,
    rules: list[dict[str, Any]] | None = None,
    qualified: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    standard_leaf(run_cli, pilots, tmp_path, rules=rules, qualified=qualified)
    plan = call(run_cli, "plan", "create", "--leaf", "liquidity.synthetic.qualified")
    pilots.business_script.append(short_page([{"bankId": "one"}]))
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    assert exported["state"] == "incomplete"
    return plan, exported


def diagnostic_rule(identifier: str = "detail-999") -> dict[str, Any]:
    return {
        "id": identifier,
        "action": "preserve",
        "reason_codes": ["DETAIL_COVERAGE_INCOMPLETE"],
        "retained_errors": [
            {
                "component": "detail",
                "retention": "failed",
                "diagnostic_code": "BUSINESS_QUERY_FAILED",
                "native_code": "999",
            }
        ],
    }


def custom_export(
    run_cli: RunCli,
    pilots: FakeBrowser,
    tmp_path: Path,
    *,
    rules: list[dict[str, Any]] | None = None,
    failures: dict[str, dict[str, Any]] | None = None,
    refusal: str | None = None,
) -> dict[str, Any]:
    pilots.href = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    source = tmp_path / "custom-qualified"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "leaf_packages/liquidity/cash.accounts",
        source,
    )
    manifest = json.loads((source / "leaf.json").read_text())
    manifest["name"] = "synthetic.custom"
    manifest["dataset"]["relation"] = "synthetic_custom"
    manifest["operations"]["list"]["import_qualification"] = {
        "version": 1,
        "rules": rules if rules is not None else [diagnostic_rule()],
    }
    (source / "leaf.json").write_text(json.dumps(manifest))
    adapter = source / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            'str(result["errorCode"]) == "999"',
            'str(result["errorCode"]) in {"999", "998"}',
        )
    )
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 0, output
    rows = [account("SYNTHETIC-A"), account("SYNTHETIC-B")]
    if failures is None:
        failures = {rows[0]["aliasName"]: failed_detail("999")}
    scripted(
        browser=pilots, cash=rows, baseline=rows, failures=failures, refusal=refusal
    )
    plan = call(run_cli, "plan", "create", "--leaf", "liquidity.synthetic.custom")
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    assert exported["state"] == "incomplete"
    return exported


@pytest.mark.parametrize(
    "rules",
    [
        [],
        [{**diagnostic_rule(), "reason_codes": ["*"]}],
        [{**diagnostic_rule(), "allow_all": True}],
        [diagnostic_rule(), diagnostic_rule()],
    ],
    ids=["empty", "wildcard", "unknown-field", "duplicate"],
)
def test_public_cli_rejects_invalid_import_qualification_rules(
    run_cli: RunCli,
    pilots: FakeBrowser,
    tmp_path: Path,
    rules: list[dict[str, Any]],
) -> None:
    pilots.href = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    source = tmp_path / "invalid-qualified"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "leaf_packages/liquidity/reference.banks",
        source,
    )
    manifest = json.loads((source / "leaf.json").read_text())
    manifest["name"] = "synthetic.invalid"
    manifest["dataset"]["relation"] = "synthetic_invalid"
    manifest["operations"]["list"]["import_qualification"] = {
        "version": 1,
        "rules": rules,
    }
    (source / "leaf.json").write_text(json.dumps(manifest))
    before = storage_snapshot()
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 1, output
    assert json.loads(output)["error"]["code"] == "INVALID_LEAF"
    assert storage_snapshot() == before


@pytest.mark.parametrize("placement", ["standard-get", "root"])
def test_public_cli_rejects_import_qualification_outside_list(
    run_cli: RunCli,
    pilots: FakeBrowser,
    tmp_path: Path,
    placement: str,
) -> None:
    pilots.href = (
        "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
    )
    source = tmp_path / "invalid-placement"
    shutil.copytree(
        Path(__file__).resolve().parents[2]
        / "src/dogopencli/leaf_packages/payment/sla.baselines",
        source,
    )
    manifest = json.loads((source / "leaf.json").read_text())
    manifest["name"] = "synthetic.invalid_placement"
    manifest["dataset"]["relation"] = "synthetic_invalid_placement"
    target = manifest["operations"]["get"] if placement == "standard-get" else manifest
    target["import_qualification"] = {"version": 1, "rules": [diagnostic_rule()]}
    (source / "leaf.json").write_text(json.dumps(manifest))
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 1, output
    assert json.loads(output)["error"]["code"] == "INVALID_LEAF"


def workflow_root() -> Path:
    return Path(os.environ["DOGOPENCLI_CONFIG"]).parent


def artifact_path(export_id: str) -> Path:
    return workflow_root() / "workflow/exports" / export_id / "metadata.json"


def storage_snapshot() -> dict[Path, bytes | None]:
    root = workflow_root()
    return {
        path.relative_to(root): None if path.is_dir() else path.read_bytes()
        for path in root.rglob("*")
        if path.relative_to(root).parts[:2] != ("workflow", "task-state")
    }


def assert_import_rejection(
    run_cli: RunCli, export_id: str, reason: str, *, action: str = "preserve"
) -> None:
    before = storage_snapshot()
    code, output, _ = run_cli(
        [
            "workflow",
            "import",
            "plan",
            "--export",
            export_id,
            "--action",
            action,
        ]
    )
    error = json.loads(output)["error"]
    assert code == 1, output
    assert error["code"] == "WORKFLOW_IMPORT_NOT_QUALIFIED"
    assert reason in error["reason_codes"]
    assert storage_snapshot() == before


def assert_apply_rejection(
    run_cli: RunCli, plan_id: str, code: str, *, reason: str | None = None
) -> None:
    before = storage_snapshot()
    status, output, _ = run_cli(["workflow", "import", "apply", "--plan", plan_id])
    error = json.loads(output)["error"]
    assert status == 1, output
    assert error["code"] == code
    if reason is not None:
        assert reason in error["reason_codes"]
    after = storage_snapshot()
    changed = {
        path
        for path in before.keys() | after.keys()
        if before.get(path) != after.get(path)
    }
    assert after == before, changed


@pytest.mark.parametrize("native_code", ["999", 999])
def test_custom_list_native_scalar_rule_preserves_through_public_cli(
    run_cli: RunCli,
    pilots: FakeBrowser,
    tmp_path: Path,
    native_code: str | int,
) -> None:
    rows = [account("SYNTHETIC-A"), account("SYNTHETIC-B")]
    exported = custom_export(
        run_cli,
        pilots,
        tmp_path,
        failures={rows[0]["aliasName"]: failed_detail(native_code)},
    )
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    diagnostic = prepared["qualification"]["retained_diagnostics"][0]
    assert diagnostic["native_code"] == "999"
    assert diagnostic["count"] == 1
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    observation = call(run_cli, "observation", "show", "--export", exported["id"])
    assert observation["records"] == exported["records"]
    assert (
        observation["records"][0]["source_metadata"]["detail_error"]["native_code"]
        == native_code
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("component", "other"),
        ("retention", "refused"),
        ("diagnostic_code", "OTHER_ERROR"),
        ("native_code", "998"),
    ],
)
def test_custom_list_rejects_each_diagnostic_mismatch_without_writes(
    run_cli: RunCli,
    pilots: FakeBrowser,
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    rule = diagnostic_rule()
    rule["retained_errors"][0][field] = value
    exported = custom_export(run_cli, pilots, tmp_path, rules=[rule])
    assert_import_rejection(run_cli, exported["id"], "UNCOVERED_RETAINED_DIAGNOSTIC")


def test_custom_list_rejects_refusal_and_additional_native_code(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    exported = custom_export(run_cli, pilots, tmp_path, refusal="SYNTHETIC-B")
    assert_import_rejection(run_cli, exported["id"], "UNCOVERED_RETAINED_DIAGNOSTIC")


def test_custom_list_rejects_uncovered_second_diagnostic(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    exported = custom_export(
        run_cli,
        pilots,
        tmp_path,
        failures={
            "SYNTHETIC-A": failed_detail("999"),
            "SYNTHETIC-B": failed_detail("998"),
        },
    )
    assert_import_rejection(run_cli, exported["id"], "UNCOVERED_RETAINED_DIAGNOSTIC")


def test_custom_list_rejects_ambiguous_covering_rules(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    exported = custom_export(
        run_cli,
        pilots,
        tmp_path,
        rules=[diagnostic_rule(), diagnostic_rule("same-policy")],
    )
    assert_import_rejection(run_cli, exported["id"], "AMBIGUOUS_QUALIFICATION")


def test_standard_list_rejects_uncovered_reason(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    rule = {
        "id": "other-only",
        "action": "preserve",
        "reason_codes": ["OTHER_REASON"],
        "retained_errors": [],
    }
    _, exported = standard_export(run_cli, pilots, tmp_path, rules=[rule])
    assert_import_rejection(run_cli, exported["id"], "UNCOVERED_ACQUISITION_REASON")


def test_additional_reason_rejects_whole_artifact(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    _, exported = standard_export(run_cli, pilots, tmp_path)
    path = artifact_path(exported["id"])
    metadata = json.loads(path.read_text())
    metadata["metadata"]["acquisition"]["reasons"].append("UNCOVERED_REASON")
    path.write_text(json.dumps(metadata))
    assert_import_rejection(run_cli, exported["id"], "UNCOVERED_ACQUISITION_REASON")


def test_old_incomplete_export_without_contract_is_not_retroactively_qualified(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    _, exported = standard_export(run_cli, pilots, tmp_path, qualified=False)
    assert "import_qualification" not in exported
    assert_import_rejection(run_cli, exported["id"], "MISSING_IMPORT_CONTRACT")


@pytest.mark.parametrize("evidence_change", ["reasons", "usable", "acquisition"])
def test_missing_or_unusable_host_evidence_fails_closed(
    run_cli: RunCli,
    pilots: FakeBrowser,
    tmp_path: Path,
    evidence_change: str,
) -> None:
    _, exported = standard_export(run_cli, pilots, tmp_path)
    path = artifact_path(exported["id"])
    metadata = json.loads(path.read_text())
    if evidence_change == "reasons":
        metadata["metadata"]["acquisition"]["reasons"] = []
    elif evidence_change == "usable":
        metadata["metadata"]["acquisition"]["usable_incomplete"] = False
    else:
        del metadata["metadata"]["acquisition"]
    path.write_text(json.dumps(metadata))
    assert_import_rejection(run_cli, exported["id"], "INSUFFICIENT_EVIDENCE")


@pytest.mark.parametrize(
    "diagnostic_change",
    [
        "retention",
        "component",
        "code",
        "native_code",
        "count",
        "diagnostics",
        "failed_counter",
        "refused_counter",
    ],
)
def test_missing_host_diagnostic_fields_fail_closed(
    run_cli: RunCli,
    pilots: FakeBrowser,
    tmp_path: Path,
    diagnostic_change: str,
) -> None:
    exported = custom_export(run_cli, pilots, tmp_path)
    path = artifact_path(exported["id"])
    metadata = json.loads(path.read_text())
    trace = next(
        item
        for item in metadata["metadata"]["acquisition"]["attempts"]
        if item.get("kind") == "custom_query"
    )
    query = trace["queries"]["detail"]
    diagnostic = query["diagnostics"][0]
    if diagnostic_change == "count":
        diagnostic["count"] = 0
    elif diagnostic_change == "diagnostics":
        del query["diagnostics"]
    elif diagnostic_change == "failed_counter":
        query["failed"] += 1
    elif diagnostic_change == "refused_counter":
        query["refused"] = 1
    else:
        del diagnostic[diagnostic_change]
    path.write_text(json.dumps(metadata))
    assert_import_rejection(run_cli, exported["id"], "INSUFFICIENT_EVIDENCE")


def test_incomplete_current_action_is_rejected_before_preview(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    _, exported = standard_export(run_cli, pilots, tmp_path)
    assert_import_rejection(
        run_cli, exported["id"], "UNSUPPORTED_ACTION", action="replace-full"
    )


def test_changed_manifest_declaration_requires_new_plan(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    standard_leaf(run_cli, pilots, tmp_path)
    plan = call(run_cli, "plan", "create", "--leaf", "liquidity.synthetic.qualified")
    installed = workflow_root() / "plugins/liquidity/synthetic.qualified/leaf.json"
    manifest = json.loads(installed.read_text())
    manifest["operations"]["list"]["import_qualification"]["rules"][0]["id"] = "changed"
    installed.write_text(json.dumps(manifest))
    run = call(run_cli, "export", "create", "--plan", plan["id"])
    code, output, _ = run_cli(["workflow", "export", "run", "--run", run["id"]])
    assert code == 1
    assert json.loads(output)["error"]["code"] == "WORKFLOW_ERROR"
    assert not pilots.business_requests


def test_apply_recomputes_qualification_before_any_write(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    _, exported = standard_export(run_cli, pilots, tmp_path)
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    path = artifact_path(exported["id"])
    metadata = json.loads(path.read_text())
    metadata["metadata"]["acquisition"]["reasons"].append("UNCOVERED_REASON")
    path.write_text(json.dumps(metadata))
    assert_apply_rejection(
        run_cli,
        prepared["id"],
        "WORKFLOW_IMPORT_NOT_QUALIFIED",
        reason="UNCOVERED_ACQUISITION_REASON",
    )


def test_apply_rejects_changed_reviewed_qualification(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    _, exported = standard_export(run_cli, pilots, tmp_path)
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    path = workflow_root() / "workflow/imports" / (prepared["id"] + ".json")
    plan = json.loads(path.read_text())
    plan["qualification"]["rule_id"] = "changed"
    path.write_text(json.dumps(plan))
    assert_apply_rejection(run_cli, prepared["id"], "WORKFLOW_ERROR")


def test_with_detail_incomplete_export_is_not_eligible(
    run_cli: RunCli, pilots: FakeBrowser
) -> None:
    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "payment.sla.baselines",
        "--with-detail",
    )
    pilots.business_script.extend(
        [
            payment_page([{"id": "one", "name": "one"}]),
            {
                "status": 200,
                "body": {
                    "success": True,
                    "resultData": {"id": "one", "name": "one"},
                },
            },
        ]
    )
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    assert exported["state"] == "complete_nonempty"
    path = artifact_path(exported["id"])
    metadata = json.loads(path.read_text())
    metadata["state"] = "incomplete"
    metadata["metadata"]["complete"] = False
    metadata["metadata"]["dataset_complete"] = False
    path.write_text(json.dumps(metadata))
    assert_import_rejection(run_cli, exported["id"], "UNSUPPORTED_OPERATION")


def test_failed_export_cannot_be_preserved(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    standard_leaf(run_cli, pilots, tmp_path)
    plan = call(run_cli, "plan", "create", "--leaf", "liquidity.synthetic.qualified")
    pilots.business_script.append({"status": 401, "body": {}})
    code, _, _ = run_cli(
        [
            "workflow",
            "export",
            "run",
            "--run",
            call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        ]
    )
    assert code == 1
    failed = call(run_cli, "status")["latest_attempt"]
    assert failed["state"] == "failed"
    assert_import_rejection(run_cli, failed["id"], "EXPORT_NOT_USABLE")


@pytest.mark.parametrize(
    ("hard_failure", "reason"),
    [
        ("identity", "IDENTITY_CONTENT_CONFLICT"),
        ("timeout", "PAGE_BUDGET_EXHAUSTED"),
    ],
)
def test_qualified_rule_cannot_hide_hard_acquisition_failures(
    run_cli: RunCli,
    pilots: FakeBrowser,
    tmp_path: Path,
    hard_failure: str,
    reason: str,
) -> None:
    rule = diagnostic_rule()
    rule["reason_codes"].append(reason)
    exported = custom_export(run_cli, pilots, tmp_path, rules=[rule])
    path = artifact_path(exported["id"])
    metadata = json.loads(path.read_text())
    acquisition = metadata["metadata"]["acquisition"]
    acquisition["reasons"].append(reason)
    if hard_failure == "identity":
        acquisition["conflict_count"] = 1
    else:
        acquisition["error"] = "TIMEOUT"
    path.write_text(json.dumps(metadata))
    assert_import_rejection(run_cli, exported["id"], "EXPORT_NOT_USABLE")


def test_complete_export_bypasses_rules_and_marks_receipt_complete(
    run_cli: RunCli, pilots: FakeBrowser
) -> None:
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    pilots.business_script.append(payment_page([{"id": "one"}]))
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    assert prepared["input_quality"] == "complete"
    assert prepared["qualification"] is None
    applied = call(run_cli, "import", "apply", "--plan", prepared["id"])
    assert applied["input_quality"] == "complete"
    assert applied["qualification"] is None
    receipt = call(run_cli, "observation", "show", "--export", exported["id"])[
        "receipt"
    ]
    assert receipt["input_quality"] == "complete"
    assert receipt["qualification"] is None


@pytest.mark.parametrize("contract_change", ["version", "rules", "unhashable_reason"])
def test_malformed_frozen_contract_fails_closed(
    run_cli: RunCli,
    pilots: FakeBrowser,
    tmp_path: Path,
    contract_change: str,
) -> None:
    _, exported = standard_export(run_cli, pilots, tmp_path)
    path = artifact_path(exported["id"])
    metadata = json.loads(path.read_text())
    if contract_change == "version":
        metadata["import_qualification"]["version"] = 2
    elif contract_change == "rules":
        metadata["import_qualification"]["rules"] = [None]
    else:
        metadata["import_qualification"]["rules"][0]["reason_codes"] = [[]]
    path.write_text(json.dumps(metadata))
    assert_import_rejection(run_cli, exported["id"], "INSUFFICIENT_EVIDENCE")


def test_qualification_summary_is_bounded_without_dropping_coverage(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    rule = diagnostic_rule()
    del rule["retained_errors"][0]["native_code"]
    exported = custom_export(run_cli, pilots, tmp_path, rules=[rule])
    path = artifact_path(exported["id"])
    metadata = json.loads(path.read_text())
    trace = next(
        item
        for item in metadata["metadata"]["acquisition"]["attempts"]
        if item.get("kind") == "custom_query"
    )
    original = trace["queries"]["detail"]["diagnostics"][0]
    trace["queries"]["detail"]["failed"] = 21
    trace["queries"]["detail"]["diagnostics"] = [
        {**deepcopy(original), "native_code": str(1000 + index)} for index in range(21)
    ]
    path.write_text(json.dumps(metadata))
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    qualification = prepared["qualification"]
    assert len(qualification["retained_diagnostics"]) == 20
    assert qualification["retained_diagnostic_group_count"] == 21
    assert qualification["retained_diagnostics_truncated"] is True
    assert qualification["retained_diagnostic_count"] == 21


def test_apply_detects_numeric_representation_change_in_incomplete_input(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    standard_leaf(run_cli, pilots, tmp_path)
    plan = call(run_cli, "plan", "create", "--leaf", "liquidity.synthetic.qualified")
    pilots.business_script.append(short_page([{"bankId": "one", "amount": 1.0}]))
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    path = workflow_root() / "workflow/exports" / exported["id"] / "records.json"
    path.write_text(path.read_text().replace("1.0", "1"))
    assert_apply_rejection(run_cli, prepared["id"], "WORKFLOW_ERROR")


def test_local_filter_incomplete_artifact_lacks_eligible_native_evidence(
    run_cli: RunCli, pilots: FakeBrowser, tmp_path: Path
) -> None:
    standard_leaf(run_cli, pilots, tmp_path)
    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.synthetic.qualified",
        "--parameters",
        '{"country":"SG"}',
    )
    pilots.business_script.append(
        short_page([{"bankId": "one", "cityCode": "SG"}], total=2)
    )
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    assert exported["state"] == "incomplete"
    assert "acquisition" not in exported["metadata"]
    assert_import_rejection(run_cli, exported["id"], "INSUFFICIENT_EVIDENCE")
