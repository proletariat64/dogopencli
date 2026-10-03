"""Snapshot inventories published domain storage without running inquiries."""

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Thread

import pytest

from dogopencli.cache import Cache, SnapshotMeta, namespace
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical
from dogopencli.plugins.collection.va_rule import COLLECTION_VA_RULES
from dogopencli.plugins.liquidity import details, leaves, store
from dogopencli.plugins.liquidity.capability import encode_scope
from dogopencli.result_policy import AcquisitionEvidence


@pytest.fixture
def domain_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "cache.sqlite3"
    config = tmp_path / "config.toml"
    config.write_text(
        "[cache]\n"
        f'path = "{path}"\n'
        "ttl_hours = 72\n"
        '[sources.liquidity]\nkind = "cdp"\n'
        '[sources.collection_va_rules]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    return Cache(path)


def snapshot(run_cli, *path):
    code, out, err = run_cli(["snapshot", *path, "--format", "json"])
    assert code == 0, err
    report = json.loads(out)
    assert report["inspection_complete"] is True
    return report["tree"], out


def publish_capture(cache, spec, rows, at, *, window=(None, None), scope="", cap=100):
    plan = store.plan_capture_publish(
        cache, spec, scope, window, rows, len(rows), at, at, cap=cap
    )
    store.commit_plan(cache, spec.name, plan, at)
    return plan


def test_history_counts_all_retained_versions_and_excludes_orphans(
    domain_cache, run_cli
):
    spec = leaves.CASH_WATERLEVELS
    scope = encode_scope({"aliasNameList": ["private-account-72819"]})
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    rows = [{"aliasName": "private-account-72819", "currency": "USD"}]
    first = publish_capture(domain_cache, spec, rows, old, scope=scope)
    publish_capture(domain_cache, spec, rows, new, scope=scope)
    # An unpublished capture namespace is not a recognized acquisition.
    orphan = replace(
        first.capture_meta,
        namespace="unpublished-private-72819",
        row_count=3,
        acquisition=None,
    )
    domain_cache.publish(
        orphan, [(i, canonical({"secret": "token-72819"})) for i in range(3)]
    )
    leaf, out = snapshot(run_cli, "liquidity", "cash", "waterlevels", "list")
    assert leaf["rows"] == 2
    assert leaf["updated"] == new
    assert leaf["cache"]["oldest_updated"] == old
    assert leaf["cache"]["status"] == "mixed"
    captures = leaf["cache"]["captures"]
    assert len(captures) == 2
    assert {c["freshness"] for c in captures} == {"fresh", "stale"}
    assert {c["variant"] for c in captures} == {"history"}
    assert len({c["capture_id"] for c in captures}) == 2
    assert all(c["complete"] is True for c in captures)
    assert "private-account-72819" not in out
    assert "token-72819" not in out
    assert "unpublished-private-72819" not in out


@pytest.mark.parametrize("start", ["20260831", "20260901"])
def test_dated_retention_keeps_holes_and_distinguishes_acquisition_quality(
    domain_cache, run_cli, start
):
    spec = leaves.CASH_STATEMENTS_INTRADAY
    old = "2026-10-01T00:00:00+00:00"
    new = "2026-10-02T00:00:00+00:00"
    scope = encode_scope({"bankAccountAliasName": ["private-alias-58219"]})
    publish_capture(
        domain_cache,
        spec,
        [
            {"bankTransNo": "old-a", "valueDate": "20260901"},
            {"bankTransNo": "old-b", "valueDate": "20260902"},
        ],
        old,
        window=(start, "20260903"),
        scope=scope,
        cap=2,
    )
    publish_capture(
        domain_cache,
        spec,
        [{"bankTransNo": "new-a", "valueDate": "20260902"}],
        new,
        window=("20260902", "20260902"),
        scope=scope,
        cap=2,
    )
    leaf, out = snapshot(run_cli, "liquidity", "cash", "statements", "intraday", "list")
    assert leaf["rows"] == 2
    captures = {c["updated"]: c for c in leaf["cache"]["captures"]}
    retained = captures[old]
    assert retained["source_complete"] is True
    assert retained["dataset_complete"] is True
    assert retained["complete"] is False
    assert "RETENTION_GAP" in retained["reasons"]
    assert retained["gaps"] == (["20260901"] if start == "20260831" else [])
    assert retained["retained_coverage"]["from"] == (
        start if start == "20260831" else "20260902"
    )
    assert retained["retained_coverage"]["requested_from"] == start
    assert retained["retained_coverage"]["to"] == "20260903"
    assert captures[new]["complete"] is True
    assert leaf["cache"]["status"] == "mixed"
    assert "private-alias-58219" not in out


@pytest.mark.parametrize(
    "path", [("operations", "forwards", "get"), ("operations", "decisions", "history")]
)
def test_native_detail_and_history_count_documents_not_nested_entries(
    domain_cache, run_cli, path
):
    spec = leaves.detail_leaf(path).spec
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    key = details.contract_detail_key(spec, {"id": "secret-object-92718"})
    document = {"members": [{"secret": "hidden-business-92718"}] * 17}
    if path[-1] == "history":
        document = [document] * 12
    details.upsert_detail(domain_cache, spec.name, key, document, old, old)
    key2 = details.contract_detail_key(spec, {"id": "secret-object-57219"})
    details.upsert_detail(domain_cache, spec.name, key2, document, new, new)
    leaf, out = snapshot(run_cli, "liquidity", *path)
    assert leaf["rows"] == 2
    assert leaf["updated"] == new
    assert leaf["cache"]["oldest_updated"] == old
    assert leaf["cache"]["status"] == "mixed"
    assert len(leaf["cache"]["captures"]) == 2
    assert all(
        c["rows"] == 1 and c["variant"] == "native_document"
        for c in leaf["cache"]["captures"]
    )
    assert "secret-object" not in out and "hidden-business" not in out
    list_leaf, _ = snapshot(run_cli, "liquidity", *path[:-1], "list")
    expected = "not_applicable" if path[-1] == "history" else "missing"
    assert list_leaf["cache"]["status"] == expected


def test_collection_refused_details_preserve_source_and_dataset_distinction(
    domain_cache, run_cli
):
    cap = COLLECTION_VA_RULES
    at = datetime.now(timezone.utc).isoformat()
    evidence = replace(
        AcquisitionEvidence.for_collection(
            complete=True, reported_total=2, collected_total=2
        ),
        dataset_complete=False,
        reasons=("DETAIL_REFUSED",),
    )
    meta = SnapshotMeta(
        namespace(cap.name, cap.default_scope, "cdp"),
        cap.name,
        cap.default_scope,
        "cdp",
        "synthetic-va-generation",
        None,
        False,
        True,
        False,
        at,
        at,
        "2020-01-01T00:00:00+00:00",
        "2020-01-02T00:00:00+00:00",
        2,
        acquisition=evidence.record(),
    )
    domain_cache.publish(
        meta,
        [
            (1, canonical({"rule": {"vaRuleId": "private-va-81821"}, "detail": None})),
            (
                2,
                canonical(
                    {
                        "rule": {"vaRuleId": "private-va-92912"},
                        "detail": {"members": [1, 2, 3]},
                    }
                ),
            ),
        ],
    )
    listed, out = snapshot(run_cli, "collection", "va", "rules", "list")
    assert listed["rows"] == 2
    capture = listed["cache"]["captures"][0]
    assert capture["source_complete"] is True
    assert capture["dataset_complete"] is False
    assert capture["complete"] is False
    assert capture["freshness"] == "fresh"
    assert capture["source_observed_from"] == meta.source_observed_from
    assert capture["source_observed_to"] == meta.source_observed_to
    assert capture["updated"] == at
    assert "DETAIL_REFUSED" in capture["reasons"]
    assert "private-va" not in out
    detail, _ = snapshot(run_cli, "collection", "va", "rules", "get")
    assert detail["rows"] == 1
    assert detail["cache"]["complete"] is False
    assert "DETAIL_COVERAGE_GAP" in detail["reason"]


def test_snapshot_uses_one_sqlite_view_during_atomic_capture_publication(
    domain_cache, run_cli, monkeypatch
):
    spec = leaves.CASH_WATERLEVELS
    old = "2026-10-01T00:00:00+00:00"
    new = "2026-10-02T00:00:00+00:00"
    first = publish_capture(
        domain_cache, spec, [{"aliasName": "a", "currency": "USD"}], old
    )
    plan = store.plan_capture_publish(
        domain_cache,
        spec,
        "",
        (None, None),
        [{"aliasName": str(i), "currency": "USD"} for i in range(3)],
        3,
        new,
        new,
    )
    connect = sqlite3.connect
    publications = []
    writer_errors = []

    def publish():
        try:
            store.commit_plan(domain_cache, spec.name, plan, new)
        except BaseException as error:
            writer_errors.append(error)

    def traced_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        if "mode=ro" in str(args[0]):

            def trace(sql):
                if "FROM snapshots" in sql and not publications:
                    publications.append(True)
                    writer = Thread(target=publish)
                    writer.start()
                    writer.join(timeout=10)
                    assert not writer.is_alive(), (
                        "atomic writer blocked by snapshot reader"
                    )

            connection.set_trace_callback(trace)
        return connection

    monkeypatch.setattr(sqlite3, "connect", traced_connect)
    leaf, _ = snapshot(run_cli, "liquidity", "cash", "waterlevels", "list")
    assert publications and not writer_errors
    assert (leaf["rows"], leaf["updated"]) == (1, old)
    assert leaf["cache"]["captures"][0]["rows"] == first.capture_meta.row_count
    after, _ = snapshot(run_cli, "liquidity", "cash", "waterlevels", "list")
    assert (after["rows"], after["updated"]) == (4, new)


@pytest.mark.parametrize("mismatch", ["evidence", "snapshot_count"])
def test_snapshot_rejects_inconsistent_published_acquisition(
    domain_cache, run_cli, mismatch
):
    # History may retain fewer records than it acquired, but its index and
    # capture must still publish identical evidence. Snapshot profiles cannot
    # trim the acquisition even when both evidence records agree.
    spec = leaves.CASH_WATERLEVELS
    if mismatch == "snapshot_count":
        spec = next(
            leaf.variants[0]
            for leaf in leaves.LIST_LEAVES.values()
            if leaf.variants[0].profile == "snapshot" and len(leaf.variants) == 1
        )
    at = datetime.now(timezone.utc).isoformat()
    plan = publish_capture(domain_cache, spec, [{"aliasName": "private-alias"}], at)
    altered = AcquisitionEvidence.for_collection(
        complete=True, reported_total=2, collected_total=2, has_identity=True
    ).record()
    with sqlite3.connect(domain_cache._path) as connection:
        index_name = store.index_namespace(spec.name)
        seqid, body = connection.execute(
            "SELECT seqid, body FROM records WHERE namespace = ?"
            " AND json_extract(body, '$.type') = 'capture'",
            (index_name,),
        ).fetchone()
        record = json.loads(body)
        record["acquisition"] = altered
        connection.execute(
            "UPDATE records SET body = ? WHERE namespace = ? AND seqid = ?",
            (canonical(record), index_name, seqid),
        )
        if mismatch == "snapshot_count":
            connection.execute(
                "UPDATE snapshots SET acquisition = ? WHERE namespace = ?",
                (canonical(altered), plan.capture_meta.namespace),
            )
    entry = store.read_index(domain_cache, spec.name).captures[0]
    with pytest.raises(CliError, match="acquisition"):
        store.read_capture(domain_cache, entry)
    code, out, err = run_cli(
        ["snapshot", "liquidity", *spec.path, "list", "--format", "json"]
    )
    report = json.loads(out)
    assert code == 1
    assert report["inspection_complete"] is False
    assert report["tree"]["cache"]["status"] == "read_error"
    assert report["tree"]["rows"] is None
    assert "private-alias" not in out + err
