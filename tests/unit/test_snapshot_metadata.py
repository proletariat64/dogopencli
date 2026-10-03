"""Inspection error and publication boundaries of the metadata report."""

import argparse
import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from dogopencli.cache import Cache, SnapshotMeta, namespace
from dogopencli.config import Config
from dogopencli.plugins.liquidity import details, leaves, spec, store
from dogopencli.snapshot import bindings, build_report


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


@pytest.mark.parametrize(
    "ttl", [float("inf"), float("nan"), 1e100, "private-invalid-policy"]
)
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


def test_absent_policy_preserves_capture_quality(configured, monkeypatch, run_cli):
    at = datetime.now(timezone.utc).isoformat()
    name = namespace("payment.cost.list", "scope", "cdp")
    meta = SnapshotMeta(
        name,
        "payment.cost.list",
        "scope",
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
        0,
    )
    Cache(configured).publish(meta, [])
    monkeypatch.setattr(
        "dogopencli.snapshot.config.load", lambda _: Config(configured, None, {})
    )
    code, out, err = run_cli(
        ["snapshot", "payment", "cost", "list", "--format", "json"]
    )
    report = json.loads(out)
    assert code == 0 and err == ""
    assert report["inspection_complete"] is True
    assert report["tree"]["cache"]["freshness"] is None
    assert report["tree"]["cache"]["complete"] is True
    assert report["tree"]["rows"] == 0


@pytest.mark.parametrize("route", ["public", "catalog", "handler"])
def test_snapshot_dispatch_preserves_selected_path(configured, capsys, route):
    from dogopencli import cli
    from dogopencli.catalog import NODES

    tokens = ["payment", "cost", "list", "--format", "json"]
    if route == "public":
        code = cli.main(["snapshot", *tokens])
    elif route == "catalog":
        code = cli._execute(NODES[("snapshot",)], ["snapshot", *tokens], {0})
    else:
        code = cli.cmd_snapshot(argparse.Namespace(path=tokens[:3], format="json"))
    out, err = capsys.readouterr()
    assert code == 0 and err == ""
    assert json.loads(out)["tree"]["command"] == "dogopencli payment cost list"


def test_legacy_refresh_ownership_does_not_depend_on_help_links(monkeypatch):
    from dogopencli.catalog import NODES

    for path in (
        ("refresh", "payment", "channel"),
        ("refresh", "payment", "cost"),
        ("refresh", "payment", "sla"),
    ):
        original = bindings()[path]
        monkeypatch.setitem(NODES, path, replace(NODES[path], next=()))
        assert bindings()[path] is original
