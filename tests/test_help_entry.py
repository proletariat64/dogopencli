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


def _env(tmp_path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["DOGOPENCLI_CONFIG"] = str(tmp_path / "config.toml")
    env["DOGOPENCLI_CONFIG_DIR"] = str(tmp_path)
    return env


def test_python_m_entry_returns_root_json(tmp_path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "dogopencli"],
        capture_output=True,
        text=True,
        env=_env(tmp_path),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    doc = json.loads(result.stdout)
    assert doc["data"]["command"] == "dogopencli"
    assert {child["name"] for child in doc["data"]["children"]} == {
        "auth",
        "collection",
        "domain",
        "fx",
        "gui",
        "liquidity",
        "login",
        "logout",
        "payment",
        "plugins",
        "workflow",
    }


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
            "list",
            "sla.baselines",
            "--help",
            "--config-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        env=_env(tmp_path),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    document = json.loads(result.stdout)["data"]
    assert document["command"] == "dogopencli payment list sla.baselines"
    assert document["children"] == []
    assert "options" in document and "fields" not in document


def test_installed_console_script(tmp_path) -> None:
    script = REPO_ROOT / ".venv" / "bin" / "dogopencli"
    dogopencli = shutil.which("dogopencli") or (
        str(script) if script.exists() else None
    )
    if dogopencli is None:
        import pytest

        pytest.skip("dogopencli console script is not installed")
    result = subprocess.run(
        [dogopencli, "--format", "text"],
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.startswith("Usage: dogopencli <command>")
    assert "plugins" in result.stdout.split("Commands:", 1)[1]
    assert "dogopencli <command> --help --format text" in result.stdout
