"""Saved inquiry intent, explicit enrollment, and frozen executions."""

import uuid
from argparse import Namespace
from dataclasses import replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import CliError
from .helpspec import opt

if TYPE_CHECKING:
    from .command_model import Invocation
    from .workflow import Store


def declaration_entries() -> list:
    return [
        (("workflow", "target"), "Save intent and explicitly freeze or run work.", ()),
        (
            ("workflow", "target", "create"),
            "Save an exact bounded plan, or explicitly opt into following.",
            (
                opt("plan", "Exact saved full/history plan.", required=True),
                opt(
                    "policy",
                    "Saved execution policy.",
                    choices=("bounded", "following"),
                    default="bounded",
                ),
                opt(
                    "lookback_days",
                    "Following: explicitly refresh this many calendar days.",
                    "int",
                    default=0,
                ),
                opt(
                    "timezone",
                    "Following: explicit IANA timezone for cutoff calendar date.",
                ),
            ),
        ),
        (
            ("workflow", "target", "enroll"),
            "Enroll installed List datasets; expose missing scope and limits.",
            (
                opt(
                    "scopes",
                    "JSON map of leaf identities to explicit native parameter objects.",
                    default="{}",
                ),
                opt(
                    "mode",
                    "Native full observation or bounded history.",
                    choices=("full", "history"),
                    default="full",
                ),
            ),
        ),
        (
            ("workflow", "target", "plan"),
            "Freeze execution cutoff and native packages offline; never exports.",
            (opt("target", "Saved target set ID.", required=True),),
        ),
        (
            ("workflow", "target", "run"),
            "Execute an exact saved execution; retain independent successes.",
            (
                opt("execution", "Frozen execution ID.", required=True),
                opt("limit", "Preview row limit.", "int", default=100),
                opt("offset", "Preview offset.", "int", default=0),
                opt("fields", "Preview fields."),
            ),
        ),
        (
            ("workflow", "target", "show"),
            "Inspect target intent, executions and exact outcomes offline.",
            (opt("target", "Saved target set ID.", required=True),),
        ),
    ]


def invalid(message: str) -> None:
    raise CliError("INVALID_ARGUMENT", message, exit_code=2)


def saved(value: dict) -> dict:
    from .workflow import now

    return {"version": 1, "id": uuid.uuid4().hex, "created_at": now(), **value}


def execution_status(store: "Store", execution: dict) -> dict:
    from .workflow_history import coverage

    if "runs" in execution:
        from .workflow_tasks import snapshot

        packages = []
        for identity in execution["runs"]:
            child = snapshot(store.config_file, "export", identity)
            run = store.read("runs", identity)
            if run["plan"]["mode"] == "history":
                packages.append(
                    {
                        **child["result"],
                        "run_id": identity,
                        "effective_state": child["effective_state"],
                    }
                )
                continue
            attempts = sorted(
                store.exports_for(identity),
                key=lambda item: (item["completed_at"], item["id"]),
            )
            successful = [
                item for item in attempts if item["state"].startswith("complete_")
            ]
            packages.append(
                {
                    "plan_id": child["plan_id"],
                    "run_id": identity,
                    "effective_state": child["effective_state"],
                    "complete": child["effective_state"] == "completed",
                    "latest_attempt": attempts[-1] if attempts else None,
                    "last_successful_export": successful[-1] if successful else None,
                }
            )
        return {
            **execution,
            "packages": packages,
            "complete": not execution["diagnostics"]
            and all(item["complete"] for item in packages),
        }
    exports = [
        {key: value for key, value in item.items() if key != "records"}
        for item in store.list("exports")
    ]
    packages = []
    for identity in execution["plans"]:
        plan = store.read("plans", identity)
        if plan["mode"] == "history":
            packages.append(coverage(store, plan))
            continue
        attempts = sorted(
            (item for item in exports if item["plan"] == identity),
            key=lambda item: (item["completed_at"], item["id"]),
        )
        successful = [
            item for item in attempts if item["state"].startswith("complete_")
        ]
        packages.append(
            {
                "plan_id": identity,
                "complete": bool(successful),
                "latest_attempt": attempts[-1] if attempts else None,
                "last_successful_export": successful[-1] if successful else None,
            }
        )
    return {
        **execution,
        "packages": packages,
        "complete": not execution["diagnostics"]
        and all(item["complete"] for item in packages),
    }


