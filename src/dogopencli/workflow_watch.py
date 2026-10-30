"""Read-only observation of one exact workflow task."""

import sys
from datetime import datetime
from pathlib import Path
from shutil import get_terminal_size
from time import monotonic, sleep
from typing import TYPE_CHECKING

from .errors import CliError
from .helpspec import opt

if TYPE_CHECKING:
    from .command_model import Invocation

SELECTORS = {
    "export": "run",
    "repair": "repair",
    "import": "plan",
    "target": "execution",
}


def declaration_entries() -> list[tuple]:
    entries = [
        (
            ("workflow", kind, "status"),
            "Read one exact task's current metadata offline; defaults to JSON.",
            (opt(name, "Exact prepared task identity.", required=True),),
        )
        for kind, name in SELECTORS.items()
    ]
    entries.extend(
        (
            ("workflow", kind, "watch"),
            "Watch one exact task offline in resident text "
            "(default interval 3 seconds).",
            (
                opt(name, "Exact prepared task identity.", required=True),
                opt(
                    "snapshot",
                    "Print one fresh text frame and exit.",
                    "bool",
                    default=False,
                ),
                opt(
                    "until_settled",
                    "Wait for the current settled result and exit.",
                    "bool",
                    default=False,
                ),
                opt(
                    "attach",
                    "Start this resident observer in an existing idle Herdr pane.",
                ),
                opt(
                    "interval",
                    "Positive polling interval in whole seconds.",
                    "int",
                    default=3,
                ),
                opt(
                    "format",
                    "Watch execution accepts text only; help accepts json or text.",
                    default="json",
                    help_default="text",
                    choices=("json", "text"),
                ),
            ),
        )
        for kind, name in SELECTORS.items()
    )
    return entries


def selector(invocation: "Invocation") -> str:
    return getattr(invocation.args, SELECTORS[invocation.node.path[1]])


def read(config_file: Path, kind: str, identity: str) -> dict:
    from .workflow_tasks import snapshot

    try:
        return snapshot(config_file, kind, identity)
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise CliError(
            "WORKFLOW_ERROR", "Local workflow state is unavailable or malformed"
        ) from error


def _value(value: object) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value).replace("\x1b", "").replace("\r", " ")


def render_frame(
    data: dict, *, frame_age_seconds: float = 0, read_error: CliError | None = None
) -> str:
    """Use snapshot facts without deriving completeness from a counter ratio."""
    attempt = data["attempt"]
    progress = data["progress"]
    observation = data["observation"]
    lines = [
        f"{data['kind'].upper()}  {data['id']}",
        f"State: {data['effective_state']}   Phase: {_value(data['phase'])}",
        "Attempt: "
        + (
            f"{attempt['number']} / {data['attempt_count']}  {attempt['id']}  "
            f"raw={attempt['state']}"
            if attempt
            else "not started"
        ),
    ]
    if read_error:
        lines.insert(0, f"STALE — last good frame age: {frame_age_seconds:.1f} seconds")
        lines.insert(1, f"Current read error: {read_error.code}: {read_error.message}")
    if data.get("leaf"):
        lines.append(f"Inquiry: {data['leaf']}  {_value(data['operation'])}")
    lines.append(f"Elapsed: {_value(data['elapsed_seconds'])} seconds")
    if progress.get("packages"):
        lines.append(
            "Packages: "
            + "  ".join(
                f"{name}={_value(value)}"
                for name, value in progress["packages"].items()
            )
        )
    for key, label in (
        ("current_package_id", "Package"),
        ("current_run_id", "Child Run"),
        ("source", "Source"),
        ("candidate", "Candidate"),
        ("candidate_page_size", "Candidate page size"),
    ):
        if progress.get(key) is not None:
            lines.append(f"{label}: {_value(progress[key])}")
    if data["kind"] != "import":
        lines.extend(
            [
                f"Source pages: {_value(progress.get('source_pages'))}   "
                "Physical request attempts: "
                f"{_value(progress.get('request_attempts'))}",
                "Received rows (provisional): "
                f"{_value(progress.get('source_rows_received'))}   "
                f"Selected rows: {_value(progress.get('source_rows_selected'))}",
                f"Native total rows: {_value(progress.get('source_total_rows'))}   "
                f"scope={_value(progress.get('source_total_scope'))}",
            ]
        )
        for key, label in (
            ("operation_request_attempts", "Operation physical request attempts"),
            ("component_requests_completed", "Component requests completed"),
            ("root_rows_received", "Get root rows"),
            ("detail_rows_completed", "Detail rows completed"),
            ("detail_rows_expected", "Detail rows expected"),
            ("baseline_exported_rows", "Frozen baseline exported rows"),
        ):
            if key in progress:
                lines.append(f"{label}: {_value(progress[key])}")
        lines.append(f"Exported rows (saved): {_value(progress.get('exported_rows'))}")
    else:
        for key, label in (
            ("expected_rows", "Expected rows"),
            ("staged_rows", "Durable staged rows"),
            ("resumed_staged_rows", "Preserved staging validated this attempt"),
            ("committed_rows", "Verified committed rows"),
            ("known_committed_rows", "Known independent committed rows"),
            ("inserted_count", "New inserted rows"),
            ("replayed", "Receipt replay"),
        ):
            lines.append(f"{label}: {_value(progress.get(key))}")
        if progress.get("current_input"):
            lines.append(
                "Current input: "
                + "  ".join(
                    f"{key}={_value(value)}"
                    for key, value in progress["current_input"].items()
                )
            )
    running = data["effective_state"] == "running"
    rate_label = "Source row rate" if running else "Last source row rate"
    eta = (
        f"{_value(progress.get('eta_seconds'))} seconds"
        if running
        else "not applicable (task not running)"
    )
    lines.append(
        f"{rate_label}: {_value(progress.get('row_rate_per_second'))} rows/s   "
        f"Source ETA: {eta}"
    )
    lines.append(
        f"Complete: {_value(data['quality']['complete'])}   "
        f"Dataset complete: {_value(data['quality']['dataset_complete'])}"
    )
    if attempt:
        lines.append(f"Attempt started: {_value(attempt['started_at'])}")
        lines.append(f"Attempt completed: {_value(attempt.get('completed_at'))}")
    if attempt and attempt.get("error"):
        lines.append(f"Attempt error: {_value(attempt['error'])}")
    if data.get("result") is not None:
        from .rendering import render_text

        lines.append("Result / proof:\n" + render_text(data["result"], 1))
    previous = data.get("recent_attempts", [])
    if previous:
        lines.append(
            "Recent attempts: "
            + "; ".join(f"{a['number']} {a['id']} {a['state']}" for a in previous)
        )
    if data.get("last_successful_attempt"):
        lines.append(
            "Last successful attempt: " + _value(data["last_successful_attempt"])
        )
    for key, label in (
        ("created_at", "Task created"),
        ("last_progress_at", "Last actual progress"),
        ("heartbeat_at", "Runner heartbeat"),
        ("summary_updated_at", "Summary updated"),
    ):
        lines.append(f"{label}: {_value(data.get(key))}")
    if data.get("last_progress_at"):
        progress_age = (
            max(
                0,
                (
                    datetime.fromisoformat(observation["observed_at"])
                    - datetime.fromisoformat(data["last_progress_at"])
                ).total_seconds(),
            )
            + frame_age_seconds
        )
        lines.append(f"Actual progress age: {progress_age:.1f} seconds")
    source_age = observation["source_age_seconds"]
    if source_age is not None:
        source_age += frame_age_seconds
    proof = observation["completion_verification"]
    lines.extend(
        [
            f"Observation: {observation['quality']}   "
            f"Ownership: {observation['ownership']}",
            f"Observed: {observation['observed_at']}   "
            f"Summary/source age: {_value(source_age)} seconds   "
            f"Frame age: {frame_age_seconds:.1f} seconds",
            f"Completion verification: {_value(proof['source'])}   "
            f"Verified at: {_value(proof['verified_at'])}",
        ]
    )
    if proof.get("reason"):
        lines.append("Verification note: " + _value(proof["reason"]))
    return "\n".join(lines)


