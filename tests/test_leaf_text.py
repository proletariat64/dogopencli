"""Readable shared output without changing JSON or native numeric values."""

import json
from decimal import Decimal

import pytest

from dogopencli import __version__
from dogopencli.errors import diagnostic
from dogopencli.jsonutil import canonical
from dogopencli.leaves.cli import emit


@pytest.mark.parametrize("help_flag", ["-h", "--help"])
def test_root_text_help_structure(run_cli, help_flag):
    code, output, error = run_cli([help_flag, "--format", "text"])
    assert code == 0
    assert error == ""
    assert output.startswith("Usage: dogopencli <command>")
    assert "plugins" in output and "gui" in output.split("Commands:", 1)[1]
    assert "payment" in output.split("Commands:", 1)[1]
    assert "dogopencli <command> --help --format text" in output
    assert "--help, -h" in output  # documented flag, not a child command
    assert "Effects:" not in output and "Errors:" not in output


def test_version_install_and_domain_text(run_cli):
    assert run_cli(["--version", "--format", "text"]) == (
        0,
        f"version: {__version__}\n",
        "",
    )
    code, output, error = run_cli(
        ["plugins", "install", "bundled:payment.sla.baselines", "--format", "text"]
    )
    assert code == 0 and error == ""
    assert "payment.sla.baselines" in output
    code, output, error = run_cli(["payment", "--format", "text"])
    assert (code, error) == (0, "")
    assert output.startswith("Usage: dogopencli payment <command>")
    assert "list" in output and "describe" in output.split("Commands:", 1)[1]
    assert "sla.baselines" not in output  # domain shows actions, not descendants


def test_registry_diagnostics_remain_visible(run_cli, tmp_path):
    plugin = tmp_path / "plugins/payment/broken"
    plugin.mkdir(parents=True)
    (plugin / "leaf.json").write_text("invalid JSON")
    args = ["--config-dir", str(tmp_path), "--help"]
    code, output, _ = run_cli(args)
    diagnostics = json.loads(output)["data"]["diagnostics"]
    assert code == 0 and diagnostics
    code, output, error = run_cli([*args, "--format", "text"])
    assert (code, error) == (0, "")
    assert "Diagnostics:\n" in output
    for item in diagnostics:
        for key, value in item.items():
            assert f"{key}: {value}" in " ".join(output.split())


def test_exact_business_values_and_metadata(capsys):
    data = [
        {
            "id": "001",
            "amount": Decimal("12345678901234567890.123400"),
            "tiny": Decimal("1E-30"),
            "integer": 123456789012345678901234567890,
            "active": False,
            "missing": None,
            "note": "中文\nsecond line",
            "empty": "",
            "details": {},
        }
    ]
    meta = {
        "returned_count": 1,
        "warnings": [
            diagnostic(
                "INCOMPLETE_RESULT",
                "Coverage is incomplete",
                severity="warning",
                count=1,
            )
        ],
        "stale": True,
    }
    before = canonical({"data": data, "meta": meta, "error": None})
    emit(data, meta, output_format="text")
    output = capsys.readouterr()
    assert output.err == "warning: INCOMPLETE_RESULT: Coverage is incomplete\n"
    assert output.out.split("Metadata:", 1)[0] == (
        "-\n  id: 001\n  amount: 12345678901234567890.123400\n"
        "  tiny: 1E-30\n  integer: 123456789012345678901234567890\n"
        "  active: false\n  missing: null\n  note:\n    中文\n    second line\n"
        '  empty: ""\n  details:\n    (empty object)\n\n'
    )
    assert "returned_count: 1" in output.out
    assert "code: INCOMPLETE_RESULT" in output.out
    assert "severity: warning" in output.out and "stale: true" in output.out
    emit(data, meta, output_format="json")
    assert capsys.readouterr().out == before + "\n"


@pytest.mark.parametrize("action", ["list", "refresh", "get", "prune"])
def test_business_commands_use_shared_text(run_cli, monkeypatch, action):
    from dogopencli.leaves import cli

    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0
    monkeypatch.setattr(
        cli,
        "execute",
        lambda *args: (
            {"amount": Decimal("0.1000")},
            {
                "warnings": [
                    diagnostic(
                        "INCOMPLETE_RESULT",
                        "Coverage is incomplete",
                        severity="warning",
                        count=1,
                    )
                ],
                "published": False,
            },
        ),
    )
    args = ["payment", action, "sla.baselines"]
    if action == "get":
        args.append("001")
    code, output, error = run_cli([*args, "--format", "text"])
    assert code == 0
    assert error == "warning: INCOMPLETE_RESULT: Coverage is incomplete\n"
    assert output.startswith("amount: 0.1000\n\nMetadata:\n")
    assert "code: INCOMPLETE_RESULT" in output and "severity: warning" in output
    assert "published: false" in output


