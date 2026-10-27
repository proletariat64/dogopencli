"""Progressive discovery through the public CLI boundary."""

import json


def test_progressive_help_is_current_and_does_not_activate(run_cli, tmp_path):
    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0
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
    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0
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
    import subprocess
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
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    from dogopencli.cache import Cache

    monkeypatch.setattr(Cache, "__init__", forbidden)
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
        assert (
            json.loads(run_cli([*path, "--help", "--format", "json"])[1])["data"] == doc
        )
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
        assert doc["command"] in " ".join(text.split())
        assert doc["summary"] in " ".join(text.split())
        for item in doc["options"]:
            assert item["summary"] in " ".join(text.split())
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

    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0
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
    from dogopencli import gui

    calls = []
    monkeypatch.setattr(gui, "main", lambda tokens: calls.append(tokens) or 0)
    assert run_cli(["gui", "-h"])[0] == 0
    assert calls == []
    assert run_cli(["gui"])[0] == 0
    assert calls == [[]]


def test_leaf_parameters_do_not_change_unrelated_command_syntax(run_cli, tmp_path):
    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0
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
    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0
    path = tmp_path / "plugins/payment/sla.baselines/leaf.json"
    manifest = json.loads(path.read_text())
    manifest["operations"]["get"].pop("list_binding")
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


def test_explicit_empty_choices_remain_a_reject_all_constraint(
    run_cli, tmp_path, monkeypatch
):
    from dogopencli.leaves import cli

    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0
    manifest_path = tmp_path / "plugins/payment/sla.baselines/leaf.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["operations"]["list"]["parameters"][3]["choices"] = []
    manifest_path.write_text(json.dumps(manifest))
    executions = []
    monkeypatch.setattr(
        cli, "execute", lambda *args: (executions.append(args) or [], {})
    )
    prefix = ["payment", "list", "sla.baselines"]
    code, out, _ = run_cli([*prefix, "-h"])
    assert code == 0
    status = next(
        option
        for option in json.loads(out)["data"]["options"]
        if option["name"] == "status"
    )
    assert status["choices"] == []
    for suffix in [["--status", "OPEN", "-h"], ["--status", "OPEN"]]:
        assert run_cli([*prefix, *suffix])[0] == 2
    assert executions == []
    assert run_cli(prefix)[0] == 0
    assert len(executions) == 1


def test_version_never_bypasses_invalid_command_paths(run_cli):
    for path in (
        ["help"],
        ["gui", "help"],
        ["bogus"],
        ["payment", "help", "sla.baselines"],
        ["gui", "unknown"],
        ["plugins", "unknown"],
    ):
        for args in ([*path, "--version"], ["--version", *path]):
            code, out, _ = run_cli(args)
            assert code == 2, (args, out)
            assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
            assert "--help" in json.loads(out)["error"]["message"]


def test_core_argument_errors_are_not_reported_as_missing_leaves(run_cli):
    for root in ("domain", "gui", "plugins", "unknown"):
        code, out, _ = run_cli([root, "list", "extra"])
        error = json.loads(out)["error"]
        assert code == 2, (root, out)
        assert error["code"] == "INVALID_ARGUMENT"
        assert "--help" in error["message"]


def test_auth_errors_keep_resolved_path_with_interleaved_global_options(run_cli):
    for options in (["--verbose"], ["--format", "json"], ["--quiet", "-h"]):
        code, out, _ = run_cli(["auth", *options, "check", "--bad"])
        document = json.loads(out)
        assert code == 1
        assert document["command"] == "auth.check"
        assert document["error"]["code"] == "invalid_arguments"
        assert document["error"]["next"] == ["dogopencli auth check --help"]


def test_core_installation_help_remains_available_without_installed_leaves(run_cli):
    code, output, _ = run_cli(["plugins", "--help"])
    document = json.loads(output)["data"]
    assert code == 0
    assert document["summary"] == "Manage local leaf installations."
    assert {"install", "uninstall", "list"} <= {
        child["name"] for child in document["children"]
    }


def test_common_option_spellings_remain_literal_business_values(
    run_cli, monkeypatch, tmp_path
):
    from dogopencli.leaves import cli

    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0
    executions = []

    def execute(leaf, operation, parameters, args, config_file):
        executions.append(
            (operation, parameters, getattr(args, "detail_identity", None), config_file)
        )
        return [], {}

    monkeypatch.setattr(cli, "execute", execute)
    for literal in (
        "--version",
        "--format",
        "--config-dir",
        "--help",
        "-h",
        "--format=text",
        "--config-dir=elsewhere",
    ):
        for tail, operation, parameters, identity in [
            (
                ["list", "sla.baselines", "--status", literal],
                "list",
                {"status": literal},
                None,
            ),
            (["get", "sla.baselines", "--", literal], "get", {}, literal),
        ]:
            before = len(executions)
            code, out, _ = run_cli(["payment", *tail])
            assert code == 0, (tail, out)
            assert len(executions) == before + 1, (tail, out)
            assert executions[-1] == (
                operation,
                parameters,
                identity,
                tmp_path / "config.toml",
            )
            assert json.loads(out)["data"] == []


