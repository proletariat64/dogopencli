"""Inspection error and publication boundaries of the metadata report."""

import argparse
import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from dogopencli.cache import Cache
from dogopencli.config import Config
from dogopencli.result_policy import AcquisitionEvidence
from dogopencli.snapshot import bindings, build_report
from dogopencli.temporary_query import publish_slot


@pytest.fixture
def configured(tmp_path, monkeypatch):
    path = tmp_path / "cache.sqlite3"
    monkeypatch.setattr(
        "dogopencli.snapshot.config.load", lambda _: Config(path, 72, {})
    )
    return path


def publish_list(path):
    at = datetime.now(timezone.utc).isoformat()
    evidence = AcquisitionEvidence(
        scope_complete=True,
        dataset_complete=True,
        collected_total=1,
        reported_total=1,
        arrivals=1,
    )
    meta = publish_slot(
        Cache(path),
        "payment.cost",
        [{"id": "private-row"}],
        capability="payment.cost.list",
        scope={"scope": "private-scope"},
        evidence=evidence,
        fetched_at=at,
    )
    return ("payment", "cost", "list"), meta


def test_unpublished_corrupt_slot_is_not_an_inspection_error(configured):
    command, meta = publish_list(configured)
    with sqlite3.connect(configured) as connection:
        connection.execute(
            "INSERT INTO snapshots SELECT namespace || '-orphan', capability, scope,"
            " source_kind, snapshot_id, dataset_id, simulated, backend_complete,"
            " dataset_complete, fetched_at, loaded_at, source_observed_from,"
            " source_observed_to, row_count, source_path, 'invalid json'"
            " FROM snapshots WHERE namespace = ?",
            (meta.namespace,),
        )
    result = build_report(command)
    assert result["inspection_complete"] is True
    assert result["tree"]["rows"] == 1


def test_acquisition_identifier_changes_with_published_generation(configured):
    command, meta = publish_list(configured)
    before = build_report(command)["tree"]["cache"]["slots"][0]["acquisition_id"]
    with sqlite3.connect(configured) as connection:
        connection.execute(
            "UPDATE snapshots SET snapshot_id = 'new-generation' WHERE namespace = ?",
            (meta.namespace,),
        )
    after = build_report(command)["tree"]["cache"]["slots"][0]["acquisition_id"]
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


def test_absent_policy_preserves_slot_quality(configured, monkeypatch, run_cli):
    publish_list(configured)
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
    assert report["tree"]["rows"] == 1


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