def test_error_text_preserves_exit_streams_and_json(run_cli):
    args = ["payment", "refresh", "missing"]
    code, output, error = run_cli(args)
    document = json.loads(output)
    assert code == 1 and error == ""
    assert set(document) == {"data", "meta", "error"}
    assert document["data"] is None
    assert document["meta"] == {
        "published": False,
        "outcome": "failed",
        "data_quality": "unusable",
        "publication": {"status": "unchanged", "reason": "rejected"},
    }
    text_code, output, text_error = run_cli([*args, "--format", "text"])
    assert (text_code, text_error) == (code, error)
    assert output.startswith("Metadata:\n")
    assert "published: false" in output
    assert "outcome: failed" in output and "data_quality: unusable" in output
    assert "status: unchanged" in output and "reason: rejected" in output
    for key, value in document["error"].items():
        assert (
            f"{key}: {value if isinstance(value, str) else canonical(value)}" in output
        )


def test_business_failure_text_keeps_metadata_and_retryability(run_cli, monkeypatch):
    from dogopencli.errors import CliError
    from dogopencli.leaves import cli

    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0

    def fail(*args):
        raise CliError(
            "BUSINESS_QUERY_FAILED",
            "native query failed",
            retryable=True,
            meta={
                "warnings": [
                    diagnostic(
                        "NATIVE_WARNING", "native diagnostic", severity="warning"
                    )
                ]
            },
        )

    monkeypatch.setattr(cli, "execute", fail)
    args = ["payment", "refresh", "sla.baselines"]
    code, output, error = run_cli(args)
    assert code == 1
    assert error == "warning: NATIVE_WARNING: native diagnostic\n"
    document = json.loads(output)
    assert document["data"] is None
    assert document["meta"]["published"] is False
    assert document["meta"]["outcome"] == "failed"
    assert document["meta"]["data_quality"] == "unusable"
    assert document["meta"]["warnings"][0]["message"] == "native diagnostic"
    assert document["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert document["error"]["message"] == "native query failed"
    assert document["error"]["retryable"] is True
    code, output, error = run_cli([*args, "--format", "text"])
    assert code == 1
    assert error == "warning: NATIVE_WARNING: native diagnostic\n"
    assert "code: NATIVE_WARNING" in output and "message: native diagnostic" in output
    assert "published: false" in output and "outcome: failed" in output
    assert "Error:\n" in output and "code: BUSINESS_QUERY_FAILED" in output
    assert "message: native query failed" in output and "retryable: true" in output


@pytest.mark.parametrize("data,expected", [([], "(empty list)"), (None, "null")])
def test_empty_result_is_explicit(capsys, data, expected):
    emit(data, output_format="text")
    assert capsys.readouterr().out == expected + "\n"


def test_auth_payload_uses_same_native_value_renderer(capsys):
    from dogopencli.auth.output import Result
    from dogopencli.auth.output import emit as emit_auth

    payload = {
        "probe": {"authenticated": True, "missing": None},
        "amount": Decimal("0.123400"),
    }
    emit(payload, output_format="text")
    business = capsys.readouterr()
    emit_auth("auth.check", Result(payload), None, "text")
    auth = capsys.readouterr()
    assert auth.out == business.out
    assert auth.err == business.err == ""
    emit_auth("auth.check", Result(payload), None, "json")
    envelope = json.loads(capsys.readouterr().out, parse_float=Decimal)
    assert envelope == {
        "output_version": 1,
        "command": "auth.check",
        "exit_code": 0,
        "result": payload,
        "error": None,
    }


def test_auth_error_keeps_stderr_and_renders_nested_partial_outcomes(capsys):
    from dogopencli.auth.output import Result
    from dogopencli.auth.output import emit as emit_auth

    error = {
        "code": "service_failure",
        "message": "One domain failed",
        "retryable": True,
        "details": {
            "domains": [
                {"domain": "payment", "authenticated": True},
                {"domain": "fx", "authenticated": False},
            ]
        },
        "next": ["Retry dogopencli auth check --domain fx"],
    }
    emit_auth("auth.check", Result(exit_code=1), error, "text")
    streams = capsys.readouterr()
    assert streams.out == ""
    assert streams.err.startswith("service_failure: One domain failed\n")
    assert "domains:\n  -\n" in streams.err
    assert (
        "authenticated: true" in streams.err and "authenticated: false" in streams.err
    )
    assert (
        "Next:\n" in streams.err
        and "Retry dogopencli auth check --domain fx" in streams.err
    )
    assert "{'" not in streams.err


@pytest.mark.parametrize("malformed", [None, "", "   ", 7, []])
def test_malformed_leaf_error_code_cannot_exit_success(run_cli, monkeypatch, malformed):
    from dogopencli.errors import CliError
    from dogopencli.leaves import cli

    assert run_cli(["plugins", "install", "bundled:payment.sla.baselines"])[0] == 0

    def fail(*args):
        raise CliError(malformed, "adapter error", exit_code=0)

    monkeypatch.setattr(cli, "execute", fail)
    code, output, _ = run_cli(["payment", "list", "sla.baselines", "--live"])
    result = json.loads(output)
    assert code == 1 and result["data"] is None
    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert result["meta"]["outcome"] == "failed"
