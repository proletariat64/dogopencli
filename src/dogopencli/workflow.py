"""Durable, explicit export and offline observation import stages."""

import os
import re
import shutil
import sqlite3
import uuid
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .command_model import Invocation

from .errors import CliError
from .helpspec import NO_EFFECTS, BizNode, opt
from .jsonutil import canonical, parse


def declarations() -> tuple[BizNode, ...]:
    """Help shares the execution grammar and performs no storage initialization."""
    entries = [
        (
            ("workflow",),
            "Plan, export and preserve scoped observations separately from "
            "current data.",
            (),
        ),
        (
            ("workflow", "plan"),
            "Compile or inspect declared inquiry scope offline.",
            (),
        ),
        (
            ("workflow", "plan", "create"),
            "Save native scope only; does not export or initialize storage.",
            (
                opt("leaf", "Installed domain.dotted-leaf identity.", required=True),
                opt(
                    "operation",
                    "Declared List or Get inquiry.",
                    choices=("list", "get"),
                    default="list",
                ),
                opt("identity", "Get only: exact native detail identity."),
                opt(
                    "with_detail",
                    "List only: compose declared Get for every selected row.",
                    "bool",
                    default=False,
                ),
                opt(
                    "mode",
                    "Full observation or bounded native history.",
                    choices=("full", "history"),
                    default="full",
                ),
                opt(
                    "windows",
                    "History only: JSON array of explicit native {from,to} windows; "
                    "default is one unchanged range.",
                ),
                opt(
                    "parameters",
                    "Native operation parameters as a JSON object.",
                    default="{}",
                ),
            ),
        ),
        (
            ("workflow", "plan", "show"),
            "Inspect one exact saved plan offline.",
            (opt("plan", "Saved plan ID.", required=True),),
        ),
        (("workflow", "export"), "Execute or inspect exact immutable exports.", ()),
        (
            ("workflow", "repair"),
            "Freeze gaps and inspect separate repair exports.",
            (),
        ),
        (
            ("workflow", "repair", "plan"),
            "Save repair work from the frozen baseline gaps.",
            (opt("plan", "Original full or history plan ID.", required=True),),
        ),
        (
            ("workflow", "repair", "show"),
            "Inspect frozen baseline and repair outcomes offline.",
            (opt("repair", "Saved repair plan ID.", required=True),),
        ),
        (
            ("workflow", "history"),
            "Inspect bounded native history observations offline.",
            (),
        ),
        (
            ("workflow", "history", "show"),
            "Show desired range, package attempts and gaps without advancing work.",
            (opt("plan", "Saved history plan ID.", required=True),),
        ),
        (
            ("workflow", "export", "run"),
            "Export one planned inquiry result; display controls never truncate "
            "saved records.",
            (
                opt("plan", "Saved plan ID.", required=True),
                opt(
                    "package",
                    "History only: execute one exact package; "
                    "completed exports are reused.",
                ),
                opt("limit", "Preview rows; zero means all.", "int", default=100),
                opt("offset", "Preview offset.", "int", default=0),
                opt("fields", "Preview fields only."),
            ),
        ),
        (
            ("workflow", "export", "show"),
            "Read the exact saved export offline.",
            (opt("export", "Exact export ID.", required=True),),
        ),
        (("workflow", "import"), "Plan or apply exact exports offline.", ()),
        (
            ("workflow", "import", "plan"),
            "Preview exact scope, counts and expected current publication.",
            (
                opt("export", "Exact complete export ID."),
                opt("repair", "Exact completed repair selection; preserve only."),
                opt(
                    "action",
                    "Preserve an observation, replace a full scope, "
                    "replace a covered historical range, or reconcile native keys.",
                    choices=("preserve", "replace-full", "replace-range", "keyed"),
                    required=True,
                ),
            ),
        ),
        (
            ("workflow", "import", "apply"),
            "Apply the reviewed write action and replay receipt offline.",
            (opt("plan", "Exact import plan ID.", required=True),),
        ),
        (("workflow", "current"), "Inspect scoped current publications offline.", ()),
        (
            ("workflow", "current", "show"),
            "Read current publication for an exact export namespace.",
            (opt("export", "Export identifying the namespace.", required=True),),
        ),
        (
            ("workflow", "observation"),
            "Read committed observations separately from current data.",
            (),
        ),
        (
            ("workflow", "observation", "show"),
            "Read stored observation records and receipt offline.",
            (opt("export", "Committed export ID.", required=True),),
        ),
        (
            ("workflow", "status"),
            "Inspect plans, attempts, last successful exports and committed "
            "observations offline.",
            (),
        ),
    ]
    from .workflow_targets import declaration_entries

    entries.extend(declaration_entries())
    return tuple(
        BizNode(
            path,
            summary,
            options=options,
            handler="workflow" if len(path) == 3 or path[-1] == "status" else None,
            effects={
                **NO_EFFECTS,
                "mutates": path[-1] in {"create", "run", "apply", "enroll"}
                or path
                in {
                    ("workflow", "import", "plan"),
                    ("workflow", "repair", "plan"),
                    ("workflow", "target", "plan"),
                },
                "network": path[-1] == "run",
                "browser_required": path[-1] == "run",
            },
        )
        for path, summary, options in entries
    )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, config_file: Path) -> None:
        self.root = config_file.parent / "workflow"

    def save(self, kind: str, value: dict) -> dict:
        directory = self.root / kind
        directory.mkdir(parents=True, exist_ok=True)
        if kind == "exports":
            # One rename publishes metadata and exact records together. Listings
            # never open the retained corpus; unpublished bundles are invisible.
            temporary = directory / ("." + uuid.uuid4().hex)
            temporary.mkdir(mode=0o700)
            try:
                for name, content in (
                    (
                        "metadata.json",
                        {k: v for k, v in value.items() if k != "records"},
                    ),
                    ("records.json", value.get("records", [])),
                ):
                    with (temporary / name).open("x", encoding="utf-8") as stream:
                        os.chmod(temporary / name, 0o600)
                        stream.write(canonical(content))
                        stream.flush()
                        os.fsync(stream.fileno())
                fd = os.open(temporary, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
                temporary.rename(directory / value["id"])
                fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
            return value
        target = directory / (value["id"] + ".json")
        temporary = directory / ("." + uuid.uuid4().hex)
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                os.chmod(temporary, 0o600)
                stream.write(canonical(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, target)
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)
        return value

    def read(self, kind: str, identity: str) -> dict:
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity):
            raise CliError("WORKFLOW_ERROR", "Invalid saved identity")
        try:
            if kind == "exports":
                bundle = self.root / kind / identity
                value = parse((bundle / "metadata.json").read_bytes())
                value["records"] = parse((bundle / "records.json").read_bytes())
            else:
                value = parse((self.root / kind / (identity + ".json")).read_bytes())
            if (
                not isinstance(value, dict)
                or value.get("id") != identity
                or value.get("version") != 1
            ):
                raise ValueError
            return value
        except (OSError, ValueError, TypeError) as error:
            raise CliError(
                "WORKFLOW_ERROR", f"Saved {kind} is unavailable or invalid"
            ) from error

    def list(self, kind: str) -> list[dict]:
        if kind == "exports":
            try:
                return [
                    parse((path / "metadata.json").read_bytes())
                    for path in sorted((self.root / kind).glob("[0-9a-f]" * 32))
                    if path.is_dir()
                ]
            except (OSError, ValueError, TypeError) as error:
                raise CliError(
                    "WORKFLOW_ERROR", "Saved export metadata is invalid"
                ) from error
        return [
            self.read(kind, path.stem)
            for path in sorted((self.root / kind).glob("*.json"))
        ]