def dispatch(invocation: "Invocation", store: "Store") -> dict:
    args = invocation.args
    action = invocation.node.path[-1]
    if action == "enroll":
        return enroll(invocation, store)
    if action == "create":
        plan = store.read("plans", args.plan)
        if plan["mode"] not in {"full", "history"}:
            invalid("Targets require full or history plans")
        if args.policy != "following" and (args.lookback_days or args.timezone):
            invalid("Lookback and timezone require explicit following policy")
        if (
            args.policy == "following"
            and plan["mode"] == "full"
            and (args.lookback_days or args.timezone)
        ):
            invalid(
                "Full following captures observations; "
                "lookback/timezone require native history"
            )
        if args.policy == "following" and plan["mode"] == "history":
            if plan["contract"].get("splitting") != "explicit_windows":
                invalid(
                    "Following requires a native calendar history contract "
                    "permitting explicit windows"
                )
            if not args.timezone or args.lookback_days < 0:
                invalid(
                    "Following requires an explicit cutoff timezone "
                    "and nonnegative lookback"
                )
            try:
                ZoneInfo(args.timezone)
            except (ZoneInfoNotFoundError, ValueError):
                invalid("Unknown cutoff timezone")
        return store.save(
            "targets",
            saved(
                {
                    "policy": args.policy,
                    "plans": [plan["id"]],
                    "diagnostics": [],
                    "selection": "selected",
                    "lookback_days": args.lookback_days,
                    "timezone": args.timezone,
                }
            ),
        )
    if action == "plan":
        target = store.read("targets", args.target)
        work = (
            following(invocation, store, target)
            if target["policy"] == "following"
            else {"plans": target["plans"]}
        )
        from .workflow_tasks import create_run

        return store.save(
            "executions",
            saved(
                {
                    "target_id": target["id"],
                    "task_contract": 1,
                    "runs": [
                        create_run(store, identity)["id"] for identity in work["plans"]
                    ],
                    **work,
                    "diagnostics": target["diagnostics"],
                    "policy": target["policy"],
                }
            ),
        )
    if action == "show":
        target = store.read("targets", args.target)
        return {
            "target": target,
            "executions": [
                execution_status(store, item)
                for item in store.list("executions")
                if item["target_id"] == target["id"]
            ],
        }
    if action == "run":
        from .workflow_tasks import attempt, execute_export

        execution = store.read("executions", args.execution)
        if "runs" not in execution:
            invalid(
                "Historical execution has no frozen child Runs; prepare a new execution"
            )
        with attempt(store, "target", execution["id"]) as active:
            current = execution_status(store, execution)
            for package in current["packages"]:
                if package["complete"]:
                    continue
                active.publish(
                    {"phase": "exporting", "current_run_id": package["run_id"]}
                )
                child = replace(
                    invocation,
                    args=Namespace(**vars(args), run=package["run_id"], package=None),
                )
                try:
                    execute_export(child, store)
                except CliError:
                    continue
            result = execution_status(store, execution)
            if not result["complete"]:
                raise CliError(
                    "INCOMPLETE_RESULT",
                    "Saved target execution has failed, incomplete "
                    "or unexecutable work",
                    meta={
                        "execution": result,
                        "complete": False,
                        "dataset_complete": False,
                    },
                )
            return result
    invalid("Unknown target stage")


