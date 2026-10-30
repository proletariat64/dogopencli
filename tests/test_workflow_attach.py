"""Watch attachment at the public adapter/external Herdr process boundary."""

from pathlib import Path

import pytest

from dogopencli.errors import CliError
from dogopencli.workflow_attach import attach_watch


def test_outside_herdr_never_invokes_external_process(monkeypatch, tmp_path):
    monkeypatch.delenv("HERDR_ENV", raising=False)

    def unexpected(*args, **kwargs):
        pytest.fail("an invocation outside Herdr must not contact a server")

    monkeypatch.setattr("subprocess.run", unexpected)
    with pytest.raises(CliError, match="Herdr"):
        attach_watch(Path(tmp_path / "custom.toml"), "export", "run_one", pane="w1:p2")


@pytest.fixture
def herdr(monkeypatch):
    """Installed CLI-shaped process responses, with no real Herdr writes."""
    import json
    import shlex
    import subprocess

    class ProcessBoundary:
        caller = "w1:p1"
        target = "w1:p2"
        occupant = None
        foreground = [{"pid": 100, "argv": ["/bin/bash"]}]
        startup = "exact"
        reported_target = "w1:p2"
        startup_reads = 0
        startup_pid = 200

        def __init__(self):
            self.calls = []
            self.launched = None

        def run(self, argv, **kwargs):
            assert argv[0] == "herdr"
            assert kwargs["shell"] is False
            assert 0 < kwargs["timeout"] <= 5
            command = argv[1:]
            self.calls.append(command)
            if command == ["pane", "current", "--current"]:
                result = {"pane": {"pane_id": self.caller}}
            elif command == ["pane", "get", self.target]:
                result = {
                    "pane": {"pane_id": self.reported_target, "agent": self.occupant}
                }
            elif command == ["pane", "process-info", "--pane", self.target]:
                foreground = self.foreground
                if self.launched is not None:
                    self.startup_reads += 1
                pending = self.startup == "delayed" and self.startup_reads < 3
                if self.launched is not None and self.startup != "idle" and not pending:
                    child = shlex.split(self.launched)
                    assert child[0:1] == ["cd"] and child[3] == "&&"
                    child = child[4:]
                    if self.startup == "wrong":
                        child[-1] = "--format=json"
                    foreground = [{"pid": self.startup_pid, "argv": child}]
                result = {
                    "process_info": {
                        "pane_id": self.target,
                        "shell_pid": 100,
                        "foreground_processes": foreground,
                    }
                }
            elif command[:3] == ["pane", "run", self.target]:
                self.launched = command[3]
                return subprocess.CompletedProcess(argv, 0, "", "")
            else:
                pytest.fail(f"unexpected Herdr operation: {command}")
            return subprocess.CompletedProcess(
                argv, 0, json.dumps({"result": result}), ""
            )

    boundary = ProcessBoundary()
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    monkeypatch.setattr("subprocess.run", boundary.run)
    return boundary


def test_launch_confirms_exact_config_identity_and_current_runtime(
    herdr, tmp_path, monkeypatch
):
    import shlex
    import sys

    config = tmp_path / "a space'$(touch SHOULD_NOT_EXIST).toml"
    cwd = tmp_path / "working dir'$(touch SHOULD_NOT_EXIST)"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    receipt = attach_watch(config, "export", "run_one", pane="w1:p2", interval=4)
    command = shlex.split(herdr.launched)
    assert command[:4] == ["cd", "--", str(Path.cwd()), "&&"]
    argv = command[4:]
    assert argv[0] == sys.executable
    assert str(config) in argv
    assert argv[-8:] == [
        "workflow",
        "export",
        "watch",
        "--run",
        "run_one",
        "--interval",
        "4",
        "--format=text",
    ]
    assert "--attach" not in argv
    assert receipt["started"] is True
    assert receipt["pane"] == "w1:p2"
    assert receipt["identity"] == "run_one"
    assert receipt["config_file"] == str(config)
    assert all(
        call[1] in {"current", "get", "process-info", "run"} for call in herdr.calls
    )