def list_detail_contract(leaf: Any) -> dict:
    """Freeze List-bound Get sources and row-to-request semantics offline."""
    specification = leaf.manifest["operations"].get("get", {})
    if not specification.get("list_binding"):
        raise CliError(
            "WORKFLOW_ERROR", "Native detail binding changed; create a new plan"
        )
    # Capability factories can require values supplied only by acquired rows.
    # Pin the loader's existing implementation identity instead of inventing
    # those values or resolving a different Get source during offline planning.
    return {
        "adapter_sha256": leaf.adapter_sha256,
        "declaration": specification,
    }


def native_plan(invocation: "Invocation") -> dict:
    from .command_model import leaf_options, parse_options

    args = invocation.args
    try:
        parameters = parse(args.parameters)
        if not isinstance(parameters, dict):
            raise ValueError
    except (ValueError, TypeError) as error:
        raise CliError(
            "INVALID_ARGUMENT", "--parameters must be a JSON object", exit_code=2
        ) from error
    domain, separator, name = args.leaf.partition(".")
    if not separator:
        raise CliError(
            "INVALID_ARGUMENT", "--leaf requires domain.dotted-leaf", exit_code=2
        )
    leaf = invocation.registry.get(domain, name)
    operation = args.operation
    if operation not in leaf.manifest["operations"]:
        raise CliError(
            "INVALID_ARGUMENT", "Leaf does not declare requested operation", exit_code=2
        )
    if operation == "get":
        from .leaves.query import validate_detail_lookup

        validate_detail_lookup(args.identity)
        if args.mode != "full" or args.with_detail:
            raise CliError(
                "INVALID_ARGUMENT",
                "Get requires full mode without --with-detail",
                exit_code=2,
            )
    elif args.identity is not None:
        raise CliError("INVALID_ARGUMENT", "--identity requires Get", exit_code=2)
    if args.with_detail and not leaf.manifest["operations"].get("get", {}).get(
        "list_binding"
    ):
        raise CliError(
            "INVALID_ARGUMENT", "Leaf has no declared List/Get binding", exit_code=2
        )
    definitions = leaf.manifest["operations"][operation].get("parameters", [])
    known = {item["name"]: item for item in definitions}
    tokens = []
    for key, value in parameters.items():
        if key not in known:
            raise CliError(
                "INVALID_ARGUMENT", f"Unknown native parameter {key}", exit_code=2
            )
        values = (
            value if isinstance(value, list) and known[key].get("multiple") else [value]
        )
        if any(isinstance(item, (dict, list)) or item is None for item in values):
            raise CliError(
                "INVALID_ARGUMENT", f"Invalid native parameter {key}", exit_code=2
            )
        for item in values:
            tokens.extend(
                ["--" + key, str(item).lower() if isinstance(item, bool) else str(item)]
            )
    parsed = parse_options(
        BizNode(
            (domain, "refresh", name),
            "",
            options=leaf_options(leaf, "get" if operation == "get" else "refresh"),
            handler="workflow",
        ),
        tokens,
    )
    effective = {
        item["name"].replace("-", "_"): getattr(parsed, item["name"].replace("-", "_"))
        for item in definitions
    }
    effective = {key: value for key, value in effective.items() if value is not None}
    from .leaves.runtime import (
        freeze_list_parameters,
        planned_get_scope,
        planned_list_scope,
    )

    runtime_leaf = invocation.registry._load(leaf.path)
    if operation == "list":
        effective = freeze_list_parameters(
            runtime_leaf, effective, invocation.config_file
        )
        scope, environment = planned_list_scope(runtime_leaf, effective)
    else:
        scope, environment = planned_get_scope(runtime_leaf, effective, args.identity)
    plan = {
        "version": 1,
        "id": uuid.uuid4().hex,
        "created_at": now(),
        "leaf": leaf.id,
        "binding": binding(invocation.config_file, leaf.id)
        if "list" in leaf.manifest["operations"]
        else None,
        "environment": environment,
        "native_scope": scope,
        "operation": operation,
        "with_detail": args.with_detail,
        **(
            {"detail_contract": list_detail_contract(runtime_leaf)}
            if args.with_detail
            else {}
        ),
        **({"identity": args.identity} if operation == "get" else {}),
        "mode": "full",
        "parameters": {
            key: value for key, value in effective.items() if value is not None
        },
    }
    if args.mode == "history":
        from .workflow_history import compile_plan

        return compile_plan(plan, runtime_leaf, args.windows)
    if args.windows is not None:
        raise CliError(
            "INVALID_ARGUMENT", "--windows requires --mode history", exit_code=2
        )
    return plan


