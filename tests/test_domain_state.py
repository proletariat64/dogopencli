"""Domain controls through the public management command boundary."""

import json
from types import SimpleNamespace

import pytest

from dogopencli import domain_contracts, domains


@pytest.mark.parametrize(
    "action", [None, "list", "show", "leaves", "enable", "disable"]
)
@pytest.mark.parametrize("format", ["json", "text"])
@pytest.mark.parametrize("entrance", ["-h", "--help"])
def test_domain_help_describes_inputs_in_both_formats(
    run_cli, monkeypatch, action, format, entrance
):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", "")
    path = ["domain", *([action] if action else [])]
    arguments = [*path, entrance]
    code, output, error = run_cli([*arguments, "--format", format])
    assert code == 0, error
    requires_domain = action in {"show", "leaves", "enable", "disable"}
    if format == "json":
        document = json.loads(output)["data"]
        options = {option["name"]: option for option in document["options"]}
        assert options["config_dir"]["flags"] == ["--config-dir"]
        assert options["format"]["choices"] == ["json", "text"]
        assert options["format"]["default"] == "json"
        assert bool(document["arguments"]) is requires_domain
        if requires_domain:
            assert document["arguments"][0]["name"] == "domain"
            assert document["arguments"][0]["required"] is True
    else:
        assert "--config-dir" in output
        assert "--format" in output
        assert ("Arguments:" in output) is requires_domain
        if requires_domain:
            assert "domain" in output.split("Arguments:", 1)[1].split("Options:", 1)[0]
            assert (
                "required" in output.split("Arguments:", 1)[1].split("Options:", 1)[0]
            )


@pytest.mark.parametrize(
    "arguments,format,command",
    [
        (["list", "--help", "--format=text"], "text", "dogopencli domain list"),
        (
            ["list", "--help", "--config-dir", "text", "--format=json"],
            "json",
            "dogopencli domain list",
        ),
        (["--config-dir", "disable", "--help"], "json", "dogopencli domain"),
    ],
)
def test_domain_help_parses_format_and_option_values_offline(
    run_cli, monkeypatch, arguments, format, command
):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", "")
    code, output, error = run_cli(["domain", *arguments])
    assert code == 0, error
    if format == "json":
        assert json.loads(output)["data"]["command"] == command
    else:
        assert output.startswith(f"Usage: {command}")


@pytest.fixture
def declarations(monkeypatch, tmp_path):
    """Install a real list leaf; static domain declarations own auth only."""
    domains = (
        SimpleNamespace(id="demo", entry_point="https://example.test/", leaves=()),
    )
    monkeypatch.setattr(domain_contracts, "domain_declarations", lambda: domains)
    monkeypatch.setattr("dogopencli.domains.domain_declarations", lambda: domains)
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "config.toml"))
    folder = tmp_path / "plugins/demo/items"
    folder.mkdir(parents=True)
    manifest = {
        "domain": "demo",
        "name": "items",
        "adapter": "adapter.py:adapter",
        "operations": {"list": {"description": "List demo items", "parameters": []}},
        "fields": [{"name": "id", "type": "string", "meaning": "Native ID"}],
        "identity": ["id"],
        "summary": "Demo",
        "purpose": "Test installed inventory",
        "identity_description": "Native ID",
        "limitations": [],
        "examples": [],
        "dataset": {"relation": "demo_items"},
    }
    (folder / "leaf.json").write_text(json.dumps(manifest))
    (folder / "adapter.py").write_text(
        "class Adapter:\n"
        " def capability(self, parameters): pass\n"
        " def scope(self, parameters): return ''\n"
        " def collector(self, *args, **kwargs): pass\n"
        " def filter(self, rows, parameters): return rows\n"
        "adapter = Adapter()\n"
    )
    broken = tmp_path / "plugins/demo/future"
    broken.mkdir()
    (broken / "leaf.json").write_text("invalid JSON")
    return domains


def invoke(capsys, tmp_path, *args):
    from dogopencli.domain_cli import main

    code = main([*args, "--config-dir", str(tmp_path)])
    return code, json.loads(capsys.readouterr().out)


