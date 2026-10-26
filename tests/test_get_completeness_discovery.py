"""Every source Get advertises strict coverage without activating business code."""

import json
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
GET_MANIFESTS = sorted(
    path
    for directory in (ROOT / "src/dogopencli/leaf_packages", ROOT / "leaf_packages")
    for path in directory.glob("*/*/leaf.json")
    if "get" in json.loads(path.read_text())["operations"]
)


@pytest.mark.parametrize(
    "manifest_path",
    GET_MANIFESTS,
    ids=lambda path: ".".join(path.parts[-3:-1]),
)
def test_source_get_strict_option_is_declaration_only(
    manifest_path, run_cli, tmp_path, monkeypatch
):
    manifest = json.loads(manifest_path.read_text())
    domain, name = manifest["domain"], manifest["name"]
    target = tmp_path / "plugins" / domain / name
    target.mkdir(parents=True)
    (target / "leaf.json").write_text(json.dumps(manifest))
    # Discovery must not import business code, initialize storage or read config.
    (target / "adapter.py").write_text('raise AssertionError("adapter activated")')
    (tmp_path / "config.toml").write_text("[invalid")
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    def forbidden(*args, **kwargs):
        raise AssertionError("discovery started a browser or business connection")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    command = [domain, "get", name]
    code, out, err = run_cli([*command, "--require-complete", "--help"])
    assert (code, err) == (0, ""), out
    help_data = json.loads(out)["data"]
    assert "--require-complete" in {
        flag for option in help_data["options"] for flag in option["flags"]
    }
    code, out, err = run_cli([*command, "--help", "--format", "text"])
    assert (code, err) == (0, ""), out
    assert "--require-complete" in out
    code, out, err = run_cli([domain, "describe", name])
    assert (code, err) == (0, ""), out
    assert "--require-complete" in out
    assert before == {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
