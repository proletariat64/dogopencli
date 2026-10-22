"""Declared Get scope stays truthful across CLI documentation and GUI preview."""

import json
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from dogopencli.leaves.documentation import DocumentationEditor
from dogopencli.leaves.registry import Registry

ROOT = Path(__file__).resolve().parents[1]
NO_HISTORY = "Separate histories, logs and child pages are not acquired"


@pytest.mark.parametrize(
    "source,custom,shape",
    [
        ("leaf_packages/liquidity/network.realtime", True, "object"),
        ("leaf_packages/liquidity/network.route_quotas", True, "object"),
        ("src/dogopencli/leaf_packages/payment/sla.baselines", False, "object"),
        ("leaf_packages/liquidity/rules.waterlevel", False, "array"),
    ],
)
def test_public_get_scope_matches_describe_and_static_preview(
    run_cli, tmp_path, monkeypatch, source, custom, shape
):
    manifest = json.loads((ROOT / source / "leaf.json").read_text())
    domain, name = manifest["domain"], manifest["name"]
    installed = tmp_path / "plugins" / domain / name
    shutil.copytree(ROOT / source, installed)
    (installed / "adapter.py").write_text("raise AssertionError('adapter activated')")

    def forbidden(*args, **kwargs):
        pytest.fail("documentation activated runtime, business IO or a process")

    monkeypatch.setattr(Registry, "scan", forbidden)
    monkeypatch.setattr(Registry, "_load", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    before = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }

    code, output, error = run_cli([domain, "describe", name])
    assert (code, error) == (0, "")
    description = json.loads(output)["data"]
    guidance = description["detail_guidance"]
    assert description["operations"]["get"] == manifest["operations"]["get"]
    code, output, error = run_cli([domain, "get", name, "--help"])
    assert (code, error) == (0, "")
    help_document = json.loads(output)["data"]
    assert help_document["summary"] == manifest["operations"]["get"]["description"]
    assert guidance in help_document["constraints"]

    if custom:
        assert "custom" in guidance.lower()
        assert "query_evidence" in guidance
        assert NO_HISTORY not in " ".join(help_document["constraints"])
        assert "declared root " + shape in guidance
        if name == "network.realtime":
            assert "operation history" in help_document["summary"]
        else:
            assert "dynamic and static quotas" in help_document["summary"]
            assert "operation history" not in guidance
    else:
        assert "native root " + shape in guidance
        assert NO_HISTORY in guidance
        if shape == "array":
            assert "empty array stays empty" in guidance
            assert "--fields projects each member" in guidance

    for action in ([domain, "describe", name], [domain, "get", name, "--help"]):
        code, output, error = run_cli([*action, "--format", "text"])
        assert (code, error) == (0, "")
        assert guidance in " ".join(output.split())

    editor = DocumentationEditor(tmp_path / "config.toml")
    loaded = editor.load(domain, name)
    preview = editor.preview(
        domain,
        name,
        {"revision": loaded["revision"], "documentation": {"purpose": "Draft prose"}},
    )
    assert guidance in loaded["preview"]
    assert guidance in preview["preview"]
    assert "Draft prose" in preview["preview"]
    after = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert before == after


def test_custom_get_binding_help_retains_its_declared_scope(
    run_cli, tmp_path, monkeypatch
):
    installed = tmp_path / "plugins/collection/sample.records"
    shutil.copytree(ROOT / "tools/leaf-dev/example", installed)
    path = installed / "leaf.json"
    manifest = json.loads(path.read_text())
    manifest["operations"]["get"].update(
        execution="custom",
        description="Read the record and its qualified history.",
        queries={
            "root": {
                "kind": "detail",
                "result_identity": {"fields": ["id"], "description": "Native ID"},
            },
            "history": {"kind": "inquiry", "result_shape": "array"},
        },
        max_requests=4,
        budget_seconds=60,
    )
    path.write_text(json.dumps(manifest))
    (installed / "adapter.py").write_text("raise AssertionError('adapter activated')")

    def forbidden(*args, **kwargs):
        pytest.fail("documentation activated an adapter")

    monkeypatch.setattr(Registry, "scan", forbidden)
    monkeypatch.setattr(Registry, "_load", forbidden)
    code, output, error = run_cli(["collection", "describe", "sample.records"])
    assert (code, error) == (0, "")
    description = json.loads(output)["data"]
    guidance = description["composition_guidance"]
    assert NO_HISTORY not in guidance
    assert "custom Get" in guidance
    code, output, error = run_cli(["collection", "list", "sample.records", "--help"])
    assert (code, error) == (0, "")
    assert guidance in json.loads(output)["data"]["constraints"]
