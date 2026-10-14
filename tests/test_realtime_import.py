import importlib.util
from pathlib import Path

import duckdb


def test_identical_detail_stored_once(tmp_path):
    path = Path(__file__).parents[1] / "scripts/duckdog/import_realtime.py"
    spec = importlib.util.spec_from_file_location("realtime_import", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner = module.load_owner(
        Path(__file__).parent / "fixtures/duckdog/import_settings.py"
    )
    row = {
        "id": 1,
        "version": 2,
        "_detail": {"version": 2, "id": 1},
        "_detail_meta": {
            "capability": "liquidity.network.realtime.get",
            "source": "live",
            "simulated": False,
            "complete": True,
            "returned_count": 1,
            "identity": {"network_id": "1"},
            "request_scope": {},
            "fetched_at": "2026-01-01T00:00:00+00:00",
        },
    }
    meta = {
        "capability": "liquidity.network.realtime.list",
        "source": "live",
        "simulated": False,
        "complete": True,
        "has_more": False,
        "scope": {},
        "query": {},
        "returned_count": 1,
        "matched_total": 1,
        "collected_total": 1,
        "reported_total": 1,
        "fetched_at": "2026-01-01T00:00:00+00:00",
    }
    result = module.publish(
        tmp_path, owner.encode({"data": [row], "meta": meta}), owner
    )
    with duckdb.connect(result["database"]) as db:
        record = db.execute(
            "SELECT _record FROM liquidity_network_realtime"
        ).fetchone()[0]
        assert '"_detail":' not in record
        assert '"state":"record"' in record
        assert '"_detail_meta":' in record
        assert (
            db.execute(
                "SELECT record FROM read_parquet(?)", [result["parquet"]]
            ).fetchone()[0]
            == record
        )


def fixture_importer():
    spec = importlib.util.spec_from_file_location(
        "realtime_import",
        Path(__file__).parents[1] / "scripts/duckdog/import_realtime.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner = module.load_owner(
        Path(__file__).parent / "fixtures/duckdog/import_settings.py"
    )
    return module, owner


def candidate(owner, root=None, detail=None, stamp="2026-01-01T00:00:00+00:00"):
    root = root or {"id": 1, "version": 2}
    detail = root.copy() if detail is None else detail
    dm = {
        "capability": "liquidity.network.realtime.get",
        "source": "live",
        "simulated": False,
        "complete": True,
        "returned_count": 1,
        "identity": {"network_id": "1"},
        "request_scope": {},
        "fetched_at": stamp,
    }
    row = dict(root, _detail=detail, _detail_meta=dm)
    meta = {
        "capability": "liquidity.network.realtime.list",
        "source": "live",
        "simulated": False,
        "complete": True,
        "has_more": False,
        "scope": {},
        "query": {},
        "returned_count": 1,
        "matched_total": 1,
        "collected_total": 1,
        "reported_total": 1,
        "fetched_at": stamp,
    }
    return {"data": [row], "meta": meta}


def read(result):
    import decimal
    import json

    with duckdb.connect(result["database"]) as db:
        view = db.execute("SELECT _record FROM liquidity_network_realtime").fetchone()[
            0
        ]
        parquet = db.execute(
            "SELECT record FROM read_parquet(?)", [result["parquet"]]
        ).fetchone()[0]
        assert view == parquet
    return json.loads(view, parse_float=decimal.Decimal)


def test_structural_differences_preserved(tmp_path):
    import decimal

    module, owner = fixture_importer()
    cases = [
        (1, "1"),
        (None, ""),
        (0, False),
        ([1, 2], [2, 1]),
        ({"x": None}, {}),
        ({"x": 2}, {"x": 3}),
        (
            decimal.Decimal("1.00000000000000000001"),
            decimal.Decimal("1.00000000000000000002"),
        ),
    ]
    for index, (left, right) in enumerate(cases):
        root, detail = {"id": 1, "value": left}, {"id": 1, "value": right}
        result = module.publish(
            tmp_path / str(index), owner.encode(candidate(owner, root, detail)), owner
        )
        stored = read(result)
        assert stored["_detail_storage"]["state"] == "full"
        assert module.effective_detail(stored) == detail
    value = candidate(owner, {"id": 1, "version": 2}, {"id": 1, "version": 3})
    assert (
        read(module.publish(tmp_path / "version", owner.encode(value), owner))[
            "_detail"
        ]["version"]
        == 3
    )


def test_b02_associations_and_partial_metadata_survive(tmp_path):
    module, owner = fixture_importer()
    for index, associations in enumerate(
        (
            {
                "operationHistory": [{"id": 2, "version": 1}],
                "routeDetails": {"dynamicQuotas": [], "staticQuotas": []},
            },
            {"operationHistory": [], "routeDetails": None},
            {"operationHistory": None, "routeDetails": None},
        )
    ):
        value = candidate(owner)
        row = value["data"][0]
        row["_detail"].update(associations)
        row["_detail_meta"].update(
            complete=False,
            components={
                "network": {
                    "status": "succeeded",
                    "complete": True,
                    "identity": {"id": 1},
                    "request_scope": {"id": 1},
                    "native_contract": "realtime-network-detail-v1",
                },
                "operationHistory": {
                    "status": "succeeded",
                    "complete": False,
                    "reasons": ["HISTORY_COVERAGE_UNPROVEN"],
                    "request_scope": {"fundAction": "TRANSFER"},
                },
                "routeDetails": {
                    "status": "inapplicable",
                    "complete": True,
                    "returned_count": 0,
                },
            },
        )
        stored = read(module.publish(tmp_path / str(index), owner.encode(value), owner))
        assert stored["_detail_storage"]["state"] == "record"
        assert stored["_detail"] == associations
        assert stored["_detail_meta"] == row["_detail_meta"]
        assert module.effective_detail(stored) == row["_detail"]


def test_absent_unknown_representation_and_legacy(tmp_path):
    module, owner = fixture_importer()
    value = candidate(owner)
    value["data"] = [{"id": 1}]
    stored = read(module.publish(tmp_path / "absent", owner.encode(value), owner))
    assert stored["_detail_storage"]["state"] == "absent"
    assert module.effective_detail(stored) is None
    value = candidate(owner)
    value["data"][0]["_detail"].update(operationHistory=[], unknown={"preserve": True})
    stored = read(module.publish(tmp_path / "unknown", owner.encode(value), owner))
    assert stored["_detail_storage"]["state"] == "full"
    assert stored["_detail"]["unknown"] == {"preserve": True}
    assert module.effective_detail(value["data"][0]) == value["data"][0]["_detail"]


def test_validation_and_failure_preserve_history(tmp_path, monkeypatch):
    import pytest

    module, owner = fixture_importer()
    original = module.publish(tmp_path, owner.encode(candidate(owner)), owner)
    old = Path(original["parquet"])
    snapshot = old.read_bytes()
    for mutate in (
        lambda row: row["_detail"].update(id="1"),
        lambda row: row["_detail_meta"].update(source="cache"),
        lambda row: row["_detail_meta"].update(identity={"network_id": "2"}),
        lambda row: row["_detail_meta"].update(tenant="other"),
        lambda row: row.update(_detail=None),
    ):
        value = candidate(owner, stamp="2026-01-02T00:00:00+00:00")
        mutate(value["data"][0])
        with pytest.raises((ValueError, owner.ImportRejected)):
            module.publish(tmp_path, owner.encode(value), owner)
        assert old.read_bytes() == snapshot
        assert read(original)["_detail_storage"]["state"] == "record"
    value = candidate(
        owner, detail={"id": 1, "version": 3}, stamp="2026-01-02T00:00:00+00:00"
    )
    # Publication verification failure occurs after candidate Parquet and view staging.
    original_connect = duckdb.connect

    class Connection:
        def __init__(self, db):
            self.db = db

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.db.close()

        def execute(self, sql, *args):
            if sql.startswith("SELECT parquet_path, content_sha256, row_count"):
                raise RuntimeError("injected publication failure")
            return self.db.execute(sql, *args)

    monkeypatch.setattr(
        duckdb, "connect", lambda *a, **kw: Connection(original_connect(*a, **kw))
    )
    with pytest.raises(RuntimeError, match="injected"):
        module.publish(tmp_path, owner.encode(value), owner)
    monkeypatch.setattr(duckdb, "connect", original_connect)
    assert old.read_bytes() == snapshot
    assert len(list(old.parent.glob("*.parquet"))) == 1
    assert read(original)["version"] == 2
    newer = module.publish(tmp_path, owner.encode(value), owner)
    assert old.read_bytes() == snapshot
    assert len(list(old.parent.glob("*.parquet"))) == 2
    assert read(newer)["_detail"]["version"] == 3


def test_live_mode_and_unrelated_selector(tmp_path):
    import subprocess

    module, owner = fixture_importer()
    value = candidate(owner)
    row = value["data"][0]
    detail, meta = row.pop("_detail"), row.pop("_detail_meta")

    def run(command, **kwargs):
        assert command == [
            "dogopencli",
            "liquidity",
            "network",
            "realtime",
            "get",
            "--network-id",
            "1",
            "--format",
            "json",
        ]
        return subprocess.CompletedProcess(
            command, 0, owner.encode({"data": detail, "meta": meta})
        )

    stored = read(
        module.publish(tmp_path, module.acquire(owner.encode(value), owner, run), owner)
    )
    assert stored["_detail_storage"]["state"] == "record"
    unrelated = candidate(owner)
    unrelated["data"] = [{"bankId": "SYNTHETIC", "value": None}]
    unrelated["meta"]["capability"] = "liquidity.reference.banks.list"
    result = owner.publish(
        tmp_path, "liquidity/reference/banks", owner.encode(unrelated)
    )
    with duckdb.connect(result["database"]) as db:
        assert db.execute("SELECT _record FROM liquidity_reference_banks").fetchone()[
            0
        ] == owner.encode(unrelated["data"][0])


def test_public_saved_input_command_and_invalid_json(tmp_path):
    import subprocess
    import sys

    import pytest

    module, owner = fixture_importer()
    source = tmp_path / "saved.json"
    source.write_text(owner.encode(candidate(owner)))
    command = [
        sys.executable,
        str(Path(__file__).parents[1] / "scripts/duckdog/import_realtime.py"),
        "--settings-importer",
        str(Path(__file__).parent / "fixtures/duckdog/import_settings.py"),
        "--root",
        str(tmp_path / "store"),
        "--input",
        str(source),
    ]
    result = subprocess.run(command, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert '"rows": 1' in result.stdout
    for text in (
        owner.encode(candidate(owner)).replace('"version":2', '"version":NaN'),
        owner.encode(candidate(owner)).replace('"id":1', '"id":1,"id":2'),
    ):
        with pytest.raises(ValueError):
            module.publish(tmp_path / "rejected", text, owner)
        assert not (tmp_path / "rejected").exists()
