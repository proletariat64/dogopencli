"""Collection SDK: native page contracts, fallback, provenance and host gating."""

import json
from argparse import Namespace
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from dogopencli.collect import collect_list
from dogopencli.contracts import (
    EndpointContract,
    ParsedPage,
    resolve_collection_provider,
)
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INCOMPLETE_RESULT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.leaves.registry import Leaf, validate_manifest
from dogopencli.transport import OriginMetadata, TransportResponse
from dogopencli.transport.cdp import FetchFailed

ORIGIN = OriginMetadata("fixture", True, None, None, None, None, None)


def config(
    sizes=(4, 2),
    *,
    mode="offset",
    primary="field",
    fields=("id",),
    provider="general",
    latest_by=None,
):
    value = {
        "provider": provider,
        "paging": {"mode": mode, "page_sizes": list(sizes)},
        "primary_id": {"type": primary, "fields": list(fields)},
    }
    if latest_by is not None:
        value["latest_by"] = latest_by
    return value


class Native:
    name = "payment.fake.list"

    def __init__(self, *, sizes=(4, 2), mode="offset"):
        self.mode = mode
        self.contract = EndpointContract(
            method="POST",
            host="fixture.invalid",
            path="/query",
            page_size=sizes[0],
            one_based=False,
            allowed_body_keys=frozenset({"rowStart", "pageNo", "pageSize"}),
            allowed_page_sizes=tuple(sizes),
        )

    def page_body(self, scope, position, size):
        key = "rowStart" if self.mode == "offset" else "pageNo"
        return {key: position, "pageSize": size}

    def parse_rows(self, raw):
        value = json.loads(raw)
        if value.get("success") is False:
            raise CliError(BUSINESS_QUERY_FAILED, "native business rejection")
        return value["rows"], value["total"]

    def parse_page(self, raw):
        value = json.loads(raw)
        if value.get("success") is False:
            raise CliError(BUSINESS_QUERY_FAILED, "native business rejection")
        return ParsedPage(
            value["rows"],
            value["page"],
            value["size"],
            value["total"],
            -(-value["total"] // value["size"]),
        )


class Script:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def execute(self, request, *, timeout):
        assert timeout > 0
        self.requests.append(dict(request.body))
        if not self.responses:
            raise AssertionError("unexpected additional backend request")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if "status" in item:
            return TransportResponse(item["status"], b"{}", ORIGIN)
        return TransportResponse(200, json.dumps(item).encode("utf-8"), ORIGIN)


def offset(rows, total):
    return {"rows": rows, "total": total, "success": True}


def numbered(rows, total, page, size):
    return {**offset(rows, total), "page": page, "size": size}


def collect(source, stream, settings, *, state_file=None, domain="payment"):
    return collect_list(
        source,
        stream,
        "owned",
        settings,
        domain=domain,
        leaf_id=domain + ".fake",
        state_file=state_file,
        budget_seconds=10,
    )


def test_provider_resolver_enforces_private_domains():
    assert resolve_collection_provider("payment", "general") == "general"
    assert (
        resolve_collection_provider("payment", "payment.collection")
        == "payment.collection"
    )
    with pytest.raises(CliError, match="does not belong"):
        resolve_collection_provider("payment", "fx.collection")
    with pytest.raises(CliError, match="unknown"):
        resolve_collection_provider("fx", "unregistered")


def test_example_manifest_opts_in_without_a_collector():
    root = Path(__file__).parents[2]
    manifest = json.loads(
        (root / "tools/leaf-dev/example/leaf.json").read_text(encoding="utf-8")
    )
    validate_manifest(manifest)
    manifest["collection"]["provider"] = "fx.collection"
    with pytest.raises(CliError) as error:
        validate_manifest(manifest)
    assert error.value.code == "INVALID_LEAF"


@pytest.mark.parametrize(
    "bad",
    [
        {"paging": {"mode": "offset", "page_sizes": [4, 4]}},
        {"paging": {"mode": "offset", "page_sizes": [4, 0]}},
        {"primary_id": {"type": "field", "fields": ["a", "b"]}},
        {"primary_id": {"type": "hash", "fields": []}},
        {"version": 1},
    ],
)
def test_manifest_rejects_invalid_collection_declarations(bad):
    root = Path(__file__).parents[2]
    manifest = json.loads(
        (root / "tools/leaf-dev/example/leaf.json").read_text(encoding="utf-8")
    )
    manifest["collection"].update(bad)
    with pytest.raises(CliError) as error:
        validate_manifest(manifest)
    assert error.value.code == "INVALID_LEAF"


def test_offset_two_pages_complete_without_unqualified_requests():
    rows = [{"id": n} for n in range(5)]
    stream = Script(offset(rows[:4], 5), offset(rows[4:], 5))
    result = collect(Native(), stream, config())
    assert result.complete and result.records == rows
    assert result.evidence.arrivals == 5
    assert [q["rowStart"] for q in stream.requests] == [0, 4]
    assert result.evidence.attempts[0]["page_size"] == 4


def test_numbered_and_single_page_modes():
    rows = [{"id": n} for n in range(3)]
    numbered_stream = Script(numbered(rows[:2], 3, 0, 2), numbered(rows[2:], 3, 1, 2))
    complete = collect(
        Native(sizes=(2,), mode="page_number"),
        numbered_stream,
        config((2,), mode="page_number"),
    )
    assert complete.complete and complete.records == rows
    assert [q["pageNo"] for q in numbered_stream.requests] == [0, 1]
    single = collect(
        Native(sizes=(2,), mode="single"),
        Script(numbered(rows[:2], 3, 0, 2)),
        config((2,), mode="single"),
    )
    assert single.complete is False
    assert "SINGLE_PAGE_CAPACITY" in single.evidence.reasons


def test_hash_identity_is_type_sensitive_and_does_not_mutate_native_rows():
    rows = [{"a": "1", "b": 2}, {"a": 1, "b": "2"}]
    value = collect(
        Native(sizes=(2,)),
        Script(offset(rows, 2)),
        config((2,), primary="hash", fields=("a", "b")),
    )
    assert value.complete and value.records == rows
    assert all("primaryId" not in row for row in value.records)


@pytest.mark.parametrize("record", [{"id": None}, {"id": []}, {"id": ""}, {}])
def test_missing_or_non_scalar_identity_is_rejected(record):
    with pytest.raises(CliError) as error:
        collect(Native(sizes=(2,)), Script(offset([record], 1)), config((2,)))
    assert error.value.code == INVALID_RESPONSE


def test_cross_page_duplicate_is_dropped_but_coverage_is_not_proven():
    a, b = {"id": "a"}, {"id": "b"}
    result = collect(
        Native(sizes=(2,)),
        Script(offset([a, b], 3), offset([b], 3)),
        config((2,)),
    )
    assert result.records == [a, b]
    assert result.evidence.arrivals == 3
    assert result.evidence.duplicate_count == 1
    assert not result.complete
    assert "DUPLICATE_ROWS" in result.evidence.reasons


def test_conflict_chooses_latest_timestamp_then_last_arrival():
    latest = {"id": 1, "changed": "2026-10-18T10:00:00Z", "value": "new"}
    old = {"id": 1, "changed": "2026-10-17T10:00:00Z", "value": "old"}
    by_time = collect(
        Native(sizes=(2,)),
        Script(offset([latest, old], 2)),
        config((2,), latest_by="changed"),
    )
    assert by_time.records == [latest]
    assert not by_time.complete
    assert by_time.evidence.attempts[0]["conflict_count"] == 1
    by_arrival = collect(
        Native(sizes=(2,)),
        Script(offset([latest, old], 2)),
        config((2,)),
    )
    assert by_arrival.records == [old]
    assert "LAST_ARRIVAL_WINS" in by_arrival.evidence.reasons


def test_short_and_empty_native_pages_do_not_hide_holes():
    stream = Script(
        offset([{"id": "a"}], 5),
        offset([], 5),
        offset([{"id": "e"}], 5),
    )
    result = collect(Native(sizes=(2,)), stream, config((2,)))
    assert [row["id"] for row in result.records] == ["a", "e"]
    assert not result.complete
    assert "SHORT_NATIVE_PAGE" in result.evidence.reasons
    assert "EMPTY_INTERIOR_PAGE" in result.evidence.reasons
    assert [q["rowStart"] for q in stream.requests] == [0, 2, 4]


def test_fallbacks_share_one_global_logical_page_budget():
    rows = [{"id": n} for n in range(4)]
    limited = Script(offset(rows[:3], 4), offset(rows[:2], 4))
    partial = collect_list(
        Native(),
        limited,
        "owned",
        config(),
        domain="payment",
        leaf_id="payment.fake",
        budget_seconds=10,
        max_pages=2,
    )
    assert not partial.complete
    assert partial.records == rows[:3]
    assert [(q["rowStart"], q["pageSize"]) for q in limited.requests] == [
        (0, 4),
        (0, 2),
    ]
    assert sum(attempt["pages"] for attempt in partial.evidence.attempts) == 2
    assert partial.evidence.attempts[-1]["error"] == "TIMEOUT"

    permitted = Script(offset(rows[:3], 4), offset(rows[:2], 4), offset(rows[2:], 4))
    complete = collect_list(
        Native(),
        permitted,
        "owned",
        config(),
        domain="payment",
        leaf_id="payment.fake",
        budget_seconds=10,
        max_pages=3,
    )
    assert complete.complete and complete.records == rows
    assert len(permitted.requests) == 3
    assert sum(attempt["pages"] for attempt in complete.evidence.attempts) == 3


def test_preference_writes_skip_busy_lock_and_remain_best_effort(tmp_path):
    import fcntl
    import os

    from dogopencli.collection_state import preferred_page_size, remember_page_size

    state = tmp_path / "collection-state.json"
    key = "a" * 64
    owner = os.open(str(state) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        remember_page_size(state, key, 2)
        assert not state.exists()
    finally:
        os.close(owner)

    remember_page_size(state, key, 2)
    assert preferred_page_size(state, key, (4, 2)) == 2


def test_fallback_restarts_from_zero_then_persists_width(tmp_path):
    rows = [{"id": n} for n in range(4)]
    state = tmp_path / "collection-state.json"
    stream = Script(
        offset(rows[:3], 4),
        offset(rows[:2], 4),
        offset(rows[2:], 4),
    )
    first = collect(Native(), stream, config(), state_file=state)
    assert first.complete and first.records == rows and first.rebuilt
    assert [(q["pageSize"], q["rowStart"]) for q in stream.requests] == [
        (4, 0),
        (2, 0),
        (2, 2),
    ]
    assert len(first.evidence.attempts) == 2
    assert json.loads(state.read_text())["preferences"]
    assert "owned" not in state.read_text()
    second_stream = Script(offset(rows[:2], 4), offset(rows[2:], 4))
    second = collect(Native(), second_stream, config(), state_file=state)
    assert second.complete
    assert [q["pageSize"] for q in second_stream.requests] == [2, 2]
    state.write_text("{malformed")
    third_stream = Script(offset(rows, 4))
    third = collect(Native(), third_stream, config(), state_file=state)
    assert third.complete
    assert third_stream.requests[0]["pageSize"] == 4


def test_timeout_can_fallback_but_business_failure_cannot(monkeypatch):
    monkeypatch.setattr("dogopencli.collect._sleep", lambda _: None)
    good = offset([{"id": "ok"}], 1)
    stream = Script(
        FetchFailed("offline"), FetchFailed("offline"), FetchFailed("offline"), good
    )
    result = collect(Native(), stream, config())
    assert result.complete and result.page_size == 2
    assert [p["error"] for p in result.evidence.attempts[:1]] == ["TIMEOUT"]
    business = Script({"success": False, "rows": [], "total": 0})
    with pytest.raises(CliError) as error:
        collect(Native(), business, config())
    assert error.value.code == BUSINESS_QUERY_FAILED
    assert len(business.requests) == 1


def test_changed_total_or_unregistered_width_is_never_hidden():
    source = Native()
    stream = Script(offset([{"id": n} for n in range(4)], 5), offset([], 6))
    with pytest.raises(CliError) as error:
        collect(source, stream, config())
    assert error.value.code == INVALID_RESPONSE
    assert len(stream.requests) == 2
    unregistered = Script()
    with pytest.raises(CliError) as denied:
        collect(source, unregistered, config((999,)))
    assert denied.value.code == REQUEST_NOT_ALLOWED
    assert unregistered.requests == []


def test_real_entity_pilot_contract_can_run_through_generic_offset_engine():
    import importlib.util
    import sys

    file = (
        Path(__file__).parents[2]
        / "src/dogopencli/leaf_packages/liquidity/reference.entities/adapter.py"
    )
    spec = importlib.util.spec_from_file_location("_sdk_entity_pilot", file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        capability = module.EntityInquiry()
    finally:
        sys.modules.pop(spec.name, None)
    # Qualify an adapter only inside this fake-transport test. The existing
    # installed pilot's source and old cache hash must remain unchanged.
    native_capability = capability

    class QualifiedEntity:
        def __init__(self, native_capability):
            self.native = native_capability
            self.name = native_capability.name
            self.contract = replace(
                native_capability.contract,
                fixed_body_values=(("tntInstId", "GUAPW3SG"),),
                json_body_contracts=(
                    (
                        "entityMaintQueryVO",
                        frozenset({"tntInstId", "rowStart", "pageSize"}),
                        (("tntInstId", "GUAPW3SG"),),
                        frozenset({5000}),
                    ),
                ),
            )

        def page_body(self, scope, row_start, page_size):
            if page_size != 5000:
                raise CliError(REQUEST_NOT_ALLOWED, "unqualified page size")
            return self.native.page_body(scope, row_start)

        def parse_rows(self, body):
            return self.native.parse_rows(body)

    capability = QualifiedEntity(native_capability)
    native = {
        "resultFlag": True,
        "result": {"entityMaintVOList": [{"instId": "ACME"}]},
        "count": 1,
    }
    stream = Script(native)
    result = collect_list(
        capability,
        stream,
        "",
        config((5000,), fields=("instId",)),
        domain="liquidity",
        leaf_id="liquidity.reference.entities",
        budget_seconds=10,
    )
    assert result.complete
    assert result.records == [{"instId": "ACME"}]
    assert json.loads(stream.requests[0]["entityMaintQueryVO"])["pageSize"] == 5000


def test_opted_in_refresh_rejects_partial_and_preserves_saved_rows(
    tmp_path, monkeypatch
):
    from dogopencli.leaves import runtime

    source = Native(sizes=(2,))
    settings = config((2,))
    queries = iter(
        [
            Script(offset([{"id": "saved"}, {"id": "kept"}], 2)),
            Script(offset([{"id": "saved"}, {"id": "saved"}], 2)),
        ]
    )

    class Adapter:
        def capability(self, parameters):
            return source

        def scope(self, parameters):
            return "owned"

        def filter(self, records, parameters):
            return records

    @contextmanager
    def fake_session(**kwargs):
        transport = next(queries)

        class Session:
            def transport(self, capability):
                return transport

        yield Session()

    monkeypatch.setattr(runtime, "inquiry_session", fake_session)
    leaf = Leaf(
        domain="payment",
        name="fake",
        path=tmp_path,
        adapter=Adapter(),
        manifest={
            "adapter": "adapter.py:adapter",
            "operations": {"list": {"parameters": []}},
            "identity": ["id"],
            "collection": settings,
        },
    )
    args = Namespace(
        limit=100,
        offset=0,
        fields=None,
        require_complete=False,
        require_fresh=False,
        live=False,
        explicit_parameters=set(),
    )
    config_file = tmp_path / "config.toml"
    runtime.execute(leaf, "refresh", {}, args, config_file)
    before, meta = runtime.execute(leaf, "list", {}, args, config_file)
    assert [r["id"] for r in before] == ["saved", "kept"]
    with pytest.raises(CliError) as error:
        runtime.execute(leaf, "refresh", {}, args, config_file)
    assert error.value.code == INCOMPLETE_RESULT
    after, current_meta = runtime.execute(leaf, "list", {}, args, config_file)
    assert after == before
    assert current_meta["fetched_at"] == meta["fetched_at"]


def test_existing_snapshot_keeps_pre_sdk_contract_hash_and_replays_offline(tmp_path):
    import hashlib
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from dogopencli.cache import SnapshotMeta
    from dogopencli.jsonutil import canonical
    from dogopencli.leaves import runtime
    from dogopencli.result_policy import AcquisitionEvidence

    # A concrete native contract with no SDK declaration is modeled as it
    # existed before EndpointContract gained allowed_page_sizes.
    contract = EndpointContract(
        method="GET",
        host="fixture.invalid",
        path="/native-list",
        page_size=100,
        one_based=False,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
    )
    capability = SimpleNamespace(name="payment.old.list", contract=contract)

    class SavedAdapter:
        def capability(self, parameters):
            return capability

        def scope(self, parameters):
            return ""

        def filter(self, records, parameters):
            return records

    leaf = Leaf(
        domain="payment",
        name="old",
        path=tmp_path,
        adapter=SavedAdapter(),
        adapter_sha256="unchanged-leaf-source",
        manifest={
            "adapter": "adapter.py:adapter",
            "operations": {"list": {"parameters": []}},
            "identity": ["id"],
        },
    )

    def old_basic(value):
        if isinstance(value, dict):
            return {key: old_basic(item) for key, item in value.items()}
        if isinstance(value, (set, frozenset)):
            return sorted(old_basic(item) for item in value)
        if isinstance(value, (tuple, list)):
            return [old_basic(item) for item in value]
        return value

    native_contract = asdict(contract)
    assert native_contract.pop("allowed_page_sizes") == ()
    legacy_context = {
        "identity": ["id"],
        "operations": {"list": []},
        "adapter_binding": "adapter.py:adapter",
        "adapter_sha256": "unchanged-leaf-source",
        "capability": capability.name,
        "native_contract": old_basic(native_contract),
    }
    original_hash = hashlib.sha256(canonical(legacy_context).encode()).hexdigest()
    assert runtime._contract_id(leaf, capability) == original_hash
    opted_in = replace(leaf, manifest={**leaf.manifest, "collection": config((100,))})
    assert runtime._contract_id(opted_in, capability) != original_hash

    config_file = tmp_path / "settings.toml"
    snapshot_time = datetime.now(timezone.utc).isoformat()
    snapshot = SnapshotMeta(
        namespace="leaf:payment.old",
        capability="payment.old",
        scope=canonical(
            {
                "parameters": {},
                "native_scope": "",
                "contract_id": original_hash,
            }
        ),
        source_kind="cdp",
        snapshot_id="existing",
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at=snapshot_time,
        loaded_at=snapshot_time,
        source_observed_from=None,
        source_observed_to=None,
        row_count=1,
        acquisition=AcquisitionEvidence.for_collection(
            complete=True, reported_total=1, collected_total=1, arrivals=1
        ).record(),
    )
    runtime.cache_for(config_file).publish(
        snapshot, [(1, canonical({"id": "existing"}))]
    )
    args = Namespace(
        limit=100,
        offset=0,
        fields=None,
        require_complete=False,
        require_fresh=False,
        live=False,
        explicit_parameters=set(),
    )
    records, metadata = runtime.execute(leaf, "list", {}, args, config_file)
    assert records == [{"id": "existing"}]
    assert metadata["source"] == "cache"
