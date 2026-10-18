"""Author helper acceptance through its standalone script entry point."""

import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/leaf-dev/leaf.py"


def invoke(*arguments, umask=-1):
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, arguments)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        umask=umask,
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
    output = tmp_path / "delivery/payment.sla.baselines.zip"
    packed = invoke("pack", source, "--output", output.parent)
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
    output = tmp_path / "delivery"
    output.write_bytes(b"keep existing output")
    assert invoke("pack", source, "--output", output).returncode != 0
    assert output.read_bytes() == b"keep existing output"
    nested = source / "delivery.zip"
    assert invoke("pack", source, "--output", nested).returncode != 0
    assert not nested.exists()


def test_helper_rejects_invalid_input_without_output(source, tmp_path):
    (source / "leaf.json").write_text("{}")
    output = tmp_path / "invalid/payment.sla.baselines.zip"
    assert invoke("verify", source).returncode != 0
    assert invoke("pack", source, "--output", output.parent).returncode != 0
    assert not output.exists()
    assert (source / "leaf.json").read_text() == "{}"
    assert invoke("verify", "https://example.invalid/package.zip").returncode != 0


def test_batch_pack_is_atomic_and_rejects_duplicate_identities(source, tmp_path):
    other = tmp_path / "other"
    shutil.copytree(source, other)
    manifest = json.loads((other / "leaf.json").read_text())
    manifest["name"] = "sla.other"
    manifest["dataset"]["relation"] = "payment_sla_other"
    (other / "leaf.json").write_text(json.dumps(manifest))
    output = tmp_path / "batch"
    result = invoke("pack", source, other, "--output", output)
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["packages"] == 2
    assert {p.name for p in output.glob("*.zip")} == {
        "payment.sla.baselines.zip",
        "payment.sla.other.zip",
    }
    invalid = tmp_path / "invalid-batch"
    (other / "leaf.json").write_text("{}")
    assert invoke("pack", source, other, "--output", invalid).returncode == 1
    assert not invalid.exists()
    duplicate = tmp_path / "duplicate-batch"
    result = invoke("pack", source, source, "--output", duplicate)
    assert result.returncode == 1
    assert (
        json.loads(result.stdout)["message"]
        == "Duplicate leaf identity: payment.sla.baselines"
    )
    assert not duplicate.exists()
    assert not list(tmp_path.glob(".leaf-pack-*"))


def test_helper_pack_install_preserves_empty_directories(source, tmp_path, run_cli):
    (source / "resources/empty/nested").mkdir(parents=True)
    output = tmp_path / "empty/payment.sla.baselines.zip"
    packed = invoke("pack", source, "--output", output.parent)
    assert packed.returncode == 0, packed.stdout + packed.stderr
    with zipfile.ZipFile(output) as archive:
        assert "resources/empty/nested/" in archive.namelist()
    # Installation checks interface only; use the valid bundled adapter.
    (source / "adapter.py").write_bytes(
        (
            ROOT / "src/dogopencli/leaf_packages/payment/sla.baselines/adapter.py"
        ).read_bytes()
    )
    runnable = tmp_path / "runnable/payment.sla.baselines.zip"
    assert invoke("pack", source, "--output", runnable.parent).returncode == 0
    code, out, error = run_cli(["plugins", "install", str(runnable)])
    assert (code, error) == (0, ""), out + error
    installed = tmp_path / "plugins/payment/sla.baselines"
    assert (installed / "resources/empty/nested").is_dir()
    assert (installed / "resources/help.txt").read_text() == "ordinary resource\n"


@pytest.mark.parametrize("compression", [zipfile.ZIP_DEFLATED, zipfile.ZIP_LZMA])
@pytest.mark.parametrize("entry_point", ["helper", "install"])
def test_corrupt_compressed_zip_has_static_diagnostics(
    source, tmp_path, run_cli, compression, entry_point
):
    if compression == zipfile.ZIP_LZMA:
        pytest.importorskip("lzma")
    archive_path = tmp_path / "corrupt-content.zip"
    with zipfile.ZipFile(archive_path, "w", compression) as archive:
        archive.write(source / "leaf.json", "leaf.json")
        archive.write(source / "adapter.py", "adapter.py")
        header = archive.getinfo("leaf.json").header_offset
    data = bytearray(archive_path.read_bytes())
    name_length, extra_length = struct.unpack_from("<HH", data, header + 26)
    payload = header + 30 + name_length + extra_length
    if compression == zipfile.ZIP_DEFLATED:
        # Reserved block type, leaving central directory and local header intact.
        data[payload] = (data[payload] & ~7) | 7
    else:
        # ZIP LZMA header: version (2), property length (2), properties.
        data[payload + 4] = 255
    archive_path.write_bytes(data)
    original = archive_path.read_bytes()
    scope = tmp_path / "operator"
    if entry_point == "helper":
        result = invoke("verify", archive_path)
        assert result.returncode == 1
        assert result.stderr == ""
        diagnostic = json.loads(result.stdout)
        assert diagnostic["error"] == "INVALID_PACKAGE"
    else:
        code, output, error = run_cli(
            ["--config-dir", str(scope), "plugins", "install", str(archive_path)]
        )
        assert (code, error) == (1, "")
        diagnostic = json.loads(output)["error"]
        assert diagnostic["code"] == "INVALID_PACKAGE"
    assert "ZIP integrity" in diagnostic["message"]
    assert archive_path.read_bytes() == original
    assert not (scope / "plugins").exists()
    assert not (scope / "duckdog.duckdb").exists()


@pytest.mark.parametrize(("umask", "permissions"), [(0o022, 0o644), (0o077, 0o600)])
def test_helper_pack_respects_artifact_umask(source, tmp_path, umask, permissions):
    output = tmp_path / "portable/payment.sla.baselines.zip"
    result = invoke("pack", source, "--output", output.parent, umask=umask)
    assert result.returncode == 0, result.stdout + result.stderr
    assert stat.S_IMODE(output.stat().st_mode) == permissions
    assert invoke("verify", output).returncode == 0
    assert list(tmp_path.glob(".leaf-pack-*")) == []


def test_same_contents_produce_same_zip_despite_source_metadata(source, tmp_path):
    first, second = (
        tmp_path / "one/payment.sla.baselines.zip",
        tmp_path / "two/payment.sla.baselines.zip",
    )
    assert invoke("pack", source, "--output", first.parent).returncode == 0
    for path in source.rglob("*"):
        os.utime(path, (1_700_000_000, 1_700_000_000))
        path.chmod(0o700 if path.is_dir() else 0o600)
    assert invoke("pack", source, "--output", second.parent).returncode == 0
    assert first.read_bytes() == second.read_bytes()
    (source / "resources/help.txt").write_text("changed ordinary resource\n")
    third = tmp_path / "three/payment.sla.baselines.zip"
    assert invoke("pack", source, "--output", third.parent).returncode == 0
    assert third.read_bytes() != first.read_bytes()
