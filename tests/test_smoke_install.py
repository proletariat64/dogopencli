"""Installed release version must match the planned source version."""

import json
import subprocess
from pathlib import Path

import pytest

from scripts import smoke_install as tool


@pytest.mark.parametrize("reported", ["0.1.0", "0.0.9"])
def test_installed_version_is_checked_before_update(tmp_path, monkeypatch, reported):
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (tmp_path / "dogopencli-0.1.0-py3-none-any.whl").touch()
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["env"]["UV_PYTHON"] == tool.sys.executable
        if args[1:] == ["--version"]:
            output = json.dumps({"data": {"version": reported}})
        else:
            output = ""
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    monkeypatch.setattr(tool.subprocess, "run", run)
    if reported == "0.1.0":
        tool.smoke(tmp_path)
        assert calls[-1][1:] == ["uninstall"]
    else:
        with pytest.raises(ValueError, match="does not match planned release"):
            tool.smoke(tmp_path)
        assert len(calls) == 2
        assert calls[-1][1:] == ["--version"]


def test_install_failure_includes_local_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (tmp_path / "dogopencli-0.1.0-py3-none-any.whl").touch()
    monkeypatch.setattr(
        tool.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 1, stdout="install failed", stderr="missing dependency"
        ),
    )
    with pytest.raises(RuntimeError, match="missing dependency"):
        tool.smoke(Path(tmp_path))


def test_timeout_includes_partial_local_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (tmp_path / "dogopencli-0.1.0-py3-none-any.whl").touch()

    def timeout(args, **kwargs):
        raise subprocess.TimeoutExpired(
            args, 180, output=b"Installing", stderr=b"download stalled"
        )

    monkeypatch.setattr(tool.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="download stalled"):
        tool.smoke(tmp_path)
