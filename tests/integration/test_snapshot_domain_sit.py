"""Temporary-slot metadata acceptance through the public snapshot CLI."""

import json
from datetime import datetime, timezone

import pytest

from dogopencli.cache import Cache, SnapshotMeta, namespace
from dogopencli.jsonutil import canonical
from dogopencli.result_policy import AcquisitionEvidence
from dogopencli.temporary_query import publish_slot


@pytest.fixture
def cache_setup(tmp_path, monkeypatch):
    path = tmp_path / "cache.sqlite3"
    config = tmp_path / "config.toml"
    config.write_text(f'[cache]\npath = "{path}"\nttl_hours = 72\n')
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    monkeypatch.delenv("DOGOPENCLI_CONFIG_DIR", raising=False)
    return Cache(path), path


def inspect(run_cli, *path):
    code, out, err = run_cli(["snapshot", *path, "--format", "json"])
    assert code == 0, err
    return json.loads(out)["tree"]


def publish(cache, leaf, rows, *, variant="daily", complete=False):
    evidence = AcquisitionEvidence(
        scope_complete=complete,
        dataset_complete=complete,
        collected_total=len(rows),
        reported_total=len(rows),
        arrivals=len(rows),
        reasons=() if complete else ("IDENTITY_UNPROVEN",),
    )
    return publish_slot(
        cache,
        leaf,
        rows,
        capability=leaf + ".list",
        scope={"entity": "PRIVATE-ENTITY"},
        evidence=evidence,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        variant=variant,
    )


def test_saved_daily_variant_and_partial_quality_survive_inspection(
    run_cli, cache_setup
):
    cache, path = cache_setup
    publish(cache, "liquidity.cash.balances", [{"PRIVATE-ROW": "1.2345"}])
    before = path.read_bytes()
    leaf = inspect(run_cli, "liquidity", "cash", "balances", "list")
    assert leaf["rows"] == 1
    assert leaf["cache"]["complete"] is False
    slot = leaf["cache"]["slots"][0]
    assert slot["contract_variant"] == "daily"
    assert slot["reasons"] == ["IDENTITY_UNPROVEN"]
    assert "PRIVATE-" not in canonical(leaf)
    assert "retained_coverage" not in slot
    assert "gaps" not in slot
    assert path.read_bytes() == before


def test_other_scope_and_variant_replace_same_inspected_slot(run_cli, cache_setup):
    cache, _ = cache_setup
    publish(cache, "liquidity.cash.balances", [{"id": "old"}], variant="latest")
    publish(cache, "liquidity.cash.balances", [{"id": "new"}, {"id": "new2"}])
    leaf = inspect(run_cli, "liquidity", "cash", "balances", "list")
    assert leaf["rows"] == 2
    assert len(leaf["cache"]["slots"]) == 1
    assert leaf["cache"]["slots"][0]["contract_variant"] == "daily"


def test_legacy_cache_names_are_not_reported_as_current_slots(run_cli, cache_setup):
    cache, path = cache_setup
    at = datetime.now(timezone.utc).isoformat()
    meta = SnapshotMeta(
        namespace=namespace("payment.cost.list", "old", "cdp"),
        capability="payment.cost.list",
        scope="old",
        source_kind="cdp",
        snapshot_id="old",
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at=at,
        loaded_at=at,
        source_observed_from=None,
        source_observed_to=None,
        row_count=1,
    )
    cache.publish(meta, [(1, canonical({"id": "PRIVATE-OLD"}))])
    before = path.read_bytes()
    leaf = inspect(run_cli, "payment", "cost", "list")
    assert leaf["cache"]["status"] == "missing"
    assert leaf["rows"] is None
    assert path.read_bytes() == before


def test_get_inspection_never_reads_list_slot(run_cli, cache_setup):
    cache, _ = cache_setup
    publish(cache, "collection.va.rules", [{"vaRuleId": "PRIVATE-VA"}])
    leaf = inspect(run_cli, "collection", "va", "rules", "get")
    assert leaf["cache"]["status"] == "not_applicable"
    assert leaf["rows"] is None
