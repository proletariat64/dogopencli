"""Installed-wheel acceptance, opt-in through DOGOPENCLI_TEST_WHEEL."""

import json
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest


@pytest.mark.skipif(
    not os.environ.get("DOGOPENCLI_TEST_WHEEL"),
    reason="Build a wheel and set DOGOPENCLI_TEST_WHEEL for distribution proof.",
)
def test_wheel_bundled_discovery_help_install_outside_checkout(tmp_path):
    wheel = Path(os.environ["DOGOPENCLI_TEST_WHEEL"]).resolve(strict=True)
    environment_path = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False, system_site_packages=True).create(environment_path)
    python = environment_path / "bin/python"
    # Reuse the test environment's dependencies; the application itself must come
    # solely from the newly built wheel installed below.
    dependencies = subprocess.check_output(
        [sys.executable, "-c", "import site; print(':'.join(site.getsitepackages()))"],
        text=True,
    ).strip()
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["DOGOPENCLI_CONFIG"] = str(tmp_path / "state/config.toml")
    # Only third-party site-packages are shared; never put src or checkout on path.
    environment["PYTHONPATH"] = dependencies
    invocation = [str(python), "-m", "dogopencli"]

    def call(*arguments):
        return subprocess.run(
            [*invocation, *arguments],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    origin = subprocess.check_output(
        [str(python), "-c", "import dogopencli; print(dogopencli.__file__)"],
        cwd=tmp_path,
        env=environment,
        text=True,
    ).strip()
    assert str(environment_path) in origin
    listed = call("plugins", "list")
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert "payment.sla.baselines" in json.dumps(json.loads(listed.stdout))
    assert not (tmp_path / "state").exists()
    help_result = call("plugins", "install", "--help")
    assert help_result.returncode == 0, help_result.stdout + help_result.stderr
    installed = call("plugins", "install", "bundled:payment.sla.baselines")
    assert installed.returncode == 0, installed.stdout + installed.stderr
    manifest = tmp_path / "state/plugins/payment/sla.baselines/leaf.json"
    assert json.loads(manifest.read_text())["name"] == "sla.baselines"
    assert manifest.with_name("adapter.py").is_file()