@pytest.mark.parametrize(
    "failure", ["missing_binary", "timeout", "rejected", "json", "shape", "caller"]
)
def test_external_failure_is_a_safe_host_error(herdr, tmp_path, monkeypatch, failure):
    import subprocess

    def run(argv, **kwargs):
        if failure == "missing_binary":
            raise FileNotFoundError("secret path")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output="secret")
        if failure == "rejected":
            return subprocess.CompletedProcess(argv, 1, "", "secret native error")
        if failure == "json":
            output = "not JSON secret"
        elif failure == "shape":
            output = '{"result": []}'
        else:
            output = '{"result": {"pane": {"pane_id": null}}}'
        return subprocess.CompletedProcess(argv, 0, output, "")

    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(CliError) as error:
        attach_watch(tmp_path / "config.toml", "target", "execution_one", pane="w1:p2")
    assert "secret" not in error.value.message
    assert herdr.launched is None


@pytest.mark.parametrize(
    "unsafe", ["self", "agent", "busy", "unknown", "mismatched", "context"]
)
def test_unsafe_target_is_never_written(herdr, tmp_path, monkeypatch, unsafe):
    if unsafe == "self":
        herdr.caller = herdr.target
    elif unsafe == "agent":
        herdr.occupant = "codex"
    elif unsafe == "busy":
        herdr.foreground = [{"pid": 222, "argv": ["vim", "file"]}]
    elif unsafe == "unknown":
        herdr.foreground = []
    elif unsafe == "mismatched":
        herdr.reported_target = "w1:p3"
    elif unsafe == "context":
        monkeypatch.delenv("HERDR_PANE_ID")
    with pytest.raises(CliError):
        attach_watch(tmp_path / "config.toml", "export", "run_one", pane="w1:p2")
    assert herdr.launched is None


def test_startup_confirmation_waits_for_foreground_not_command_acceptance(
    herdr, tmp_path
):
    herdr.startup = "delayed"
    receipt = attach_watch(
        tmp_path / "config.toml", "repair", "repair_one", pane="w1:p2"
    )
    assert receipt["started"] is True
    assert herdr.startup_reads >= 3


@pytest.mark.parametrize("startup", ["idle", "wrong"])
def test_unconfirmed_startup_fails_without_interrupting_target(
    herdr, tmp_path, monkeypatch, startup
):
    import itertools

    herdr.startup = startup
    # Time is an external boundary: expire quickly without five seconds of sleep.
    ticks = itertools.count()
    monkeypatch.setattr("time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("time.sleep", lambda _: None)
    with pytest.raises(CliError, match="startup") as error:
        attach_watch(tmp_path / "config.toml", "import", "import_one", pane="w1:p2")
    assert error.value.code == "ATTACH_STARTUP_UNCONFIRMED"
    assert all(
        call[1] in {"current", "get", "process-info", "run"} for call in herdr.calls
    )


def test_exact_argv_without_valid_process_identity_is_not_startup(
    herdr, tmp_path, monkeypatch
):
    import itertools

    herdr.startup_pid = 0
    ticks = itertools.count()
    monkeypatch.setattr("time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("time.sleep", lambda _: None)
    with pytest.raises(CliError, match="startup"):
        attach_watch(tmp_path / "config.toml", "export", "run_one", pane="w1:p2")


@pytest.mark.parametrize(
    "options",
    [
        {"kind": "other"},
        {"identity": "--run=another"},
        {"identity": ""},
        {"pane": ""},
        {"interval": 0},
        {"interval": True},
        {"interval": 1.5},
    ],
)
def test_invalid_attach_selection_cannot_launch(herdr, tmp_path, options):
    arguments = {"kind": "export", "identity": "run_one", "pane": "w1:p2"}
    arguments.update(options)
    with pytest.raises(CliError) as error:
        attach_watch(tmp_path / "config.toml", **arguments)
    assert error.value.code == "INVALID_ARGUMENT"
    assert herdr.launched is None
