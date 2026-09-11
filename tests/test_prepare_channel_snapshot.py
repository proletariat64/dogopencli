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
            self.assertTrue(result["dataset_complete"])
            self.assertFalse(result["source_pages_complete"])
            self.assertTrue(
                all(not s["source_pages_complete"] for s in result["sources"])
            )
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

    def test_source_page_accounting_is_independent_of_mock_completeness(self):
        for case in ("complete", "failed", "missing", "short", "changed_total"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = self.export(root, "source", [{"payoutType": "EXTERNAL"}])
                path = source / "manifest.json"
                manifest = json.loads(path.read_text())
                manifest["summary"].update(failed_pages=[], reported_totals=[1])
                if case == "failed":
                    manifest["summary"]["failed_pages"] = [2]
                elif case == "missing":
                    manifest["pages"][0]["page"] = 2
                elif case == "short":
                    manifest["summary"]["reported_totals"] = [2]
                elif case == "changed_total":
                    manifest["summary"]["reported_totals"] = [1, 2]
                path.write_text(json.dumps(manifest))
                result = MODULE.prepare([source], root / "out")
                self.assertEqual(result["source_pages_complete"], case == "complete")
                self.assertTrue(result["dataset_complete"])
                self.assertFalse(result["backend_complete"])

    def test_duplicate_page_numbers_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.export(root, "source", [{"payoutType": "EXTERNAL"}])
            path = source / "manifest.json"
            manifest = json.loads(path.read_text())
            manifest["pages"].append(
                {"page": 1, "outcome": "failure", "rows_observed": 0}
            )
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                MODULE.prepare([source], root / "out")
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

    def test_non_object_row_main_returns_safe_error(self):
        import contextlib
        import io
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.export(root, "source", [{"payoutType": "EXTERNAL"}])
            (source / "records.jsonl").write_text('"PRIVATE-ROW"\n')
            output = io.StringIO()
            with (
                patch(
                    "sys.argv", ["prepare", str(source), "--output", str(root / "out")]
                ),
                contextlib.redirect_stdout(output),
            ):
                code = MODULE.main()
            self.assertEqual(code, 1)
            self.assertEqual(
                json.loads(output.getvalue())["error"], "SOURCE_PREPARATION_FAILED"
            )
            self.assertNotIn("PRIVATE-ROW", output.getvalue())
            self.assertFalse((root / "out").exists())

    def test_bad_manifest_accounting_is_rejected(self):
        for change in ("scope", "count", "range"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = self.export(root, "source", [{"payoutType": "EXTERNAL"}])
                path = source / "manifest.json"
                manifest = json.loads(path.read_text())
                if change == "scope":
                    manifest["summary"]["scope"] = "LIQUIDITY"
                elif change == "count":
                    manifest["summary"]["exported_rows"] = 99
                else:
                    manifest["pages"][0]["seqid_end"] = 99
                path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    MODULE.prepare([source], root / "out")
                self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()