def test_inventory_is_offline_and_does_not_create_store(declarations, tmp_path, capsys):
    code, body = invoke(capsys, tmp_path, "list")
    assert code == 0
    domain = body["result"][0]
    assert domain["id"] == "demo"
    assert domain["enabled"] is True
    assert domain["auth"] == {"outcome": "unknown", "updated_at": None}
    assert domain["leaves"][0]["last_execution"]["outcome"] == "unknown"
    assert domain["diagnostics"][0]["id"] == "demo.future"
    assert not (tmp_path / "config.toml.domains.sqlite3").exists()
    assert not (tmp_path / "leaf-cache.sqlite3").exists()


def test_domain_toggle_survives_reopen_without_rewriting_leaf_settings(
    declarations, tmp_path, capsys
):
    code, body = invoke(capsys, tmp_path, "disable", "demo")
    assert code == 0
    assert body["result"]["enabled"] is False
    assert body["result"]["leaves"][0]["enabled"] is True
    assert body["result"]["leaves"][0]["effective_enabled"] is False
    assert invoke(capsys, tmp_path, "show", "demo")[1]["result"]["enabled"] is False
    code, body = invoke(capsys, tmp_path, "enable", "demo")
    assert body["result"]["leaves"][0]["effective_enabled"] is True
    assert len(body["result"]["leaves"]) == 1
    assert body["result"]["diagnostics"][0]["id"] == "demo.future"


def test_recorded_results_are_persisted_separate_from_auth(
    declarations, tmp_path, capsys
):
    from dogopencli.domains import DomainService

    service = DomainService(tmp_path / "config.toml")
    service.record_execution(
        "demo",
        "demo.items",
        outcome="warning",
        operation="list",
        diagnostic="Bearer PRIVATE; account=123",
    )
    _, body = invoke(capsys, tmp_path, "show", "demo")
    row = body["result"]
    assert row["auth"]["outcome"] == "unknown"
    observation = row["leaves"][0]["last_execution"]
    assert observation["outcome"] == "warning"
    assert observation["operation"] == "list"
    assert observation["updated_at"].endswith("Z")
    assert "PRIVATE" not in json.dumps(row)
    service.record_auth("demo", {"authenticated": True, "cookie": "PRIVATE"})
    row = invoke(capsys, tmp_path, "show", "demo")[1]["result"]
    assert row["auth"]["outcome"] == "authenticated"
    assert row["auth"]["updated_at"].endswith("Z")
    assert row["leaves"][0]["last_execution"] == observation
    assert b"PRIVATE" not in service.state_path.read_bytes()
    service.invalidate_auth()
    row = invoke(capsys, tmp_path, "show", "demo")[1]["result"]
    assert row["auth"]["outcome"] == "unknown"
    assert row["auth"]["updated_at"] is None
    assert row["leaves"][0]["last_execution"] == observation


def test_gates_follow_registration_and_leave_last_result_intact(
    declarations, tmp_path, capsys
):
    from dogopencli.domains import DomainService

    service = DomainService(tmp_path / "config.toml")
    service.record_execution("demo", "demo.items", outcome="success", operation="list")
    previous = service.inventory()[0]["leaves"][0]["last_execution"]
    service.set_enabled("demo", False)
    from dogopencli.cli import main

    assert main(["demo", "list", "items", "--config-dir", str(tmp_path)]) == 1
    failure = json.loads(capsys.readouterr().out)
    assert failure["error"]["code"] == "DOMAIN_DISABLED"
    assert service.inventory()[0]["leaves"][0]["last_execution"] == previous


def test_selection_validates_before_auth_and_deduplicates(declarations, tmp_path):
    from dogopencli.domains import DomainService
    from dogopencli.errors import CliError

    service = DomainService(tmp_path / "config.toml")
    assert [d.id for d in service.select_domains()] == ["demo"]
    assert [d.id for d in service.select_domains(["demo", "demo"])] == ["demo"]
    with pytest.raises(CliError, match="Unknown domain"):
        service.select_domains(["absent"])
    service.set_enabled("demo", False)
    with pytest.raises(CliError, match="disabled"):
        service.select_domains(["demo"])
    with pytest.raises(CliError, match="No enabled domains"):
        service.select_domains()


