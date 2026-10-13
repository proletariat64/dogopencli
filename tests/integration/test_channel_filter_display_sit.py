"""Public-CLI SIT for Channel local filtering, display pagination, field
projection, table output and quality requirements (issue #4).

Extends the #2 snapshot SIT; same offline boundary (the integration
conftest blocks all sockets and subprocesses). The preparation tool orders
records by content hash, so expected seqids are derived from the prepared
dataset rather than assumed from fixture input order.

Sample rows (abilityId, status, inst, account, no, clearing, debit, credit,
country, version): 101 ENABLE CITILD ACCT-A 9001 BOOK RTP USD CNY GB v1;
102 DISABLE CITILD ACCT-A 9001 BOOK RTP USD USD GB v2; 103 ENABLE SCBLSG
ACCT-B 9002 FX PAYOUT EUR USD SG v1; 104 GRAY HSBCHK ACCT-C 9003 BOOK USD
IDR HK v1; 105 ENABLE CITILD ACCT-D 9004 BOOK RTP USD CNY GB v3; 106 INIT
SCBLSG ACCT-B 9002 FX PAYOUT EUR USD SG v2; 107 TEST HSBCHK ACCT-E 9005
BOOK HKD USD HK v1; 108 ENABLE CITILD ACCT-F 9006 BOOK RTP GBP CNY GB v1.
"""

import json
from pathlib import Path

import pytest

META_KEYS = {
    "source",
    "backend",
    "simulated",
    "scope",
    "snapshot_id",
    "dataset_id",
    "fetched_at",
    "loaded_at",
    "stale",
    "complete",
    "dataset_complete",
    "source_observed_from",
    "source_observed_to",
    "matched_total",
    "returned_count",
    "has_more",
}


@pytest.fixture
def refreshed(run_cli, dataset_factory, config_factory, sample_channel_rows):
    dataset = dataset_factory(sample_channel_rows)
    config_factory(dataset)
    code, _, _ = run_cli(["refresh", "payment", "channel"])
    assert code == 0
    return dataset


def listing(run_cli, *extra: str) -> tuple[int, str, str]:
    return run_cli(["payment", "channel", "list", *extra])


def by_seqid(dataset: Path) -> list[dict]:
    rows = [
        json.loads(line)
        for line in (dataset / "records.jsonl").read_text().splitlines()
    ]
    return sorted(rows, key=lambda row: row["seqid"])


def expect_seqids(dataset: Path, *ability_ids: int) -> list[int]:
    wanted = set(ability_ids)
    return [row["seqid"] for row in by_seqid(dataset) if row["abilityId"] in wanted]


def seqids(envelope_result: dict) -> list[int]:
    return [row["seqid"] for row in envelope_result["data"]]


def meta_has(
    result: dict, matched: int = 8, returned: int = 8, more: bool = False
) -> bool:
    meta = result["meta"]
    return (
        meta["matched_total"] == matched
        and meta["returned_count"] == returned
        and meta["has_more"] is more
    )


def test_scalar_filters_individually(run_cli, envelope, refreshed):
    code, out, _ = listing(run_cli, "--financial-inst-id", "CITILD")
    assert code == 0
    assert seqids(envelope(out)) == expect_seqids(refreshed, 101, 102, 105, 108)

    code, out, _ = listing(run_cli, "--debit-inst-country-code", "SG")
    assert code == 0
    assert seqids(envelope(out)) == expect_seqids(refreshed, 103, 106)

    code, out, _ = listing(run_cli, "--status", "GRAY")
    assert code == 0
    assert seqids(envelope(out)) == expect_seqids(refreshed, 104)


def test_array_filters_individually(run_cli, envelope, refreshed):
    cases = (
        (("--debit-account-name", "ACCT-B"), (103, 106)),
        (("--debit-account-no", "9001"), (101, 102)),
        (("--clearing-system-name", "BOOK"), (104, 107)),
        (("--debit-currency", "EUR"), (103, 106)),
        (("--credit-currency", "USD"), (102, 103, 106, 107)),
    )
    for option, abilities in cases:
        code, out, _ = listing(run_cli, *option)
        assert code == 0, option
        assert seqids(envelope(out)) == expect_seqids(refreshed, *abilities), option


