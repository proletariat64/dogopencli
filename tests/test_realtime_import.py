import importlib.util
from pathlib import Path

import duckdb
import pytest


def test_newer_list_accepts_unchanged_numeric_detail_after_record_reconstruction(
    tmp_path,
):
    import copy
    from decimal import Decimal

    module, owner = fixture_importer()
    value = b02_candidate(owner)
    row = value["data"][0]
    row["singlePaymentLimit"] = {"maxAmount": {"amount": 1}}
    row["_detail"]["singlePaymentLimit"] = {"maxAmount": {"amount": Decimal("1.0")}}
    acquired = copy.deepcopy(row["_detail"])
    metadata = copy.deepcopy(row["_detail_meta"])
    first = module.publish(tmp_path, owner.encode(value), owner)
    assert read(first)["_detail_storage"]["state"] == "record"
    value["meta"]["fetched_at"] = "2026-01-02T00:00:00+00:00"
    row["singlePaymentLimit"]["maxAmount"]["amount"] = 2
    second = module.publish(tmp_path, owner.encode(value), owner)
    stored = read(second)
    assert stored["_detail_storage"]["state"] == "full"
    assert stored["singlePaymentLimit"]["maxAmount"]["amount"] == 2
    assert module.effective_detail(stored) == acquired
    assert stored["_detail_meta"] == metadata
    assert Path(first["parquet"]).exists()


@pytest.mark.parametrize(
    "difference", ["precision", "string", "boolean", "null", "absent", "array_order"]
)
def test_shared_numeric_equality_keeps_real_component_conflicts(tmp_path, difference):
    import copy
    from decimal import Decimal

    module, owner = fixture_importer()
    value = b02_candidate(owner)
    row = value["data"][0]
    row["singlePaymentLimit"] = {"maxAmount": {"amount": 1}, "schedule": [1, 2]}
    row["_detail"]["singlePaymentLimit"] = {
        "maxAmount": {"amount": Decimal("1.0")},
        "schedule": [1, 2],
    }
    first = module.publish(tmp_path, owner.encode(value), owner)
    before = Path(first["parquet"]).read_bytes()
    previous = read(first)
    changed = copy.deepcopy(value)
    changed["meta"]["fetched_at"] = "2026-01-02T00:00:00+00:00"
    changed["data"][0]["singlePaymentLimit"]["maxAmount"]["amount"] = 2
    limit = changed["data"][0]["_detail"]["singlePaymentLimit"]
    if difference == "absent":
        del limit["maxAmount"]["amount"]
    elif difference == "array_order":
        limit["schedule"] = [2, 1]
    else:
        limit["maxAmount"]["amount"] = {
            "precision": Decimal("1.0000000000000000000000000001"),
            "string": "1",
            "boolean": True,
            "null": None,
        }[difference]
    with pytest.raises(owner.ImportRejected, match="same component capture"):
        module.publish(tmp_path, owner.encode(changed), owner)
    assert read(first) == previous
    assert Path(first["parquet"]).read_bytes() == before
    assert list(Path(first["parquet"]).parent.glob("*.parquet")) == [
        Path(first["parquet"])
    ]


def test_same_list_numeric_representation_allows_fresh_detail(tmp_path):
    from decimal import Decimal

    module, owner = fixture_importer()
    value = b02_candidate(owner)
    row = value["data"][0]
    row["singlePaymentLimit"] = {"maxAmount": {"amount": 1}}
    row["_detail"]["singlePaymentLimit"] = {"maxAmount": {"amount": Decimal("1.0")}}
    first = module.publish(tmp_path, owner.encode(value), owner)
    row["singlePaymentLimit"]["maxAmount"]["amount"] = Decimal("1.0")
    row["_detail_meta"]["fetched_at"] = "2026-01-02T00:00:00+00:00"
    row["_detail_meta"]["components"]["network"]["captured_at"] = (
        "2026-01-02T00:00:00+00:00"
    )
    second = module.publish(tmp_path, owner.encode(value), owner)
    assert read(second)["_detail_storage"]["state"] == "record"
    assert second["fetched_at"] == first["fetched_at"]
    assert Path(first["parquet"]).exists()


