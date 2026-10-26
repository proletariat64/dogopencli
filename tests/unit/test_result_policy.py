"""Public result-policy contracts for usable but incomplete acquisitions."""

from dataclasses import replace

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
        usable_incomplete=True,
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


def test_safe_shortfall_is_usable_live_and_refresh_but_strict_rejects():
    evidence = AcquisitionEvidence.for_collection(
        complete=False, reported_total=100, collected_total=99, arrivals=100
    )
    decision = evaluate_result(evidence, mode="live")
    assert decision.expose_data and not decision.publishable
    assert decision.error is None and decision.exit_code == 0
    assert decision.warnings[0]["reason_codes"] == [
        "COUNT_SHORTFALL",
        "DUPLICATE_ROWS",
        "UNEXPECTED_DUPLICATE_ROWS",
    ]
    strict = evaluate_result(evidence, mode="live", require_complete=True)
    assert not strict.expose_data and not strict.publishable
    assert strict.error["code"] == "INCOMPLETE_RESULT" and strict.exit_code == 1
    refresh = evaluate_result(evidence, mode="refresh")
    assert refresh.expose_data and refresh.publishable
    assert refresh.error is None and refresh.exit_code == 0


def test_complete_empty_refresh_preserves_saved_snapshot():
    evidence = AcquisitionEvidence.for_collection(
        complete=True, reported_total=0, collected_total=0, arrivals=0
    )
    decision = evaluate_result(evidence, mode="refresh")
    assert decision.expose_data and not decision.publishable
    assert decision.error is None and decision.exit_code == 0


@pytest.mark.parametrize("mode", ["live", "refresh", "cache"])
def test_incomplete_evidence_needs_explicit_usability_qualification(mode):
    evidence = AcquisitionEvidence(
        scope_complete=False,
        dataset_complete=False,
        collected_total=1,
        reasons=("SUPPLEMENT_UNAVAILABLE",),
    )
    decision = evaluate_result(evidence, mode=mode)
    assert decision.expose_data is False
    assert decision.publishable is False
    assert decision.error["code"] == "INCOMPLETE_RESULT"
    assert decision.exit_code == 1


def test_incomplete_qualification_survives_evidence_roundtrip():
    evidence = AcquisitionEvidence.for_collection(
        complete=False, reported_total=2, collected_total=1, arrivals=1
    )
    retained = AcquisitionEvidence.from_record(evidence.record())
    assert retained.usable_incomplete is True
    assert evaluate_result(retained, mode="cache").expose_data is True
    record = evidence.record()
    record["usable_incomplete"] = "yes"
    with pytest.raises(CliError):
        AcquisitionEvidence.from_record(record)


def test_decision_keeps_outcome_quality_and_actual_publication_separate():
    evidence = AcquisitionEvidence.for_collection(
        complete=False, reported_total=2, collected_total=1, arrivals=1
    )
    decision = evaluate_result(evidence, mode="refresh")
    assert decision.meta(mode="refresh", published=True) == {
        "outcome": "warning",
        "data_quality": "incomplete",
        "publication": {"status": "published", "reason": "accepted"},
    }
    assert decision.meta(mode="cache")["publication"] == {
        "status": "not_requested",
        "reason": None,
    }
    strict = evaluate_result(evidence, mode="refresh", require_complete=True)
    assert strict.meta(mode="refresh") == {
        "outcome": "failed",
        "data_quality": "incomplete",
        "publication": {"status": "unchanged", "reason": "rejected"},
    }


def test_complete_warning_retains_its_reason_instead_of_inventing_duplicates():
    evidence = AcquisitionEvidence.for_collection(
        complete=True,
        reported_total=1,
        collected_total=1,
        reasons=("SOURCE_BOUNDARY_CONFIRMED",),
    )
    decision = evaluate_result(evidence, mode="live", require_complete=True)
    assert decision.warnings[0]["code"] == "SOURCE_BOUNDARY_CONFIRMED"
    assert "duplicate" not in decision.warnings[0]["message"]