def test_text_help_uses_sections_and_preserves_contract(run_cli):
    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0
    code, text, err = run_cli(
        ["payment", "list", "sla.baselines", "-h", "--format", "text"]
    )
    assert (code, err) == (0, "")
    assert text.startswith("Usage: dogopencli payment list sla.baselines")
    for heading in (
        "Options:",
        "Constraints:",
        "Examples:",
        "Next:",
        "Effects:",
        "Errors:",
    ):
        assert heading in text
    assert "default: 100" in text
    assert "default: false" not in text.lower()
    assert "required: false" not in text.lower()
    assert "(empty list)" not in text
    assert "help_version:" not in text


def test_installed_parameter_modes_follow_operation_and_local_mapping(
    run_cli, tmp_path
):
    import shutil
    from pathlib import Path

    shutil.copytree(
        Path(__file__).parents[1] / "src/dogopencli/leaf_packages", tmp_path / "plugins"
    )

    def options(domain, operation, leaf):
        code, out, _ = run_cli([domain, operation, leaf, "-h"])
        assert code == 0
        return {o["name"]: o for o in json.loads(out)["data"]["options"]}

    fx = options("fx", "list", "trade")["bcode"]["argument_contract"]["modes"]
    assert fx["cache"] == {"available": False}
    assert fx["live"]["available"] is True
    freshness = options("fx", "list", "trade")["require_fresh"]["argument_contract"][
        "modes"
    ]
    assert freshness["live"]["available"] is True
    assert freshness["live"]["effective"] is False
    payment = options("payment", "list", "sla.baselines")["status"][
        "argument_contract"
    ]["modes"]
    assert payment["cache"]["role"] == "local-filter"
    assert payment["cache"]["required"] is False
    assert set(
        options("payment", "refresh", "sla.baselines")["status"]["argument_contract"][
            "modes"
        ]
    ) == {"refresh"}
    path = tmp_path / "plugins/payment/sla.baselines/leaf.json"
    doc = json.loads(path.read_text())
    parameter = {
        "name": "attempt",
        "type": "integer",
        "required": True,
        "multiple": True,
        "choices": [1, 2],
        "description": "Native attempts.",
    }
    doc["operations"]["get"].pop("list_binding")
    doc["operations"]["get"]["parameters"] = [parameter]
    doc["operations"]["list"]["parameters"] = [parameter]
    # The synthetic parameter contract no longer has the SLA sync scope.
    doc.pop("sync")
    path.write_text(json.dumps(doc))
    for operation, expected in (
        ("list", {"cache", "live"}),
        ("refresh", {"refresh"}),
        ("get", {"get"}),
    ):
        option = options("payment", operation, "sla.baselines")["attempt"]
        modes = option["argument_contract"]["modes"]
        assert set(modes) == expected
        acquisition = modes["live" if operation == "list" else operation]
        assert acquisition["required"] is True
        assert acquisition["cardinality"] == {"min": 1, "max": None}
        assert option["choices"] == [1, 2] and option["repeatable"] is True


def test_leaf_errors_are_operation_specific_and_match_cache_failure(run_cli):
    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0
    errors = {}
    for operation in ("list", "get", "refresh", "prune", "describe"):
        code, output, _ = run_cli(["payment", operation, "sla.baselines", "-h"])
        assert code == 0
        errors[operation] = json.loads(output)["data"]["errors"]
    assert {
        "CACHE_MISS",
        "CACHE_STALE",
        "CACHE_CONTRACT_CHANGED",
        "INCOMPLETE_RESULT",
        "CONFIG_ERROR",
        "AUTH_REQUIRED",
    } <= set(errors["list"])
    assert "INCOMPLETE_RESULT" in errors["refresh"]
    assert "AUTH_REQUIRED" in errors["get"]
    for operation in ("get", "refresh", "prune", "describe"):
        assert "CACHE_MISS" not in errors[operation]
    for operation in ("prune", "describe"):
        assert "AUTH_REQUIRED" not in errors[operation]
    code, output, _ = run_cli(["payment", "list", "sla.baselines"])
    assert code == 1
    assert json.loads(output)["error"]["code"] == "CACHE_MISS"


