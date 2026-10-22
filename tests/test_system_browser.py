"""Optional isolated real-browser acceptance for the production System panel."""

import os
import shutil
import subprocess
import threading
from pathlib import Path

import duckdb
import pytest
from test_system_info import system_scope as system_scope

from dogopencli.domains import DomainService
from dogopencli.gui import create_server


@pytest.mark.parametrize("scenario", ["populated", "empty", "busy"])
def test_system_browser(system_scope, tmp_path, scenario):
    if not os.environ.get("DOGOPENCLI_PLAYWRIGHT_MODULE") or not shutil.which("node"):
        pytest.skip("Set DOGOPENCLI_PLAYWRIGHT_MODULE and install Node for browser UAT")
    config, _ = system_scope
    if scenario == "empty":
        config = tmp_path / "new-scope" / "config.toml"
    writer = (
        duckdb.connect(str(config.parent / "duckdog.duckdb"))
        if scenario == "busy"
        else None
    )
    server = create_server(DomainService(config))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                "node",
                str(Path(__file__).parent / "browser/system.cjs"),
                f"http://127.0.0.1:{server.server_port}",
                scenario,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        if writer is not None:
            writer.close()
