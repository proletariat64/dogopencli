"""Corrupted cache rows cannot become usable partial Payment results."""

import sqlite3
from datetime import datetime, timezone

import pytest

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.jsonutil import canonical
from dogopencli.result_policy import AcquisitionEvidence
from dogopencli.temporary_query import publish_candidate
from dogopencli.temporary_query import query_namespace as namespace

CASES = (
    ("channel", "payment.channel.list", "EXTERNAL", ("payment", "channel", "list")),
    (
        "cost",
        "payment.cost.list",
        "FUND_OUT_CHANNEL_TRANS_FEE",
        ("payment", "cost", "list"),
    ),
    (
        "sla",
        "payment.sla.baselines.list",
        "baselines",
        ("payment", "sla", "baselines", "list"),
    ),
)


@pytest.mark.parametrize("kind,capability,scope,path", CASES)
def test_malformed_acquisition_metadata_is_a_safe_cache_diagnostic(
    run_cli, envelope, tmp_path, monkeypatch, kind, capability, scope, path
):
    cache_path = publish(
        tmp_path, monkeypatch, kind, capability, scope, records(kind, scope)
    )
    with sqlite3.connect(cache_path) as connection:
        connection.execute(
            "UPDATE snapshots SET acquisition = ?", ("BROKEN-PRIVATE-METADATA",)
        )
    before = cache_path.read_bytes()
    code, out, err = run_cli(list(path))
    assert code == 1
    result = envelope(out)
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert "acquisition" in result["error"]["message"]
    assert "BROKEN-PRIVATE" not in out + err
    assert cache_path.read_bytes() == before


def records(kind, scope):
    if kind == "channel":
        return [
            {"seqid": i, "abilityId": i, "payoutType": scope, "configVersion": "v1"}
            for i in (1, 2)
        ]
    if kind == "cost":
        return [{"itemId": str(i), "itemType": scope} for i in (1, 2)]
    return [{"id": str(i)} for i in (1, 2)]


def publish(tmp_path, monkeypatch, kind, capability, scope, rows):
    cache_path = tmp_path / "cache.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[cache]\npath = "{cache_path}"\n[sources.payment_{kind}]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config_path))
    now = datetime.now(timezone.utc).isoformat()
    snapshot = SnapshotMeta(
        namespace=namespace(capability, scope, "cdp"),
        capability=capability,
        scope=scope,
        source_kind="cdp",
        snapshot_id="synthetic",
        dataset_id=None,
        simulated=False,
        backend_complete=False,
        dataset_complete=True,
        fetched_at=now,
        loaded_at=now,
        source_observed_from=None,
        source_observed_to=None,
        row_count=len(rows),
    )
    publish_candidate(
        Cache(cache_path),
        snapshot,
        [(i, canonical(row)) for i, row in enumerate(rows, 1)],
    )
    return cache_path


@pytest.mark.parametrize("kind,capability,scope,path", CASES)
@pytest.mark.parametrize(
    "corruption",
    ["missing", "malformed_json", "shape", "identity", "scope_or_pair", "seqid_gap"],
)
def test_whole_cache_rejected_before_list_window_or_get_selection(
    run_cli,
    envelope,
    tmp_path,
    monkeypatch,
    kind,
    capability,
    scope,
    path,
    corruption,
):
    rows = records(kind, scope)
    cache_path = publish(tmp_path, monkeypatch, kind, capability, scope, rows)
    with sqlite3.connect(cache_path) as connection:
        if corruption == "missing":
            connection.execute("DELETE FROM records WHERE seqid = 2")
        elif corruption == "seqid_gap":
            connection.execute("UPDATE records SET seqid = 3 WHERE seqid = 2")
        else:
            if corruption == "malformed_json":
                body = "BROKEN-PRIVATE-RESPONSE"
            elif corruption == "shape":
                body = "null"
            elif corruption == "identity":
                if kind == "channel":
                    rows[1]["seqid"] = 1
                elif kind == "cost":
                    rows[1]["itemId"] = "1"
                else:
                    rows[1] = rows[0]
                body = canonical(rows[1])
            else:
                if kind == "channel":
                    rows[1]["payoutType"] = "WRONG"
                elif kind == "cost":
                    rows[1]["itemType"] = "WRONG"
                else:
                    rows[1]["id"] = ""
                body = canonical(rows[1])
            connection.execute("UPDATE records SET body = ? WHERE seqid = 2", (body,))
    before = cache_path.read_bytes()
    flags = ("--limit", "1") if path[-1] == "list" else ()
    code, out, err = run_cli([*path, *flags])
    assert code == 1
    result = envelope(out)
    assert result["data"] is None
    assert result["error"]["code"] in ("INVALID_RESPONSE", "INCOMPLETE_RESULT")
    assert "BROKEN-PRIVATE" not in out + err
    assert cache_path.read_bytes() == before


def test_channel_identical_occurrences_with_distinct_local_seqids_remain_valid(
    run_cli,
    envelope,
    tmp_path,
    monkeypatch,
):
    kind, capability, scope, path = CASES[0]
    rows = records(kind, scope)
    rows[1] = {**rows[0], "seqid": 2}
    cache_path = publish(tmp_path, monkeypatch, kind, capability, scope, rows)
    before = cache_path.read_bytes()
    code, out, err = run_cli([*path, "--limit", "0"])
    assert code == 0
    result = envelope(out)
    assert result["data"] == rows
    assert result["meta"]["complete"] is False
    assert "INCOMPLETE_RESULT" in err
    assert cache_path.read_bytes() == before


@pytest.mark.parametrize("kind,capability,scope,path", CASES)
def test_acquisition_contradicting_snapshot_flags_is_corruption(
    run_cli,
    envelope,
    tmp_path,
    monkeypatch,
    kind,
    capability,
    scope,
    path,
):
    rows = records(kind, scope)
    cache_path = publish(tmp_path, monkeypatch, kind, capability, scope, rows)
    evidence = AcquisitionEvidence(
        scope_complete=True,
        dataset_complete=True,
        collected_total=len(rows),
    )
    with sqlite3.connect(cache_path) as connection:
        connection.execute(
            "UPDATE snapshots SET acquisition = ?",
            (canonical(evidence.record()),),
        )
    before = cache_path.read_bytes()
    for flags in ((), ("--require-complete",)):
        code, out, _ = run_cli([*path, *flags])
        assert code == 1
        result = envelope(out)
        assert result["data"] is None
        assert result["error"]["code"] == "INVALID_RESPONSE"
    assert cache_path.read_bytes() == before