def test_or_within_field_and_across_fields(run_cli, envelope, refreshed):
    code, out, _ = listing(
        run_cli, "--debit-account-name", "ACCT-A", "--debit-account-name", "ACCT-E"
    )
    assert code == 0
    result = envelope(out)
    assert seqids(result) == expect_seqids(refreshed, 101, 102, 107)
    assert result["meta"]["matched_total"] == 3

    code, out, _ = listing(
        run_cli,
        "--debit-currency",
        "EUR",
        "--debit-currency",
        "HKD",
        "--status",
        "INIT",
    )
    assert code == 0
    assert seqids(envelope(out)) == expect_seqids(refreshed, 106)

    code, out, _ = listing(
        run_cli, "--financial-inst-id", "CITILD", "--credit-currency", "USD"
    )
    assert code == 0
    assert seqids(envelope(out)) == expect_seqids(refreshed, 102)

    code, out, _ = listing(
        run_cli,
        "--clearing-system-name",
        "BOOK RTP",
        "--clearing-system-name",
        "FX PAYOUT",
        "--debit-inst-country-code",
        "GB",
    )
    assert code == 0
    assert seqids(envelope(out)) == expect_seqids(refreshed, 101, 102, 105, 108)


def test_all_statuses_and_versions_preserved(run_cli, envelope, refreshed):
    code, out, _ = listing(run_cli, "--limit", "0")
    assert code == 0
    rows = envelope(out)["data"]
    assert {row["status"] for row in rows} == {
        "ENABLE",
        "DISABLE",
        "GRAY",
        "INIT",
        "TEST",
    }
    assert {row["configVersion"] for row in rows} == {"v1", "v2", "v3"}

    code, out, _ = listing(run_cli, "--financial-inst-id", "CITILD")
    assert code == 0
    rows = envelope(out)["data"]
    assert {row["configVersion"] for row in rows} == {"v1", "v2", "v3"}
    by_account = {}
    for row in rows:
        by_account.setdefault(row["debitAccountName"], set()).add(row["configVersion"])
    assert by_account["ACCT-A"] == {"v1", "v2"}


def test_filter_and_pagination_do_not_renumber(run_cli, envelope, refreshed):
    matched = expect_seqids(refreshed, 101, 102, 105, 108)
    code, out, _ = listing(
        run_cli, "--financial-inst-id", "CITILD", "--limit", "2", "--offset", "1"
    )
    assert code == 0
    result = envelope(out)
    assert seqids(result) == matched[1:3]
    assert result["data"][0]["seqid"] != 1 or matched[1] == 1
    meta = result["meta"]
    assert meta["matched_total"] == 4
    assert meta["returned_count"] == 2
    assert meta["has_more"] is True


def test_pagination_boundaries(run_cli, envelope, refreshed):
    code, out, _ = listing(run_cli, "--offset", "8")
    assert code == 0
    result = envelope(out)
    assert result["data"] == []
    assert result["error"] is None
    meta = result["meta"]
    assert meta["matched_total"] == 8
    assert meta["returned_count"] == 0
    assert meta["has_more"] is False

    code, out, _ = listing(run_cli, "--offset", "100")
    assert code == 0
    result = envelope(out)
    assert result["data"] == []
    assert result["meta"]["has_more"] is False

    code, out, _ = listing(run_cli, "--limit", "8")
    assert code == 0
    result = envelope(out)
    assert meta_has(result, returned=8, more=False)
    assert seqids(result) == [row["seqid"] for row in by_seqid(refreshed)]

    code, out, _ = listing(run_cli, "--limit", "1")
    assert code == 0
    result = envelope(out)
    assert meta_has(result, returned=1, more=True)

    enable = expect_seqids(refreshed, 101, 103, 105, 108)
    code, out, _ = listing(
        run_cli, "--status", "ENABLE", "--limit", "2", "--offset", "2"
    )
    assert code == 0
    result = envelope(out)
    assert seqids(result) == enable[2:4]
    assert meta_has(result, matched=4, returned=2, more=False)

    code, out, _ = listing(run_cli, "--status", "ENABLE", "--limit", "0")
    assert code == 0
    result = envelope(out)
    assert seqids(result) == enable
    assert meta_has(result, matched=4, returned=4, more=False)