def dispatch(invocation: "Invocation") -> tuple[Any, dict | None]:
    try:
        return _dispatch(invocation)
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise CliError(
            "WORKFLOW_ERROR", "Local workflow state is unavailable or malformed"
        ) from error


def _dispatch(invocation: "Invocation") -> tuple[Any, dict | None]:
    store = Store(invocation.config_file)
    path = invocation.node.path[1:]
    if path[0] == "target":
        from .workflow_targets import dispatch as targets

        return targets(invocation, store), None
    if path == ("plan", "create"):
        return store.save("plans", native_plan(invocation)), None
    if path == ("plan", "show"):
        return store.read("plans", invocation.args.plan), None
    if path == ("repair", "plan"):
        from .workflow_repair import compile_plan

        return compile_plan(
            invocation, store, store.read("plans", invocation.args.plan)
        ), None
    if path == ("repair", "show"):
        from .workflow_repair import inspect

        return inspect(store, store.read("plans", invocation.args.repair)), None
    if path == ("history", "show"):
        from .workflow_history import coverage

        return coverage(store, store.read("plans", invocation.args.plan)), None
    if path == ("export", "run"):
        return run_export(invocation, store)
    if path == ("export", "show"):
        return store.read("exports", invocation.args.export), None
    if path == ("import", "plan"):
        saved = import_plan(invocation, store)
        # Frozen copies stay durable; previews show the bounded scope/count
        # contract rather than serializing an entire million-row input again.
        return {k: v for k, v in saved.items() if k not in {"input", "inputs"}}, None
    if path == ("import", "apply"):
        from .workflow_storage import apply, exact_match

        plan = store.read("imports", invocation.args.plan)
        if "repair_id" in plan:
            from .workflow_repair import apply as apply_repair

            return apply_repair(invocation.config_file, store, plan), None
        artifact = exact_export(store, plan["export_id"])
        # Direct comparison binds exact values and numeric representations to
        # the reviewed plan without an adapter/configuration fingerprint.
        if (
            plan.get("action")
            not in {"preserve", "replace-full", "replace-range", "keyed"}
            or not exact_match(plan.get("input"), artifact)
            or plan.get("binding") != artifact["binding"]
        ):
            raise CliError(
                "WORKFLOW_ERROR", "Import plan differs from its exact frozen input"
            )
        verify_binding(invocation.config_file, artifact)
        if plan["action"] == "keyed":
            from .workflow_keyed import apply as reconcile

            return reconcile(invocation.config_file, plan, artifact, now()), None
        if plan["action"] == "replace-range":
            from .workflow_range import apply as replace_range

            return replace_range(invocation.config_file, plan, artifact, now()), None
        if plan["action"] == "replace-full":
            from .workflow_snapshot import apply as replace

            return replace(invocation.config_file, plan, artifact, now()), None
        return apply(invocation.config_file, plan, artifact, now()), None
    if path == ("current", "show"):
        from .workflow_snapshot import current

        artifact = exact_export(store, invocation.args.export)
        verify_binding(invocation.config_file, artifact)
        from .workflow_keyed import active
        from .workflow_keyed import current as keyed_current

        if active(artifact):
            return keyed_current(artifact), None
        from .workflow_range import active as range_active
        from .workflow_range import current as range_current

        if range_active(artifact):
            return range_current(artifact), None
        return current(artifact), None
    if path == ("observation", "show"):
        from .workflow_storage import read

        artifact = exact_export(store, invocation.args.export)
        verify_binding(invocation.config_file, artifact)
        return read(artifact["binding"], artifact["id"]), None
    if path == ("status",):
        from .workflow_history import coverage
        from .workflow_keyed import imports as keyed_imports
        from .workflow_range import publications as range_publications
        from .workflow_repair import inspect as repair_status
        from .workflow_snapshot import publications
        from .workflow_storage import receipts
        from .workflow_targets import summaries as target_summaries

        exports = [
            {key: value for key, value in item.items() if key != "records"}
            for item in store.list("exports")
        ]
        bindings = {
            canonical(item["binding"]): item["binding"]
            for item in exports
            if item["binding"] is not None
        }
        committed = [
            row for destination in bindings.values() for row in receipts(destination)
        ]
        ordered = sorted(exports, key=lambda item: (item["completed_at"], item["id"]))
        successful = [
            item
            for item in ordered
            if item["state"] in {"complete_empty", "complete_nonempty"}
        ]
        plans = store.list("plans")
        plan_status = [
            {
                "plan_id": plan["id"],
                "state": next(
                    (
                        item["state"]
                        for item in reversed(ordered)
                        if item["plan"] == plan["id"]
                    ),
                    "unqueried",
                ),
            }
            for plan in plans
        ]
        histories = [
            coverage(store, plan) for plan in plans if plan.get("mode") == "history"
        ]
        repairs = [
            repair_status(store, plan) for plan in plans if plan.get("mode") == "repair"
        ]
        for repair in repairs:
            next(
                item for item in plan_status if item["plan_id"] == repair["repair_id"]
            )["state"] = "complete" if repair["complete"] else "incomplete"
        for history in histories:
            states = [item["state"] for item in history["packages"]]
            state = (
                (
                    "complete_nonempty"
                    if "complete_nonempty" in states
                    else "complete_empty"
                )
                if history["complete"]
                else "unqueried"
                if all(item == "unqueried" for item in states)
                else "incomplete"
            )
            next(item for item in plan_status if item["plan_id"] == history["plan_id"])[
                "state"
            ] = state
        return {
            "plans": plans,
            "plan_status": plan_status,
            "exports": exports,
            "latest_attempt": ordered[-1] if ordered else None,
            "last_successful_export": successful[-1] if successful else None,
            "committed_observations": committed,
            "keyed_imports": [
                row
                for destination in bindings.values()
                for row in keyed_imports(destination)
            ],
            "range_publications": [
                row
                for destination in bindings.values()
                for row in range_publications(destination)
            ],
            "current_publications": [
                row
                for destination in bindings.values()
                for row in publications(destination)
            ],
            "current_effect": "unchanged",
            "history": histories,
            "repairs": repairs,
            "targets": target_summaries(store),
        }, None
    raise CliError("INVALID_ARGUMENT", "Unknown workflow stage", exit_code=2)


