"""Host startup remains independent of retired business implementations."""

import os
import subprocess
import sys
from pathlib import Path


def test_public_help_and_domain_inventory_reject_retired_imports(tmp_path):
    script = r"""
import importlib.abc
import json
import sys

class RetiredImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "dogopencli.plugins" or fullname.startswith(
            "dogopencli.plugins."
        ):
            raise AssertionError("retired business import: " + fullname)

sys.meta_path.insert(0, RetiredImports())
from dogopencli.cli import main
for arguments in ([], ["payment", "--help"], ["domain", "list"]):
    assert main(arguments) == 0
assert not any(
    name == "dogopencli.plugins" or name.startswith("dogopencli.plugins.")
    for name in sys.modules
)
"""
    environment = dict(os.environ)
    environment["DOGOPENCLI_CONFIG"] = str(tmp_path / "config.toml")
    source = Path(__file__).resolve().parents[1] / "src"
    environment["PYTHONPATH"] = str(source)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "config.toml").exists()
