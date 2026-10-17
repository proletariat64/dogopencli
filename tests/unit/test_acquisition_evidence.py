"""Validated coverage gaps produce evidence; semantic failures stay hard."""

from dataclasses import replace

import pytest
from synthetic_capability import SAMPLE, SCOPE

from dogopencli import collect
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical
from dogopencli.transport import TransportResponse
from dogopencli.transport.cdp import ORIGIN_CDP

FIXED = replace(
    SAMPLE,
    contract=replace(
        SAMPLE.contract, page_size=1000, rebuild_page_size=None, single_page=True
    ),
)


def row(identity="1", scope=SCOPE, **values):
    return {"id": identity, "scope": scope, **values}


class Transport:
    def __init__(self, candidates):
        self.candidates = iter(candidates)
        self.requests = []

    def execute(self, request, *, timeout):
        assert timeout > 0
        self.requests.append(request.body)
        rows, total = next(self.candidates)
        body = {
            "success": True,
            "pageNo": request.body["pageNo"],
            "pageSize": request.body["pageSize"],
            "totalCount": total,
            "resultDataList": rows,
        }
        return TransportResponse(200, canonical(body).encode(), ORIGIN_CDP)


def test_rebuild_keeps_independent_candidates_and_raw_duplicate_evidence():
    transport = Transport([([row(), row()], 2), ([row("2")], 2)])
    result = collect.collect_scope(SAMPLE, transport, SCOPE)
    assert result.records == [row("2")]
    assert result.complete is False
    assert result.evidence.arrivals == 1
    assert result.evidence.unique_count == 1
    assert result.evidence.reported_total == 2
    assert result.evidence.reasons == ("COUNT_SHORTFALL",)
    assert [item["page_size"] for item in result.evidence.attempts] == [5000, 10000]
    assert result.evidence.attempts[0]["duplicate_count"] == 1
    assert result.evidence.attempts[0]["complete"] is False
    assert result.rebuilt is True


@pytest.mark.parametrize("rows,total", [([], 2), (["1"], 1001), (["1", "1"], 1)])
def test_fixed_contract_finishes_one_request_and_returns_safe_partial(rows, total):
    cap = FIXED
    records = [row(identity, cap.default_scope) for identity in rows]
    transport = Transport([(records, total)])
    result = collect.collect_scope(cap, transport, cap.default_scope)
    assert result.complete is False
    assert result.pages == 1
    assert result.evidence.arrivals == len(rows)
    assert result.evidence.collected_total == len(set(rows))
    assert len(transport.requests) == 1
    assert transport.requests[0]["pageSize"] == 1000


def test_duplicate_tolerance_needs_explicit_contract_and_preserves_warning():
    contract = replace(
        SAMPLE.contract,
        duplicate_policy="allow_identical_overlap",
        total_semantics="unique_objects",
    )
    cap = replace(SAMPLE, contract=contract)
    result = collect.collect_scope(cap, Transport([([row(), row()], 1)]), SCOPE)
    assert result.complete is True
    assert result.rebuilt is False
    assert result.evidence.reasons == ("DUPLICATE_ROWS",)
    assert result.evidence.duplicate_count == 1


@pytest.mark.parametrize(
    "records,total",
    [([row(), row(status="drift")], 2), ([row(), row("2")], 1)],
)
def test_conflicts_and_excess_unique_are_hard_and_do_not_rebuild(records, total):
    transport = Transport([(records, total)])
    with pytest.raises(CliError) as error:
        collect.collect_scope(SAMPLE, transport, SCOPE)
    assert error.value.code == "INVALID_RESPONSE"
    assert len(transport.requests) == 1


def test_business_consistency_failure_is_hard_even_with_distinct_identities():
    cap = replace(
        SAMPLE,
        contract=replace(SAMPLE.contract, consistency_field="business"),
    )
    transport = Transport([([row(business="same"), row("2", business="same")], 2)])
    with pytest.raises(CliError) as error:
        collect.collect_scope(cap, transport, SCOPE)
    assert error.value.code == "INVALID_RESPONSE"
    assert len(transport.requests) == 1


def test_rebuild_shares_deadline_and_can_converge_to_independent_total(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(collect, "_monotonic", lambda: clock[0])
    timeouts = []

    class TimedTransport(Transport):
        def execute(self, request, *, timeout):
            timeouts.append(timeout)
            clock[0] += 2
            return super().execute(request, timeout=timeout)

    transport = TimedTransport([([row(), row()], 2), ([row("2")], 1)])
    result = collect.collect_scope(
        SAMPLE,
        transport,
        SCOPE,
        budget_seconds=10,
    )
    assert result.complete is True
    assert result.records == [row("2")]
    assert result.deadline == 10
    assert timeouts == [10, 8]
    assert result.evidence.reported_total == 1
    assert result.evidence.reasons == ()
    assert [item["reported_total"] for item in result.evidence.attempts] == [2, 1]


def test_paginated_empty_page_before_range_end_stays_hard_failure():
    transport = Transport([([], 5001)])
    with pytest.raises(CliError) as error:
        collect.collect_scope(SAMPLE, transport, SCOPE)
    assert error.value.code == "INVALID_RESPONSE"
    assert len(transport.requests) == 1


def test_no_native_identity_preserves_identical_occurrences():
    cap = replace(
        SAMPLE,
        contract=replace(
            SAMPLE.contract,
            has_identity=False,
            total_semantics="occurrences",
        ),
    )
    result = collect.collect_scope(cap, Transport([([row(), row()], 2)]), SCOPE)
    assert result.complete is True
    assert result.records == [row(), row()]
    assert result.evidence.arrivals == 2
    assert result.evidence.unique_count is None
    assert result.evidence.duplicate_count is None
    assert result.evidence.reasons == ()


@pytest.mark.parametrize("same_version", [False, True])
def test_versioned_business_key_does_not_prove_native_row_identity(
    same_version,
):
    cap = replace(
        SAMPLE,
        contract=replace(
            SAMPLE.contract,
            has_identity=False,
            total_semantics="occurrences",
            consistency_field="business",
            consistency_version_field="version",
            rebuild_page_size=None,
        ),
    )
    records = [
        row(business="same", version="v1"),
        row("2", business="same", version="v1" if same_version else "v2"),
    ]
    transport = Transport([(records, 2)])
    result = collect.collect_scope(cap, transport, SCOPE)
    assert result.records == records
    assert result.complete is False
    assert result.evidence.reasons == ("BUSINESS_CONSISTENCY_UNPROVEN",)
    assert result.evidence.unique_count is None


def test_unreported_versions_cannot_establish_same_version_conflict():
    cap = replace(
        SAMPLE,
        contract=replace(
            SAMPLE.contract,
            has_identity=False,
            total_semantics="occurrences",
            consistency_field="business",
            consistency_version_field="version",
            rebuild_page_size=None,
        ),
    )
    records = [row(business="same"), row("2", business="same")]
    result = collect.collect_scope(cap, Transport([(records, 2)]), SCOPE)
    assert result.records == records
    assert result.complete is False
    assert result.evidence.reasons == ("BUSINESS_CONSISTENCY_UNPROVEN",)
