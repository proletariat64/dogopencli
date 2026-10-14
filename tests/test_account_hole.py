"""Boundary proof for native omitted-position diagnostics."""

import json
import time
from dataclasses import replace

import pytest

from dogopencli.errors import BUSINESS_QUERY_FAILED, TIMEOUT, CliError
from dogopencli.plugins.liquidity.account_hole import verify_hole
from dogopencli.plugins.liquidity.capability import LiquidityListCapability
from dogopencli.plugins.liquidity.leaves import CASH_ACCOUNTS
from dogopencli.transport import OriginMetadata, TransportResponse


class NativeRows:
    def __init__(self, total=25, hole=12):
        self.total = total
        self.hole = hole
        self.positions = [
            None if i == hole else {"aliasName": f"account-{i}", "currency": "USD"}
            for i in range(total)
        ]
        self.requests = []

    @property
    def records(self):
        return [row for row in self.positions if row is not None]

    def execute(self, request, *, timeout=None):
        body = json.loads(request.body["bankAccountQueryVO"])
        start, size = body["rowStart"], body["pageSize"]
        self.requests.append((start, size))
        rows = [row for row in self.positions[start : start + size] if row is not None]
        payload = {
            "resultFlag": True,
            "count": self.total,
            "result": {"bankAccountPropertyVOList": rows},
        }
        return TransportResponse(
            200,
            json.dumps(payload).encode(),
            OriginMetadata("fake", True, None, True, True, None, None),
        )


def test_moved_interior_hole_is_verified_and_persisted(tmp_path):
    source = NativeRows()
    hint = tmp_path / "hints.json"
    result = verify_hole(
        LiquidityListCapability(CASH_ACCOUNTS),
        source,
        "",
        source.records,
        source.total,
        time.monotonic() + 120,
        hint_path=hint,
    )
    assert result["code"] == "VERIFIED_BACKEND_HOLE"
    assert result["native_total"] == 25
    assert result["effective_total"] == 24
    assert result["hole_offset"] == 12
    assert result["hint_saved"] is True
    assert "account-" not in hint.read_text()
    assert len(source.requests) <= 64


def verify(source, hint, records=None, deadline=None):
    return verify_hole(
        LiquidityListCapability(CASH_ACCOUNTS),
        source,
        "",
        source.records if records is None else records,
        source.total,
        time.monotonic() + 120 if deadline is None else deadline,
        hint_path=hint,
    )


def test_saved_hint_is_revalidated_by_next_acquisition(tmp_path):
    hint = tmp_path / "hints.json"
    assert verify(NativeRows(hole=18), hint)["hole_offset"] == 18
    source = NativeRows(hole=18)
    assert verify(source, hint)["hole_offset"] == 18
    assert (18, 1) in source.requests
    assert all(size in (1, 3) for _, size in source.requests)
    moved = NativeRows(hole=7)
    assert verify(moved, hint)["hole_offset"] == 7


def test_boundary_holes_are_never_accepted(tmp_path):
    for hole in (0, 24):
        assert verify(NativeRows(hole=hole), tmp_path / "hint.json") is None
    assert not (tmp_path / "hint.json").exists()


def test_duplicates_and_wrong_deficit_do_not_probe(tmp_path):
    source = NativeRows()
    assert verify(source, tmp_path / "hint.json", source.records[:-1]) is None
    rows = source.records.copy()
    rows[-1] = rows[0]
    assert verify(source, tmp_path / "hint.json", rows) is None
    assert source.requests == []


def test_corrupt_and_out_of_range_hint_are_rediscovered(tmp_path):
    hint = tmp_path / "hint.json"
    hint.write_text("{invalid")
    assert verify(NativeRows(), hint)["hole_offset"] == 12
    document = json.loads(hint.read_text())
    for value in document["hints"].values():
        value["offset"] = 20000
    hint.write_text(json.dumps(document))
    assert verify(NativeRows(hole=6), hint)["hole_offset"] == 6


def test_acquisition_reordering_is_never_accepted(tmp_path):
    source = NativeRows()
    rows = source.records.copy()
    rows[2], rows[3] = rows[3], rows[2]
    assert verify(source, tmp_path / "hint.json", rows) is None


def test_hint_save_failure_does_not_reject_verified_query(tmp_path):
    hint = tmp_path / "hint.json"
    hint.mkdir()
    result = verify(NativeRows(), hint)
    assert result["code"] == "VERIFIED_BACKEND_HOLE"
    assert result["hint_saved"] is False
    assert result["hint_warning"] == "Verified cash hole hint could not be saved"


class DriftingRows(NativeRows):
    def execute(self, request, *, timeout=None):
        response = super().execute(request, timeout=timeout)
        document = json.loads(response.body)
        if len(self.requests) > 2:
            document["count"] += 1
        return TransportResponse(200, json.dumps(document).encode(), response.origin)


def test_total_drift_invalidates_diagnostic(tmp_path):
    assert verify(DriftingRows(), tmp_path / "hint.json") is None


class RefusingRows(NativeRows):
    def execute(self, request, *, timeout=None):
        response = super().execute(request, timeout=timeout)
        document = json.loads(response.body)
        document["resultFlag"] = False
        return TransportResponse(200, json.dumps(document).encode(), response.origin)


def test_business_refusal_is_hard_error_not_an_empty_hole(tmp_path):
    with pytest.raises(CliError) as caught:
        verify(RefusingRows(), tmp_path / "hint.json")
    assert caught.value.code == BUSINESS_QUERY_FAILED
    assert not (tmp_path / "hint.json").exists()


def test_expired_aggregate_budget_fails_without_request(tmp_path):
    source = NativeRows()
    with pytest.raises(CliError) as caught:
        verify(source, tmp_path / "hint.json", deadline=time.monotonic() - 1)
    assert caught.value.code == TIMEOUT
    assert source.requests == []


def test_initial_candidate_is_currently_proved_not_trusted(tmp_path):
    source = NativeRows(total=2100, hole=2062)
    result = verify(source, tmp_path / "hint.json")
    assert result["hole_offset"] == 2062
    assert source.requests.count((2062, 1)) >= 2
    assert all(size in (1, 3) for _, size in source.requests)


def test_changed_native_contract_does_not_reuse_hint(tmp_path):
    hint = tmp_path / "hint.json"
    assert verify(NativeRows(hole=12), hint)["hint_saved"]
    changed = replace(
        CASH_ACCOUNTS, template={**CASH_ACCOUNTS.template, "wallet": True}
    )
    source = NativeRows(hole=12)
    result = verify_hole(
        LiquidityListCapability(changed),
        source,
        "",
        source.records,
        source.total,
        time.monotonic() + 120,
        hint_path=hint,
    )
    assert result["hole_offset"] == 12
    assert any(size > 3 for _, size in source.requests)
    assert len(json.loads(hint.read_text())["hints"]) == 2
