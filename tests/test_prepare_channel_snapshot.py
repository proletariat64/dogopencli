"""Synthetic offline checks; no production rows or CDP access."""

import importlib.util
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "prepare_channel_snapshot",
    Path(__file__).resolve().parents[1] / "scripts/prepare_channel_snapshot.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrepareSnapshotTests(unittest.TestCase):
    def test_explicit_repository_tmp_is_allowed(self):
        repo = Path(__file__).resolve().parents[1]
        (repo / "tmp").mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=repo / "tmp") as temp:
            root = Path(temp)
            source = self.export(root, "source", [{"payoutType": "EXTERNAL"}])
            result = MODULE.prepare([source], root / "dataset")
            self.assertEqual(result["row_count"], 1)
        with self.assertRaises(ValueError):
            MODULE.prepare([], repo / "docs" / "forbidden-data")

    def export(self, root: Path, name: str, rows: list[dict]) -> Path:
        directory = root / name
        directory.mkdir()
        data = [{"seqid": i, **r} for i, r in enumerate(rows, 1)]
        (directory / "records.jsonl").write_text(
            "\n".join(MODULE.canonical(r) for r in data) + "\n"
        )
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "summary": {
                        "scope": "EXTERNAL",
                        "observed_at": "2026-09-09T00:00:00+00:00",
                        "exported_rows": len(rows),
                        "page_size": 10,
                        "failed_pages": [2],
                        "reported_totals": [20],
                    },
                    "pages": [
                        {
                            "page": 1,
                            "outcome": "success",
                            "rows_observed": len(rows),
                            "seqid_start": 1,
                            "seqid_end": len(rows),
                        }
                    ],
                }
            )
        )
        return directory

    def test_union_preserves_versions_precision_and_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            row = {
                "payoutType": "EXTERNAL",
                "abilityId": 1,
                "configVersion": "1",
                "value": Decimal("0.1234567890123456789"),
            }
            a = self.export(root, "a", [row, row])
            b = self.export(root, "b", [row, {**row, "configVersion": "2"}])
            result = MODULE.prepare([a, b, a], root / "out")
            other = MODULE.prepare([b, a], root / "other")
            self.assertEqual(result["dataset_id"], other["dataset_id"])
            self.assertEqual((result["input_rows"], result["row_count"]), (4, 2))
            self.assertFalse(result["backend_complete"])
            records = [
                json.loads(l, parse_float=Decimal)
                for l in (root / "out/records.jsonl").read_text().splitlines()
            ]
            self.assertEqual([r["seqid"] for r in records], [1, 2])
            self.assertEqual({r["configVersion"] for r in records}, {"1", "2"})
            self.assertTrue(all(r["value"] == row["value"] for r in records))
            refs = [
                json.loads(l)
                for l in (root / "out/provenance.jsonl").read_text().splitlines()
            ]
            self.assertEqual(sum(len(r["observations"]) for r in refs), 4)

    def test_reject_bad_input_without_publishing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = self.export(root, "a", [{"payoutType": "OTHER"}])
            with self.assertRaises(ValueError):
                MODULE.prepare([a], root / "out")
            self.assertFalse((root / "out").exists())

    def test_missing_input_cannot_be_reconstructed_from_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(FileNotFoundError):
                MODULE.prepare([root / "missing"], root / "out")
            self.assertFalse((root / "out").exists())

    def test_existing_dataset_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "out").mkdir()
            with self.assertRaises(ValueError):
                MODULE.prepare([], root / "out")


if __name__ == "__main__":
    unittest.main()