def test_display_truncation_is_not_collection_incomplete(
    run_cli, envelope, dataset_factory, config_factory, bulk_channel_rows
):
    dataset = dataset_factory(bulk_channel_rows(205), name="bulk")
    config_factory(dataset)
    assert run_cli(["refresh", "payment", "channel"])[0] == 0
    code, out, _ = listing(run_cli)
    assert code == 0
    meta = envelope(out)["meta"]
    assert meta["has_more"] is True
    assert meta["dataset_complete"] is True
    assert meta["complete"] is False
    assert meta["matched_total"] == 205
    assert meta["returned_count"] == 100

    code, out, _ = listing(run_cli, "--offset", "205")
    assert code == 0
    result = envelope(out)
    assert result["data"] == []
    assert result["meta"]["has_more"] is False
    assert result["meta"]["matched_total"] == 205


def test_all_conflicts_with_explicit_offset_zero(run_cli, envelope, refreshed):
    code, out, _ = listing(run_cli, "--all", "--offset", "0")
    assert code == 2
    assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_fields_projection_keeps_meta(run_cli, envelope, refreshed):
    ordered = by_seqid(refreshed)
    code, out, _ = listing(
        run_cli, "--fields", "seqid,status", "--limit", "2", "--offset", "1"
    )
    assert code == 0
    result = envelope(out)
    assert result["data"] == [
        {"seqid": ordered[1]["seqid"], "status": ordered[1]["status"]},
        {"seqid": ordered[2]["seqid"], "status": ordered[2]["status"]},
    ]
    meta = result["meta"]
    assert META_KEYS <= set(meta)
    assert meta["matched_total"] == 8
    assert meta["returned_count"] == 2
    assert meta["has_more"] is True
    assert meta["simulated"] is True
    assert meta["complete"] is False

    code, out, _ = listing(run_cli, "--fields", "seqid,unknownField", "--limit", "1")
    assert code == 0
    assert envelope(out)["data"] == [{"seqid": ordered[0]["seqid"]}]


def test_empty_result_does_not_claim_backend_absence(run_cli, envelope, refreshed):
    code, out, _ = listing(run_cli, "--status", "ENABLE", "--debit-currency", "HKD")
    assert code == 0
    result = envelope(out)
    assert result["data"] == []
    assert result["error"] is None
    meta = result["meta"]
    assert meta["matched_total"] == 0
    assert meta["returned_count"] == 0
    assert meta["has_more"] is False
    assert meta["complete"] is False
    assert meta["dataset_complete"] is True


def test_require_fresh_passes_on_fresh_cache(run_cli, envelope, refreshed):
    code, out, _ = listing(run_cli, "--require-fresh")
    assert code == 0
    result = envelope(out)
    assert result["error"] is None
    assert result["meta"]["stale"] is False
    assert result["meta"]["matched_total"] == 8


def test_require_fresh_rejects_stale_with_null_data(
    run_cli, envelope, dataset_factory, config_factory, sample_channel_rows
):
    dataset = dataset_factory(
        sample_channel_rows, observed_at="2026-01-01T00:00:00+00:00"
    )
    config_factory(dataset, ttl_hours=0)
    assert run_cli(["refresh", "payment", "channel"])[0] == 0
    code, out, _ = listing(run_cli, "--require-fresh")
    assert code == 1
    result = envelope(out)
    assert result["data"] is None
    assert result["error"]["code"] == "CACHE_STALE"