@pytest.mark.parametrize("component", ["network", "operationHistory", "routeDetails"])
@pytest.mark.parametrize("conflict", ["older", "equal_changed"])
@pytest.mark.parametrize("new_list", [False, True])
def test_refresh_preserves_component_observations(
    tmp_path, component, conflict, new_list
):
    import copy

    module, owner = fixture_importer()
    initial = b02_candidate(owner)
    initial_meta = initial["data"][0]["_detail_meta"]
    initial_meta["fetched_at"] = "2026-01-02T00:00:00+00:00"
    for name, proof in initial_meta["components"].items():
        proof["captured_at"] = (
            "2026-01-02T00:00:00+00:00"
            if name == "network"
            else "2026-01-05T00:00:00+00:00"
        )
    published = module.publish(tmp_path, owner.encode(initial), owner)
    before = Path(published["parquet"]).read_bytes()
    registry_sql = (
        "SELECT selector, kind, relation_name, parquet_path, content_sha256, "
        "row_count, epoch(fetched_at), epoch(imported_at), acquisition_metadata "
        "FROM _duckdog_datasets"
    )
    with duckdb.connect(published["database"], read_only=True) as db:
        registry = db.execute(registry_sql).fetchall()
    refreshed = copy.deepcopy(initial)
    if new_list:
        refreshed["meta"]["fetched_at"] = "2026-01-02T12:00:00+00:00"
    row = refreshed["data"][0]
    meta = row["_detail_meta"]
    meta["fetched_at"] = "2026-01-03T00:00:00+00:00"
    meta["components"]["network"]["captured_at"] = meta["fetched_at"]
    proof = meta["components"][component]
    if conflict == "older":
        proof["captured_at"] = (
            "2026-01-01T00:00:00+00:00"
            if component == "network"
            else "2026-01-04T00:00:00+00:00"
        )
    else:
        proof["captured_at"] = initial_meta["components"][component]["captured_at"]
        if component == "network":
            row["_detail"]["version"] = 3
            proof["source_version"] = 3
        elif component == "operationHistory":
            row["_detail"][component][0]["version"] = 99
        else:
            row["_detail"][component]["staticQuotas"] = [{"quotaId": "NEW"}]
            proof["member_counts"]["staticQuotas"] = 1
    with pytest.raises(owner.ImportRejected):
        module.publish(tmp_path, owner.encode(refreshed), owner)
    assert Path(published["parquet"]).read_bytes() == before
    assert list(Path(published["parquet"]).parent.glob("*.parquet")) == [
        Path(published["parquet"])
    ]
    with duckdb.connect(published["database"], read_only=True) as db:
        assert db.execute(registry_sql).fetchall() == registry
    assert read(published)["_detail_meta"] == initial_meta


def test_component_refresh_allows_equal_payload_and_new_scopes(tmp_path):
    import copy

    module, owner = fixture_importer()
    initial = b02_candidate(owner)
    initial_meta = initial["data"][0]["_detail_meta"]
    initial_meta["fetched_at"] = "2026-01-02T00:00:00+00:00"
    for name, proof in initial_meta["components"].items():
        proof["captured_at"] = (
            "2026-01-02T00:00:00+00:00"
            if name == "network"
            else "2026-01-05T00:00:00+00:00"
        )
    first = module.publish(tmp_path, owner.encode(initial), owner)
    refreshed = copy.deepcopy(initial)
    meta = refreshed["data"][0]["_detail_meta"]
    meta["fetched_at"] = "2026-01-03T00:00:00+00:00"
    meta["components"]["network"]["captured_at"] = meta["fetched_at"]
    second = module.publish(tmp_path, owner.encode(refreshed), owner)
    assert (
        read(second)["_detail"]["operationHistory"]
        == initial["data"][0]["_detail"]["operationHistory"]
    )
    changed = copy.deepcopy(refreshed)
    row = changed["data"][0]
    row["_detail"].update(version=3, debitAliasName="NEW_DEBIT", routeId="NEW_ROUTE")
    meta = row["_detail_meta"]
    meta["fetched_at"] = "2026-01-04T00:00:00+00:00"
    meta["components"]["network"].update(
        captured_at=meta["fetched_at"], source_version=3
    )
    history = meta["components"]["operationHistory"]
    history["captured_at"] = "2026-01-04T12:00:00+00:00"
    history["request_scope"]["debitAliasName"] = ["NEW_DEBIT"]
    row["_detail"]["operationHistory"][0]["debitAliasName"] = "NEW_DEBIT"
    route = meta["components"]["routeDetails"]
    route["captured_at"] = "2026-01-04T12:00:00+00:00"
    for document in (
        route["identity"],
        route["request_scope"],
        row["_detail"]["routeDetails"],
    ):
        document.update(routeId="NEW_ROUTE", aliasName="NEW_DEBIT")
    third = module.publish(tmp_path, owner.encode(changed), owner)
    assert read(third)["_detail_storage"]["state"] == "full"
    assert module.effective_detail(read(third)) == row["_detail"]
    assert all(Path(result["parquet"]).exists() for result in (first, second, third))


