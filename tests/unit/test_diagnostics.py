"""Acceptance of the shared public diagnostic and process-status contracts."""

import pytest

from dogopencli.errors import diagnostic, error_exit_code


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (None, 0),
        ("INVALID_ARGUMENT", 2),
        ("INTERRUPTED", 130),
        ("INCOMPLETE_RESULT", 1),
        ("BUSINESS_QUERY_FAILED", 1),
        ("MY_NATIVE_CODE", 1),
    ],
)
def test_process_status_is_owned_by_shared_outcome(code, expected):
    assert error_exit_code(code) == expected


def test_diagnostic_keeps_safe_cause_and_marks_unknown_facts():
    error = diagnostic(
        "BUSINESS_QUERY_FAILED",
        "The detail query was refused",
        native_code="NATIVE_099",
        component="history",
        consequence="The requested detail cannot be returned",
    )
    assert error == {
        "code": "BUSINESS_QUERY_FAILED",
        "message": "The detail query was refused",
        "severity": "error",
        "origin": "backend",
        "stage": "query",
        "component": "history",
        "scope": None,
        "retryable": None,
        "native_code": "NATIVE_099",
        "consequence": "The requested detail cannot be returned",
        "action": None,
    }


def test_diagnostic_rejects_sensitive_native_context():
    error = diagnostic(
        "BUSINESS_QUERY_FAILED", "Query failed", native_code="token=secret body"
    )
    assert error["native_code"] is None


def test_warning_keeps_coverage_reasons_without_becoming_fatal():
    warning = diagnostic(
        "INCOMPLETE_RESULT",
        "History coverage is unproven",
        severity="warning",
        reason_codes=["HISTORY_COVERAGE_UNPROVEN"],
        component="history",
        count=2,
    )
    assert warning["severity"] == "warning"
    assert warning["reason_codes"] == ["HISTORY_COVERAGE_UNPROVEN"]
    assert warning["count"] == 2
    assert warning["action"] == "Inspect coverage reasons or use --require-complete."