def test_require_complete_rejects_snapshot_with_null_data(run_cli, envelope, refreshed):
    code, out, _ = listing(run_cli, "--require-complete")
    assert code == 1
    result = envelope(out)
    assert result["data"] is None
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["error"]["retryable"] is False


def test_table_shows_quality_markers(run_cli, refreshed):
    enable = expect_seqids(refreshed, 101, 103, 105, 108)
    code, out, err = listing(
        run_cli, "--format", "table", "--status", "ENABLE", "--limit", "2"
    )
    assert code == 0
    assert "INCOMPLETE_RESULT" in err
    for marker in (
        "source: cache",
        "backend: snapshot",
        "scope: EXTERNAL",
        "simulated: true",
        "complete: false",
        "dataset_complete: true",
        "stale: false",
        "fetched_at: ",
        "loaded_at: ",
        "dataset_id: ",
        "matched_total: 4",
        "returned_count: 2",
        "has_more: true",
    ):
        assert marker in out, marker
    lines = out.splitlines()
    header_index = next(i for i, line in enumerate(lines) if line.startswith("seqid"))
    header = lines[header_index].split()
    assert "abilityId" in header
    assert "status" in header
    assert "configVersion" in header
    assert all(
        token and set(token) == {"-"} for token in lines[header_index + 1].split()
    )
    body = [line.split() for line in lines[header_index + 2 :]]
    assert [row[0] for row in body] == [str(seqid) for seqid in enable[:2]]
    assert all(row[header.index("status")] == "ENABLE" for row in body)


def test_table_stale_marker(
    run_cli, dataset_factory, config_factory, sample_channel_rows
):
    dataset = dataset_factory(
        sample_channel_rows, observed_at="2026-01-01T00:00:00+00:00"
    )
    config_factory(dataset, ttl_hours=0)
    assert run_cli(["refresh", "payment", "channel"])[0] == 0
    code, out, _ = listing(run_cli, "--format", "table", "--limit", "1")
    assert code == 0
    assert "stale: true" in out
    assert "fetched_at: 2026-01-01T00:00:00+00:00" in out


def test_table_with_fields(run_cli, refreshed):
    ordered = by_seqid(refreshed)
    code, out, _ = listing(
        run_cli,
        "--format",
        "table",
        "--fields",
        "seqid,debitCurrency",
        "--limit",
        "2",
    )
    assert code == 0
    lines = out.splitlines()
    header_index = next(i for i, line in enumerate(lines) if line.startswith("seqid"))
    assert lines[header_index].split() == ["seqid", "debitCurrency"]
    body = [line.split() for line in lines[header_index + 2 :]]
    assert body == [[str(row["seqid"]), row["debitCurrency"]] for row in ordered[:2]]
    assert "matched_total: 8" in out
    assert "simulated: true" in out


def test_table_empty_result(run_cli, refreshed):
    code, out, _ = listing(run_cli, "--format", "table", "--financial-inst-id", "NOPE")
    assert code == 0
    assert "(no rows)" in out
    assert "matched_total: 0" in out
    assert "has_more: false" in out


def test_table_errors_go_to_stderr(run_cli, refreshed):
    code, out, err = listing(run_cli, "--format", "table", "--require-complete")
    assert code == 1
    assert out == ""
    assert "INCOMPLETE_RESULT" in err


def test_table_cache_miss_goes_to_stderr(
    run_cli, dataset_factory, config_factory, sample_channel_rows
):
    config_factory(dataset_factory(sample_channel_rows))
    code, out, err = listing(run_cli, "--format", "table")
    assert code == 1
    assert out == ""
    assert "CACHE_MISS" in err


def test_table_argument_error_exit_2(run_cli, refreshed):
    code, out, err = listing(run_cli, "--format", "table", "--all", "--limit", "5")
    assert code == 2
    assert "INVALID_ARGUMENT" in out
    assert "--all removed" in out