def test_help_terminal_width_redirect_and_wide_prose(run_cli, tmp_path, monkeypatch):
    import os
    import shutil
    import sys
    import unicodedata
    from pathlib import Path

    shutil.copytree(
        Path(__file__).parents[1] / "src/dogopencli/leaf_packages", tmp_path / "plugins"
    )
    path = tmp_path / "plugins/payment/sla.baselines/leaf.json"
    manifest = json.loads(path.read_text())
    chinese = "缓存查询保留原生业务字段并支持本地过滤且不访问生产网络。" * 3
    long_token = "--" + "unchanged-native-token-" * 8
    manifest["operations"]["list"]["description"] = chinese + " " + long_token
    path.write_text(json.dumps(manifest))
    args = ["payment", "list", "sla.baselines", "-h", "--format", "text"]

    def width(text):
        return sum(
            0
            if unicodedata.combining(c)
            else 2
            if unicodedata.east_asian_width(c) in {"W", "F"}
            else 1
            for c in text
        )

    for columns in (36, 88, 140):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "fileno", lambda: 1)
        monkeypatch.setattr(
            os,
            "get_terminal_size",
            lambda *_, columns=columns: os.terminal_size((columns, 24)),
        )
        code, text, err = run_cli(args)
        assert (code, err) == (0, "")
        assert long_token in text
        assert chinese in "".join(text.split())
        for line in text.splitlines():
            assert width(line) <= columns or any(
                width(word) > columns - 4 for word in line.split()
            ), line
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    outputs = []
    for columns in (20, 200):
        monkeypatch.setenv("COLUMNS", str(columns))
        outputs.append(run_cli(args)[1])
    assert outputs[0] == outputs[1]
    assert "\x1b" not in outputs[0]
    assert all(
        width(line) <= 88 or long_token in line for line in outputs[0].splitlines()
    )


def test_help_keeps_unicode_command_tokens_intact(run_cli, monkeypatch):
    import os
    import sys
    from dataclasses import replace

    from dogopencli.auth import spec

    token = "/tmp/" + "中文配置目录" * 15
    example = "dogopencli login --config-dir " + token
    monkeypatch.setattr(
        spec,
        "COMMANDS",
        tuple(
            replace(command, examples=(example,), summary="Use " + token)
            if command.path == ("login",)
            else command
            for command in spec.COMMANDS
        ),
    )
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "fileno", lambda: 1)
    monkeypatch.setattr(os, "get_terminal_size", lambda *_: os.terminal_size((36, 24)))
    code, text, err = run_cli(["login", "-h", "--format", "text"])
    assert (code, err) == (0, "")
    assert text.count(token) == 2
    assert example in " ".join(text.split())


def test_help_keeps_false_choices_true_defaults_and_zero_defaults(run_cli, tmp_path):
    import shutil
    from pathlib import Path

    shutil.copytree(
        Path(__file__).parents[1] / "src/dogopencli/leaf_packages", tmp_path / "plugins"
    )
    path = tmp_path / "plugins/payment/sla.baselines/leaf.json"
    manifest = json.loads(path.read_text())
    manifest["operations"]["get"]["parameters"] = [
        {
            "name": "enabled",
            "type": "boolean",
            "required": False,
            "default": True,
            "choices": [True, False],
            "description": "Native switch.",
        },
        {
            "name": "restricted",
            "type": "string",
            "required": False,
            "choices": [],
            "description": "No accepted supplied values.",
        },
    ]
    path.write_text(json.dumps(manifest))
    code, text, _ = run_cli(
        ["payment", "get", "sla.baselines", "-h", "--format", "text"]
    )
    assert code == 0
    flattened = " ".join(text.split())
    assert "default: True" in flattened
    assert "choices: True, False" in flattened
    assert "choices: none (no supplied value accepted)" in flattened
    assert "detail_identity" in flattened and "[required]" in flattened
    assert "default: 0" in run_cli(["gui", "-h", "--format", "text"])[1]
    for option in ("--all", "--recursive", "--tree"):
        assert run_cli(["-h", option])[0] == 2


def test_help_stacks_description_tokens_that_fit_terminal_but_not_column(
    run_cli, tmp_path, monkeypatch
):
    import os
    import shutil
    import sys
    from pathlib import Path

    shutil.copytree(
        Path(__file__).parents[1] / "src/dogopencli/leaf_packages",
        tmp_path / "plugins",
    )
    manifest_path = tmp_path / "plugins/payment/sla.baselines/leaf.json"
    manifest = json.loads(manifest_path.read_text())
    path_token = "/tmp/" + "a" * 35
    manifest["operations"]["list"]["parameters"][0]["description"] = (
        "Read configuration from " + path_token
    )
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "fileno", lambda: 1)
    monkeypatch.setattr(os, "get_terminal_size", lambda *_: os.terminal_size((60, 24)))
    code, text, error = run_cli(
        ["payment", "list", "sla.baselines", "-h", "--format", "text"]
    )
    assert (code, error) == (0, "")
    assert path_token in text
    assert all(len(line) <= 60 for line in text.splitlines())
