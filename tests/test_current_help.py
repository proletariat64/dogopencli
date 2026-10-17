"""Progressive discovery through the public CLI boundary."""

import json


def test_progressive_help_is_current_and_does_not_activate(run_cli, tmp_path):
    assert run_cli(["plugins", "install-pilots"])[0] == 0
    adapter = tmp_path / "plugins/payment/sla.baselines/adapter.py"
    adapter.write_text('raise RuntimeError("must not activate")')
    before = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    for path, expected in [
        ([], {"plugins", "domain", "gui", "auth", "login", "logout", "payment"}),
        (["payment"], {"list", "get", "refresh", "prune", "describe"}),
        (["payment", "list"], {"sla.baselines"}),
        (["payment", "list", "sla.baselines"], set()),
    ]:
        code, out, err = run_cli([*path, "-h"])
        assert (code, err) == (0, "")
        doc = json.loads(out)["data"]
        assert doc["command"] == " ".join(["dogopencli", *path])
        assert expected <= {child["name"] for child in doc["children"]}
        assert "adapter" not in doc
    after = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert before == after


def test_operation_contracts_and_help_syntax(run_cli):
    assert run_cli(["plugins", "install-pilots"])[0] == 0
    prefix = ["payment", "get", "sla.baselines"]
    code, out, _ = run_cli([*prefix, "--help"])
    doc = json.loads(out)["data"]
    assert code == 0 and doc["arguments"][0]["required"]
    assert "--live" not in {f for o in doc["options"] for f in o["flags"]}
    for args in [
        ["payment", "list", "sla.baselines", "--limit", "5", "-h"],
        [*prefix, "--fields", "help", "-h"],
        [*prefix, "-h", "--", "--help"],
        ["login", "--timeout-seconds", "5", "-h"],
    ]:
        assert run_cli(args)[0] == 0
    for args in [
        ["payment", "list", "sla.baselines", "--limit", "bad", "-h"],
        ["payment", "list", "sla.baselines", "--limit", "-1", "-h"],
        ["payment", "get", "sla.baselines", "--live", "-h"],
        ["payment", "list", "sla.baselines", "--unknown", "-h"],
        ["collection", "get", "cost", "-h"],
        ["login", "--timeout-seconds", "nan", "-h"],
        ["gui", "--port", "-1", "-h"],
    ]:
        assert run_cli(args)[0] != 0


