"""Author helper acceptance through its standalone script entry point."""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/plugin-helper/scripts/plugin_helper.py"


def invoke(*arguments):
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, arguments)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "arbitrary-name"
    shutil.copytree(ROOT / "src/dogopencli/leaf_packages/payment/sla.baselines", path)
    (path / "adapter.py").write_text("raise RuntimeError('must never execute')\n")
    (path / "resources").mkdir()
    (path / "resources/help.txt").write_text("ordinary resource\n")
    return path


def test_helper_verifies_and_packs_static_snapshot(source, tmp_path):
    before = {
        p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()
    }
    verified = invoke("verify", source)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert json.loads(verified.stdout)["identity"] == "payment.sla.baselines"
    output = tmp_path / "arbitrary-delivery.zip"
    packed = invoke("pack", source, "--output", output)
    assert packed.returncode == 0, packed.stdout + packed.stderr
    assert invoke("verify", output).returncode == 0
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {p.as_posix() for p in before} | {
            "resources/"
        }
        assert archive.read("resources/help.txt") == b"ordinary resource\n"
    assert {
        p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()
    } == before
    assert not (tmp_path / "plugins").exists()


def test_helper_preserves_existing_output_and_rejects_self_inclusion(source, tmp_path):
    output = tmp_path / "delivery.zip"
    output.write_bytes(b"keep existing output")
    assert invoke("pack", source, "--output", output).returncode != 0
    assert output.read_bytes() == b"keep existing output"
    nested = source / "delivery.zip"
    assert invoke("pack", source, "--output", nested).returncode != 0
    assert not nested.exists()


def test_helper_rejects_invalid_input_without_output(source, tmp_path):
    (source / "leaf.json").write_text("{}")
    output = tmp_path / "invalid.zip"
    assert invoke("verify", source).returncode != 0
    assert invoke("pack", source, "--output", output).returncode != 0
    assert not output.exists()
    assert (source / "leaf.json").read_text() == "{}"
    assert invoke("verify", "https://example.invalid/package.zip").returncode != 0


def test_helper_pack_install_preserves_empty_directories(source, tmp_path, run_cli):
    (source / "resources/empty/nested").mkdir(parents=True)
    output = tmp_path / "with-empty-directories.zip"
    packed = invoke("pack", source, "--output", output)
    assert packed.returncode == 0, packed.stdout + packed.stderr
    with zipfile.ZipFile(output) as archive:
        assert "resources/empty/nested/" in archive.namelist()
    # Installation checks interface only; use the valid bundled adapter.
    (source / "adapter.py").write_bytes(
        (
            ROOT / "src/dogopencli/leaf_packages/payment/sla.baselines/adapter.py"
        ).read_bytes()
    )
    runnable = tmp_path / "runnable.zip"
    assert invoke("pack", source, "--output", runnable).returncode == 0
    code, out, error = run_cli(["plugins", "install", str(runnable)])
    assert (code, error) == (0, ""), out + error
    installed = tmp_path / "plugins/payment/sla.baselines"
    assert (installed / "resources/empty/nested").is_dir()
    assert (installed / "resources/help.txt").read_text() == "ordinary resource\n"
