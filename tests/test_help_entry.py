"""Subprocess entry-point tests for the progressive help (Issue #13).

Covers the installed console script and ``python -m dogopencli``; the
in-process SIT in tests/integration/test_help_sit.py covers behavior.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return env


def test_python_m_entry_returns_root_json() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "dogopencli"],
        capture_output=True,
        text=True,
        env=_env(),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    doc = json.loads(result.stdout)
    assert doc["help_version"] == 1
    assert doc["command"] == "dogopencli"
    assert [child["name"] for child in doc["children"]] == [
        "snapshot",
        "domain",
        "gui",
        "payment",
        "refresh",
        "collection",
        "liquidity",
        "fx",
        "describe",
        "prune",
        "auth",
        "login",
        "logout",
    ]


def test_python_m_help_path() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "dogopencli", "help", "payment", "channel"],
        capture_output=True,
        text=True,
        env=_env(),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout)["command"] == "dogopencli payment channel"


def test_installed_console_script() -> None:
    script = REPO_ROOT / ".venv" / "bin" / "dogopencli"
    dogopencli = shutil.which("dogopencli") or (
        str(script) if script.exists() else None
    )
    if dogopencli is None:
        import pytest

        pytest.skip("dogopencli console script is not installed")
    result = subprocess.run(
        [dogopencli, "--format", "text"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.startswith("dogopencli\n")
    assert "payment" in result.stdout
