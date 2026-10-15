"""Latest-created bank selection through CLI, fake CDP and real temporary SQLite."""

import json

import pytest
from test_liquidity_reference_access_lists import access_page, source_rows

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]

ROOT = ["liquidity", "reference", "blacklist", "bank"]
FIELD = "bankFilterConfigQuery"


def bank(identity, created, **values):
    return {"bankId": identity, "gmtCreate": created, "status": "INVALID", **values}


@pytest.mark.parametrize("reverse", [False, True])
def test_bank_selects_latest_creation_before_filters_and_preserves_counts(
    setup, run_cli, reverse
):
    older = bank("B1", 10, status="VALID", gmtModified=999)
    newer = bank("B1", 20, nested={"amount": "1.002500", "empty": None})
    other = bank("B2", 15, status="VALID")
    rows = [older, other, newer]
    if reverse:
        rows.reverse()
    source_rows(setup, {FIELD: rows})
    code, out, err = run_cli(
        [*ROOT, "list", "--live", "--limit", "0", "--require-complete"]
    )
    assert code == 0, err
    result = parse(out)
    assert {row["bankId"]: row for row in result["data"]} == {"B1": newer, "B2": other}
    meta = result["meta"]
    assert meta["complete"] is True
    assert meta["reported_total"] == 3
    assert meta["collected_total"] == meta["matched_total"] == 2
    assert meta["acquisition"]["arrivals"] == 3
    assert meta["acquisition"]["duplicate_count"] == 1
    assert meta["missing_count"] == 0 and meta["coverage_ratio"] == 1
    assert "BANK_LATEST_CREATED_SELECTED" in meta["warnings"][0]["reason_codes"]
    assert "identical" not in meta["warnings"][0]["message"]
    assert "COUNT_SHORTFALL" not in meta["acquisition"]["reasons"]
    assert not setup.cache_path.exists()
    for request in setup.state.business_requests:
        vo = json.loads(request[FIELD])
        assert set(request) == {"tntInstId", FIELD}
        assert set(vo) == {
            "tntInstId",
            "timezone",
            "currentArea",
            "rowStart",
            "pageSize",
        }
        assert vo["currentArea"] == "2"
    code, out, err = run_cli(
        [*ROOT, "list", "--live", "--status", "VALID", "--require-complete"]
    )
    assert code == 0, err
    assert parse(out)["data"] == [other]


def test_bank_latest_across_pages_and_identical_ties(setup, run_cli):
    rows = [bank(f"B{i}", 10) for i in range(1001)]
    newer = bank("B1", 20, status="VALID")
    rows.extend([newer, dict(newer)])

    def answer(payload, index):
        vo = json.loads(payload[FIELD])
        start = vo["rowStart"]
        return access_page(rows[start : start + min(vo["pageSize"], 1000)], len(rows))

    setup.state.business_handler = answer
    code, out, err = run_cli(
        [*ROOT, "list", "--live", "--limit", "0", "--require-complete"]
    )
    assert code == 0, err
    result = parse(out)
    assert len(result["data"]) == 1001
    assert next(row for row in result["data"] if row["bankId"] == "B1") == newer
    assert result["meta"]["complete"] is True
    assert result["meta"]["reported_total"] == 1003
    assert result["meta"]["acquisition"]["duplicate_count"] == 2
    assert [
        json.loads(r[FIELD])["rowStart"] for r in setup.state.business_requests
    ] == [0, 0, 1000, 1, 999, 1003]


def test_bank_capped_page_without_duplicates_keeps_native_warning_offline(
    setup, run_cli
):
    rows = [bank(f"B{i}", 10) for i in range(1001)]

    def answer(payload, index):
        vo = json.loads(payload[FIELD])
        start = vo["rowStart"]
        return access_page(rows[start : start + min(vo["pageSize"], 1000)], len(rows))

    setup.state.business_handler = answer
    code, out, err = run_cli(["refresh", *ROOT, "--require-complete"])
    assert code == 0, err
    refreshed = parse(out)["meta"]
    assert refreshed["complete"] is True and refreshed["published"] is True
    assert refreshed["reported_total"] == refreshed["collected_total"] == 1001
    assert refreshed["acquisition"]["duplicate_count"] == 0
    warning = refreshed["warnings"][0]
    assert warning["code"] == "PAGE_SIZE_CAPPED"
    assert warning["reason_codes"] == ["PAGE_SIZE_CAPPED"]
    assert "duplicate" not in warning["message"]
    setup.state.running = False
    requests = len(setup.state.transports)
    code, out, err = run_cli([*ROOT, "list", "--require-complete"])
    assert code == 0, err
    assert parse(out)["meta"]["warnings"] == refreshed["warnings"]
    assert len(setup.state.transports) == requests


