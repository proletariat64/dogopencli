"""Observe domain controls and execution records through the public CLI."""

import json

import pytest


def test_disabled_domain_rejects_before_query_and_does_not_record_execution(
    run_cli, monkeypatch, tmp_path
):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "config.toml"))
    assert run_cli(["domain", "disable", "payment"])[0] == 0
    code, output, _ = run_cli(["payment", "cost", "list"])
    assert code == 1
    assert json.loads(output)["error"]["code"] == "DOMAIN_DISABLED"
    code, output, _ = run_cli(["domain", "leaves", "payment"])
    leaves = json.loads(output)["result"]
    assert all(leaf["last_execution"]["outcome"] == "unknown" for leaf in leaves)


def test_failed_query_records_operation_error_and_preserves_auth_unknown(
    run_cli, monkeypatch, tmp_path
):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "config.toml"))
    code, output, _ = run_cli(["payment", "cost", "list"])
    assert code == 2
    assert json.loads(output)["error"]["code"] == "CONFIG_ERROR"
    code, output, _ = run_cli(["domain", "show", "payment"])
    domain = json.loads(output)["result"]
    leaf = next(leaf for leaf in domain["leaves"] if leaf["id"] == "payment.cost.list")
    assert leaf["last_execution"]["outcome"] == "failed"
    assert leaf["last_execution"]["operation"] == "list"
    assert leaf["last_execution"]["error_code"] == "CONFIG_ERROR"
    assert leaf["last_execution"]["updated_at"] is not None
    assert domain["auth"]["outcome"] == "unknown"


def test_describe_remains_independent_of_invalid_config(run_cli, monkeypatch):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", "")
    code, output, error = run_cli(["describe", "payment", "channel", "list"])
    assert code == 0, error
    assert json.loads(output)["describe_version"] == 1


@pytest.mark.parametrize("format", ["json", "table"])
def test_usable_incomplete_result_records_warning_independent_of_rendering(
    run_cli, config_factory, dataset_factory, sample_channel_rows, format
):
    config_factory(dataset_factory(sample_channel_rows))
    assert run_cli(["refresh", "payment", "channel"])[0] == 0
    code, _, _ = run_cli(["payment", "channel", "list", "--format", format])
    assert code == 0
    _, output, _ = run_cli(["domain", "show", "payment"])
    leaf = next(
        item
        for item in json.loads(output)["result"]["leaves"]
        if item["id"] == "payment.channel.list"
    )
    assert leaf["last_execution"]["outcome"] == "warning"
    assert leaf["last_execution"]["operation"] == "list"
