"""Repair frozen gaps with new exports and explicit offline reconciliation."""

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import CliError
from .jsonutil import canonical
from .workflow_history import gaps, invalid, overlaps

if TYPE_CHECKING:
    from .command_model import Invocation
    from .workflow import Store


def compile_plan(invocation: "Invocation", store: "Store", baseline: dict) -> dict:
    from .leaves.history import window_parameters
    from .leaves.runtime import planned_list_scope
    from .workflow import now
    from .workflow_history import coverage

    frozen = coverage(store, baseline) if baseline.get("mode") == "history" else None
    exports = store.list("exports")
    if frozen:
        selected = [
            {"range": item["range"], "export_id": item["export_id"]}
            for item in frozen["packages"]
            if item["state"] in {"complete_empty", "complete_nonempty"}
        ]
        if overlaps(
            [{"id": item["export_id"], "range": item["range"]} for item in selected],
            baseline["contract"],
        )[0]:
            invalid("Ambiguous overlapping baseline exports; select disjoint work")
        missing = frozen["uncovered_ranges"]
        if not missing:
            invalid("Baseline has no uncovered ranges to repair")
        if baseline["contract"].get("splitting") != "explicit_windows":
            invalid("Native contract does not permit gap windows; retry exact query")
        domain, name = baseline["leaf"].split(".", 1)
        leaf = invocation.registry._load(invocation.registry.get(domain, name).path)
        packages = []
        for window in missing:
            parameters = window_parameters(
                leaf, baseline["parameters"], window, baseline["contract"]
            )
            scope, environment = planned_list_scope(leaf, parameters)
            if environment != baseline["environment"]:
                invalid("Repair cannot change baseline environment")
            packages.append(
                {
                    "id": uuid.uuid4().hex,
                    "range": window,
                    "parameters": parameters,
                    "native_scope": scope,
                }
            )
    else:
        if baseline.get("mode") != "full":
            invalid("Repair requires an original full or history plan")
        attempts = [item for item in exports if item["plan"] == baseline["id"]]
        if not attempts or any(
            item["state"].startswith("complete_") for item in attempts
        ):
            invalid("Full repair requires a failed or incomplete baseline attempt")
        selected, missing = [], []
        packages = [
            {
                "id": uuid.uuid4().hex,
                "parameters": baseline["parameters"],
                "native_scope": baseline["native_scope"],
            }
        ]
    return store.save(
        "plans",
        {
            **baseline,
            "id": uuid.uuid4().hex,
            "created_at": now(),
            "mode": "repair",
            "baseline_plan": baseline["id"],
            "baseline": baseline,
            "baseline_coverage": frozen,
            "baseline_exports": selected,
            "baseline_gaps": missing,
            "packages": packages,
        },
    )


def inspect(store: "Store", plan: dict) -> dict:
    if plan.get("mode") != "repair":
        invalid("Selected plan is not a repair")
    exports = store.list("exports")
    packages = []
    for package in plan["packages"]:
        attempts = sorted(
            [item for item in exports if item["plan"] == package["id"]],
            key=lambda item: (item["completed_at"], item["id"]),
        )
        complete = [item for item in attempts if item["state"].startswith("complete_")]
        effective = complete[-1] if complete else attempts[-1] if attempts else None
        packages.append(
            {
                **package,
                "state": effective["state"] if effective else "unqueried",
                "export_id": effective["id"] if effective else None,
                "attempts": [
                    {k: v for k, v in item.items() if k != "records"}
                    for item in attempts
                ],
            }
        )
    selected = [
        *plan["baseline_exports"],
        *[
            {
                "export_id": item["export_id"],
                **({"range": item["range"]} if "range" in item else {}),
            }
            for item in packages
            if item["state"].startswith("complete_")
        ],
    ]
    missing = (
        gaps(plan["baseline"], [item["range"] for item in selected])
        if plan["baseline"].get("mode") == "history"
        else []
    )
    return {
        "repair_id": plan["id"],
        "baseline_plan": plan["baseline_plan"],
        "baseline_gaps": plan["baseline_gaps"],
        "packages": packages,
        "selected_exports": selected,
        "uncovered_ranges": missing,
        "complete": not missing
        and all(item["state"].startswith("complete_") for item in packages),
        "coverage_basis": "exact_baseline_and_separate_repair_exports",
    }


def run(invocation: "Invocation", store: "Store", plan: dict) -> tuple[dict, dict]:
    from .workflow import run_export

    state = inspect(store, plan)
    requested = invocation.args.package
    if requested and requested not in {item["id"] for item in plan["packages"]}:
        invalid("--package is not part of this frozen repair plan")
    for package in state["packages"]:
        if (requested and package["id"] != requested) or package["state"].startswith(
            "complete_"
        ):
            continue
        child = {
            **plan["baseline"],
            **package,
            "mode": "full",
            "repair_plan": plan["id"],
            "baseline_plan": plan["baseline_plan"],
        }
        if "range" in package:
            child["history_plan"] = plan["baseline_plan"]
        try:
            run_export(invocation, store, child)
        except CliError:
            continue
    state = inspect(store, plan)
    if not state["complete"]:
        raise CliError(
            "INCOMPLETE_RESULT",
            "Repair retains unqueried, failed or incomplete gaps",
            meta={"repair": state, "complete": False, "dataset_complete": False},
        )
    return state, {"complete": True, "dataset_complete": True}


def import_plan(invocation: "Invocation", store: "Store") -> dict:
    from .workflow import exact_export, now, verify_binding
    from .workflow_storage import receipts

    if invocation.args.action != "preserve":
        invalid(
            "Repair reconciliation preserves exact observations; "
            "select individual exports for current actions"
        )
    plan = store.read("plans", invocation.args.repair)
    state = inspect(store, plan)
    if not state["complete"]:
        invalid("Repair still has gaps; export the frozen repair work first")
    artifacts = [
        exact_export(store, item["export_id"]) for item in state["selected_exports"]
    ]
    if len({item["id"] for item in artifacts}) != len(artifacts):
        invalid("Ambiguous repeated repair input")
    for artifact in artifacts:
        verify_binding(invocation.config_file, artifact)
        if (
            artifact["binding"] != plan["binding"]
            or artifact["environment"] != plan["environment"]
        ):
            invalid("Repair input destination or environment conflicts")
    committed = {item["export_id"] for item in receipts(plan["binding"])}
    return store.save(
        "imports",
        {
            "version": 1,
            "id": uuid.uuid4().hex,
            "created_at": now(),
            "repair_id": plan["id"],
            "action": "preserve",
            "binding": plan["binding"],
            "export_ids": [item["id"] for item in artifacts],
            "inputs": artifacts,
            "new_count": sum(
                item["record_count"]
                for item in artifacts
                if item["id"] not in committed
            ),
            "current_effect": "unchanged",
            "coverage": state,
        },
    )


def apply(config_file: Path, store: "Store", plan: dict) -> dict:
    from .workflow import exact_export, now, verify_binding
    from .workflow_storage import apply as preserve

    artifacts = [exact_export(store, identity) for identity in plan["export_ids"]]
    if plan["action"] != "preserve" or canonical(artifacts) != canonical(
        plan["inputs"]
    ):
        invalid("Repair import differs from exact frozen inputs")
    # Validate the whole selection before committing independent observations.
    for artifact in artifacts:
        verify_binding(config_file, artifact)
        if artifact["binding"] != plan["binding"]:
            invalid("Repair destination conflicts")
    return {
        "plan_id": plan["id"],
        "repair_id": plan["repair_id"],
        "receipts": [
            preserve(config_file, plan, artifact, now()) for artifact in artifacts
        ],
    }