def warn_if_degraded(data: dict) -> None:
    observation = data["observation"]
    if observation["quality"] == "degraded":
        reason = observation["completion_verification"].get("reason")
        print(
            "warning: observation degraded: "
            + (reason or "Task ownership or completion evidence is unavailable"),
            file=sys.stderr,
        )


def watch(invocation: "Invocation") -> int:
    args = invocation.args
    if args.format == "json" and any(
        token == "--format=json" for token in invocation.remaining
    ):
        raise CliError(
            "INVALID_ARGUMENT",
            "Watch accepts text only; use status for JSON.",
            exit_code=2,
        )
    if args.interval <= 0:
        raise CliError(
            "INVALID_ARGUMENT", "--interval must be a positive integer", exit_code=2
        )
    if (
        sum(bool(value) for value in (args.snapshot, args.until_settled, args.attach))
        > 1
    ):
        raise CliError(
            "INVALID_ARGUMENT",
            "--snapshot, --until-settled and --attach are mutually exclusive",
            exit_code=2,
        )
    kind = invocation.node.path[1]
    identity = selector(invocation)
    if args.attach:
        # Validate the exact selected object before submitting any pane command.
        read(invocation.config_file, kind, identity)
        from .leaves.cli import emit
        from .workflow_attach import attach_watch

        receipt = attach_watch(
            invocation.config_file,
            kind,
            identity,
            pane=args.attach,
            interval=args.interval,
        )
        emit(receipt, output_format="text")
        return 0
    previous_lines = 0
    last_good = None
    last_good_at = None
    try:
        while True:
            try:
                data = read(invocation.config_file, kind, identity)
            except CliError as error:
                if last_good is None or args.snapshot or args.until_settled:
                    raise
                age = max(0, monotonic() - last_good_at)
                frame = render_frame(last_good, frame_age_seconds=age, read_error=error)
                print(f"warning: {error.code}: {error.message}", file=sys.stderr)
                data = None
            else:
                last_good, last_good_at = data, monotonic()
                frame = render_frame(data)
                warn_if_degraded(data)
            if previous_lines and sys.stdout.isatty():
                print(f"\x1b[{previous_lines}F\x1b[J", end="")
            print(frame, flush=True)
            columns = max(1, get_terminal_size().columns)
            previous_lines = sum(
                max(1, (len(line) + columns - 1) // columns)
                for line in frame.splitlines()
            )
            if args.snapshot:
                return 0
            if args.until_settled:
                state = data["effective_state"]
                if state in {"completed", "incomplete", "failed", "interrupted"}:
                    return 0 if state == "completed" else 1
                if state == "unknown":
                    raise CliError(
                        "WORKFLOW_ERROR",
                        "Cannot establish this task's liveness or completion "
                        "from current evidence",
                    )
            sleep(args.interval)
    except KeyboardInterrupt:
        print("Observer interrupted; task execution is unaffected.", file=sys.stderr)
        return 130
