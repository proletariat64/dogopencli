"""Reject unusable adapter signatures at public installation boundary."""

import json
import shutil
from pathlib import Path

import duckdb
import pytest


@pytest.mark.parametrize(
    "broken", ["capability", "scope", "collector", "filter", "detail_capability"]
)
def test_install_rejects_wrong_signature_without_storage(
    run_cli, tmp_path, monkeypatch, broken
):
    scope = tmp_path / "scope"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    source = tmp_path / "source"
    shutil.copytree(
        Path(__file__).parents[1]
        / "src/dogopencli/leaf_packages/payment/sla.baselines",
        source,
    )
    if broken == "collector":
        # Independently maintained non-SDK leaves still require a collector.
        manifest_path = source / "leaf.json"
        manifest = json.loads(manifest_path.read_text())
        manifest.pop("collection")
        manifest_path.write_text(json.dumps(manifest))
    methods = []
    for name in ["capability", "scope", "collector", "filter", "detail_capability"]:
        parameters = "self" if name == broken else "self, *args, **kwargs"
        methods.append(
            f"    def {name}({parameters}):\n"
            "        raise RuntimeError('method must never execute during install')\n"
        )
    (source / "adapter.py").write_text(
        "class Adapter:\n" + "".join(methods) + "adapter = Adapter()\n"
    )
    code, output, error = run_cli(["plugins", "install", str(source)])
    assert code == 1, output + error
    assert json.loads(output)["error"]["code"] == "INVALID_LEAF"
    assert not (scope / "plugins/payment/sla.baselines").exists()
    if (scope / "duckdog.duckdb").exists():
        with duckdb.connect(str(scope / "duckdog.duckdb")) as database:
            assert database.execute("SHOW TABLES").fetchall() == []


def test_install_accepts_variadic_adapter_without_executing_methods(
    run_cli, tmp_path, monkeypatch
):
    scope = tmp_path / "scope"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(scope))
    source = tmp_path / "source"
    shutil.copytree(
        Path(__file__).parents[1]
        / "src/dogopencli/leaf_packages/payment/sla.baselines",
        source,
    )
    (source / "adapter.py").write_text(
        "class Adapter:\n"
        "    def method(self, *args, **kwargs):\n"
        "        raise RuntimeError('method must never execute during install')\n"
        "    capability = scope = filter = detail_capability = method\n"
        "    def collector(self, capability, transport, scope, *, progress=None):\n"
        "        raise RuntimeError('method must never execute during install')\n"
        "adapter = Adapter()\n"
    )
    code, output, error = run_cli(["plugins", "install", str(source)])
    assert (code, error) == (0, ""), output + error
    assert (scope / "plugins/payment/sla.baselines").is_dir()
