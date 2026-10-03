"""Inspection error and publication boundaries of the metadata report."""

import sqlite3
from datetime import datetime, timezone

import pytest

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.config import Config
from dogopencli.plugins.liquidity import details, leaves, spec, store
from dogopencli.snapshot import build_report


@pytest.fixture
def configured(tmp_path, monkeypatch):
    path = tmp_path / "cache.sqlite3"
    monkeypatch.setattr(
        "dogopencli.snapshot.config.load", lambda _: Config(path, 72, {})
    )
    return path


def publish_list(path):
    leaf = next(
        leaf
        for leaf in leaves.LIST_LEAVES.values()
        if leaf.variants[0].profile == spec.PROFILE_SNAPSHOT and len(leaf.variants) == 1
    )
    declared = leaf.variants[0]
    at = datetime.now(timezone.utc).isoformat()
    plan = store.plan_capture_publish(
        Cache(path), declared, "private-scope", (None, None), [], 0, at, at
    )
    store.commit_plan(Cache(path), declared.name, plan, at)
    return ("liquidity", *leaf.path, "list"), declared, plan


def test_unpublished_corrupt_capture_is_not_an_inspection_error(configured):
    command, declared, _ = publish_list(configured)
    with sqlite3.connect(configured) as connection:
        connection.execute(
            "INSERT INTO snapshots SELECT namespace || '-orphan', capability, scope,"
            " source_kind, snapshot_id, dataset_id, simulated, backend_complete,"
            " dataset_complete, fetched_at, loaded_at, source_observed_from,"
            " source_observed_to, row_count, source_path, 'invalid json'"
            " FROM snapshots WHERE namespace = ?",
            (store.index_namespace(declared.name),),
        )
    result = build_report(command)
    assert result["inspection_complete"] is True
    assert result["tree"]["rows"] == 0


def test_capture_identifier_changes_with_published_generation(configured):
    command, _, plan = publish_list(configured)
    before = build_report(command)["tree"]["cache"]["captures"][0]["capture_id"]
    with sqlite3.connect(configured) as connection:
        # Change both publication records to keep their generation consistent.
        connection.execute(
            "UPDATE snapshots SET snapshot_id = 'new-generation' WHERE namespace = ?",
            (plan.capture_meta.namespace,),
        )
        connection.execute(
            "UPDATE records SET body = json_set(body, '$.snapshot_id',"
            " 'new-generation') WHERE json_extract(body, '$.type') = 'capture'"
        )
    after = build_report(command)["tree"]["cache"]["captures"][0]["capture_id"]
    assert before != after


@pytest.mark.parametrize("ttl", [float("inf"), float("nan"), 1e100])
def test_invalid_ttl_keeps_error_report(configured, monkeypatch, ttl):
    monkeypatch.setattr(
        "dogopencli.snapshot.config.load", lambda _: Config(configured, ttl, {})
    )
    result = build_report(("payment", "cost", "list"))
    assert result["inspection_complete"] is False
    assert result["inspection_errors"][0]["code"] == "CONFIG_ERROR"
    assert result["tree"]["cache"]["status"] == "read_error"


@pytest.mark.parametrize("payload", ["null", None])
def test_detail_envelope_requires_native_payload(configured, payload):
    leaf = next(iter(leaves.DETAIL_LEAVES.values()))
    at = datetime.now(timezone.utc).isoformat()
    name = details.details_namespace(leaf.spec.name)
    meta = SnapshotMeta(
        name,
        leaf.spec.name,
        "detail",
        "cdp",
        "id",
        None,
        False,
        True,
        True,
        at,
        at,
        None,
        None,
        1,
    )
    body = (
        '{"key":"private-account", "fetched_at":"'
        + at
        + '"'
        + (', "detail": null' if payload is not None else "")
        + "}"
    )
    Cache(configured).publish(meta, [(1, body)])
    result = build_report(("liquidity", *leaf.path))
    assert result["inspection_complete"] is False
    assert result["tree"]["cache"]["status"] == "read_error"
