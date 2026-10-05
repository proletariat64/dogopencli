"""Public result-policy contracts for usable but incomplete acquisitions."""

import pytest

from dogopencli.errors import CliError
from dogopencli.result_policy import (
    AcquisitionEvidence,
    evaluate_result,
    prepare_result,
)


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
