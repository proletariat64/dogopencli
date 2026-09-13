"""Offline discovery and rejection through the public CLI."""

import json
import shlex
import socket
import sqlite3

import pytest

from dogopencli import cli

PATHS = [
    ["payment", "channel", "list"],
    ["payment", "cost", "list"],
    ["payment", "sla", "baselines", "list"],
    ["payment", "sla", "baselines", "get"],
]


@pytest.fixture
def offline(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("description attempted business/environment access")

    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "invalid.toml"))
    (tmp_path / "invalid.toml").write_text("not valid = [ TOML")
    monkeypatch.setattr(cli.config_mod, "load", forbidden)
    monkeypatch.setattr(cli, "Cache", forbidden)
    monkeypatch.setattr(cli, "inquiry_session", forbidden)
    monkeypatch.setattr(cli, "load_dataset", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    from dogopencli.auth import cli as auth_cli
    from dogopencli.browser import cdp

    monkeypatch.setattr(auth_cli, "main", forbidden)
    monkeypatch.setattr(cdp, "make_transport", forbidden)
    for name in ("cmd_channel_list", "cmd_cost_list", "cmd_sla_list", "cmd_sla_get"):
        monkeypatch.setattr(cli, name, forbidden)
    return tmp_path


@pytest.mark.parametrize("path", PATHS)
def test_describe_offline_deterministic_and_discoverable(run_cli, offline, path):
    help_doc = json.loads(run_cli(["help", *path])[1])
    assert "dogopencli describe " + " ".join(path) in help_doc["next"]
    result = run_cli(["describe", *path])
    assert result == run_cli(["describe", *path, "--format", "json"])
    code, out, err = result
    assert code == 0 and err == ""
    doc = json.loads(out)
    assert set(doc) == {
        "describe_version",
        "capability",
        "schema_version",
        "data_schema",
        "read_guide",
        "query_help",
    }
    assert doc["describe_version"] == doc["schema_version"] == 1
    assert doc["capability"] == ".".join(path)
    assert doc["read_guide"]["options"] == help_doc["options"]
    assert json.loads(run_cli(shlex.split(doc["query_help"])[1:])[1]) == help_doc
    assert sorted(p.name for p in offline.iterdir()) == ["invalid.toml"]


@pytest.mark.parametrize(
    "path",
    [
        [],
        ["payment"],
        ["payment", "channel"],
        ["payment", "cost"],
        ["payment", "sla"],
        ["payment", "sla", "baselines"],
    ],
)
def test_describe_groups_and_help(run_cli, offline, path):
    variants = [
        ["describe", *path],
        ["help", "describe", *path],
        ["describe", *path, "--help"],
    ]
    results = [run_cli(argv) for argv in variants]
    assert results[0] == results[1] == results[2]
    doc = json.loads(results[0][1])
    assert doc["children"]
    assert all(value is False for value in doc["effects"].values())
    assert run_cli(["help", "describe", *path, "--format", "text"])[0] == 0


@pytest.mark.parametrize(
    "tail",
    [
        ["auth"],
        ["login"],
        ["logout"],
        ["refresh", "payment", "channel"],
        ["payment", "unknown"],
        ["payment", "sla", "get"],
        ["payment", "channel", "list", "--live"],
        ["payment", "channel", "list", "--fields", "abilityId"],
        ["payment", "sla", "baselines", "get", "--id", "BASELINE_ID"],
        ["payment", "channel", "list", "--format", "text"],
        ["payment", "unknown", "--format", "text"],
        ["auth", "--format", "text"],
        ["--bogus"],
    ],
)
def test_describe_rejections_are_business_errors(run_cli, offline, tail):
    code, out, err = run_cli(["describe", *tail])
    assert code == 2
    assert err == ""
    doc = json.loads(out)
    assert doc["data"] is None and doc["meta"] is None
    assert doc["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("path", PATHS)
def test_guide_examples_resolve_and_annotations_are_defined(run_cli, path):
    doc = json.loads(run_cli(["describe", *path])[1])
    guide = doc["read_guide"]
    for example in guide["examples"]:
        code, out, err = run_cli([*shlex.split(example)[1:], "--help"])
        assert code == 0 and err == "", (example, out)
    annotations = guide["annotations"]
    assert set(annotations["x-evidence"]["aspects"]) == {
        "type",
        "presence",
        "nullability",
        "unit",
        "meaning",
    }
    assert set(annotations["x-evidence"]["values"]) == {
        "verified",
        "observed",
        "unknown",
        "not_applicable",
    }
    filters = {entry["flag"]: entry for entry in guide["filters"]}
    if path[1] == "cost":
        assert filters["--bank-account"]["record_field"] == "bankAccountAliasName"
    elif path[1] == "channel":
        assert filters["--financial-inst-id"]["record_field"] == "financialInstCode"
        assert filters["--debit-account-no"]["request_field"] == "debitAccountNoList"
    elif path[-1] == "list":
        assert filters["--biz-legal-entity"]["record_field"] is None
