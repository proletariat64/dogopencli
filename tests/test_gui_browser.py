"""Optional real-browser acceptance against an isolated installed leaf.

Set DOGOPENCLI_PLAYWRIGHT_MODULE to an installed Playwright module directory.
DOGOPENCLI_CHROME optionally selects an existing Chromium executable.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from test_leaf_editor import editor as editor  # Reuse the isolated HTTP fixture.


def test_gui_browser_acceptance(editor):
    if not os.environ.get("DOGOPENCLI_PLAYWRIGHT_MODULE") or not shutil.which("node"):
        pytest.skip("Set DOGOPENCLI_PLAYWRIGHT_MODULE and install Node for browser UAT")
    url, _, manifest = editor
    original = json.loads(manifest.read_text())
    original["operations"]["get"]["parameters"] = [
        {
            "name": "native-revision",
            "type": "integer",
            "description": "Native version",
            "required": False,
            "default": 9007199254740993,
        }
    ]
    manifest.write_text(json.dumps(original))
    other = manifest.parent.parent / "sample_two"
    other.mkdir()
    payload = json.loads(manifest.read_text())
    payload.update(name="sample_two", summary="Second document")
    (other / "leaf.json").write_text(json.dumps(payload))
    shutil.copy(manifest.parent / "adapter.py", other / "adapter.py")
    result = subprocess.run(
        ["node", str(Path(__file__).parent / "browser/gui.cjs"), url, str(manifest)],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