def binding(config_file: Path, leaf_id: str) -> dict:
    location = config_file.parent / "leaf-registry.sqlite3"
    try:
        with sqlite3.connect(location.as_uri() + "?mode=ro", uri=True) as db:
            row = db.execute(
                "SELECT database_path, relation_name FROM bindings WHERE leaf_id=?",
                (leaf_id,),
            ).fetchone()
        if row is None:
            raise ValueError
        return {"database": row[0], "relation": row[1], "leaf": leaf_id}
    except (sqlite3.Error, ValueError) as error:
        raise CliError(
            "WORKFLOW_ERROR", "Registered destination is unavailable"
        ) from error


def run_export(
    invocation: "Invocation", store: Store, plan: dict | None = None
) -> tuple[dict, dict]:
    from .domains import DomainService
    from .leaves.registry import Registry
    from .leaves.runtime import execute, planned_get_scope, planned_list_scope

    if plan is None:
        plan = store.read("plans", invocation.args.plan)
        if plan.get("mode") == "history":
            from .workflow_history import run

            return run(invocation, store, plan)
        if plan.get("mode") == "repair":
            from .workflow_repair import run as repair

            return repair(invocation, store, plan)
        if invocation.args.package is not None:
            raise CliError(
                "INVALID_ARGUMENT", "--package requires a history plan", exit_code=2
            )
    result = {
        "version": 1,
        "id": uuid.uuid4().hex,
        "plan": plan["id"],
        "leaf": plan["leaf"],
        "operation": plan["operation"],
        "binding": plan["binding"],
        "environment": plan["environment"],
        "parameters": plan["parameters"],
        "started_at": now(),
        "state": "unqueried",
        **(
            {"repair_plan": plan["repair_plan"], "baseline_plan": plan["baseline_plan"]}
            if "repair_plan" in plan
            else {}
        ),
        **(
            {
                "history_plan": plan["history_plan"],
                "native_range": plan["range"],
                "history_contract": plan["contract"],
            }
            if "history_plan" in plan
            else {}
        ),
    }
    captured = {}

    def capture(records: list[dict], metadata: dict) -> None:
        captured.update(records=records, metadata=metadata)

    try:
        domain, name = plan["leaf"].split(".", 1)
        if not DomainService(
            invocation.config_file, registry=invocation.registry
        ).inventory(domain)[0]["enabled"]:
            raise CliError("DOMAIN_DISABLED", f"Domain is disabled: {domain}")
        leaf = Registry(invocation.config_file).scan().get(domain, name)
        current_binding = (
            binding(invocation.config_file, plan["leaf"])
            if "list" in leaf.manifest["operations"]
            else None
        )
        if current_binding != plan["binding"]:
            raise CliError(
                "WORKFLOW_ERROR", "Registered destination differs from saved plan"
            )
        if plan["operation"] == "get":
            scope, environment = planned_get_scope(
                leaf, plan["parameters"], plan["identity"]
            )
        else:
            scope, environment = planned_list_scope(leaf, plan["parameters"])
        if plan.get("with_detail") and list_detail_contract(leaf) != plan.get(
            "detail_contract"
        ):
            raise CliError(
                "WORKFLOW_ERROR", "Native detail contract changed; create a new plan"
            )
        replacement = getattr(leaf.adapter, "range_replacement_contract", None)
        if (
            callable(replacement)
            and plan["operation"] == "list"
            and not plan.get("with_detail")
        ):
            result["range_replacement_contract"] = replacement(plan["parameters"])
        keyed = getattr(leaf.adapter, "keyed_contract", None)
        if (
            callable(keyed)
            and plan["operation"] == "list"
            and not plan.get("with_detail")
        ):
            result["keyed_contract"] = keyed(plan["parameters"])
        if "history_plan" in plan:
            from .leaves.history import resolve as resolve_history

            expected = {**plan["contract"], **plan["range"]}
            if canonical(resolve_history(leaf, plan["parameters"])) != canonical(
                expected
            ):
                raise CliError(
                    "WORKFLOW_ERROR",
                    "Native history contract changed; create a new plan",
                )
        if scope != plan["native_scope"] or environment != plan["environment"]:
            raise CliError(
                "WORKFLOW_ERROR", "Native scope/environment changed; create a new plan"
            )
        args = Namespace(
            live=True,
            with_detail=plan.get("with_detail", False),
            detail_identity=plan.get("identity"),
            fields=invocation.args.fields,
            limit=invocation.args.limit,
            offset=invocation.args.offset,
            require_complete=False,
            require_fresh=False,
            explicit_parameters=set(plan["parameters"]),
        )
        displayed, meta = execute(
            leaf,
            plan["operation"],
            plan["parameters"],
            args,
            invocation.config_file,
            capture=capture,
        )
    except (Exception, KeyboardInterrupt) as error:
        if not isinstance(error, (CliError, KeyboardInterrupt)):
            error = CliError("INTERNAL_ERROR", "Unexpected export failure")
        result.update(
            state="failed",
            completed_at=now(),
            metadata=error.meta or {} if isinstance(error, CliError) else {},
            error=error.diagnostic()
            if isinstance(error, CliError)
            else {"code": "INTERRUPTED"},
        )
        store.save("exports", result)
        if isinstance(error, CliError):
            error.meta = {**(error.meta or {}), "export_id": result["id"]}
        raise error
    records = captured["records"]
    complete = meta.get("complete") is True and meta.get("dataset_complete") is True
    result.update(
        captured,
        parameters=captured["metadata"]["query"],
        record_count=len(records),
        completed_at=now(),
        state=("complete_nonempty" if records else "complete_empty")
        if complete
        else "incomplete",
    )
    store.save("exports", result)
    return {**result, "records": displayed}, meta


