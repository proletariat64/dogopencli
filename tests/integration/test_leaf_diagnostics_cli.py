# ruff: noqa: F811
"""Diagnostic and process-status acceptance through installed leaf commands."""

import json
import os
from pathlib import Path

import pytest
from test_leaf_pilots_cli import pilots  # noqa: F401


@pytest.mark.parametrize("leaf_exit", [0, 2, 7, 130])
def test_leaf_cannot_override_failure_status_and_native_cause_survives(
    run_cli, pilots, leaf_exit
):
    adapter = (
        Path(os.environ["DOGOPENCLI_CONFIG"]).parent
        / "plugins/payment/sla.baselines/adapter.py"
    )
    adapter.write_text(
        adapter.read_text().replace(
            "return parse_detail(body, identity)",
            'raise CliError("BUSINESS_QUERY_FAILED", "qualified native failure", '
            f'exit_code={leaf_exit}, meta={{"native_code": "099"}})',
        )
    )
    pilots.business_script.append(
        {"status": 200, "body": {"success": True, "resultData": {"id": "101"}}}
    )
    status, output, _ = run_cli(["payment", "get", "sla.baselines", "101"])
    value = json.loads(output)
    assert status == 1
    assert value["data"] is None
    assert value["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert value["error"]["native_code"] == "099"
    assert value["error"]["origin"] == "backend"
    assert value["meta"]["outcome"] == "failed"
    assert value["meta"]["publication"]["status"] == "not_requested"


@pytest.mark.parametrize("output_format", ["json", "text"])
def test_invalid_input_keeps_usage_status_and_actionable_diagnostic(
    run_cli, pilots, output_format
):
    status, output, _ = run_cli(
        [
            "payment",
            "get",
            "sla.baselines",
            "101",
            "--unsupported-option",
            "--format",
            output_format,
        ]
    )
    assert status == 2
    if output_format == "json":
        error = json.loads(output)["error"]
        assert error["code"] == "INVALID_ARGUMENT"
        assert error["origin"] == "input"
        assert error["stage"] == "validation"
        assert error["action"] == "Correct the arguments and retry."
    else:
        assert "code: INVALID_ARGUMENT" in output
        assert "origin: input" in output
        assert "Correct the arguments and retry." in output
    assert not pilots.business_requests


def test_strict_rejection_retains_sdk_coverage_diagnostic_and_one_warning(
    run_cli, pilots
):
    from test_leaf_pilots_cli import native_page, native_row

    partial = native_page("collection", [native_row("collection", "partial")])
    partial["body"]["totalCount"] = 1001
    pilots.business_script.append(partial)
    status, output, stderr = run_cli(
        ["collection", "list", "cost", "--live", "--require-complete"]
    )
    value = json.loads(output)
    assert status == 1
    assert value["data"] is None
    assert value["error"]["code"] == "INCOMPLETE_RESULT"
    assert value["error"]["origin"] == "sdk"
    assert value["error"]["stage"] == "coverage"
    assert "COUNT_SHORTFALL" in value["error"]["reason_codes"]
    assert value["error"]["consequence"] == (
        "candidate data is withheld; no replacement is published"
    )
    assert stderr.count("warning: INCOMPLETE_RESULT") == 1