def following(invocation: "Invocation", store: "Store", target: dict) -> dict:
    """Subtract successful native query intervals; never infer row-date coverage."""
    from .leaves.runtime import planned_list_scope
    from .workflow import now
    from .workflow_history import calendar, compile_plan, gaps

    seed = store.read("plans", target["plans"][0])
    if seed["mode"] == "full":
        plan = {**seed, "id": uuid.uuid4().hex, "created_at": now()}
        store.save("plans", plan)
        return {
            "plans": [plan["id"]],
            "cutoff": plan["created_at"],
            "coverage_basis": "full_observations",
        }
    domain, name = seed["leaf"].split(".", 1)
    declaration = invocation.registry.get(domain, name)
    leaf = invocation.registry._load(declaration.path)
    # Validate the original bounds before reusing their successful coverage.
    # Dynamic following dates are checked separately when compiling new work.
    scope, environment = planned_list_scope(leaf, seed["parameters"])
    refreshed = compile_plan(
        {**seed, "native_scope": scope, "environment": environment}, leaf, None
    )
    if (
        scope != seed["native_scope"]
        or environment != seed["environment"]
        or refreshed["contract"] != seed["contract"]
    ):
        invalid("Native history semantics changed; save a new target")
    contract = seed["contract"]
    cutoff = (
        datetime.fromisoformat(now()).astimezone(ZoneInfo(target["timezone"])).date()
    )
    start = calendar(seed["desired_range"]["from"], contract)
    if cutoff < start:
        invalid("Following cutoff precedes the saved native start")
    frozen = {
        "from": start.strftime(contract["format"]),
        "to": cutoff.strftime(contract["format"]),
    }
    history = {**seed, "desired_range": frozen}
    previous = {seed["id"]} | {
        identity
        for execution in store.list("executions")
        if execution["target_id"] == target["id"]
        for identity in execution["plans"]
    }
    complete = [
        item["native_range"]
        for item in store.list("exports")
        if item.get("history_plan") in previous
        and item["state"].startswith("complete_")
    ]
    missing = gaps(history, complete)
    if target["lookback_days"]:
        left = max(start, cutoff - timedelta(days=target["lookback_days"] - 1))
        missing.append({"from": left.strftime(contract["format"]), "to": frozen["to"]})
    # Coalesce overlapping requested intervals without inventing daily queries.
    intervals = sorted(
        (calendar(item["from"], contract), calendar(item["to"], contract))
        for item in missing
    )
    merged = []
    for left, right in intervals:
        if merged and left.toordinal() <= merged[-1][1].toordinal() + 1:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    plans = []
    for left, right in merged:
        parameters = {
            **seed["parameters"],
            contract["from_parameter"]: left.strftime(contract["format"]),
            contract["to_parameter"]: right.strftime(contract["format"]),
        }
        scope, environment = planned_list_scope(leaf, parameters)
        plan = compile_plan(
            {
                **seed,
                "id": uuid.uuid4().hex,
                "created_at": now(),
                "parameters": parameters,
                "native_scope": scope,
                "environment": environment,
            },
            leaf,
            None,
        )
        if {
            key: value
            for key, value in plan["contract"].items()
            if key not in {"from", "to"}
        } != {
            key: value for key, value in contract.items() if key not in {"from", "to"}
        } or environment != seed["environment"]:
            invalid("Native history semantics changed; save a new target")
        store.save("plans", plan)
        plans.append(plan["id"])
    return {
        "plans": plans,
        "cutoff": frozen["to"],
        "cutoff_timezone": target["timezone"],
        "desired_range": frozen,
        "coverage_basis": "native_query_observations",
    }


def enroll(invocation: "Invocation", store: "Store") -> dict:
    from .jsonutil import canonical, parse
    from .workflow import native_plan

    try:
        scopes = parse(invocation.args.scopes)
    except (ValueError, TypeError):
        invalid("--scopes requires a JSON map of leaf IDs to native parameters")
    if not isinstance(scopes, dict) or not all(
        isinstance(value, dict) for value in scopes.values()
    ):
        invalid("--scopes requires a JSON map of leaf IDs to native parameters")
    leaves = invocation.registry.leaves
    if set(scopes) - set(leaves):
        invalid("--scopes includes uninstalled leaf identities")
    plans, diagnostics, excluded, selected, capabilities = [], [], [], [], []
    for leaf in leaves.values():
        if "list" not in leaf.manifest["operations"]:
            excluded.append({"leaf": leaf.id, "reason": "Get-only dataset"})
            continue
        selected.append(leaf.id)
        capabilities.append(
            {
                "leaf": leaf.id,
                "operation": "list",
                "limitations": leaf.manifest.get("limitations", []),
            }
        )
        supplied = scopes.get(leaf.id, {})
        missing = [
            item["name"]
            for item in leaf.manifest["operations"]["list"].get("parameters", [])
            if item.get("required")
            and item.get("default") is None
            and item["name"] not in supplied
        ]
        if missing:
            diagnostics.append(
                {
                    "leaf": leaf.id,
                    "code": "MISSING_SCOPE",
                    "missing_arguments": missing,
                    "message": "Missing native arguments: "
                    + ", ".join("--" + name for name in missing),
                }
            )
            continue
        child = replace(
            invocation,
            args=Namespace(
                leaf=leaf.id,
                parameters=canonical(supplied),
                mode=invocation.args.mode,
                windows=None,
                operation="list",
                identity=None,
                with_detail=False,
            ),
        )
        try:
            plan = native_plan(child)
            store.save("plans", plan)
            plans.append(plan["id"])
        except CliError as error:
            diagnostics.append(
                {"leaf": leaf.id, "code": error.code, "message": error.message}
            )
    diagnostics.extend(
        {"leaf": item["id"], "code": item["code"], "message": item["message"]}
        for item in invocation.registry.diagnostics
    )
    return store.save(
        "targets",
        saved(
            {
                "selection": "all-installed",
                "policy": "bounded",
                "plans": plans,
                "diagnostics": diagnostics,
                "enrolled_leaves": selected,
                "capabilities": capabilities,
                "excluded": excluded,
                "scopes": scopes,
                "mode": invocation.args.mode,
            }
        ),
    )


def summaries(store: "Store") -> list[dict]:
    return [
        {
            "target": target,
            "executions": [
                execution_status(store, item)
                for item in store.list("executions")
                if item["target_id"] == target["id"]
            ],
        }
        for target in store.list("targets")
    ]
