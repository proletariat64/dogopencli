"""Retained authentication help routing and offline isolation contracts."""

import json

import pytest


def help_json(run_cli, argv):
    code, out, err = run_cli(argv)
    assert code == 0, (argv, out, err)
    assert err == "", argv
    assert out.endswith("\n") and out.count("\n") == 1, argv
    envelope = json.loads(out)
    assert set(envelope) == {"data", "meta", "error"}, argv
    assert envelope["error"] is None, argv
    assert envelope["meta"] is None, argv
    assert envelope["data"]["help_version"] == 1, argv
    return envelope["data"]


def test_auth_help_flags_and_bare_navigation_agree(run_cli):
    document = help_json(run_cli, ["auth"])
    assert document == help_json(run_cli, ["auth", "-h"])
    assert document == help_json(run_cli, ["auth", "--help"])
    assert document["command"] == "dogopencli auth"
    assert [child["name"] for child in document["children"]] == ["check"]
    for path in (["login"], ["logout"], ["auth", "check"]):
        document = help_json(run_cli, [*path, "--help"])
        assert document == help_json(run_cli, [*path, "-h"])
        assert document["command"] == "dogopencli " + " ".join(path)


def test_auth_help_never_dispatches(run_cli, monkeypatch):
    def broken(*args, **kwargs):
        raise AssertionError("auth dispatch must not run for help")

    monkeypatch.setattr("dogopencli.auth.cli.dispatch", broken)
    for argv in (
        ["login", "-h"],
        ["logout", "--help"],
        ["auth", "check", "--help"],
        ["login", "--help"],
    ):
        code, _, _ = run_cli(argv)
        assert code == 0, argv


def test_auth_argument_error_protocol(run_cli):
    code, out, _ = run_cli(["login", "bogus", "--help"])
    assert code == 1
    envelope = json.loads(out)
    assert envelope["error"]["code"] == "invalid_arguments"
    assert envelope["error"]["next"] == ["dogopencli login --help"]
    code, out, _ = run_cli(["auth", "bogus", "--help"])
    assert code == 1
    assert json.loads(out)["error"]["code"] == "invalid_arguments"


@pytest.fixture
def environment_entry_points_fail(monkeypatch):
    def broken(*args, **kwargs):
        raise AssertionError("help must not touch config/cache/browser")

    monkeypatch.setattr("dogopencli.cli.config_mod.load", broken)
    monkeypatch.setattr("dogopencli.cli.Cache", broken)
    monkeypatch.setattr("dogopencli.cached_query.Cache", broken)
    monkeypatch.setattr("dogopencli.inquiry.resolve_environment", broken)
    monkeypatch.setattr("dogopencli.inquiry.make_transport", broken)
    monkeypatch.setattr("dogopencli.inquiry.acquire_browser_control", broken)
    monkeypatch.setattr("dogopencli.inquiry.check_authentication", broken)
    monkeypatch.setattr("dogopencli.auth.cli.dispatch", broken)


@pytest.mark.parametrize("option", ["--format=json", "--config-dir=elsewhere"])
@pytest.mark.parametrize("path", [["auth"], ["login"], ["logout"], ["auth", "check"]])
def test_auth_help_accepts_equals_globals(
    run_cli, environment_entry_points_fail, option, path
):
    assert help_json(run_cli, [option, *path, "--help"]) == help_json(
        run_cli, [*path, "--help"]
    )


@pytest.mark.parametrize("path", [["login"], ["logout"], ["auth", "check"]])
def test_auth_help_rejects_unknown_options_and_has_navigation(run_cli, path):
    for args in ([*path, "--help", "--bad"], [*path, "-h", "--bad"]):
        code, out, err = run_cli(args)
        assert code == 1
        assert json.loads(out)["error"]["code"] == "invalid_arguments"
        assert err == ""
    doc = help_json(run_cli, [*path, "--help"])
    assert doc["examples"]
    assert doc["next"]


def test_unknown_prefix_cannot_crash_auth_route(run_cli):
    code, out, err = run_cli(["--bogus", "auth", "--help"])
    assert code in (1, 2)
    assert json.loads(out)["error"]
    assert not err


@pytest.mark.parametrize("path", [["login"], ["logout"], ["auth"], ["auth", "check"]])
def test_positional_auth_help_is_rejected(run_cli, environment_entry_points_fail, path):
    code, out, err = run_cli(["help", *path])
    assert code != 0
    assert not err
    error = json.loads(out)["error"]
    assert error["code"] == "INVALID_ARGUMENT"
    assert "--help" in error["message"]