def exact_export(store: Store, identity: str) -> dict:
    value = store.read("exports", identity)
    try:
        if value["state"] not in {"complete_empty", "complete_nonempty"}:
            raise CliError(
                "WORKFLOW_ERROR", "Normal import requires an exact complete export"
            )
        rows = value["records"]
        metadata = value["metadata"]
        if (
            not isinstance(rows, list)
            or not all(isinstance(row, dict) for row in rows)
            or type(value["record_count"]) is not int
            or len(rows) != value["record_count"]
            or bool(rows) != (value["state"] == "complete_nonempty")
            or metadata["complete"] is not True
            or metadata["dataset_complete"] is not True
            or canonical(metadata["query"]) != canonical(value["parameters"])
            or (
                value["binding"] is None
                and value["operation"] != "get"
                or value["binding"] is not None
                and value["binding"]["leaf"] != value["leaf"]
            )
            or not isinstance(metadata["scope"], (dict, str))
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise CliError(
            "WORKFLOW_ERROR", "Exact export format or integrity is invalid"
        ) from error
    return value


def verify_binding(config_file: Path, artifact: dict) -> None:
    if artifact["binding"] is None:
        raise CliError(
            "WORKFLOW_ERROR",
            "Get export has no registered dataset destination; "
            "inspect the saved export without importing it",
        )
    if binding(config_file, artifact["leaf"]) != artifact["binding"]:
        raise CliError("WORKFLOW_ERROR", "Exact export destination binding conflicts")


def import_plan(invocation: "Invocation", store: Store) -> dict:
    from .workflow_keyed import preview as keyed_preview
    from .workflow_range import preview as range_preview
    from .workflow_snapshot import preview as snapshot_preview
    from .workflow_storage import current_count, receipts

    if bool(invocation.args.export) == bool(invocation.args.repair):
        raise CliError(
            "INVALID_ARGUMENT", "Select exactly one --export or --repair", exit_code=2
        )
    if invocation.args.repair:
        from .workflow_repair import import_plan as repair_import

        return repair_import(invocation, store)
    artifact = exact_export(store, invocation.args.export)
    verify_binding(invocation.config_file, artifact)
    existing = receipts(artifact["binding"])
    replayed = any(item["export_id"] == artifact["id"] for item in existing)
    scoped = [
        item
        for item in existing
        if canonical(item["scope"]) == canonical(artifact["metadata"]["scope"])
        and canonical(item["environment"]) == canonical(artifact["environment"])
    ]
    return store.save(
        "imports",
        {
            "version": 1,
            "id": uuid.uuid4().hex,
            "created_at": now(),
            "export_id": artifact["id"],
            "binding": artifact["binding"],
            "action": invocation.args.action,
            "scope": artifact["metadata"]["scope"],
            "existing_count": sum(item["record_count"] for item in scoped),
            "new_count": 0 if replayed else artifact["record_count"],
            "current_effect": "unchanged",
            "current_count": current_count(artifact["binding"]),
            "count_basis": "preserved_observations_in_exact_scope",
            "input": artifact,
            **(
                snapshot_preview(artifact)
                if invocation.args.action == "replace-full"
                else range_preview(artifact)
                if invocation.args.action == "replace-range"
                else keyed_preview(artifact)
                if invocation.args.action == "keyed"
                else {}
            ),
        },
    )
