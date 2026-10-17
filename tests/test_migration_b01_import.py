"""Apply the bounded external importer patch and verify current leaf envelopes."""

import importlib.util
import json
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
SELECTORS = {
    "liquidity/reference/banks": "bankId",
    "liquidity/investment/benchmarks": "id",
    "liquidity/rules/forecast": "ruleId",
}


@pytest.fixture
def importer(tmp_path):
    source = tmp_path / ".agents/skills/duckdog-import/scripts/import_settings.py"
    source.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "tests/fixtures/duckdog/import_settings.py", source)
    patch = ROOT / "scripts/patches/migration-b01-duckdog-import.patch"
    result = subprocess.run(
        ["patch", "--batch", "-p1", "-i", str(patch)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    spec = importlib.util.spec_from_file_location("b01_external_importer", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate(selector):
    return {
        "data": [
            {
                SELECTORS[selector]: "rule-1",
                "value": Decimal("0.12345678901234567890123456789"),
                "unknown": {"zero": 0, "empty": "", "null": None},
            }
        ],
        "error": None,
        "meta": {
            "leaf": selector.replace("/", "."),
            "operation": "list",
            "source": "live",
            "backend": "cdp",
            "simulated": False,
            "complete": True,
            "dataset_complete": True,
            "has_more": False,
            "scope": "",
            "query": {},
            "returned_count": 1,
            "matched_total": 1,
            "collected_total": 1,
            "reported_total": 1,
            "unique_count": 1,
            "duplicate_count": 0,
            "fetched_at": "2026-10-17T12:00:00+08:00",
            "contract_id": "a" * 64,
            "acquisition": {
                "scope_complete": True,
                "dataset_complete": True,
                "reported_total": 1,
                "collected_total": 1,
                "arrivals": 1,
                "unique_count": 1,
                "duplicate_count": 0,
                "total_semantics": "unique_objects",
                "reasons": [],
                "attempts": [],
            },
        },
    }


@pytest.mark.parametrize("selector", SELECTORS)
def test_current_leaf_import_preserves_exact_records_and_metadata(
    importer, tmp_path, selector
):
    envelope = candidate(selector)
    result = importer.publish(tmp_path / "store", selector, importer.encode(envelope))
    with duckdb.connect(result["database"], read_only=True) as db:
        rows = db.execute(
            'SELECT _record FROM "' + result["relation"] + '" ORDER BY _row_order'
        ).fetchall()
        assert [json.loads(row[0], parse_float=Decimal) for row in rows] == envelope[
            "data"
        ]
        raw_meta = db.execute(
            "SELECT acquisition_metadata FROM _duckdog_datasets WHERE selector=?",
            [selector],
        ).fetchone()[0]
        stored = json.loads(raw_meta, parse_float=Decimal)
        assert stored["acquisition"] == envelope["meta"]
        assert stored["command"] == [
            "dogopencli",
            "liquidity",
            "list",
            selector.removeprefix("liquidity/").replace("/", "."),
            "--live",
            "--limit",
            "0",
            "--require-complete",
            "--format",
            "json",
        ]


@pytest.mark.parametrize("selector", SELECTORS)
@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "temporary-cache"),
        ("backend", "mock"),
        ("simulated", True),
        ("complete", False),
        ("dataset_complete", False),
        ("has_more", True),
        ("scope", {}),
        ("scope", "Z21"),
        ("query", {"country": ["US"]}),
        ("query", {"limit": 1}),
        ("leaf", "liquidity.reference.entities"),
        ("operation", "get"),
        ("operation", "refresh"),
        ("capability", "liquidity.rules.forecast.list"),
        ("returned_count", 0),
        ("matched_total", 2),
        ("collected_total", True),
        ("reported_total", "1"),
        ("unique_count", 0),
        ("duplicate_count", True),
        ("acquisition", {}),
    ],
)
def test_b01_import_rejects_invalid_metadata_before_storage(
    importer, tmp_path, selector, field, value
):
    envelope = candidate(selector)
    envelope["meta"][field] = value
    root = tmp_path / "store"
    with pytest.raises(importer.ImportRejected):
        importer.publish(root, selector, importer.encode(envelope))
    assert not root.exists()


@pytest.mark.parametrize("selector", SELECTORS)
@pytest.mark.parametrize(
    "field,value",
    [
        ("scope_complete", False),
        ("dataset_complete", False),
        ("total_semantics", "arrivals"),
        ("reasons", ["DUPLICATES"]),
        ("reported_total", 0),
        ("collected_total", 2),
        ("arrivals", True),
        ("unique_count", "1"),
        ("duplicate_count", 1),
    ],
)
def test_b01_import_rejects_contradictory_acquisition(
    importer, tmp_path, selector, field, value
):
    envelope = candidate(selector)
    envelope["meta"]["acquisition"][field] = value
    with pytest.raises(importer.ImportRejected):
        importer.publish(tmp_path / "store", selector, importer.encode(envelope))
    assert not (tmp_path / "store").exists()


def test_b01_cached_candidate_preserves_previous_dataset(importer, tmp_path):
    selector = "liquidity/rules/forecast"
    envelope = candidate(selector)
    root = tmp_path / "store"
    result = importer.publish(root, selector, importer.encode(envelope))
    envelope["meta"]["source"] = "temporary-cache"
    envelope["data"][0]["value"] = "unexpected"
    with pytest.raises(importer.ImportRejected):
        importer.publish(root, selector, importer.encode(envelope))
    with duckdb.connect(result["database"], read_only=True) as db:
        assert db.execute("SELECT _record FROM liquidity_rules_forecast").fetchone()[
            0
        ] == importer.encode(candidate(selector)["data"][0])
    assert len(list((root / "parquet" / selector).glob("*.parquet"))) == 1


def test_current_non_b01_leaf_is_not_implicitly_supported(importer, tmp_path):
    envelope = candidate("liquidity/reference/banks")
    envelope["meta"]["leaf"] = "liquidity.reference.entities"
    envelope["data"] = [{"id": "one", "instId": "one"}]
    with pytest.raises(importer.ImportRejected):
        importer.publish(
            tmp_path / "store",
            "liquidity/reference/entities",
            importer.encode(envelope),
        )
    assert not (tmp_path / "store").exists()


def test_native_identity_json_types_remain_distinct(importer):
    selector = "liquidity/investment/benchmarks"
    envelope = candidate(selector)
    envelope["data"] = [{"id": 0}, {"id": "0"}]
    for document in (envelope["meta"], envelope["meta"]["acquisition"]):
        for key in (
            "returned_count",
            "matched_total",
            "collected_total",
            "reported_total",
            "unique_count",
            "arrivals",
        ):
            if key in document:
                document[key] = 2
    assert importer.validate(importer.encode(envelope), selector)[0] == envelope["data"]


@pytest.mark.parametrize("selector", SELECTORS)
def test_b01_live_acquisition_uses_current_public_command(
    importer, tmp_path, monkeypatch, capsys, selector
):
    envelope = candidate(selector)
    commands = []

    def acquire(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, importer.encode(envelope), "")

    monkeypatch.setattr(importer.subprocess, "run", acquire)
    monkeypatch.setattr(
        "sys.argv",
        [
            "import_settings.py",
            "--selector",
            selector,
            "--root",
            str(tmp_path / "store"),
        ],
    )
    assert importer.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["rows"] == 1
    assert commands == [
        [
            "dogopencli",
            "liquidity",
            "list",
            selector.removeprefix("liquidity/").replace("/", "."),
            "--live",
            "--limit",
            "0",
            "--require-complete",
            "--format",
            "json",
        ]
    ]
