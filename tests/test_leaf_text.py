"""Readable shared output without changing JSON or native numeric values."""

import json
from decimal import Decimal

import pytest

from dogopencli import __version__
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
    meta = {"returned_count": 1, "warnings": ["INCOMPLETE_RESULT"], "stale": True}
    before = canonical({"data": data, "meta": meta, "error": None})
    emit(data, meta, output_format="text")
    output = capsys.readouterr()
    assert output.err == ""
    assert output.out == (
        "-\n  id: 001\n  amount: 12345678901234567890.123400\n"
        "  tiny: 1E-30\n  integer: 123456789012345678901234567890\n"
        "  active: false\n  missing: null\n  note:\n    中文\n    second line\n"
        '  empty: ""\n  details:\n    (empty object)\n\n'
        "Metadata:\n  returned_count: 1\n  warnings:\n"
        "    - INCOMPLETE_RESULT\n  stale: true\n"
    )
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
            {"warnings": ["INCOMPLETE_RESULT"], "published": False},
        ),
    )
    args = ["payment", action, "sla.baselines"]
    if action == "get":
        args.append("001")
    code, output, error = run_cli([*args, "--format", "text"])
    assert (code, error) == (0, "")
    assert output == (
        "amount: 0.1000\n\nMetadata:\n  warnings:\n"
        "    - INCOMPLETE_RESULT\n  published: false\n"
    )


def test_error_text_preserves_exit_streams_and_json(run_cli):
    args = ["payment", "refresh", "missing"]
    code, output, error = run_cli(args)
    document = json.loads(output)
    assert code == 1 and error == ""
    assert set(document) == {"data", "meta", "error"}
    assert document["data"] is None
    assert document["meta"] == {"published": False}
    text_code, output, text_error = run_cli([*args, "--format", "text"])
    assert (text_code, text_error) == (code, error)
    assert output == (
        "Metadata:\n  published: false\n\nError:\n"
        f"  code: {document['error']['code']}\n"
        f"  message: {document['error']['message']}\n"
        f"  retryable: {canonical(document['error']['retryable'])}\n"
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
            meta={"warnings": ["native diagnostic"]},
        )

    monkeypatch.setattr(cli, "execute", fail)
    args = ["payment", "refresh", "sla.baselines"]
    code, output, error = run_cli(args)
    assert code == 1 and error == ""
    document = json.loads(output)
    assert document == {
        "data": None,
        "meta": {"warnings": ["native diagnostic"], "published": False},
        "error": {
            "code": "BUSINESS_QUERY_FAILED",
            "message": "native query failed",
            "retryable": True,
        },
    }
    code, output, error = run_cli([*args, "--format", "text"])
    assert code == 1 and error == ""
    assert output == (
        "Metadata:\n  warnings:\n    - native diagnostic\n  published: false\n\n"
        "Error:\n  code: BUSINESS_QUERY_FAILED\n  message: native query failed\n"
        "  retryable: true\n"
    )


@pytest.mark.parametrize("data,expected", [([], "(empty list)"), (None, "null")])
def test_empty_result_is_explicit(capsys, data, expected):
    emit(data, output_format="text")
    assert capsys.readouterr().out == expected + "\n"
