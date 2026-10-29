"""Finite native query packages and observation coverage; no inferred timeline."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from .errors import CliError
from .jsonutil import parse
from .leaves.runtime import planned_list_scope

if TYPE_CHECKING:
    from .command_model import Invocation
    from .leaves.registry import Leaf
    from .workflow import Store


def invalid(message: str) -> None:
    raise CliError("INVALID_ARGUMENT", message, exit_code=2)


def calendar(value: str, contract: dict) -> date:
    try:
        result = datetime.strptime(value, contract["format"]).date()
        if result.strftime(contract["format"]) != value:
            raise ValueError
        return result
    except (ValueError, TypeError) as error:
        raise CliError(
            "INVALID_ARGUMENT", "Invalid native calendar bound", exit_code=2
        ) from error


def compile_plan(plan: dict, leaf: "Leaf", windows: str | None) -> dict:
    method = getattr(leaf.adapter, "history_contract", None)
    if not callable(method):
        invalid(
            "Leaf has no native history range contract; "
            "preserve a full scoped observation instead"
        )
    contract = method(plan["parameters"])
    if (
        contract.get("interpretation") != "calendar_date"
        or contract.get("boundary") != "inclusive"
    ):
        invalid("History planner requires a declared inclusive calendar range")
    start, end = (
        calendar(contract["from"], contract),
        calendar(contract["to"], contract),
    )
    if start > end:
        invalid("Native history range is reversed")
    selected = [{"from": contract["from"], "to": contract["to"]}]
    if windows is not None:
        if contract.get("splitting") != "explicit_windows":
            invalid("Leaf does not permit explicit history windows")
        try:
            selected = parse(windows)
        except (ValueError, TypeError) as error:
            raise CliError(
                "INVALID_ARGUMENT", "--windows must be a JSON array", exit_code=2
            ) from error
        if not isinstance(selected, list) or not selected or len(selected) > 10000:
            invalid("--windows requires 1 to 10000 exact native windows")
    packages = []
    for window in selected:
        if not isinstance(window, dict) or set(window) != {"from", "to"}:
            invalid("Each history window requires only from and to")
        left, right = (
            calendar(window["from"], contract),
            calendar(window["to"], contract),
        )
        if not start <= left <= right <= end:
            invalid("History window is outside the frozen desired range or reversed")
        parameters = {
            **plan["parameters"],
            contract["from_parameter"]: window["from"],
            contract["to_parameter"]: window["to"],
        }
        scope, environment = planned_list_scope(leaf, parameters)
        if environment != plan["environment"]:
            invalid("History windows cannot change inquiry environment")
        packages.append(
            {
                "id": uuid.uuid4().hex,
                "range": window,
                "parameters": parameters,
                "native_scope": scope,
            }
        )
    return {
        **plan,
        "mode": "history",
        "contract": contract,
        "desired_range": {"from": contract["from"], "to": contract["to"]},
        "cutoff": contract["to"],
        "packages": packages,
        "coverage_basis": "native_query_observations",
    }


def gaps(plan: dict, ranges: list[dict]) -> list[dict]:
    """Subtract queried calendar intervals without reading record maxima."""
    contract = plan["contract"]
    cursor = calendar(plan["desired_range"]["from"], contract).toordinal()
    end = calendar(plan["desired_range"]["to"], contract).toordinal()
    result = []
    for left, right in sorted(
        (
            calendar(item["from"], contract).toordinal(),
            calendar(item["to"], contract).toordinal(),
        )
        for item in ranges
    ):
        if left > cursor:
            result.append(
                {
                    "from": date.fromordinal(cursor).strftime(contract["format"]),
                    "to": date.fromordinal(left - 1).strftime(contract["format"]),
                }
            )
        cursor = max(cursor, right + 1)
    if cursor <= end:
        result.append(
            {
                "from": date.fromordinal(cursor).strftime(contract["format"]),
                "to": date.fromordinal(end).strftime(contract["format"]),
            }
        )
    return result


def overlaps(packages: list[dict], contract: dict) -> tuple[list[list[str]], bool]:
    """Bound diagnostics even when every explicitly selected query overlaps."""
    intervals = sorted(
        (
            calendar(item["range"]["from"], contract),
            calendar(item["range"]["to"], contract),
            item["id"],
        )
        for item in packages
    )
    active = []
    pairs = []
    for left, right, identity in intervals:
        active = [(end, previous) for end, previous in active if end >= left]
        for _, previous in active:
            if len(pairs) == 100:
                return pairs, True
            pairs.append([previous, identity])
        active.append((right, identity))
    return pairs, False


def coverage(store: "Store", plan: dict) -> dict:
    if plan.get("mode") != "history":
        invalid("Selected plan is not bounded history")
    exports = store.list("exports")
    packages = []
    for package in plan["packages"]:
        attempts = sorted(
            (item for item in exports if item["plan"] == package["id"]),
            key=lambda item: (item["completed_at"], item["id"]),
        )
        completed = [
            item
            for item in attempts
            if item["state"] in {"complete_empty", "complete_nonempty"}
        ]
        effective = completed[-1] if completed else (attempts[-1] if attempts else None)
        packages.append(
            {
                **package,
                "state": effective["state"] if effective else "unqueried",
                "export_id": effective["id"] if effective else None,
                "attempts": [
                    {key: value for key, value in item.items() if key != "records"}
                    for item in attempts
                ],
            }
        )
    missing = gaps(
        plan,
        [item["range"] for item in packages if item["state"].startswith("complete_")],
    )
    overlapping, overlap_truncated = overlaps(packages, plan["contract"])
    return {
        "plan_id": plan["id"],
        "desired_range": plan["desired_range"],
        "cutoff": plan["cutoff"],
        "contract": plan["contract"],
        "packages": packages,
        "unqueried_ranges": gaps(
            plan, [item["range"] for item in packages if item["state"] != "unqueried"]
        ),
        "unplanned_ranges": gaps(plan, [item["range"] for item in packages]),
        "uncovered_ranges": missing,
        "complete": not missing
        and all(
            item["state"] in {"complete_empty", "complete_nonempty"}
            for item in packages
        ),
        "overlapping_packages": overlapping,
        "overlapping_packages_truncated": overlap_truncated,
        "coverage_basis": "native_query_observations",
        "current_history_effect": "separate_observations",
    }


def run(invocation: "Invocation", store: "Store", plan: dict) -> tuple[dict, dict]:
    from .workflow import run_export

    current = coverage(store, plan)
    selected = invocation.args.package
    if selected is not None and selected not in {
        item["id"] for item in current["packages"]
    }:
        invalid("--package is not part of this frozen history plan")
    for package in current["packages"]:
        if selected is not None and package["id"] != selected:
            continue
        if package["state"] in {"complete_empty", "complete_nonempty"}:
            continue
        child = {
            **plan,
            **{
                key: package[key]
                for key in ("id", "parameters", "native_scope", "range")
            },
            "mode": "full",
            "history_plan": plan["id"],
        }
        try:
            run_export(invocation, store, child)
        except CliError:
            # Every failed attempt is already durable; independent packages
            # continue and the aggregate command still reports failure below.
            continue
    result = coverage(store, plan)
    if not result["complete"]:
        raise CliError(
            "INCOMPLETE_RESULT",
            "Requested history has unqueried, failed or incomplete scopes; "
            "inspect workflow history show and resume exact packages",
            meta={"history": result, "complete": False, "dataset_complete": False},
        )
    return result, {
        "complete": True,
        "dataset_complete": True,
        "coverage_basis": "native_query_observations",
    }
