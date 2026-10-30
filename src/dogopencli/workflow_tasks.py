"""Exact workflow task ownership and bounded, read-only task snapshots.

An advisory lock owns an attempt. Kernel process identity plus the held lock
establish liveness; an old heartbeat or a recycled PID alone never does.
"""

import fcntl
import os
import re
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .errors import CliError
from .jsonutil import canonical, parse
from .workflow import Store

KINDS = {
    "export": "runs",
    "repair": "plans",
    "import": "imports",
    "target": "executions",
}
COMPLETE = {"complete_empty", "complete_nonempty"}


def now() -> str:
    """Task wall time is independent of frozen inquiry/capture clocks."""
    return datetime.now(timezone.utc).isoformat()


def create_run(store: Store, plan_id: str) -> dict:
    plan = store.read("plans", plan_id)
    if plan.get("mode") not in {"full", "history"}:
        raise CliError(
            "INVALID_ARGUMENT",
            "Export create requires a full/history plan",
            exit_code=2,
        )
    return store.save(
        "runs",
        {
            "version": 1,
            "id": uuid.uuid4().hex,
            "created_at": now(),
            "task_contract": 1,
            "plan_id": plan_id,
            "plan": plan,
        },
    )


def run_plan(run: dict) -> dict:
    plan = run.get("plan")
    if (
        not isinstance(plan, dict)
        or plan.get("id") != run.get("plan_id")
        or plan.get("mode") not in {"full", "history"}
    ):
        raise CliError("WORKFLOW_ERROR", "Frozen Export Run input is invalid")
    return {**plan, "run_id": run["id"]}


def _path(store: Store, kind: str, identity: str) -> Path:
    return store.root / "task-state" / kind / (identity + ".json")


def _read(path: Path) -> dict | None:
    try:
        result = parse(path.read_bytes())
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("attempts"), list)
            or type(result.get("attempt_count")) is not int
            or any(
                not isinstance(a, dict)
                or not isinstance(a.get("id"), str)
                or type(a.get("number")) is not int
                or a.get("state")
                not in {"running", "completed", "incomplete", "failed", "interrupted"}
                or not isinstance(a.get("started_at"), str)
                for a in result["attempts"]
            )
        ):
            raise ValueError
        return result
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError) as error:
        raise CliError(
            "WORKFLOW_ERROR", "Task attempt metadata is unavailable or invalid"
        ) from error


