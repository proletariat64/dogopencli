"""Explicit Duckdog import of actual installed CLI envelopes, using fake CDP."""

import pytest
from integration.leaves.liquidity.test_risk_rules_cli import LEAVES, page, rows
from integration.leaves.liquidity.test_risk_rules_cli import installed as installed
from integration.leaves.liquidity.test_risk_rules_cli import (
    source_format as source_format,
)

from dogopencli.jsonutil import parse


def test_explicit_import_of_installed_live_json_full_readback(
    installed, settings_importer, tmp_path
):
    import duckdb

    leaf, cli, browser, config = installed
    identity = LEAVES[leaf][3]
    records = rows(identity)
    browser.business_script.append(page(leaf, records))
    live = cli(
        "liquidity", "list", leaf, "--live", "--limit", "0", "--require-complete"
    )
    selector = "liquidity/" + leaf.replace(".", "/")
    store = tmp_path / "explicit-import"
    assert not store.exists()
    result = settings_importer.publish(store, selector, settings_importer.encode(live))
    with duckdb.connect(result["database"], read_only=True) as db:
        values = db.execute(
            'SELECT _record FROM "' + result["relation"] + '" ORDER BY _row_order'
        ).fetchall()
        assert [parse(row[0]) for row in values] == records
        parquet = db.execute(
            "SELECT record FROM read_parquet(?) ORDER BY _row_order",
            [result["parquet"]],
        ).fetchall()
        assert [parse(row[0]) for row in parquet] == records
        metadata = parse(
            db.execute(
                "SELECT acquisition_metadata FROM _duckdog_datasets WHERE selector=?",
                [selector],
            ).fetchone()[0]
        )
        assert metadata["acquisition"] == live["meta"]
        assert metadata["command"] == [
            "dogopencli",
            "liquidity",
            "list",
            leaf,
            "--live",
            "--limit",
            "0",
            "--require-complete",
            "--format",
            "json",
        ]
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"
    # Cached and scoped candidates cannot replace an explicitly imported full live list.
    for field, bad in [
        ("source", "temporary-cache"),
        ("query", {"currency": ["USD"]}),
        ("operation", "get"),
        ("dataset_complete", False),
    ]:
        rejected = {**live, "meta": {**live["meta"], field: bad}}
        with pytest.raises(settings_importer.ImportRejected):
            settings_importer.publish(
                store, selector, settings_importer.encode(rejected)
            )
    with duckdb.connect(result["database"], read_only=True) as db:
        assert [
            parse(row[0])
            for row in db.execute(
                'SELECT _record FROM "' + result["relation"] + '" ORDER BY _row_order'
            ).fetchall()
        ] == records