@pytest.mark.parametrize("created", [None, True, "20", -1, 20.5, 1760000000000.0])
def test_bank_invalid_creation_is_hard_failure(setup, run_cli, created):
    source_rows(setup, {FIELD: [bank("B1", 10), bank("B1", created)]})
    code, out, err = run_cli(["refresh", *ROOT])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert parse(out)["data"] is None
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("newest_first", [False, True])
def test_bank_conflicting_equal_creation_preserves_prior_slot(
    setup, run_cli, newest_first
):
    sources = {FIELD: [bank("B1", 5)]}
    source_rows(setup, sources)
    assert run_cli(["refresh", *ROOT, "--require-complete"])[0] == 0
    before = setup.cache_path.read_bytes()
    rows = [bank("B1", 10), bank("B1", 10, status="VALID"), bank("B1", 20)]
    if newest_first:
        rows.reverse()
    sources[FIELD] = rows
    code, out, err = run_cli(["refresh", *ROOT])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert parse(out)["data"] is None
    assert setup.cache_path.read_bytes() == before


def test_bank_slot_replays_native_counts_without_network_and_preserves_other_slots(
    setup, run_cli
):
    newer = bank("B1", 20)
    sources = {
        FIELD: [bank("B1", 10), newer],
        "accountFilterConfigQuery": [{"aliasName": "A1"}],
    }
    source_rows(setup, sources)
    account = ["liquidity", "reference", "blacklist", "account"]
    assert run_cli(["refresh", *account])[0] == 0
    assert run_cli(["refresh", *ROOT, "--require-complete"])[0] == 0
    before = setup.cache_path.read_bytes()
    sources[FIELD] = []
    code, out, err = run_cli(["refresh", *ROOT, "--require-complete"])
    assert code == 0, err
    assert parse(out)["meta"]["published"] is False
    assert setup.cache_path.read_bytes() == before
    setup.state.running = False
    count = len(setup.state.transports)
    code, out, err = run_cli([*ROOT, "list", "--require-complete", "--bank-id", "B1"])
    assert code == 0, err
    assert parse(out)["data"] == [newer]
    assert parse(out)["meta"]["reported_total"] == 2
    assert parse(out)["meta"]["acquisition"]["arrivals"] == 2
    assert len(setup.state.transports) == count
    assert setup.cache_path.read_bytes() == before
    assert run_cli([*ROOT, "prune"])[0] == 0
    assert run_cli([*ROOT, "list"])[0] == 1
    assert run_cli([*account, "list"])[0] == 0


def test_bank_raw_overlap_change_cannot_be_hidden_by_latest_selection(setup, run_cli):
    rows = [bank("B1", 10), bank("B1", 20), bank("B2", 10)]

    def answer(payload, index):
        vo = json.loads(payload[FIELD])
        page = rows[vo["rowStart"] : vo["rowStart"] + vo["pageSize"]]
        if vo["rowStart"] == 1:
            page = [bank("B1", 19), rows[-1]]
        return access_page(page, len(rows))

    setup.state.business_handler = answer
    code, out, err = run_cli(["refresh", *ROOT, "--require-complete"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


def test_bank_budget_partial_is_rejected_by_strict_refresh(setup, run_cli, monkeypatch):
    from dogopencli import collect

    source_rows(setup, {FIELD: [bank("B1", 10), bank("B1", 20)]})
    assert run_cli(["refresh", *ROOT, "--require-complete"])[0] == 0
    before = setup.cache_path.read_bytes()
    monkeypatch.setattr(collect, "MAX_PAGES", 1)
    code, out, err = run_cli(["refresh", *ROOT, "--require-complete"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli([*ROOT, "list", "--live"])
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is False


def test_bank_describe_declares_selection_and_actual_fields(run_cli):
    code, out, err = run_cli(["describe", *ROOT, "list"])
    assert code == 0, err
    result = parse(out)
    properties = result["data_schema"]["properties"]
    assert "id" not in properties and "gmtCreate" in properties
    assert "country" in properties and "timezone" in properties
    assert "gmtCreate" in str(result["read_guide"])