def test_first_help_traverses_all_children_without_runtime(
    run_cli, tmp_path, monkeypatch
):
    import shutil
    import socket
    from pathlib import Path

    from dogopencli.domains import DomainService
    from dogopencli.leaves import cli as leaf_cli
    from dogopencli.leaves.registry import Registry

    source = Path(__file__).parents[1] / "src/dogopencli/leaf_packages"
    shutil.copytree(source, tmp_path / "plugins")
    for adapter in (tmp_path / "plugins").glob("*/*/adapter.py"):
        adapter.write_text('raise RuntimeError("PRIVATE-ADAPTER-CONTENT")')
    (tmp_path / "config.toml").write_text("[broken PRIVATE-CONFIG-CONTENT")
    broken = tmp_path / "plugins/payment/broken"
    broken.mkdir()
    (broken / "leaf.json").write_text("PRIVATE-MANIFEST-CONTENT")
    # Removed-leaf/cache artifacts must remain byte-for-byte untouched.
    for name in ("leaf-cache.sqlite3", "leaf-registry.sqlite3", "duckdog.duckdb"):
        (tmp_path / name).write_bytes(b"existing-private-state")

    def forbidden(*args, **kwargs):
        raise AssertionError("help crossed runtime boundary")

    monkeypatch.setattr(Registry, "scan", forbidden)
    monkeypatch.setattr(leaf_cli, "execute", forbidden)
    monkeypatch.setattr(DomainService, "__init__", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    before = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    pending = [[]]
    while pending:
        path = pending.pop()
        code, out, err = run_cli([*path, "--help"])
        assert (code, err) == (0, ""), (path, out, err)
        doc = json.loads(out)["data"]
        assert doc["command"] == " ".join(["dogopencli", *path])
        names = [child["name"] for child in doc["children"]]
        assert names == sorted(names)
        for child in names:
            assert " " not in child
            pending.append([*path, child])
        for flag in ("-h", "--help"):
            assert json.loads(run_cli([*path, flag])[1])["data"] == doc
        if (
            names
            or len(path) == 0
            or path in [["payment"], ["collection"], ["fx"], ["liquidity"]]
        ):
            assert json.loads(run_cli(path)[1])["data"] == doc
        text_code, text, text_err = run_cli([*path, "--help", "--format", "text"])
        assert (text_code, text_err) == (0, "")
        assert doc["command"] in text and doc["summary"] in text
        for item in doc["options"]:
            assert item["summary"] in text
            assert all(flag in text for flag in item["flags"])
        assert "PRIVATE-" not in out + text
    after = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert before == after
    assert not (tmp_path / "leaf-registry.lock").exists()


def test_help_values_are_data_and_describe_remains_distinct(run_cli, monkeypatch):
    from dogopencli.leaves import cli

    assert run_cli(["plugins", "install-pilots"])[0] == 0
    captured = []

    def execute(leaf, operation, parameters, args, config):
        captured.append((operation, getattr(args, "detail_identity", None), parameters))
        return [], {}

    monkeypatch.setattr(cli, "execute", execute)
    for identity in ("help", "--help", "-h"):
        assert run_cli(["payment", "get", "sla.baselines", "--", identity])[0] == 0
        assert captured[-1][:2] == ("get", identity)
    assert run_cli(["payment", "list", "sla.baselines", "--status", "help"])[0] == 0
    assert captured[-1][2] == {"status": "help"}
    assert run_cli(["payment", "list", "sla.baselines", "--status=--help"])[0] == 0
    assert captured[-1][2] == {"status": "--help"}
    doc = json.loads(run_cli(["payment", "describe", "sla.baselines"])[1])["data"]
    help_doc = json.loads(run_cli(["payment", "describe", "sla.baselines", "-h"])[1])[
        "data"
    ]
    assert "fields" in doc and "operations" in doc
    assert "fields" not in help_doc and "operations" not in help_doc


def test_positional_help_is_rejected_with_flag_guidance(run_cli):
    for args in [
        ["help"],
        ["help", "gui"],
        ["help", "login"],
        ["help", "payment", "list", "sla.baselines"],
        ["payment", "help", "sla.baselines"],
        ["plugins", "help"],
        ["gui", "help"],
    ]:
        code, out, _ = run_cli(args)
        assert code != 0 and "--help" in out


def test_bare_gui_executes_but_help_does_not(run_cli, monkeypatch):
    from dogopencli import cli

    calls = []
    monkeypatch.setattr(cli, "cmd_gui", lambda args: calls.append(args.tokens) or 0)
    assert run_cli(["gui", "-h"])[0] == 0
    assert calls == []
    assert run_cli(["gui"])[0] == 0
    assert calls == [[]]


def test_leaf_parameters_do_not_change_unrelated_command_syntax(run_cli, tmp_path):
    assert run_cli(["plugins", "install-pilots"])[0] == 0
    manifest = tmp_path / "plugins/payment/sla.baselines/leaf.json"
    value = json.loads(manifest.read_text())
    value["operations"]["list"]["parameters"].extend(
        {
            "name": name,
            "type": "string",
            "required": False,
            "description": "Native value.",
        }
        for name in ("quiet", "verbose", "port", "domain", "timeout-seconds")
    )
    manifest.write_text(json.dumps(value))
    for args in [
        ["auth", "-h", "--quiet"],
        ["auth", "--quiet", "-h"],
        ["--quiet", "auth", "-h"],
    ]:
        code, out, _ = run_cli(args)
        assert code == 0
        assert json.loads(out)["data"]["command"] == "dogopencli auth"
    code, out, _ = run_cli(
        [
            "payment",
            "list",
            "sla.baselines",
            "--quiet",
            "help",
            "--verbose",
            "help",
            "--port",
            "help",
            "--domain",
            "help",
            "-h",
        ]
    )
    assert code == 0
    assert json.loads(out)["data"]["command"] == "dogopencli payment list sla.baselines"


def test_required_typed_parameters_validate_before_activation(run_cli, tmp_path):
    assert run_cli(["plugins", "install-pilots"])[0] == 0
    path = tmp_path / "plugins/payment/sla.baselines/leaf.json"
    manifest = json.loads(path.read_text())
    manifest["operations"]["get"]["parameters"] = [
        {
            "name": "attempt",
            "type": "integer",
            "required": True,
            "multiple": True,
            "description": "Native attempts.",
            "choices": [1, 2],
        },
        {
            "name": "enabled",
            "type": "boolean",
            "required": False,
            "description": "Native switch.",
        },
    ]
    path.write_text(json.dumps(manifest))
    prefix = ["payment", "get", "sla.baselines"]
    assert run_cli([*prefix, "--help"])[0] == 0
    assert run_cli([*prefix, "--attempt", "2", "--enabled", "false", "-h"])[0] == 0
    assert run_cli([*prefix, "--attempt", "3", "-h"])[0] == 2
    assert run_cli([*prefix, "--enabled", "no", "-h"])[0] == 2
    code, out, _ = run_cli([*prefix, "native-id"])
    assert code == 2
    assert json.loads(out)["error"]["message"] == "--attempt is required"
