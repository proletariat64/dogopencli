"""Public-CLI SIT for the Channel snapshot source (issue #2).

Drives refresh + list through dogopencli.cli.main with synthetic datasets;
asserts stdout/stderr, exit codes and cache file state. Fully offline.
"""

from decimal import Decimal
from pathlib import Path

import pytest

PRECISE_AMOUNT = "0.1234567890123456789"


@pytest.fixture
def small_setup(dataset_factory, config_factory, sample_channel_rows):
    dataset = dataset_factory(sample_channel_rows)
    config_factory(dataset)
    return dataset


def refresh(run_cli, *extra: str) -> tuple[int, str, str]:
    return run_cli(["refresh", "payment", "channel", *extra])


def listing(run_cli, *extra: str) -> tuple[int, str, str]:
    return run_cli(["payment", "channel", "list", *extra])


def test_cli_exposes_version(run_cli):
    with pytest.raises(SystemExit) as caught:
        run_cli(["--version"])
    assert caught.value.code == 0


def test_cache_miss_is_explicit(
    run_cli, dataset_factory, config_factory, sample_channel_rows, envelope
):
    config_factory(dataset_factory(sample_channel_rows))
    code, out, _ = listing(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["data"] is None
    assert result["error"]["code"] == "CACHE_MISS"
    assert result["error"]["retryable"] is False
    assert "refresh" in result["error"]["message"]


def test_refresh_then_list_offline(run_cli, envelope, small_setup, tmp_path: Path):
    code, out, err = refresh(run_cli)
    assert code == 0
    assert "published 8 rows" in err
    result = envelope(out)
    assert result["error"] is None
    assert result["data"]["published"] is True
    assert result["data"]["row_count"] == 8
    meta = result["meta"]
    assert meta["backend"] == "snapshot"
    assert meta["simulated"] is True
    assert meta["complete"] is False
    assert meta["dataset_complete"] is True
    assert meta["scope"] == "EXTERNAL"
    assert meta["matched_total"] == 8
    cache_path = tmp_path / "cache.sqlite3"
    assert cache_path.is_file()
    assert cache_path.stat().st_mode & 0o777 == 0o600

    code, out, err = listing(run_cli)
    assert code == 0
    assert err == ""
    result = envelope(out)
    assert result["error"] is None
    rows = result["data"]
    assert len(rows) == 8
    assert [row["seqid"] for row in rows] == list(range(1, 9))
    meta = result["meta"]
    assert meta["source"] == "cache"
    assert meta["backend"] == "snapshot"
    assert meta["simulated"] is True
    assert meta["complete"] is False
    assert meta["dataset_complete"] is True
    assert meta["stale"] is False
    assert meta["matched_total"] == 8
    assert meta["returned_count"] == 8
    assert meta["has_more"] is False
    assert meta["dataset_id"] == meta["snapshot_id"]
    assert meta["fetched_at"] == meta["source_observed_from"]
    assert meta["source_observed_from"] is not None
    assert meta["loaded_at"] is not None


def test_refresh_rejects_missing_dataset(
    run_cli, envelope, config_factory, tmp_path: Path
):
    config_factory(tmp_path / "no-such-dataset")
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "SOURCE_DATA_MISSING"
    assert not (tmp_path / "cache.sqlite3").exists()
    code, out, _ = listing(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "SOURCE_DATA_MISSING"


def test_refresh_rejects_missing_dataset_file(run_cli, envelope, small_setup):
    (small_setup / "provenance.jsonl").unlink()
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "SOURCE_DATA_MISSING"


def test_corrupt_dataset_not_published_and_old_snapshot_kept(
    run_cli, envelope, small_setup
):
    assert refresh(run_cli)[0] == 0
    records = small_setup / "records.jsonl"
    with records.open("a") as stream:
        stream.write('{"seqid": 9, "payoutType": "EXTERNAL"}\n')
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "SOURCE_DATA_INVALID"
    code, out, _ = listing(run_cli)
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 8
    assert len(result["data"]) == 8


def test_first_failure_keeps_empty_cache(
    run_cli, envelope, dataset_factory, config_factory, sample_channel_rows
):
    dataset = dataset_factory(sample_channel_rows)
    (dataset / "records.jsonl").write_bytes(b"not-json\n")
    config_factory(dataset)
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "SOURCE_DATA_INVALID"
    code, out, _ = listing(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_MISS"


def test_configured_dataset_id_mismatch(
    run_cli, envelope, dataset_factory, config_factory, sample_channel_rows
):
    dataset = dataset_factory(sample_channel_rows)
    config_factory(dataset, dataset_id="f" * 64)
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "SOURCE_DATA_INVALID"

    config_factory(dataset)
    assert refresh(run_cli)[0] == 0
    config_factory(dataset, dataset_id="e" * 64)
    code, out, _ = listing(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["error"]["code"] == "CACHE_MISS"
    assert "refresh" in result["error"]["message"]


def test_quality_markers_stale_and_incomplete(
    run_cli, envelope, dataset_factory, config_factory, sample_channel_rows
):
    dataset = dataset_factory(
        sample_channel_rows, observed_at="2026-01-01T00:00:00+00:00"
    )
    config_factory(dataset, ttl_hours=0)
    assert refresh(run_cli)[0] == 0
    code, out, _ = listing(run_cli)
    assert code == 0
    meta = envelope(out)["meta"]
    assert meta["stale"] is True
    assert meta["complete"] is False
    assert meta["dataset_complete"] is True
    assert meta["fetched_at"] == "2026-01-01T00:00:00+00:00"

    code, out, _ = listing(run_cli, "--require-fresh")
    assert code == 1
    result = envelope(out)
    assert result["data"] is None
    assert result["error"]["code"] == "CACHE_STALE"

    code, out, _ = listing(run_cli, "--require-complete")
    assert code == 1
    assert envelope(out)["error"]["code"] == "INCOMPLETE_RESULT"


def test_reimport_does_not_extend_freshness(
    run_cli, envelope, dataset_factory, config_factory, sample_channel_rows
):
    dataset = dataset_factory(
        sample_channel_rows, observed_at="2026-01-01T00:00:00+00:00"
    )
    config_factory(dataset, ttl_hours=0)
    assert refresh(run_cli)[0] == 0
    first = envelope(listing(run_cli)[1])["meta"]
    assert refresh(run_cli)[0] == 0
    second = envelope(listing(run_cli)[1])["meta"]
    assert second["fetched_at"] == first["fetched_at"] == "2026-01-01T00:00:00+00:00"
    assert second["stale"] is True
    assert second["loaded_at"] >= first["loaded_at"]


def test_live_is_unavailable(run_cli, envelope, small_setup):
    assert refresh(run_cli)[0] == 0
    code, out, _ = listing(run_cli, "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "LIVE_SOURCE_UNAVAILABLE"


def test_non_external_scope_unavailable(run_cli, envelope, small_setup):
    assert refresh(run_cli)[0] == 0
    code, out, _ = listing(run_cli, "--payout-type", "LIQUIDITY")
    assert code == 1
    assert envelope(out)["error"]["code"] == "SOURCE_SCOPE_UNAVAILABLE"
    code, out, _ = refresh(run_cli, "--payout-type", "MANUAL")
    assert code == 1
    assert envelope(out)["error"]["code"] == "SOURCE_SCOPE_UNAVAILABLE"


def test_local_filters_exact_or_and(run_cli, envelope, small_setup):
    assert refresh(run_cli)[0] == 0

    code, out, _ = listing(run_cli, "--status", "ENABLE")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 4
    assert {row["status"] for row in result["data"]} == {"ENABLE"}

    code, out, _ = listing(
        run_cli, "--debit-currency", "USD", "--credit-currency", "CNY"
    )
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 2
    assert all(
        row["debitCurrency"] == "USD" and row["creditCurrency"] == "CNY"
        for row in result["data"]
    )

    code, out, _ = listing(
        run_cli, "--debit-currency", "EUR", "--debit-currency", "HKD"
    )
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 3
    assert {row["debitCurrency"] for row in result["data"]} == {"EUR", "HKD"}

    code, out, _ = listing(run_cli, "--financial-inst-id", "NOPE")
    assert code == 0
    result = envelope(out)
    assert result["data"] == []
    assert result["meta"]["matched_total"] == 0
    assert result["meta"]["has_more"] is False

    code, out, _ = listing(run_cli, "--debit-account-name", "ACCT-A")
    assert code == 0
    assert envelope(out)["meta"]["matched_total"] == 2


def test_display_pagination_and_fields(
    run_cli, envelope, dataset_factory, config_factory, bulk_channel_rows
):
    dataset = dataset_factory(bulk_channel_rows(205), name="bulk")
    config_factory(dataset)
    code, _, err = refresh(run_cli)
    assert code == 0
    assert "page 1/3" in err and "page 3/3" in err

    code, out, _ = listing(run_cli)
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 205
    assert result["meta"]["returned_count"] == 100
    assert result["meta"]["has_more"] is True
    assert [row["seqid"] for row in result["data"]] == list(range(1, 101))

    code, out, _ = listing(run_cli, "--limit", "5", "--offset", "5")
    assert code == 0
    result = envelope(out)
    assert [row["seqid"] for row in result["data"]] == [6, 7, 8, 9, 10]
    assert result["meta"]["has_more"] is True

    code, out, _ = listing(run_cli, "--all")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["returned_count"] == 205
    assert [row["seqid"] for row in result["data"]] == list(range(1, 206))

    code, out, _ = listing(run_cli, "--limit", "2", "--fields", "seqid,status")
    assert code == 0
    result = envelope(out)
    assert result["data"] == [
        {"seqid": 1, "status": "ENABLE"},
        {"seqid": 2, "status": "ENABLE"},
    ]
    assert result["meta"]["matched_total"] == 205


def test_argument_errors_exit_2(run_cli, envelope, small_setup):
    assert refresh(run_cli)[0] == 0
    for extra in (
        ["--all", "--limit", "5"],
        ["--all", "--offset", "1"],
        ["--limit", "0"],
        ["--limit", "-3"],
        ["--offset", "-1"],
        ["--fields", " , "],
    ):
        code, out, _ = listing(run_cli, *extra)
        assert code == 2, extra
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_unknown_scope_is_usage_error(run_cli, small_setup):
    with pytest.raises(SystemExit) as caught:
        listing(run_cli, "--payout-type", "OTHER")
    assert caught.value.code == 2


def test_decimal_precision_preserved(run_cli, small_setup):
    assert refresh(run_cli)[0] == 0
    code, out, _ = listing(run_cli, "--all")
    assert code == 0
    assert PRECISE_AMOUNT in out
    rows = json_decimal(out)["data"]
    amounts = {str(row["chargeAmount"]["amount"]) for row in rows}
    assert PRECISE_AMOUNT in amounts


def json_decimal(stdout: str) -> dict:
    import json

    return json.loads(stdout, parse_float=Decimal)


def test_records_keep_unknown_fields_and_versions(run_cli, envelope, small_setup):
    assert refresh(run_cli)[0] == 0
    code, out, _ = listing(run_cli, "--debit-account-name", "ACCT-A")
    assert code == 0
    rows = envelope(out)["data"]
    assert {row["configVersion"] for row in rows} == {"v1", "v2"}
    assert all("abilityId" in row and "chargeAmount" in row for row in rows)
