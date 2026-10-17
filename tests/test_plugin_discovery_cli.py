"""Plugin lifecycle navigation and declaration-only discovery through CLI."""

import json


def test_plugins_progressively_disclose_single_leaf_lifecycle(run_cli, tmp_path):
    for path, expected in [
        ([], {"plugins"}),
        (["plugins"], {"install", "uninstall", "list"}),
    ]:
        code, out, _ = run_cli([*path, "--help"])
        assert code == 0
        document = json.loads(out)["data"]
        assert expected <= {child["name"] for child in document["children"]}
    for action, argument in [("install", "source"), ("uninstall", "identity")]:
        code, out, _ = run_cli(["plugins", action, "--help"])
        assert code == 0
        document = json.loads(out)["data"]
        assert document["arguments"][0]["name"] == argument
        assert document["arguments"][0]["required"] is True
        assert run_cli(["plugins", action])[0] == 2
    assert run_cli(["plugins", "install-pilots"])[0] == 2
    assert not list(tmp_path.iterdir())


def test_list_distinguishes_bundled_installed_and_invalid_without_effects(
    run_cli, tmp_path, monkeypatch
):
    import shutil
    import socket
    from pathlib import Path

    from dogopencli.domains import DomainService
    from dogopencli.leaves.registry import Registry

    source = (
        Path(__file__).parents[1] / "src/dogopencli/leaf_packages/payment/sla.baselines"
    )
    target = tmp_path / "plugins/payment/sla.baselines"
    shutil.copytree(source, target)
    (target / "adapter.py").write_text('raise RuntimeError("must not execute")')
    broken = tmp_path / "plugins/payment/broken"
    broken.mkdir()
    (broken / "leaf.json").write_text("broken")
    (tmp_path / "config.toml").write_text("[invalid")
    for name in ("duckdog.duckdb", "leaf-cache.sqlite3", "leaf-registry.sqlite3"):
        (tmp_path / name).write_bytes(b"private state")

    def forbidden(*args, **kwargs):
        raise AssertionError("discovery crossed runtime boundary")

    monkeypatch.setattr(Registry, "scan", forbidden)
    monkeypatch.setattr(DomainService, "__init__", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    before = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    code, output, error = run_cli(["plugins", "list"])
    assert (code, error) == (0, "")
    result = json.loads(output)
    assert result["error"] is None
    rows = {item["identity"]: item for item in result["data"]["plugins"]}
    assert rows["payment.sla.baselines"]["state"] == "installed"
    assert rows["payment.sla.baselines"]["bundled"] is True
    assert rows["collection.cost"]["state"] == "available"
    assert rows["payment.broken"]["state"] == "invalid"
    assert rows["payment.broken"]["diagnostics"]
    assert (
        "dogopencli plugins uninstall payment.broken"
        in rows["payment.broken"]["next_commands"]
    )
    text_code, text, text_error = run_cli(["plugins", "list", "--format", "text"])
    assert (text_code, text_error) == (0, "")
    for row in rows.values():
        assert row["identity"] in text
        assert row["state"] in text
        assert row["summary"] in text
        assert all(command in text for command in row["next_commands"])
    after = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert before == after


def test_bundled_list_does_not_create_missing_configuration(run_cli, tmp_path):
    directory = tmp_path / "absent"
    code, out, _ = run_cli(["--config-dir", str(directory), "plugins", "list"])
    assert code == 0
    rows = json.loads(out)["data"]["plugins"]
    assert {row["identity"] for row in rows} == {
        "payment.sla.baselines",
        "collection.cost",
        "liquidity.reference.entities",
        "fx.trade",
    }
    assert all(row["state"] == "available" for row in rows)
    assert not directory.exists()