def test_saved_list_refresh_orders_detail_without_changing_list_metadata(tmp_path):
    import copy
    import json
    import subprocess

    import pytest

    module, owner = fixture_importer()
    saved = candidate(owner)
    detail = saved["data"][0].pop("_detail")
    detail_meta = saved["data"][0].pop("_detail_meta")
    captures = iter(("2026-01-02T00:00:00+00:00", "2026-01-03T00:00:00+00:00"))

    def run(command, **kwargs):
        meta = dict(detail_meta, fetched_at=next(captures))
        return subprocess.CompletedProcess(
            command, 0, owner.encode({"data": detail, "meta": meta})
        )

    first_input = module.acquire(owner.encode(saved), owner, run)
    first = module.publish(tmp_path, first_input, owner)
    second_input = module.acquire(owner.encode(saved), owner, run)
    second = module.publish(tmp_path, second_input, owner)
    assert first["parquet"] != second["parquet"]
    assert Path(first["parquet"]).exists()
    assert read(second)["_detail_meta"]["fetched_at"] == "2026-01-03T00:00:00+00:00"
    with duckdb.connect(second["database"], read_only=True) as db:
        metadata, capture = db.execute(
            "SELECT acquisition_metadata, epoch(fetched_at) FROM _duckdog_datasets"
        ).fetchone()
    assert json.loads(metadata)["acquisition"] == saved["meta"]
    assert capture == 1767225600
    unchanged = module.publish(tmp_path, second_input, owner)
    assert unchanged["reused_content"] is True

    baseline = Path(second["parquet"]).read_bytes()
    generations = sorted(Path(second["parquet"]).parent.glob("*.parquet"))
    conflicting = json.loads(second_input)
    conflicting["data"][0]["_detail"]["version"] = 99
    older_list = copy.deepcopy(conflicting)
    older_list["meta"]["fetched_at"] = "2025-12-31T00:00:00+00:00"
    older_list["data"][0]["_detail_meta"]["fetched_at"] = "2026-01-04T00:00:00+00:00"
    changed_list = copy.deepcopy(older_list)
    changed_list["meta"] = saved["meta"].copy()
    changed_list["data"][0]["version"] = 99
    for text in (
        first_input,
        owner.encode(conflicting),
        owner.encode(older_list),
        owner.encode(changed_list),
    ):
        with pytest.raises(owner.ImportRejected):
            module.publish(tmp_path, text, owner)
        assert read(second)["_detail_meta"]["fetched_at"] == "2026-01-03T00:00:00+00:00"
        assert Path(second["parquet"]).read_bytes() == baseline
        assert sorted(Path(second["parquet"]).parent.glob("*.parquet")) == generations
        with duckdb.connect(second["database"], read_only=True) as db:
            assert db.execute(
                "SELECT acquisition_metadata, epoch(fetched_at) FROM _duckdog_datasets"
            ).fetchone() == (metadata, capture)


def test_detail_refresh_rejects_one_stale_member_despite_newer_batch_max(tmp_path):
    import copy

    import pytest

    module, owner = fixture_importer()
    value = candidate(owner)
    value["data"][0]["_detail_meta"]["fetched_at"] = "2026-01-02T00:00:00+00:00"
    other = copy.deepcopy(value["data"][0])
    other["id"] = other["_detail"]["id"] = "2"
    other["_detail_meta"]["identity"] = {"network_id": "2"}
    other["_detail_meta"]["fetched_at"] = "2026-01-03T00:00:00+00:00"
    value["data"].append(other)
    for key in ("returned_count", "matched_total", "collected_total", "reported_total"):
        value["meta"][key] = 2
    first = module.publish(tmp_path, owner.encode(value), owner)
    original = Path(first["parquet"]).read_bytes()
    value["data"][0]["_detail_meta"]["fetched_at"] = "2026-01-04T00:00:00+00:00"
    value["data"][1]["_detail_meta"]["fetched_at"] = "2026-01-02T00:00:00+00:00"
    with pytest.raises(owner.ImportRejected):
        module.publish(tmp_path, owner.encode(value), owner)
    assert Path(first["parquet"]).read_bytes() == original
    assert list(Path(first["parquet"]).parent.glob("*.parquet")) == [
        Path(first["parquet"])
    ]


