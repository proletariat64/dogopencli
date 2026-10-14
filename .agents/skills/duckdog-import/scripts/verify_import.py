"""Verify settings publication in isolated temporary storage; no live calls."""

import decimal
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import duckdb
from import_settings import ImportRejected, encode, publish

SELECTOR = "liquidity/reference/entities"
RELATION = "liquidity_reference_entities"


def envelope(rows, captured="2026-10-14T00:00:00+00:00"):
    return {
        "data": rows,
        "error": None,
        "meta": {
            "capability": "liquidity.reference.entities.list",
            "source": "live",
            "simulated": False,
            "complete": True,
            "has_more": False,
            "scope": {},
            "query": {},
            "fetched_at": captured,
            **{
                key: len(rows)
                for key in (
                    "returned_count",
                    "matched_total",
                    "collected_total",
                    "reported_total",
                )
            },
        },
    }


class SettingsImportChecks(unittest.TestCase):
    def test_retired_import_modes_refuse_without_creating_storage(self):
        resources = (
            "factors",
            "factor-values",
            "cost-prices",
            "strategies",
            "client-prices",
            "fee-orders",
        )
        for resource in resources:
            for saved_input in (False, True):
                with self.subTest(resource=resource, saved_input=saved_input):
                    command = [
                        sys.executable,
                        str(Path(__file__).with_name("import_settings.py")),
                        "--root",
                        str(self.root),
                        "--selector",
                        "liquidity/pricing/" + resource,
                    ]
                    if saved_input:
                        command.extend(
                            ["--input", str(self.root / "missing-input.json")]
                        )
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        env={**os.environ, "PATH": ""},
                    )
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertEqual(result.stdout, "")
                    error = json.loads(result.stderr)
                    self.assertEqual(error["code"], "UNSUPPORTED_CAPABILITY")
                    self.assertIn("retired", error["message"])
                    self.assertFalse(error["published"])
                    self.assertFalse(self.root.exists())

    def test_retired_pricing_publication_preserves_existing_dataset(self):
        self.write()
        before = {
            p.relative_to(self.root): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        for selector in ("liquidity/pricing/factors", "liquidity/pricing/strategies"):
            with self.subTest(selector=selector):
                candidate = envelope([{"code": "SYNTHETIC", "id": "SYNTHETIC"}])
                candidate["meta"]["capability"] = selector.replace("/", ".") + ".list"
                with self.assertRaisesRegex(ImportRejected, "retired.*#164"):
                    publish(self.root, selector, encode(candidate))
                after = {
                    p.relative_to(self.root): p.read_bytes()
                    for p in self.root.rglob("*")
                    if p.is_file()
                }
                self.assertEqual(before, after)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "dataset"
        self.row = {
            "id": 9007199254740993,
            "instId": "NATIVE_A",
            "instCode": "CODE",
            "state": "VALID",
            "unknown": {"nested": [None, "", 0]},
            "amount": decimal.Decimal("12345678901234567890.123456789012345678"),
        }

    def write(self, rows=None, captured="2026-10-14T00:00:00+00:00"):
        return publish(
            self.root,
            SELECTOR,
            encode(envelope([self.row] if rows is None else rows, captured)),
        )

    def read(self):
        with duckdb.connect(
            str(self.root / "duckdb/duckdog.duckdb"), read_only=True
        ) as db:
            return db.execute(
                f"SELECT _record::VARCHAR, instId FROM {RELATION} ORDER BY _row_order"
            ).fetchall()

    def test_precision_unknown_nested_and_id_preserved(self):
        self.write()
        raw, native = self.read()[0]
        recovered = json.loads(raw, parse_float=decimal.Decimal)
        self.assertEqual(recovered, self.row)
        self.assertEqual(native, "NATIVE_A")

    def test_repeat_replace_empty_and_one_generation(self):
        first = self.write()
        repeated = self.write()
        self.assertEqual(first["parquet"], repeated["parquet"])
        replacement = dict(self.row, id=2, instId="NATIVE_B")
        self.write([replacement], "2026-10-14T01:00:00+00:00")
        self.assertEqual(self.read()[0][1], "NATIVE_B")
        self.assertFalse(Path(first["parquet"]).exists())
        self.write([], "2026-10-14T02:00:00+00:00")
        self.assertEqual(self.read(), [])
        self.assertEqual(
            len(list((self.root / "parquet" / SELECTOR).glob("*.parquet"))), 1
        )

    def test_bad_quality_scope_source_counts_and_identity_preserve(self):
        self.write()
        original = self.read()
        changes = (
            {"complete": False},
            {"source": "cache"},
            {"simulated": True},
            {"has_more": True},
            {"scope": {"entity": "NATIVE_A"}},
            {"returned_count": 0},
            {"capability": "wrong.leaf"},
        )
        for change in changes:
            bad = envelope([self.row])
            bad["meta"].update(change)
            with self.subTest(change=change), self.assertRaises(ImportRejected):
                publish(self.root, SELECTOR, encode(bad))
            self.assertEqual(self.read(), original)
        with self.assertRaises(ImportRejected):
            self.write([self.row, self.row])
        self.assertEqual(self.read(), original)

    def test_older_or_conflicting_capture_preserve(self):
        self.write()
        with self.assertRaises(ImportRejected):
            self.write([], "2026-10-13T00:00:00+00:00")
        with self.assertRaises(ImportRejected):
            self.write([])
        self.assertEqual(len(self.read()), 1)

    def test_duplicate_instcode_kept_and_banks_independent(self):
        second = dict(self.row, id=2, instId="NATIVE_B")
        self.write([self.row, second])
        self.assertEqual(len(self.read()), 2)
        banks = envelope([{"bankId": "BANK", "other": [1, 2]}])
        banks["meta"]["capability"] = "liquidity.reference.banks.list"
        publish(self.root, "liquidity/reference/banks", encode(banks))
        self.assertEqual(len(self.read()), 2)
        with duckdb.connect(
            str(self.root / "duckdb/duckdog.duckdb"), read_only=True
        ) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM _duckdog_datasets").fetchone()[0], 2
            )

    def test_compound_identity_and_default_scope(self):
        selector = "liquidity/ledger/customers"
        rows = [{"customerNo": "A", "version": 1}, {"customerNo": "A", "version": 2}]
        data = envelope(rows)
        data["meta"]["capability"] = selector.replace("/", ".") + ".list"
        publish(self.root, selector, encode(data))
        data["data"][1]["version"] = 1
        with self.assertRaises(ImportRejected):
            publish(self.root, selector, encode(data))
        data = envelope([{"id": "GROUP"}])
        data["meta"]["capability"] = "liquidity.cash.groups.list"
        data["meta"]["scope"] = {"equiCurrency": "USD"}
        data["meta"]["query"] = {"equiCurrency": "USD"}
        publish(self.root, "liquidity/cash/groups", encode(data))
        data["meta"]["scope"]["groupCode"] = "FILTERED"
        with self.assertRaises(ImportRejected):
            publish(self.root, "liquidity/cash/groups", encode(data))

    def test_transaction_failure_rolls_back_view_and_metadata(self):
        first = self.write()
        original = self.read()
        connect = duckdb.connect

        class FailingConnection:
            def __init__(self, *args, **kwargs):
                self.connection = connect(*args, **kwargs)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.connection.close()

            def execute(self, sql, *args):
                if sql.startswith("INSERT OR REPLACE INTO _duckdog_datasets"):
                    raise RuntimeError("injected publication failure")
                return self.connection.execute(sql, *args)

        with mock.patch.object(duckdb, "connect", FailingConnection):
            with self.assertRaises(RuntimeError):
                self.write(
                    [dict(self.row, id=2, instId="NATIVE_B")],
                    "2026-10-14T01:00:00+00:00",
                )
        self.assertEqual(self.read(), original)
        self.assertTrue(Path(first["parquet"]).exists())
        self.assertEqual(
            len(list((self.root / "parquet" / SELECTOR).glob("*.parquet"))), 1
        )


if __name__ == "__main__":
    unittest.main()
