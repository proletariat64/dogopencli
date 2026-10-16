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
    assert doc["data"]["usage"] == "dogopencli <domain> <action> <dotted-leaf>"
    assert doc["data"]["domains"] == ["collection", "fx", "liquidity", "payment"]
    assert doc["data"]["actions"] == [
        "list",
        "get",
        "refresh",
        "prune",
        "help",
        "describe",
    ]


def test_python_m_help_path(tmp_path) -> None:
    import shutil

    shutil.copytree(
        REPO_ROOT / "src/dogopencli/leaf_packages/payment/sla.baselines",
        tmp_path / "plugins/payment/sla.baselines",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dogopencli",
            "payment",
            "help",
            "sla.baselines",
            "--config-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        env=_env(),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    document = json.loads(result.stdout)["data"]
    assert document["id"] == "payment.sla.baselines"
    assert set(document["operations"]) == {"list", "get"}
    assert "--format json|text" in document["guidance"]


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
        env=_env(),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert "dogopencli <domain> <action> <dotted-leaf>" in result.stdout
    assert "payment" in result.stdout