def test_identical_detail_stored_once(tmp_path):
    path = Path(__file__).parents[1] / "scripts/duckdog/import_realtime.py"
    spec = importlib.util.spec_from_file_location("realtime_import", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner = module.load_owner(
        Path(__file__).parent / "fixtures/duckdog/import_settings.py"
    )
    row = {
        "id": "1",
        "version": 2,
        "_detail": {"version": 2, "id": "1"},
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
    root = root or {"id": "1", "version": 2}
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
        root, detail = {"id": "1", "value": left}, {"id": "1", "value": right}
        result = module.publish(
            tmp_path / str(index), owner.encode(candidate(owner, root, detail)), owner
        )
        stored = read(result)
        assert stored["_detail_storage"]["state"] == "full"
        assert module.effective_detail(stored) == detail
    value = candidate(owner, {"id": "1", "version": 2}, {"id": "1", "version": 3})
    assert (
        read(module.publish(tmp_path / "version", owner.encode(value), owner))[
            "_detail"
        ]["version"]
        == 3
    )


def test_b02_associations_and_partial_metadata_survive(tmp_path):
    module, owner = fixture_importer()
    for index in range(3):
        value = b02_candidate(owner, route=index == 0)
        row = value["data"][0]
        if index == 1:
            row["_detail"]["operationHistory"] = []
            row["_detail_meta"]["components"]["operationHistory"]["returned_count"] = 0
        elif index == 2:
            for document in (row, row["_detail"]):
                del document["scene"]
            row["_detail"]["operationHistory"] = None
            row["_detail_meta"]["components"]["operationHistory"] = {
                "status": "unverified",
                "applicability": "unverified",
                "identity": None,
                "request_scope": None,
                "native_contract": None,
                "captured_at": None,
                "returned_count": None,
                "reported_count": None,
                "count_unit": "history_record",
                "complete": False,
                "reasons": ["HISTORY_CONTEXT_UNVERIFIED"],
            }
        stored = read(module.publish(tmp_path / str(index), owner.encode(value), owner))
        associations = {
            key: row["_detail"][key] for key in ("operationHistory", "routeDetails")
        }
        assert stored["_detail_storage"]["state"] == "record"
        assert stored["_detail"] == associations
        assert stored["_detail_meta"] == row["_detail_meta"]
        assert module.effective_detail(stored) == row["_detail"]


def test_absent_unknown_representation_and_legacy(tmp_path):
    module, owner = fixture_importer()
    value = candidate(owner)
    value["data"] = [{"id": "1"}]
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
        lambda row: row["_detail"].update(id=1),
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
        owner, detail={"id": "1", "version": 3}, stamp="2026-01-02T00:00:00+00:00"
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
        owner.encode(candidate(owner)).replace('"id":"1"', '"id":"1","id":"2"'),
    ):
        with pytest.raises(ValueError):
            module.publish(tmp_path / "rejected", text, owner)
        assert not (tmp_path / "rejected").exists()


def b02_candidate(owner, *, route=True):
    from dogopencli.plugins.liquidity.spec import TENANT

    root = {
        "id": "1",
        "version": 2,
        "scene": "REALTIME",
        "fundAction": "TRANSFER",
        "creditAliasName": "CREDIT",
        "debitAliasName": "DEBIT",
        "routeId": "ROUTE" if route else None,
    }
    value = candidate(owner, root)
    row = value["data"][0]
    stamp = row["_detail_meta"]["fetched_at"]
    history = [{**root, "id": "2", "version": 1}]
    route_payload = (
        {
            "routeId": "ROUTE",
            "aliasName": "DEBIT",
            "tntInstId": TENANT,
            "dynamicQuotas": [],
            "staticQuotas": [],
        }
        if route
        else None
    )
    row["_detail"].update(operationHistory=history, routeDetails=route_payload)
    components = {
        "network": {
            "status": "succeeded",
            "applicability": "applicable",
            "identity": {"id": "1"},
            "request_scope": {"id": "1"},
            "native_contract": "realtime-network-detail-v1",
            "captured_at": stamp,
            "returned_count": 1,
            "reported_count": None,
            "count_unit": "network",
            "complete": True,
            "reasons": [],
            "source_version": 2,
        },
        "operationHistory": {
            "status": "succeeded",
            "applicability": "applicable",
            "identity": None,
            "request_scope": {
                "creditAliasName": ["CREDIT"],
                "debitAliasName": ["DEBIT"],
                "fundAction": "TRANSFER",
            },
            "native_contract": "realtime-network-history-v1",
            "captured_at": stamp,
            "returned_count": 1,
            "reported_count": None,
            "count_unit": "history_record",
            "complete": False,
            "reasons": ["HISTORY_COVERAGE_UNPROVEN"],
            "selected_root_relation": "not_present",
        },
        "routeDetails": {
            "status": "succeeded",
            "applicability": "applicable",
            "identity": {"routeId": "ROUTE", "aliasName": "DEBIT", "tntInstId": TENANT},
            "request_scope": {
                "routeId": "ROUTE",
                "aliasName": "DEBIT",
                "tntInstId": TENANT,
            },
            "native_contract": "route-quota-detail-v1",
            "captured_at": stamp,
            "returned_count": 1,
            "reported_count": None,
            "count_unit": "route_aggregate",
            "complete": True,
            "reasons": [],
            "member_counts": {"dynamicQuotas": 0, "staticQuotas": 0},
            "native_context_echo": {
                "routeId": "present",
                "aliasName": "present",
                "tntInstId": "present",
            },
        },
    }
    if not route:
        components["routeDetails"] = {
            "status": "inapplicable",
            "applicability": "inapplicable",
            "identity": None,
            "request_scope": None,
            "native_contract": None,
            "captured_at": None,
            "returned_count": None,
            "reported_count": None,
            "count_unit": None,
            "complete": True,
            "reasons": [],
        }
    row["_detail_meta"].update(complete=False, components=components)
    return value


def test_foreign_b02_association_scopes_and_invalid_acquisitions_rejected(tmp_path):
    import copy

    import pytest

    module, owner = fixture_importer()
    source = b02_candidate(owner)
    mutations = [
        lambda row: row["_detail_meta"]["components"]["operationHistory"][
            "request_scope"
        ].update(creditAliasName=["OTHER"]),
        lambda row: row["_detail"]["operationHistory"][0].update(fundAction="OTHER"),
        lambda row: row["_detail_meta"]["components"]["routeDetails"][
            "request_scope"
        ].update(routeId="OTHER"),
        lambda row: row["_detail"]["routeDetails"].update(aliasName="OTHER"),
        lambda row: row["_detail_meta"]["components"]["routeDetails"][
            "identity"
        ].update(tntInstId="OTHER"),
        lambda row: row["_detail"].update(routeDetails=None),
        lambda row: row["_detail_meta"]["components"]["operationHistory"].update(
            captured_at=None
        ),
        lambda row: row["_detail_meta"]["components"]["routeDetails"].update(
            returned_count=None
        ),
        lambda row: row["_detail"].update(tntInstId="OTHER"),
    ]
    for index, mutate in enumerate(mutations):
        value = copy.deepcopy(source)
        mutate(value["data"][0])
        root = tmp_path / str(index)
        with pytest.raises(ValueError):
            module.publish(root, owner.encode(value), owner)
        assert not root.exists()


def test_live_list_duplicate_json_keys_rejected_before_get(tmp_path):
    import pytest

    module, owner = fixture_importer()
    value = candidate(owner)
    value["data"] = [{"id": "1", "value": 1}]
    text = owner.encode(value).replace('"value":1', '"value":1,"value":2')
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        raise AssertionError("invalid saved list must not trigger acquisition")

    with pytest.raises(ValueError):
        module.acquire(text, owner, run)
    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_associations_bind_to_changed_acquired_root_and_unknown_versions_preserved(
    tmp_path,
):
    module, owner = fixture_importer()
    value = b02_candidate(owner)
    row = value["data"][0]
    row["_detail"].update(version=3, routeId="NEW_ROUTE", debitAliasName="NEW_DEBIT")
    components = row["_detail_meta"]["components"]
    components["network"]["source_version"] = 3
    components["operationHistory"]["request_scope"]["debitAliasName"] = ["NEW_DEBIT"]
    row["_detail"]["operationHistory"][0]["debitAliasName"] = "NEW_DEBIT"
    for document in (
        components["routeDetails"]["identity"],
        components["routeDetails"]["request_scope"],
        row["_detail"]["routeDetails"],
    ):
        document.update(routeId="NEW_ROUTE", aliasName="NEW_DEBIT")
    stored = read(module.publish(tmp_path / "changed", owner.encode(value), owner))
    assert stored["_detail_storage"]["state"] == "full"
    assert stored["routeId"] == "ROUTE"
    assert module.effective_detail(stored) == row["_detail"]
    value = b02_candidate(owner)
    row = value["data"][0]
    row["_detail_meta"]["components"]["network"]["native_contract"] = (
        "future-network-v2"
    )
    stored = read(module.publish(tmp_path / "unknown", owner.encode(value), owner))
    assert stored["_detail_storage"]["state"] == "full"
    assert module.effective_detail(stored) == row["_detail"]


def test_tracked_owner_patch_matches_tested_snapshot(tmp_path):
    import subprocess

    fixture = Path(__file__).parent / "fixtures/duckdog/import_settings.py"
    patch = Path(__file__).parents[1] / "scripts/patches/b03-duckdog-import.patch"
    copy = tmp_path / ".agents/skills/duckdog-import/scripts/import_settings.py"
    copy.parent.mkdir(parents=True)
    copy.write_bytes(fixture.read_bytes())
    reverse = subprocess.run(
        ["patch", "--batch", "-R", "-p1", "-i", str(patch)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )
    assert reverse.returncode == 0, reverse.stderr + reverse.stdout
    baseline = copy.read_bytes()
    assert b"B03_STORAGE_VERSION" not in baseline
    applied = subprocess.run(
        ["patch", "--batch", "-p1", "-i", str(patch)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )
    assert applied.returncode == 0, applied.stderr + applied.stdout
    assert copy.read_bytes() == fixture.read_bytes()


def test_integer_realtime_identity_rejected_without_storage_or_acquisition(tmp_path):
    import pytest

    module, owner = fixture_importer()
    value = candidate(owner)
    row = value["data"][0]
    row["id"] = row["_detail"]["id"] = 1
    with pytest.raises(ValueError, match="native identity must be a string"):
        module.publish(tmp_path / "store", owner.encode(value), owner)
    assert not (tmp_path / "store").exists()
    value["data"] = [{"id": 1}]
    calls = []

    def run(*args, **kwargs):
        calls.append(args)

    with pytest.raises(ValueError, match="native identity must be a string"):
        module.acquire(owner.encode(value), owner, run)
    assert calls == []


def test_conflicting_history_identity_rejected_and_identical_repeats_preserved(
    tmp_path,
):
    import copy

    import pytest

    module, owner = fixture_importer()
    value = b02_candidate(owner)
    previous = module.publish(tmp_path, owner.encode(value), owner)
    old = Path(previous["parquet"])
    previous_bytes = old.read_bytes()
    previous_record = read(previous)
    with duckdb.connect(previous["database"]) as db:
        registry = db.execute(
            "SELECT to_json(dataset) FROM _duckdog_datasets dataset"
        ).fetchall()
    row = value["data"][0]
    row["_detail"]["operationHistory"].append(
        copy.deepcopy(row["_detail"]["operationHistory"][0])
    )
    row["_detail"]["operationHistory"][1]["version"] = 99
    row["_detail_meta"]["components"]["operationHistory"]["returned_count"] = 2
    value["meta"]["fetched_at"] = "2026-01-02T00:00:00+00:00"
    with pytest.raises(ValueError, match="conflicting history identity"):
        module.publish(tmp_path, owner.encode(value), owner)
    assert old.read_bytes() == previous_bytes
    assert read(previous) == previous_record
    with duckdb.connect(previous["database"]) as db:
        assert (
            db.execute(
                "SELECT to_json(dataset) FROM _duckdog_datasets dataset"
            ).fetchall()
            == registry
        )
    assert list(old.parent.glob("*.parquet")) == [old]
    row["_detail"]["operationHistory"][1]["version"] = 1
    row["_detail_meta"]["fetched_at"] = "2026-01-02T00:00:00+00:00"
    for name in ("network", "operationHistory"):
        row["_detail_meta"]["components"][name]["captured_at"] = (
            "2026-01-02T00:00:00+00:00"
        )
    result = module.publish(tmp_path, owner.encode(value), owner)
    assert (
        read(result)["_detail"]["operationHistory"]
        == row["_detail"]["operationHistory"]
    )
    assert len(read(result)["_detail"]["operationHistory"]) == 2
