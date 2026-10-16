"""Retained authentication help routing and offline isolation contracts."""

import json

import pytest


def help_json(run_cli, argv):
    code, out, err = run_cli(argv)
    assert code == 0, (argv, out, err)
    assert err == "", argv
    assert out.endswith("\n") and out.count("\n") == 1, argv
    return json.loads(out)


def test_auth_help_unchanged_and_routed(run_cli):
    _, auth_bare, _ = run_cli(["auth"])
    _, auth_help, _ = run_cli(["help", "auth"])
    assert auth_bare == auth_help
    assert json.loads(auth_bare)["children"] == [
        {"name": "check", "summary": json.loads(auth_bare)["children"][0]["summary"]}
    ]
    for argv in (
        ["login", "--help"],
        ["logout", "--help"],
        ["auth", "check", "--help"],
    ):
        code, out, _ = run_cli(argv)
        assert code == 0
        assert json.loads(out)["help_version"] == 1
    _, login_help, _ = run_cli(["login", "--help"])
    _, help_login, _ = run_cli(["help", "login"])
    assert login_help == help_login
    _, logout_help, _ = run_cli(["logout", "--help"])
    _, help_logout, _ = run_cli(["help", "logout"])
    assert logout_help == help_logout


def test_auth_help_never_dispatches(run_cli, monkeypatch):
    def broken(*args, **kwargs):
        raise AssertionError("auth dispatch must not run for help")

    monkeypatch.setattr("dogopencli.auth.cli.dispatch", broken)
    for argv in (
        ["help", "login"],
        ["help", "logout"],
        ["help", "auth", "check"],
        ["login", "--help"],
    ):
        code, _, _ = run_cli(argv)
        assert code == 0, argv


def test_auth_argument_error_protocol(run_cli):
    code, out, _ = run_cli(["help", "login", "bogus"])
    assert code == 1
    envelope = json.loads(out)
    assert envelope["output_version"] == 1
    assert envelope["error"]["code"] == "invalid_arguments"
    assert envelope["error"]["next"] == ["dogopencli login --help"]
    code, out, _ = run_cli(["help", "auth", "bogus"])
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
    for args in ([*path, "--help", "--bad"], ["help", *path, "--bad"]):
        code, out, err = run_cli(args)
        assert code == 1
        assert json.loads(out)["error"]["code"] == "invalid_arguments"
        assert err == ""
    doc = help_json(run_cli, ["help", *path])
    assert doc["examples"]
    assert doc["next"]


def test_unknown_prefix_cannot_crash_auth_route(run_cli):
    code, out, err = run_cli(["--bogus", "auth", "--help"])
    assert code in (1, 2)
    assert json.loads(out)["error"]
    assert not err
