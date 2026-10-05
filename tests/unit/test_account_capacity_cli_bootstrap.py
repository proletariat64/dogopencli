"""Cold public CLI startup catches registration/collector import cycles."""

import os
import subprocess
import sys
from pathlib import Path

from dogopencli.jsonutil import parse


def test_fresh_cli_process_bootstraps_without_collection_import_cycle(tmp_path):
    environment = dict(os.environ)
    source = Path(__file__).resolve().parents[2] / "src"
    environment["PYTHONPATH"] = str(source)
    environment["DOGOPENCLI_CONFIG"] = str(tmp_path / "missing-config.toml")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dogopencli",
            "help",
            "liquidity",
            "risk",
            "account-capacity",
            "list",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert parse(result.stdout)["kind"] == "runtimes"
    assert list(tmp_path.iterdir()) == []
