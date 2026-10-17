"""Explicit Duckdog import of actual installed CLI envelopes, using fake CDP."""

from pathlib import Path

import pytest
from integration.test_migration_b02 import LEAVES, page, rows
from integration.test_migration_b02 import installed as installed

from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def importer(tmp_path):
    import importlib.util
    import shutil
    import subprocess

    source = (
        tmp_path / "helper/.agents/skills/duckdog-import/scripts/import_settings.py"
    )
    source.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "tests/fixtures/duckdog/import_settings.py", source)
    patches = [
        "migration-b01-duckdog-import.patch",
        "migration-b02-duckdog-import.patch",
    ]
    for patch in patches:
        result = subprocess.run(
            ["patch", "--batch", "-p1", "-i", str(ROOT / "scripts/patches" / patch)],
            cwd=tmp_path / "helper",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    spec = importlib.util.spec_from_file_location("b02_external_importer", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_explicit_import_of_installed_live_json_full_readback(
    installed, importer, tmp_path
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
    result = importer.publish(store, selector, importer.encode(live))
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
        with pytest.raises(importer.ImportRejected):
            importer.publish(store, selector, importer.encode(rejected))
    with duckdb.connect(result["database"], read_only=True) as db:
        assert [
            parse(row[0])
            for row in db.execute(
                'SELECT _record FROM "' + result["relation"] + '" ORDER BY _row_order'
            ).fetchall()
        ] == records
