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
    collection = manifest.parents[3] / "plugins/collection/sample_collection"
    collection.mkdir(parents=True)
    payload.update(
        domain="collection", name="sample_collection", summary="Collection-only summary"
    )
    (collection / "leaf.json").write_text(json.dumps(payload))
    shutil.copy(manifest.parent / "adapter.py", collection / "adapter.py")

    from dogopencli.cache import SnapshotMeta
    from dogopencli.domains import DomainService
    from dogopencli.leaves.runtime import cache_for
    from dogopencli.result_policy import AcquisitionEvidence

    config_file = manifest.parents[3] / "config.toml"
    cache_for(config_file).publish(
        SnapshotMeta(
            namespace="leaf:payment.sample",
            capability="payment.sample",
            scope="{}",
            source_kind="snapshot",
            snapshot_id="browser-example",
            dataset_id=None,
            simulated=True,
            backend_complete=False,
            dataset_complete=False,
            fetched_at="2026-10-21T10:00:00Z",
            loaded_at="2026-10-21T11:00:00Z",
            source_observed_from=None,
            source_observed_to=None,
            row_count=2,
            acquisition=AcquisitionEvidence.for_collection(
                complete=False, reported_total=3, collected_total=2, arrivals=2
            ).record(),
        ),
        [(1, '{"id":"example-one"}'), (2, '{"id":"example-two"}')],
    )
    DomainService(config_file).record_execution(
        "payment", "payment.sample", outcome="success", operation="get"
    )
    result = subprocess.run(
        ["node", str(Path(__file__).parent / "browser/gui.cjs"), url, str(manifest)],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
