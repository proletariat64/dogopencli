"""Portable synchronization declarations are validated before installation."""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_install_rejects_sync_key_without_native_identity(run_cli, tmp_path):
    source = tmp_path / "sample"
    shutil.copytree(ROOT / "tools/leaf-dev/example", source)
    path = source / "leaf.json"
    manifest = json.loads(path.read_text())
    manifest["sync"] = [
        {
            "variant": "default",
            "mode": "settings",
            "key_fields": [],
            "scope_parameters": [],
            "evidence": "Complete sample inquiry.",
        }
    ]
    path.write_text(json.dumps(manifest))
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 1
    assert "sync" in output


def test_install_rejects_time_range_as_record_namespace(run_cli, tmp_path):
    source = tmp_path / "balances"
    shutil.copytree(ROOT / "leaf_packages/liquidity/cash.balances", source)
    path = source / "leaf.json"
    manifest = json.loads(path.read_text())
    manifest["sync"][1]["scope_parameters"] = ["from-date"]
    path.write_text(json.dumps(manifest))
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 1
    assert "time windows cannot be record namespaces" in output


def test_install_rejects_following_unknown_source_clock(run_cli, tmp_path):
    source = tmp_path / "swaps"
    shutil.copytree(ROOT / "leaf_packages/liquidity/operations.swaps", source)
    path = source / "leaf.json"
    manifest = json.loads(path.read_text())
    manifest["sync"][0]["time"]["follow_supported"] = True
    path.write_text(json.dumps(manifest))
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 1
    assert "qualified timezone and partitioning" in output


def test_new_package_can_declare_sync_without_host_registration(run_cli, tmp_path):
    source = tmp_path / "future"
    shutil.copytree(ROOT / "tools/leaf-dev/example", source)
    path = source / "leaf.json"
    manifest = json.loads(path.read_text())
    manifest["sync"] = [
        {
            "variant": "default",
            "mode": "settings",
            "key_fields": ["id"],
            "scope_parameters": [],
            "evidence": "Complete native sample list with unique id.",
        }
    ]
    path.write_text(json.dumps(manifest))
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 0, output
    code, output, _ = run_cli(["collection", "describe", "sample.records"])
    assert code == 0, output