def test_unknown_domain_fails_without_creating_state(declarations, tmp_path, capsys):
    code, body = invoke(capsys, tmp_path, "disable", "absent")
    assert code != 0
    assert body["error"]["code"] == "DOMAIN_NOT_FOUND"
    assert not (tmp_path / "config.toml.domains.sqlite3").exists()


def test_configuration_files_in_same_directory_are_isolated(declarations, tmp_path):
    from dogopencli.domains import DomainService

    first = DomainService(tmp_path / "first.toml")
    second = DomainService(tmp_path / "second.toml")
    first.set_enabled("demo", False)
    assert second.inventory()[0]["enabled"] is True
    assert first.inventory()[0]["enabled"] is False


def test_absent_registration_does_not_return_from_retained_state(
    declarations, monkeypatch, tmp_path
):
    from dogopencli.domains import DomainService

    service = DomainService(tmp_path / "config.toml")
    service.set_enabled("demo", False)
    service.record_execution(
        "demo", "demo.items", outcome="failed", operation="get", error_code="NOT_FOUND"
    )
    monkeypatch.setattr(domains, "domain_declarations", lambda: ())
    assert service.inventory() == []
    monkeypatch.setattr(domains, "domain_declarations", lambda: declarations)
    assert service.inventory()[0]["enabled"] is False
    assert (
        service.inventory()[0]["leaves"][0]["last_execution"]["error_code"]
        == "NOT_FOUND"
    )


def test_concurrent_settings_and_result_writes_do_not_replace_each_other(
    declarations, tmp_path
):
    from concurrent.futures import ThreadPoolExecutor

    from dogopencli.domains import DomainService

    location = tmp_path / "config.toml"

    def setting():
        DomainService(location).set_enabled("demo", False)

    def result():
        DomainService(location).record_execution(
            "demo", "demo.items", outcome="success", operation="refresh"
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(setting), executor.submit(result)]
        for future in futures:
            future.result()
    row = DomainService(location).inventory()[0]
    assert row["enabled"] is False
    assert row["leaves"][0]["last_execution"]["operation"] == "refresh"


def test_invalid_store_is_reported_instead_of_reenabling_domain(
    declarations, tmp_path, capsys
):
    from dogopencli.domains import DomainService

    service = DomainService(tmp_path / "config.toml")
    service.state_path.write_bytes(b"invalid sqlite")
    code, body = invoke(capsys, tmp_path, "list")
    assert code != 0
    assert body["error"]["code"] == "DOMAIN_STATE_ERROR"
    assert service.state_path.read_bytes() == b"invalid sqlite"


def test_failed_state_save_preserves_previous_observation(declarations, tmp_path):
    from dogopencli.domains import DomainService
    from dogopencli.errors import CliError

    service = DomainService(tmp_path / "config.toml")
    service.record_execution("demo", "demo.items", outcome="success", operation="list")
    previous = service.inventory()[0]["leaves"][0]["last_execution"]
    service.state_path.chmod(0o400)
    try:
        with pytest.raises(CliError) as failure:
            service.record_execution(
                "demo",
                "demo.items",
                outcome="failed",
                operation="get",
                error_code="TIMEOUT",
            )
        assert failure.value.code == "DOMAIN_STATE_ERROR"
    finally:
        service.state_path.chmod(0o600)
    assert service.inventory()[0]["leaves"][0]["last_execution"] == previous


@pytest.mark.parametrize(
    "bad_record",
    [
        "{}",
        '{"outcome": [], "updated_at": null}',
        '{"outcome":"success","updated_at":"yesterday","operation":"list"}',
    ],
)
def test_invalid_observations_fail_clearly(declarations, tmp_path, capsys, bad_record):
    import sqlite3

    from dogopencli.domains import DomainService

    service = DomainService(tmp_path / "config.toml")
    service.record_execution("demo", "demo.items", outcome="success", operation="list")
    with sqlite3.connect(service.state_path) as database:
        database.execute("UPDATE executions SET record=?", (bad_record,))
    code, body = invoke(capsys, tmp_path, "show", "demo")
    assert code != 0
    assert body["error"]["code"] == "DOMAIN_STATE_ERROR"
