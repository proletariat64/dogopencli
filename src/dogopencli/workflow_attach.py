"""Launch a resident workflow observer through the external Herdr boundary."""

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from .errors import INVALID_ARGUMENT, CliError

# --config-dir cannot express a custom filename. Keeping these values in argv
# also makes the selected config and current module tree verifiable by Herdr.
_BOOTSTRAP = (
    "import os,runpy,sys; "
    "os.environ.pop('DOGOPENCLI_CONFIG_DIR',None); "
    "os.environ['DOGOPENCLI_CONFIG']=sys.argv.pop(1); "
    "sys.path.insert(0,sys.argv.pop(1)); "
    "runpy.run_module('dogopencli',run_name='__main__')"
)
_SELECTORS = {
    "export": "--run",
    "repair": "--repair",
    "import": "--plan",
    "target": "--execution",
}


def attach_watch(
    config_file: Path, kind: str, identity: str, *, pane: str, interval: int = 3
) -> dict:
    """Attach one exact resident watcher; return only confirmed startup facts."""
    if os.environ.get("HERDR_ENV") != "1" or not os.environ.get("HERDR_PANE_ID"):
        raise CliError(INVALID_ARGUMENT, "watch attachment requires a Herdr caller")
    if (
        not isinstance(kind, str)
        or kind not in _SELECTORS
        or not isinstance(identity, str)
        or not identity.strip()
        or identity.startswith("-")
        or "\x00" in identity
        or not isinstance(pane, str)
        or not pane.strip()
        or pane.startswith("-")
        or "\x00" in pane
        or type(interval) is not int
        or interval < 1
    ):
        raise CliError(
            INVALID_ARGUMENT,
            "attach requires a typed identity, pane and positive integer interval",
        )
    selected_config = config_file.expanduser().resolve()
    cwd = Path.cwd()
    command = [
        sys.executable,
        "-c",
        _BOOTSTRAP,
        str(selected_config),
        str(Path(__file__).resolve().parent.parent),
        "workflow",
        kind,
        "watch",
        _SELECTORS[kind],
        identity,
        "--interval",
        str(interval),
        "--format=text",
    ]
    current = _herdr_json("pane", "current", "--current").get("pane")
    caller = current.get("pane_id") if isinstance(current, dict) else None
    # Live resolution also handles inherited caller IDs after a pane move.
    if not isinstance(caller, str) or not caller:
        raise CliError(INVALID_ARGUMENT, "Herdr caller context could not be verified")
    if caller == pane:
        raise CliError(INVALID_ARGUMENT, "cannot attach to the caller pane")
    _require_idle(pane)
    _require_idle(pane)
    launch = f"cd -- {shlex.quote(str(cwd))} && {shlex.join(command)}"
    _herdr_run("pane", "run", pane, launch)
    _confirm_startup(pane, command)
    return {
        "started": True,
        "pane": pane,
        "kind": kind,
        "identity": identity,
        "config_file": str(selected_config),
        "cwd": str(cwd),
    }


def _herdr_run(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["herdr", *args],
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=5,
        )
    except subprocess.TimeoutExpired as error:
        raise CliError("ATTACH_REJECTED", "Herdr command timed out") from error
    except OSError as error:
        raise CliError("ATTACH_REJECTED", "Herdr could not be invoked") from error
    if completed.returncode:
        raise CliError("ATTACH_REJECTED", "Herdr rejected the pane operation")
    return completed.stdout


def _herdr_json(*args: str) -> dict:
    try:
        response = json.loads(_herdr_run(*args))
    except (ValueError, TypeError) as error:
        raise CliError("ATTACH_REJECTED", "Herdr returned malformed JSON") from error
    result = response.get("result") if isinstance(response, dict) else None
    if not isinstance(result, dict):
        raise CliError("ATTACH_REJECTED", "Herdr returned malformed result")
    return result


def _require_idle(pane: str) -> None:
    target = _herdr_json("pane", "get", pane).get("pane")
    if not isinstance(target, dict) or target.get("pane_id") != pane:
        raise CliError("ATTACH_REJECTED", "target pane was not found")
    if target.get("agent"):
        raise CliError("ATTACH_REJECTED", "target pane is occupied by an agent")
    info = _herdr_json("pane", "process-info", "--pane", pane).get("process_info")
    if not isinstance(info, dict) or info.get("pane_id") != pane:
        raise CliError("ATTACH_REJECTED", "target pane process identity is unknown")
    processes = info.get("foreground_processes")
    shell_pid = info.get("shell_pid")
    if (
        type(shell_pid) is not int
        or shell_pid <= 0
        or not isinstance(processes, list)
        or len(processes) != 1
        or not isinstance(processes[0], dict)
        or processes[0].get("pid") != shell_pid
        or not processes[0].get("argv")
    ):
        raise CliError(
            "ATTACH_REJECTED", "target pane is busy or its foreground is unknown"
        )


def _confirm_startup(pane: str, command: list[str]) -> None:
    deadline = time.monotonic() + 5
    while True:
        info = _herdr_json("pane", "process-info", "--pane", pane).get("process_info")
        if not isinstance(info, dict) or info.get("pane_id") != pane:
            raise CliError(
                "ATTACH_STARTUP_UNCONFIRMED", "watch startup identity is unknown"
            )
        processes = info.get("foreground_processes")
        shell_pid = info.get("shell_pid")
        if type(shell_pid) is not int or shell_pid <= 0:
            raise CliError(
                "ATTACH_STARTUP_UNCONFIRMED", "watch startup shell is unknown"
            )
        if isinstance(processes, list) and len(processes) == 1:
            process = processes[0]
            if (
                isinstance(process, dict)
                and type(process.get("pid")) is int
                and process["pid"] > 0
                and process["pid"] != shell_pid
            ):
                if process.get("argv") == command:
                    return
                raise CliError(
                    "ATTACH_STARTUP_UNCONFIRMED", "watch startup command mismatched"
                )
        if time.monotonic() >= deadline:
            raise CliError(
                "ATTACH_STARTUP_UNCONFIRMED", "watch startup confirmation timed out"
            )
        time.sleep(0.1)