def _atomic(path: Path, value: dict) -> None:
    temporary = path.with_name("." + uuid.uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def _process(pid: int) -> dict | None:
    try:
        # comm can contain spaces or parentheses; fields after its final ')'
        # begin with state (field 3). starttime is field 22.
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return {
            "pid": pid,
            "start_ticks": fields[19],
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        }
    except FileNotFoundError:
        return None


def ownership(path: Path, attempt: dict | None) -> str:
    if attempt is None or attempt["state"] != "running":
        return "inactive"
    owner = attempt.get("owner")
    if not isinstance(owner, dict):
        return "unknown"
    try:
        process = _process(owner["pid"])
        if process is not None and process == {
            key: owner.get(key) for key in ("pid", "start_ticks", "boot_id")
        }:
            descriptor = Path(f"/proc/{owner['pid']}/fd/{owner['lock_fd']}")
            exact_file = os.path.samestat(
                descriptor.stat(), path.with_suffix(".lock").stat()
            )
            info = Path(f"/proc/{owner['pid']}/fdinfo/{owner['lock_fd']}").read_text()
            if exact_file and re.search(
                rf"^lock:\s+\d+:\s+FLOCK\s+ADVISORY\s+WRITE\s+{owner['pid']}\s",
                info,
                re.MULTILINE,
            ):
                return "verified"
    except (OSError, KeyError, TypeError, ValueError):
        pass
    # /proc can expose another PID namespace or deny access. Missing or
    # mismatched process identity cannot establish exit while this task's
    # lock is still held. Only a verified release supports interruption.
    try:
        with path.with_suffix(".lock").open("rb") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return "unknown"
            fcntl.flock(lock, fcntl.LOCK_UN)
            return "exited"
    except OSError:
        return "unknown"


class Attempt:
    def __init__(self, path: Path, state: dict, attempt: dict):
        self.path, self.state, self.attempt = path, state, attempt
        self.mutex = threading.Lock()
        self.active = True
        self.rate_sample = None
        self.diagnostics_enabled = False
        self.last_diagnostic = None
        self.last_diagnostic_at = 0.0

    def diagnostic(self, progress: dict, *, final: bool = False) -> None:
        phase = progress.get("phase")
        if phase not in {
            "starting",
            "acquisition",
            "get",
            "detail",
            "query",
            "staging",
            "publication",
            "exporting",
            "export_saved",
            "settled",
        }:
            phase = "working"
        metrics = tuple(
            (key, progress[key])
            for key in (
                "source_pages",
                "request_attempts",
                "source_rows_received",
                "source_total_rows",
                "exported_rows",
                "expected_rows",
                "staged_rows",
                "committed_rows",
                "detail_rows_completed",
                "detail_rows_expected",
            )
            if type(progress.get(key)) is int
        )
        signature = (phase, metrics)
        tick = time.monotonic()
        previous = self.last_diagnostic
        if (
            self.diagnostics_enabled
            and (signature != previous or final)
            and (previous is None or final or tick - self.last_diagnostic_at >= 3)
        ):
            counts = " ".join(f"{key}={value}" for key, value in metrics)
            try:
                print(
                    f"{self.state['kind']} {self.state['id']} "
                    f"attempt {self.attempt['number']} phase={phase} {counts}".rstrip()
                    + (f" state={self.attempt['state']}" if final else ""),
                    file=sys.stderr,
                    flush=True,
                )
            except OSError:
                return
            self.last_diagnostic, self.last_diagnostic_at = signature, tick

    def publish(self, facts: dict, *, flush: bool = False) -> None:
        with self.mutex:
            if not self.active:
                return
            # Only the task lock owner writes; an expired observer cannot
            # publish against a later attempt after its operation context ends.
            stamp = now()
            if facts:
                progress = self.state.setdefault("progress", {})
                if any(
                    facts.get(key) != progress.get(key)
                    for key in (
                        "source",
                        "candidate",
                        "current_package_id",
                        *(("export_id",) if self.state["kind"] == "import" else ()),
                    )
                    if key in facts
                ):
                    for key in (
                        "source_pages",
                        "source_rows_received",
                        "source_total_rows",
                        "source_total_scope",
                        "source_total_scope_reason",
                        "request_attempts",
                        "row_rate_per_second",
                        "eta_seconds",
                    ):
                        progress.pop(key, None)
                progress.update(facts)
                if self.state["kind"] == "import" and facts.get("export_id"):
                    item = self.state.setdefault("input_progress", {}).setdefault(
                        facts["export_id"], {}
                    )
                    item.update(
                        {
                            key: facts[key]
                            for key in (
                                "expected_rows",
                                "staged_rows",
                                "committed_rows",
                                "replayed",
                                "inserted_count",
                            )
                            if key in facts
                            and (
                                key in {"expected_rows", "staged_rows"}
                                or facts.get("phase") == "publication"
                            )
                        }
                    )
                scope = tuple(
                    progress.get(key)
                    for key in ("current_package_id", "source", "candidate")
                )
                received = progress.get("source_rows_received")
                tick = time.monotonic()
                if isinstance(received, int) and scope[1] is not None:
                    previous = self.rate_sample
                    if (
                        previous is None
                        or previous[0] != scope
                        or received < previous[1]
                    ):
                        self.rate_sample = (scope, received, tick)
                        progress["row_rate_per_second"] = None
                        progress["eta_seconds"] = None
                    elif received > previous[1]:
                        elapsed = tick - previous[2]
                        rate = (
                            (received - previous[1]) / elapsed if elapsed > 0 else None
                        )
                        progress["row_rate_per_second"] = rate
                        total = progress.get("source_total_rows")
                        progress["eta_seconds"] = (
                            max(0, total - received) / rate
                            if rate and isinstance(total, int) and total >= received
                            else None
                        )
                        self.rate_sample = (scope, received, tick)
                self.state["last_progress_at"] = stamp
                if "phase" in facts:
                    self.attempt["phase"] = facts["phase"]
            self.state["heartbeat_at"] = stamp
            # Coalesce hot-path facts; the existing heartbeat flushes at one
            # second intervals. Ownership and final outcomes remain immediate.
            if flush:
                self.state["updated_at"] = stamp
                _atomic(self.path, self.state)
            if facts:
                self.diagnostic(self.state.get("progress", {}))


@contextmanager
def attempt(store: Store, kind: str, identity: str) -> Iterator[Attempt]:
    path = _path(store, kind, identity)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+b") as lock:
        os.chmod(path.with_suffix(".lock"), 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise CliError(
                "WORKFLOW_BUSY", "This exact task already has an active attempt"
            ) from error
        state = _read(path) or {
            "version": 1,
            "id": identity,
            "kind": kind,
            "attempt_count": 0,
            "attempts": [],
        }
        previous = state["attempts"][-1] if state["attempts"] else None
        if previous and previous["state"] == "running":
            previous.update(state="interrupted", completed_at=now())
        state["attempt_count"] += 1
        try:
            owner = _process(os.getpid())
        except OSError:
            owner = None
        current = {
            "id": uuid.uuid4().hex,
            "number": state["attempt_count"],
            "state": "running",
            "phase": "starting",
            "started_at": now(),
            "completed_at": None,
            "error": None,
            "owner": {**owner, "lock_fd": lock.fileno()} if owner else None,
        }
        state["attempts"] = [*state["attempts"][-4:], current]
        state["progress"] = {}
        writer = Attempt(path, state, current)
        writer.publish({"phase": "starting"}, flush=True)
        print(
            f"{kind} {identity} attempt {current['number']} {current['id']}",
            file=sys.stderr,
            flush=True,
        )
        writer.diagnostics_enabled = True
        writer.diagnostic(state["progress"])
        stop = threading.Event()

        def heartbeat() -> None:
            while not stop.wait(1):
                writer.publish({}, flush=True)

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            from .progress import observe

            with observe(writer.publish):
                yield writer
        except BaseException as error:
            with writer.mutex:
                current.update(
                    state="interrupted"
                    if isinstance(error, (KeyboardInterrupt, SystemExit))
                    else "incomplete"
                    if isinstance(error, CliError) and error.code == "INCOMPLETE_RESULT"
                    else "failed",
                    error={"code": error.code}
                    if isinstance(error, CliError)
                    else {
                        "code": "INTERRUPTED"
                        if isinstance(error, (KeyboardInterrupt, SystemExit))
                        else "INTERNAL_ERROR"
                    },
                )
            raise
        else:
            with writer.mutex:
                if current["state"] == "running":
                    current["state"] = "completed"
        finally:
            stop.set()
            thread.join()
            with writer.mutex:
                writer.active = False
                current["completed_at"] = now()
                state["updated_at"] = now()
                if current["state"] == "completed":
                    state["last_successful_attempt"] = {
                        k: v for k, v in current.items() if k != "owner"
                    }
                _atomic(path, state)
                writer.diagnostic(state.get("progress", {}), final=True)
            fcntl.flock(lock, fcntl.LOCK_UN)


def execute_export(invocation, store: Store) -> tuple[dict, dict]:
    from .workflow import run_export
    from .workflow_history import run as history_run

    run = store.read("runs", invocation.args.run)
    plan = run_plan(run)
    with attempt(store, "export", run["id"]) as active:
        if plan["mode"] == "history":
            result, meta = history_run(invocation, store, plan)
        else:
            if invocation.args.package is not None:
                raise CliError(
                    "INVALID_ARGUMENT", "--package requires history", exit_code=2
                )
            saved = [e for e in store.exports_for(run["id"]) if e["state"] in COMPLETE]
            if saved:
                result = store.read("exports", saved[-1]["id"])
                meta = result["metadata"]
                from .leaves.runtime import _project
                from .temporary_query import display_options, window_rows

                limit, offset, fields = display_options(invocation.args)
                rows = result["records"]
                if plan["operation"] == "get":
                    rows = _project(rows, fields)
                    displayed = rows if result["display_shape"] == "array" else rows[0]
                elif plan.get("with_detail"):
                    displayed = [
                        {**item, "record": _project([item["record"]], fields)[0]}
                        for item in window_rows(rows, limit, offset)
                    ]
                else:
                    displayed = _project(window_rows(rows, limit, offset), fields)
                result = {**result, "records": displayed}
            else:
                result, meta = run_export(invocation, store, plan)
        active.publish({"phase": "settled"})
        if meta.get("complete") is not True or meta.get("dataset_complete") is not True:
            with active.mutex:
                active.attempt["state"] = "incomplete"
        return result, meta


def execute_repair(invocation, store: Store) -> tuple[dict, dict]:
    from .workflow_repair import run

    plan = store.read("plans", invocation.args.repair)
    if plan.get("mode") != "repair":
        raise CliError(
            "INVALID_ARGUMENT", "Selected object is not a repair", exit_code=2
        )
    with attempt(store, "repair", plan["id"]):
        return run(invocation, store, plan)


def execute_import(invocation, store: Store) -> dict:
    from .workflow import apply_import

    plan = store.read("imports", invocation.args.plan)
    if not (store.root / "import_headers" / (plan["id"] + ".json")).is_file():
        from .workflow_storage import import_plan_header

        store.save("import_headers", import_plan_header(plan))
    with attempt(store, "import", plan["id"]) as active:
        result = apply_import(invocation, store)
        with active.mutex:
            active.state["result"] = result
        active.publish({"phase": "settled"})
        return result


def import_proof(plan: dict) -> dict:
    """Read only exact action receipts and metadata, never committed row arrays."""
    from .workflow_storage import connection

    tables = {
        "preserve": "_dogopencli_observations",
        "replace-full": "_dogopencli_publication_receipts",
        "replace-range": "_dogopencli_range_receipts",
        "keyed": "_dogopencli_keyed_receipts",
    }
    action = plan["action"]
    inputs = plan["input_metadata"]
    verified, staged = [], 0
    with connection(plan["binding"]) as db:
        installed = {
            r[0]
            for r in db.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='main'"
            ).fetchall()
        }
        for artifact in inputs:
            identity = artifact["id"]
            if "_dogopencli_import_staging" in installed:
                saved = db.execute(
                    "SELECT metadata FROM _dogopencli_import_staging WHERE export_id=?",
                    [identity],
                ).fetchone()
                if (
                    saved
                    and canonical(parse(saved[0])) == canonical(artifact)
                    and "_dogopencli_observation_rows" in installed
                ):
                    staged += db.execute(
                        "SELECT count(*) FROM _dogopencli_observation_rows "
                        "WHERE export_id=?",
                        [identity],
                    ).fetchone()[0]
            if (
                tables[action] not in installed
                or "_dogopencli_observations" not in installed
            ):
                continue
            saved = db.execute(
                "SELECT artifact FROM _dogopencli_observations WHERE export_id=? "
                "AND leaf_id=? AND relation_name=?",
                [identity, plan["binding"]["leaf"], plan["binding"]["relation"]],
            ).fetchone()
            if not saved or canonical(parse(saved[0])) != canonical(artifact):
                continue
            row = db.execute(
                f"SELECT receipt FROM {tables[action]} WHERE export_id=?", [identity]
            ).fetchone()
            if not row:
                continue
            receipt = parse(row[0])
            if (
                receipt.get("binding") != plan["binding"]
                or receipt.get("export_id") != identity
                or receipt.get("record_count") != artifact["record_count"]
                or receipt.get("scope") != artifact["metadata"]["scope"]
                or receipt.get("environment") != artifact["environment"]
                or action != "preserve"
                and receipt.get("action") != action
            ):
                continue
            verified.append(receipt)
        current_publication = {
            "is_latest": None,
            "export_id": None,
            "reason": "Preserve does not request current publication"
            if action == "preserve"
            else "Keyed publication has per-key current state",
        }
        pointer_table = {
            "replace-full": "_dogopencli_current_publications",
            "replace-range": "_dogopencli_range_publications",
        }.get(action)
        if pointer_table and pointer_table in installed and verified:
            row = db.execute(
                f"SELECT export_id FROM {pointer_table} "
                "WHERE relation_name=? AND namespace=?",
                [plan["binding"]["relation"], canonical(verified[-1]["namespace"])],
            ).fetchone()
            current_publication = {
                "is_latest": row == (verified[-1]["export_id"],),
                "export_id": row[0] if row else None,
                "reason": None,
            }
        return {
            "action": action,
            "current_publication": current_publication,
            "action_completed": len(verified) == len(inputs),
            "receipts": verified,
            "expected_rows": sum(a["record_count"] for a in inputs),
            "staged_rows": staged,
            "committed_rows": sum(r["record_count"] for r in verified),
            "current_effect": verified[-1]["current_effect"] if verified else None,
            "commit_verification": "verified",
        }


def package_progress(
    store: Store, packages: list[dict], progress: dict, owner: str
) -> None:
    active_id = progress.get("current_package_id") if owner == "verified" else None
    complete = sum(p["state"] in COMPLETE for p in packages)
    active = sum(p["id"] == active_id and p["state"] not in COMPLETE for p in packages)
    failed = sum(p["state"] == "failed" and p["id"] != active_id for p in packages)
    progress["packages"] = {
        "total": len(packages),
        "complete": complete,
        "active": active,
        "failed": failed,
        "pending": len(packages) - complete - active - failed,
    }
    ids = {p["export_id"] for p in packages if p.get("export_id")}
    progress["exported_rows"] = sum(
        store.read("exports", identity, records=False).get("record_count", 0)
        for identity in ids
    )


def snapshot(config_file: Path, kind: str, identity: str) -> dict:
    try:
        return _snapshot(config_file, kind, identity)
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise CliError(
            "WORKFLOW_ERROR", "Task metadata is unavailable or invalid"
        ) from error


def _snapshot(config_file: Path, kind: str, identity: str) -> dict:
    store = Store(config_file)
    if kind not in KINDS:
        raise CliError("INVALID_ARGUMENT", "Unknown workflow task kind", exit_code=2)
    if kind == "import":
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity):
            raise CliError("INVALID_ARGUMENT", "Invalid saved identity", exit_code=2)
        if not (store.root / "imports" / (identity + ".json")).is_file():
            raise CliError("WORKFLOW_ERROR", "Exact import plan is unavailable")
        if (store.root / "import_headers" / (identity + ".json")).is_file():
            task = store.read("import_headers", identity)
        else:
            # Legacy row-bearing plans remain executable and inspectable by
            # their original surfaces. Polling cannot parse their row arrays.
            task = {
                "id": identity,
                "created_at": None,
                "legacy_metadata_unavailable": True,
            }
    else:
        task = store.read(KINDS[kind], identity)
    if kind == "repair" and task.get("mode") != "repair":
        raise CliError(
            "INVALID_ARGUMENT", "Selected object is not a repair", exit_code=2
        )
    path = _path(store, kind, identity)
    state = _read(path)
    if state and (state.get("id") != identity or state.get("kind") != kind):
        raise CliError("WORKFLOW_ERROR", "Task attempt metadata identity differs")
    current = state["attempts"][-1] if state and state["attempts"] else None
    owner = ownership(path, current)
    effective = "pending" if task.get("task_contract") == 1 else "unknown"
    if current:
        effective = current["state"]
        if effective == "running":
            effective = {"verified": "running", "exited": "interrupted"}.get(
                owner, "unknown"
            )
    result = None
    quality = {"complete": None, "dataset_complete": None}
    progress = dict(state.get("progress", {})) if state else {}
    if kind == "export":
        plan = run_plan(task)
        if plan["mode"] == "history":
            from .workflow_history import coverage

            result = coverage(store, plan)
            packages = result["packages"]
            package_progress(store, packages, progress, owner)
            complete = result["complete"]
        else:
            exports = store.exports_for(identity)
            successful = [e for e in exports if e["state"] in COMPLETE]
            selected = (
                (successful or sorted(exports, key=lambda e: e["completed_at"]))[-1]
                if exports
                else None
            )
            complete = bool(successful)
            progress["exported_rows"] = (
                selected.get("record_count", 0) if selected else 0
            )
            if selected:
                result = {
                    "export_id": selected["id"],
                    "state": selected["state"],
                    "record_count": selected.get("record_count"),
                }
        if complete:
            effective = "completed"
            quality = {"complete": True, "dataset_complete": True}
        elif result and current and effective in {"completed", "incomplete"}:
            effective = "incomplete"
            quality = {"complete": False, "dataset_complete": False}
    if kind == "repair":
        from .workflow_repair import inspect

        result = inspect(store, task)
        complete = result["complete"]
        packages = result["packages"]
        package_progress(store, packages, progress, owner)
        progress["packages"]["baseline_reused"] = len(task["baseline_exports"])
        baseline_ids = {p["export_id"] for p in task["baseline_exports"]}
        progress["baseline_exported_rows"] = sum(
            store.read("exports", identity, records=False).get("record_count", 0)
            for identity in baseline_ids
        )
        if complete:
            effective = "completed"
            quality = {"complete": True, "dataset_complete": True}
    if kind == "target":
        from .workflow_targets import execution_status

        result = execution_status(store, task)
        children = [
            {
                "kind": "export",
                "id": p.get("run_id"),
                "plan_id": p["plan_id"],
                "complete": p["complete"],
                "effective_state": p.get(
                    "effective_state", "completed" if p["complete"] else "unknown"
                ),
            }
            for p in result["packages"]
        ]
        child_states = [child["effective_state"] for child in children]
        progress["packages"] = {
            "total": len(children),
            "complete": sum(p["complete"] for p in children),
            "active": child_states.count("running"),
            "pending": child_states.count("pending"),
            "failed": child_states.count("failed"),
            "incomplete": child_states.count("incomplete"),
            "interrupted": child_states.count("interrupted"),
            "unknown": child_states.count("unknown"),
            "unknown_reason": (
                "child_task_state_unverified" if "unknown" in child_states else None
            ),
        }
        result = {
            "target_id": task["target_id"],
            "complete": result["complete"],
            "children": children,
            "diagnostics": task["diagnostics"],
        }
        current_run = progress.get("current_run_id")
        if current_run in task.get("runs", []):
            child = snapshot(config_file, "export", current_run)
            result["current_child"] = {
                key: child[key]
                for key in ("id", "effective_state", "phase", "attempt", "progress")
            }
        if result["complete"]:
            effective = "completed"
            quality = {"complete": True, "dataset_complete": True}
    if (
        kind in {"repair", "target"}
        and current
        and result
        and result["complete"] is False
        and effective in {"completed", "incomplete", "failed", "interrupted"}
    ):
        quality = {"complete": False, "dataset_complete": False}
        if effective == "completed":
            effective = "incomplete"
    if kind in {"export", "repair"} and result and "packages" in result:
        result = {
            **result,
            "packages": [
                {key: package.get(key) for key in ("id", "state", "range", "export_id")}
                for package in result["packages"]
            ],
        }
    verification_source = "immutable_export_metadata" if result else None
    verification_reason = None
    read_quality = "degraded" if effective == "unknown" else "ok"
    if kind == "import" and not task.get("legacy_metadata_unavailable"):
        result = {
            "action": task["action"],
            "action_completed": None,
            "commit_verification": "unavailable",
            "replayed": state.get("result", {}).get("replayed") if state else None,
        }
        if owner == "verified":
            verification_reason = (
                "Active writer: independent database verification deferred"
            )
            read_quality = "degraded"
            for metric in ("committed_rows", "staged_rows"):
                progress.setdefault(metric, None)
        else:
            try:
                result.update(import_proof(task))
                verification_source = "database_receipts"
                for metric in ("expected_rows", "staged_rows", "committed_rows"):
                    progress[metric] = result.pop(metric)
                if result["action_completed"]:
                    effective = "completed"
                elif current and effective == "completed":
                    effective = "unknown"
                    read_quality = "degraded"
            except (CliError, KeyError, TypeError, ValueError):
                verification_reason = (
                    "Registered destination receipt verification unavailable"
                )
                read_quality = "degraded"
                progress["committed_rows"] = None
                if effective == "completed":
                    effective = "unknown"
        progress["current_input"] = {
            key: progress.get(key)
            for key in (
                "export_id",
                "expected_rows",
                "staged_rows",
                "committed_rows",
                "replayed",
                "inserted_count",
            )
        }
        progress["expected_rows"] = sum(
            a["record_count"] for a in task["input_metadata"]
        )
        if owner == "verified":
            inputs_progress = state.get("input_progress", {}) if state else {}
            for metric in ("staged_rows", "committed_rows", "inserted_count"):
                values = [
                    inputs_progress.get(a["id"], {}).get(metric)
                    for a in task["input_metadata"]
                ]
                progress[metric] = (
                    sum(values) if all(type(v) is int for v in values) else None
                )
            progress["known_committed_rows"] = sum(
                p.get("committed_rows", 0) for p in inputs_progress.values()
            )
    if task.get("legacy_metadata_unavailable"):
        verification_reason = (
            "Historical import has no bounded task metadata; "
            "execution telemetry unavailable"
        )
        effective, read_quality = "unknown", "degraded"
    for metric in (
        "source_pages",
        "request_attempts",
        "source_rows_received",
        "source_total_rows",
        "exported_rows",
        "expected_rows",
        "staged_rows",
        "committed_rows",
        "row_rate_per_second",
        "eta_seconds",
    ):
        progress.setdefault(metric, None)
    progress.setdefault("source_total_scope", None)
    progress["source_total_scope_reason"] = (
        None
        if progress["source_total_scope"] is not None
        else "native_total_unavailable"
        if progress["source_total_rows"] is None
        else "source_scope_unrecorded"
    )
    if effective != "running":
        progress["eta_seconds"] = None
        progress["eta_reason"] = "task_not_running"
    observed = now()
    stamp = state.get("updated_at") if state else task["created_at"]
    age = (
        max(
            0,
            (
                datetime.now(timezone.utc) - datetime.fromisoformat(stamp)
            ).total_seconds(),
        )
        if stamp
        else None
    )
    return {
        "kind": kind,
        "id": identity,
        "plan_id": task.get("plan_id"),
        "created_at": task["created_at"],
        "effective_state": effective,
        "leaf": task.get("plan", task).get("leaf"),
        "operation": task.get("plan", task).get("operation"),
        "elapsed_seconds": max(
            0,
            (
                datetime.fromisoformat(current.get("completed_at") or observed)
                - datetime.fromisoformat(current["started_at"])
            ).total_seconds(),
        )
        if current
        else None,
        "phase": current.get("phase") if current else effective,
        "attempt": {k: v for k, v in current.items() if k != "owner"}
        if current
        else None,
        "attempt_count": state["attempt_count"] if state else 0,
        "recent_attempts": [
            {k: v for k, v in a.items() if k != "owner"} for a in state["attempts"][:-1]
        ]
        if state
        else [],
        "last_successful_attempt": state.get("last_successful_attempt")
        if state
        else None,
        "progress": progress,
        "result": result,
        "quality": quality,
        "last_progress_at": state.get("last_progress_at") if state else None,
        "heartbeat_at": state.get("heartbeat_at") if state else None,
        "summary_updated_at": state.get("updated_at") if state else None,
        "observation": {
            "quality": read_quality,
            "observed_at": observed,
            "source_age_seconds": age,
            "ownership": owner,
            "completion_verification": {
                "source": verification_source,
                "verified_at": observed if verification_source else None,
                "reason": verification_reason,
            },
        },
    }