@pytest.mark.parametrize("latest_by", [False, True])
def test_conflicting_identity_is_not_qualified_by_a_partial_usability_witness(
    latest_by,
):
    reasons = ("IDENTITY_CONTENT_CONFLICT",)
    if not latest_by:
        reasons += ("LAST_ARRIVAL_WINS",)
    evidence = AcquisitionEvidence.for_collection(
        complete=False,
        reported_total=2,
        collected_total=1,
        arrivals=2,
        usable_incomplete=True,
        reasons=reasons,
    )
    assert evidence.usable_incomplete is False
    for mode in ("live", "refresh", "cache"):
        decision = evaluate_result(replace(evidence, usable_incomplete=True), mode=mode)
        assert decision.expose_data is False
        assert decision.publishable is False
        assert "IDENTITY_CONTENT_CONFLICT" in decision.error["reason_codes"]


@pytest.mark.parametrize("trace", [False, True])
def test_explicit_usability_cannot_mask_observed_source_identity_conflicts(trace):
    conflicting = AcquisitionEvidence.for_collection(
        complete=False,
        reported_total=2,
        collected_total=1,
        arrivals=2,
        reasons=("IDENTITY_CONTENT_CONFLICT",),
    ).record()
    source = {"acquisition": conflicting, "scope": "requested"}
    evidence = AcquisitionEvidence(
        scope_complete=False,
        dataset_complete=False,
        collected_total=1,
        usable_incomplete=True,
        attempts=(
            {
                "kind": "custom_query",
                "queries": {"root": {"collections": [source]}},
            },
        )
        if trace
        else (),
        sources=None if trace else {"root": conflicting},
    )
    decision = evaluate_result(evidence, mode="refresh")
    assert decision.expose_data is False
    assert decision.publishable is False
    assert "IDENTITY_CONTENT_CONFLICT" in decision.error["reason_codes"]


def test_native_diagnostics_do_not_override_qualified_acquisition_evidence():
    evidence = AcquisitionEvidence.for_collection(
        complete=True,
        reported_total=1,
        collected_total=1,
        attempts=({"kind": "account_context", "sources": [{"source": "cache"}]},),
    )
    evidence = replace(
        evidence,
        native_metadata=(
            {
                "position": 0,
                "page_size": 1,
                "metadata": {
                    "conflict_count": 1,
                    "reasons": ["IDENTITY_CONTENT_CONFLICT"],
                },
            },
        ),
    )
    decision = evaluate_result(evidence, mode="live", require_complete=True)
    assert decision.expose_data is True
    assert decision.error is None


@pytest.mark.parametrize("meta", [{}, {"complete": True}, {"complete": False}])
def test_output_policy_requires_explicit_acquisition_evidence(meta):
    with pytest.raises(CliError) as error:
        prepare_result(meta)
    assert error.value.code == "INVALID_RESPONSE"


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


@pytest.mark.parametrize("complete", [False, True])
def test_timeout_attempt_is_recovered_only_by_completed_acquisition(complete):
    from dogopencli.result_policy import check_complete

    evidence = AcquisitionEvidence.for_collection(
        complete=complete,
        reported_total=1,
        collected_total=1,
        arrivals=1,
        attempts=({"complete": False, "error": "TIMEOUT"}, {"complete": complete}),
    )
    decision = evaluate_result(evidence, mode="refresh")
    if complete:
        assert decision.expose_data and decision.publishable
        assert check_complete(
            evidence, mode="refresh", require_complete=True
        ).publishable
    else:
        assert not decision.expose_data and not decision.publishable
        assert decision.error["code"] == "TIMEOUT"
        assert decision.error["retryable"] is True


def test_completed_source_timeout_history_does_not_poison_unrelated_supplementary_gap():
    completed = AcquisitionEvidence.for_collection(
        complete=True,
        reported_total=1,
        collected_total=1,
        arrivals=1,
        attempts=({"complete": False, "error": "TIMEOUT"}, {"complete": True}),
    )
    composite = AcquisitionEvidence.for_collection(
        complete=False,
        reported_total=None,
        collected_total=1,
        arrivals=1,
        reasons=("SUPPLEMENTARY_COVERAGE_UNPROVEN",),
        attempts=({"kind": "composition", "source_acquisition": completed.record()},),
    )
    assert evaluate_result(composite, mode="refresh").publishable


def test_exhausted_page_budget_is_not_a_qualified_publishable_gap():
    evidence = AcquisitionEvidence.for_collection(
        complete=False,
        reported_total=None,
        collected_total=2,
        arrivals=2,
        reasons=("PAGE_BUDGET_EXHAUSTED",),
    )
    decision = evaluate_result(evidence, mode="refresh")
    assert not decision.expose_data and not decision.publishable
    assert decision.error["code"] == "TIMEOUT"
