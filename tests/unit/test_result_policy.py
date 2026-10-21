"""Public result-policy contracts for usable but incomplete acquisitions."""

import pytest

from dogopencli.errors import CliError
from dogopencli.result_policy import (
    SOURCE_ROW_OCCURRENCES,
    AcquisitionEvidence,
    evaluate_result,
    prepare_result,
)


def source_selection_evidence():
    return AcquisitionEvidence(
        scope_complete=True,
        dataset_complete=True,
        reported_total=3,
        arrivals=3,
        collected_total=2,
        unique_count=2,
        duplicate_count=1,
        total_semantics=SOURCE_ROW_OCCURRENCES,
        reasons=("SOURCE_ROWS_SELECTED",),
        attempts=(
            {
                "kind": "source_selection",
                "selection_fields": ["businessKey", "dimension"],
                "selection_order": ["modified", "created"],
                "raw_rows": 3,
                "selected_records": 2,
                "raw_coverage_complete": True,
            },
        ),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"arrivals": 2, "duplicate_count": 0},
        {"reported_total": 4},
        {"dataset_complete": False},
        {"attempts": []},
        {"reasons": []},
    ],
)
def test_source_selection_cannot_claim_complete_with_bad_native_evidence(change):
    record = source_selection_evidence().record()
    record.update(change)
    with pytest.raises(CliError):
        AcquisitionEvidence.from_record(record)


def test_source_selection_roundtrip_keeps_native_counts_and_honest_warning():
    evidence = AcquisitionEvidence.from_record(source_selection_evidence().record())
    decision = evaluate_result(evidence, mode="refresh", require_complete=True)
    assert decision.publishable and decision.expose_data
    assert decision.warnings[0]["code"] == "SOURCE_ROWS_SELECTED"
    assert "identical" not in decision.warnings[0]["message"]
    assert evidence.meta()["missing_count"] == 0
    assert evidence.meta()["coverage_ratio"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_rows", 2),
        ("selected_records", 1),
        ("raw_coverage_complete", False),
        ("selection_fields", []),
        ("selection_order", []),
        ("selection_order", [False]),
        ("selection_fields", [""]),
    ],
)
def test_source_selection_requires_consistent_counts_coverage_and_rule(field, value):
    record = source_selection_evidence().record()
    record["attempts"][0][field] = value
    with pytest.raises(CliError, match="selection evidence"):
        AcquisitionEvidence.from_record(record)


def test_incomplete_source_selection_reports_raw_shortfall_and_strict_rejects():
    record = source_selection_evidence().record()
    record.update(scope_complete=False, dataset_complete=False, reported_total=5)
    record["attempts"][0]["raw_coverage_complete"] = False
    evidence = AcquisitionEvidence.from_record(record)
    assert evidence.meta()["missing_count"] == 2
    assert evidence.meta()["coverage_ratio"] == 0.6
    decision = evaluate_result(evidence, mode="refresh", require_complete=True)
    assert not decision.publishable
    assert decision.error["code"] == "INCOMPLETE_RESULT"


def test_safe_shortfall_is_usable_and_publishable_but_strictly_rejected():
    evidence = AcquisitionEvidence.for_collection(
        complete=False, reported_total=100, collected_total=99, arrivals=100
    )
    decision = evaluate_result(evidence, mode="refresh")
    assert decision.expose_data and decision.publishable
    assert decision.error is None and decision.exit_code == 0
    assert decision.warnings[0]["reason_codes"] == [
        "COUNT_SHORTFALL",
        "DUPLICATE_ROWS",
        "UNEXPECTED_DUPLICATE_ROWS",
    ]
    strict = evaluate_result(evidence, mode="refresh", require_complete=True)
    assert not strict.expose_data and not strict.publishable
    assert strict.error["code"] == "INCOMPLETE_RESULT" and strict.exit_code == 1


def test_declared_identical_overlap_can_be_complete_and_strictly_usable():
    evidence = AcquisitionEvidence.for_collection(
        complete=True,
        reported_total=100,
        collected_total=100,
        arrivals=102,
        duplicate_policy="allow_identical_overlap",
        total_semantics="unique_objects",
    )
    decision = evaluate_result(evidence, mode="live", require_complete=True)
    assert evidence.scope_complete is True and evidence.duplicate_count == 2
    assert decision.expose_data and decision.exit_code == 0
    assert decision.warnings[0]["code"] == "DUPLICATE_ROWS"
    assert decision.error is None


def test_corrupt_complete_evidence_cannot_claim_missing_records_are_complete():
    record = AcquisitionEvidence.for_collection(
        complete=False, reported_total=100, collected_total=99, arrivals=99
    ).record()
    record["scope_complete"] = True
    with pytest.raises(CliError, match="evidence"):
        AcquisitionEvidence.from_record(record)


@pytest.mark.parametrize(
    "flags", [("complete",), ("dataset_complete",), ("complete", "dataset_complete")]
)
def test_output_metadata_cannot_promote_validated_incomplete_evidence(flags):
    evidence = AcquisitionEvidence.for_collection(
        complete=False, reported_total=100, collected_total=99, arrivals=99
    )
    meta = evidence.meta()
    for flag in flags:
        meta[flag] = True
    with pytest.raises(CliError) as caught:
        prepare_result(meta, require_complete=True)
    assert caught.value.code == "INVALID_RESPONSE"


def test_explicit_scope_counters_roundtrip_without_inventing_server_total():
    evidence = AcquisitionEvidence(
        scope_complete=True,
        dataset_complete=True,
        collected_total=3,
        requested_count=3,
        resolved_count=3,
        total_semantics="requested_accounts",
    )
    parsed = AcquisitionEvidence.from_record(evidence.record())
    assert parsed.meta()["requested_count"] == parsed.meta()["resolved_count"] == 3
    assert parsed.meta()["reported_total"] is None
    assert (
        "requested_count"
        not in AcquisitionEvidence.for_collection(
            complete=True, reported_total=1, collected_total=1
        ).record()
    )


@pytest.mark.parametrize(
    "counts",
    [
        {"requested_count": 3},
        {"resolved_count": 3},
        {"requested_count": 2, "resolved_count": 3},
        {"requested_count": 4, "resolved_count": 3},
        {"requested_count": 3, "resolved_count": 2},
        {"requested_count": True, "resolved_count": 3},
        {"requested_count": 3, "resolved_count": -1},
    ],
)
def test_inconsistent_explicit_scope_counters_are_invalid(counts):
    record = AcquisitionEvidence.for_collection(
        complete=True, reported_total=None, collected_total=3
    ).record()
    record.update(counts)
    with pytest.raises(CliError) as error:
        AcquisitionEvidence.from_record(record)
    assert error.value.code == "INVALID_RESPONSE"
