"""Collection SDK: native page contracts, fallback, provenance and host gating."""

import json
from argparse import Namespace
from contextlib import contextmanager
from dataclasses import replace
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


@pytest.mark.parametrize("operation", ["list", "refresh"])
@pytest.mark.parametrize("explicit_null", [False, True])
def test_runtime_rejects_undeclared_collection_before_acquisition_or_cache(
    tmp_path, monkeypatch, operation, explicit_null
):
    from dogopencli.leaves import runtime

    def unexpected(*args, **kwargs):
        raise AssertionError("invalid List must fail before acquiring owned state")

    monkeypatch.setattr(runtime, "cache_for", unexpected)
    monkeypatch.setattr(runtime, "inquiry_session", unexpected)
    leaf = Leaf(
        domain="payment",
        name="invalid",
        path=tmp_path,
        adapter=object(),
        manifest={"operations": {"list": {"parameters": []}}},
    )
    if explicit_null:
        leaf.manifest["collection"] = None
    with pytest.raises(CliError, match="standard List requires a collection") as error:
        runtime.execute(leaf, operation, {}, Namespace(), tmp_path / "config.toml")
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


def test_opted_in_hash_keeps_empty_null_and_zero_distinct():
    rows = [
        {"account": "A", "kind": "", "created": None},
        {"account": "A", "kind": "", "created": 0},
        {"account": "A", "kind": None, "created": None},
    ]
    settings = config((4,), primary="hash", fields=("account", "kind", "created"))
    with pytest.raises(CliError, match="identity"):
        collect(Native(sizes=(4,)), Script(offset(rows, 3)), settings)
    settings["primary_id"]["allow_empty_components"] = True
    result = collect(Native(sizes=(4,)), Script(offset(rows, 3)), settings)
    assert result.complete and result.records == rows
    assert result.evidence.unique_count == 3
    from dogopencli.leaves.runtime import _validate_records

    assert _validate_records(rows, list(rows[0]), settings["primary_id"]) == rows
    with pytest.raises(CliError, match="identity"):
        _validate_records(rows, list(rows[0]))


@pytest.mark.parametrize("bad", [{"account": "A"}, {"account": "A", "created": []}])
def test_nullable_hash_still_rejects_missing_or_structured_components(bad):
    settings = config((4,), primary="hash", fields=("account", "created"))
    settings["primary_id"]["allow_empty_components"] = True
    with pytest.raises(CliError, match="identity"):
        collect(Native(sizes=(4,)), Script(offset([bad], 1)), settings)


@pytest.mark.parametrize("kind,flag", [("field", True), ("hash", "true")])
def test_empty_component_opt_in_requires_a_hash_and_boolean(kind, flag):
    manifest = json.loads(
        (Path(__file__).parents[2] / "tools/leaf-dev/example/leaf.json").read_text()
    )
    manifest["collection"]["primary_id"].update(type=kind, allow_empty_components=flag)
    with pytest.raises(CliError):
        validate_manifest(manifest)


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


@pytest.mark.parametrize(
    "identities,total", [([], 2), (["one"], 1001), (["one"] * 2, 1)]
)
def test_single_request_retains_valid_partial_records_and_arrival_evidence(
    identities, total
):
    rows = [
        {"id": identity, "native": [None, False, "2.00"]} for identity in identities
    ]
    stream = Script(numbered(rows, total, 0, 1000))
    result = collect(
        Native(sizes=(1000,), mode="single"),
        stream,
        config((1000,), mode="single"),
    )
    assert result.complete is False
    assert result.records == rows[: len(set(identities))]
    assert result.evidence.arrivals == len(rows)
    assert result.evidence.unique_count == len(set(identities))
    assert result.pages == len(stream.requests) == 1


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


def test_width_fallback_preserves_one_deadline_and_independent_candidates(monkeypatch):
    from dogopencli import collect as collection

    clock = [0.0]
    monkeypatch.setattr(collection, "_monotonic", lambda: clock[0])
    timeouts = []

    class TimedScript(Script):
        def execute(self, request, *, timeout):
            timeouts.append(timeout)
            clock[0] += 2
            return super().execute(request, timeout=timeout)

    rows = [{"id": "chosen-one"}, {"id": "chosen-two"}]
    stream = TimedScript(offset([{"id": "discarded"}], 2), offset(rows, 2))
    result = collect(Native(), stream, config())
    assert result.complete and result.rebuilt
    assert result.records == rows
    assert result.deadline == 10
    assert timeouts == [5, 8]
    assert [request["rowStart"] for request in stream.requests] == [0, 0]


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


def test_real_entity_pilot_contract_can_run_through_generic_offset_engine(monkeypatch):
    import importlib.util
    import sys

    monkeypatch.setattr(sys, "dont_write_bytecode", True)
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


@pytest.mark.parametrize("failure", ["partial", "missing_evidence"])
def test_strict_refresh_rejects_unpublishable_acquisition_and_preserves_saved_rows(
    tmp_path, monkeypatch, failure
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
        require_complete=True,
        require_fresh=False,
        live=False,
        with_detail=False,
        explicit_parameters=set(),
    )
    config_file = tmp_path / "config.toml"
    runtime.execute(leaf, "refresh", {}, args, config_file)
    before, meta = runtime.execute(leaf, "list", {}, args, config_file)
    assert [r["id"] for r in before] == ["saved", "kept"]
    if failure == "missing_evidence":
        from types import SimpleNamespace

        monkeypatch.setattr(
            runtime,
            "collect_list",
            lambda *args, **kwargs: SimpleNamespace(
                records=[{"id": "unproven"}], evidence=None
            ),
        )
    with pytest.raises(CliError) as error:
        runtime.execute(leaf, "refresh", {}, args, config_file)
    assert error.value.code == (
        INVALID_RESPONSE if failure == "missing_evidence" else INCOMPLETE_RESULT
    )
    after, current_meta = runtime.execute(leaf, "list", {}, args, config_file)
    assert after == before
    assert current_meta["fetched_at"] == meta["fetched_at"]


@pytest.mark.parametrize(
    "rows,total", [([{"id": "same"}] * 2, 2), ([{"value": 1}], 1), ([], 0)]
)
def test_unproven_identity_preserves_arrivals_and_never_learns(tmp_path, rows, total):
    source = Native(sizes=(2,))
    source.contract = replace(
        source.contract, has_identity=False, total_semantics="unknown"
    )
    state = tmp_path / "collection-state.json"
    result = collect_list(
        source,
        Script(offset(rows, total)),
        "scope",
        config((2,), primary="unproven", fields=()),
        domain="fx",
        leaf_id="fx.trade",
        state_file=state,
    )
    assert result.records == rows
    assert result.complete is False
    assert result.evidence.unique_count is None
    assert result.evidence.duplicate_count is None
    assert result.evidence.arrivals == len(rows)
    assert result.evidence.total_semantics == "unknown"
    assert {"IDENTITY_UNPROVEN", "TOTAL_SEMANTICS_UNPROVEN"} <= set(
        result.evidence.reasons
    )
    assert not state.exists()


@pytest.mark.parametrize(
    "setting,value",
    [
        ("max_pages", 0),
        ("max_pages", True),
        ("max_pages", 1001),
        ("budget_seconds", 0),
        ("budget_seconds", 901),
        ("budget_seconds", "120"),
    ],
)
def test_manifest_rejects_invalid_acquisition_limits(setting, value):
    root = Path(__file__).parents[2]
    manifest = json.loads(
        (root / "src/dogopencli/leaf_packages/fx/trade/leaf.json").read_text()
    )
    manifest["collection"][setting] = value
    with pytest.raises(CliError, match="must be integer|allowed range"):
        validate_manifest(manifest)


@pytest.mark.parametrize("change", ["fields", "latest_by", "identity"])
def test_unproven_identity_cannot_claim_native_identity(change):
    root = Path(__file__).parents[2]
    manifest = json.loads(
        (root / "src/dogopencli/leaf_packages/fx/trade/leaf.json").read_text()
    )
    manifest["identity"] = []
    manifest["collection"]["primary_id"] = {"type": "unproven", "fields": []}
    if change == "fields":
        manifest["collection"]["primary_id"]["fields"] = ["uniqueId"]
    elif change == "latest_by":
        manifest["collection"]["latest_by"] = "updated"
    else:
        manifest["identity"] = ["uniqueId"]
    with pytest.raises(CliError, match="identity"):
        validate_manifest(manifest)


def test_declared_limits_bound_sdk_acquisition():
    source = Native(sizes=(2,))
    settings = {**config((2,)), "max_pages": 1}
    stream = Script(offset([{"id": "one"}, {"id": "two"}], 3))
    with pytest.raises(CliError, match="budget"):
        collect_list(
            source, stream, "", settings, domain="payment", leaf_id="payment.test"
        )
    assert len(stream.requests) == 1


def test_sdk_rejects_identity_contract_mismatch_before_requests():
    source = Native(sizes=(2,))
    stream = Script()
    with pytest.raises(CliError, match="identity declaration"):
        collect_list(
            source,
            stream,
            "",
            config((2,), primary="unproven", fields=()),
            domain="payment",
            leaf_id="payment.test",
        )
    assert stream.requests == []


def test_unproven_total_does_not_discard_rows_at_page_cap():
    source = Native(sizes=(2,))
    source.contract = replace(
        source.contract, has_identity=False, total_semantics="unknown"
    )
    rows = [{"value": i} for i in range(4)]
    stream = Script(offset(rows[:2], 5), offset(rows[2:], 5))
    result = collect_list(
        source,
        stream,
        "",
        {**config((2,), primary="unproven", fields=()), "max_pages": 2},
        domain="fx",
        leaf_id="fx.trade",
    )
    assert result.records == rows
    assert len(stream.requests) == 2
    assert result.complete is False
    assert result.evidence.reported_total == 5
    assert "PAGE_BUDGET_EXHAUSTED" in result.evidence.reasons


@pytest.mark.parametrize("rows", [[{"value": 1}], [{"value": 1}] * 2])
def test_unproven_large_total_stops_at_short_or_overlap_page(rows):
    source = Native(sizes=(2,))
    source.contract = replace(
        source.contract, has_identity=False, total_semantics="unknown"
    )
    stream = Script(offset(rows, 50000))
    result = collect_list(
        source,
        stream,
        "",
        {**config((2,), primary="unproven", fields=()), "max_pages": 2},
        domain="fx",
        leaf_id="fx.trade",
    )
    assert result.records == rows
    assert len(stream.requests) == 1
    assert result.complete is False


def short_page_settings(*, mode="page_number", sizes=(2,)):
    settings = config(sizes, mode=mode)
    settings["paging"]["termination"] = "short_page"
    return settings


class ShortPageNative(Native):
    def parse_page(self, raw):
        value = json.loads(raw)
        if value.get("success") is False:
            raise CliError(BUSINESS_QUERY_FAILED, "native business rejection")
        return ParsedPage(
            value["rows"],
            value["page"],
            value["size"],
            value.get("total"),
            value.get("totalPages"),
        )


@pytest.mark.parametrize("mode", ["offset", "page_number"])
@pytest.mark.parametrize("final_rows", [[], [{"id": "three"}]])
def test_short_page_ignores_totals_and_retains_native_records(mode, final_rows):
    from dogopencli.result_policy import AcquisitionEvidence

    source = ShortPageNative(sizes=(2,), mode=mode)
    source.contract = replace(source.contract, total_semantics="unknown")
    rows = [{"id": "one"}, {"id": "two", "native": [None, False, "0.000"]}]
    first = numbered(rows, 0, 0, 2)
    last = numbered(final_rows, "unreliable", 1, 2)
    empty = (
        [numbered([], None, 2, 2), numbered([], None, 3, 2)]
        if final_rows
        else [numbered([], None, 2, 2)]
    )
    stream = Script(first, last, *empty)
    result = collect(source, stream, short_page_settings(mode=mode))
    assert result.records == rows + final_rows
    assert result.complete
    position = "rowStart" if mode == "offset" else "pageNo"
    assert [request[position] for request in stream.requests] == [
        n * (2 if mode == "offset" else 1) for n in range(2 + len(empty))
    ]
    evidence = result.evidence
    assert evidence.reported_total is None
    assert evidence.total_semantics == "unknown"
    assert evidence.coverage_basis == "qualified_short_page"
    assert evidence.attempts[-1]["termination_reason"] == "two_empty_batches"
    assert AcquisitionEvidence.from_record(evidence.record()) == evidence


def test_short_page_exact_multiple_requires_empty_request_and_uses_one_based_pages():
    source = ShortPageNative(sizes=(2,), mode="page_number")
    source.contract = replace(source.contract, one_based=True)
    stream = Script(
        numbered([{"id": "one"}, {"id": "two"}], 2, 1, 2),
        numbered([], None, 2, 2),
        numbered([], None, 3, 2),
    )
    result = collect(source, stream, short_page_settings())
    assert result.complete and result.pages == 3
    assert [q["pageNo"] for q in stream.requests] == [1, 2, 3]


def test_short_page_empty_first_response_is_complete_without_total():
    result = collect(
        ShortPageNative(sizes=(2,), mode="page_number"),
        Script(numbered([], None, 0, 2), numbered([], None, 1, 2)),
        short_page_settings(),
    )
    assert result.complete and result.records == []
    assert result.evidence.attempts[-1]["termination_reason"] == "two_empty_batches"


@pytest.mark.parametrize("conflict", [False, True])
def test_short_page_preserves_deduplication_but_rejects_complete_claim(conflict):
    first = {"id": "one", "value": 1}
    last = {"id": "one", "value": 2 if conflict else 1}
    result = collect(
        ShortPageNative(sizes=(2,), mode="page_number"),
        Script(
            numbered([first, {"id": "two"}], 1, 0, 2),
            numbered([last], 1000, 1, 2),
            numbered([], None, 2, 2),
            numbered([], None, 3, 2),
        ),
        short_page_settings(),
    )
    assert not result.complete
    assert result.records == [last, {"id": "two"}]
    assert result.evidence.duplicate_count == 1
    assert result.evidence.attempts[-1]["conflict_count"] == int(conflict)
    assert result.evidence.reported_total is None


def test_short_page_full_page_at_budget_limit_never_becomes_complete():
    stream = Script(numbered([{"id": "one"}, {"id": "two"}], 0, 0, 2))
    with pytest.raises(CliError, match="budget"):
        collect(
            ShortPageNative(sizes=(2,), mode="page_number"),
            stream,
            {**short_page_settings(), "max_pages": 1},
        )
    assert len(stream.requests) == 1


@pytest.mark.parametrize("failure", ["auth", "business", "echo", "oversize"])
def test_short_page_failures_are_not_terminal_empty_success(failure):
    final = numbered([], None, 1, 2)
    if failure == "auth":
        final = {"status": 401}
    elif failure == "business":
        final["success"] = False
    elif failure == "echo":
        final["page"] = 0
    else:
        final["rows"] = [{"id": n} for n in range(3)]
    stream = Script(numbered([{"id": "one"}, {"id": "two"}], None, 0, 2), final)
    with pytest.raises(CliError) as error:
        collect(
            ShortPageNative(sizes=(2,), mode="page_number"),
            stream,
            short_page_settings(),
        )
    assert (
        error.value.code
        == {
            "auth": "AUTH_REQUIRED",
            "business": BUSINESS_QUERY_FAILED,
            "echo": INVALID_RESPONSE,
            "oversize": INVALID_RESPONSE,
        }[failure]
    )


@pytest.mark.parametrize("mode", ["single", "single_response"])
def test_manifest_rejects_short_page_on_single_request_modes(mode):
    root = Path(__file__).parents[2]
    manifest = json.loads((root / "tools/leaf-dev/example/leaf.json").read_text())
    manifest["collection"] = short_page_settings(mode=mode)
    with pytest.raises(CliError, match="Short-page"):
        validate_manifest(manifest)


def test_short_page_requires_verified_identity_before_queries():
    source = ShortPageNative(sizes=(2,), mode="page_number")
    source.contract = replace(source.contract, has_identity=False)
    settings = short_page_settings()
    settings["primary_id"] = {"type": "unproven", "fields": []}
    stream = Script()
    with pytest.raises(CliError, match="verified identity"):
        collect(source, stream, settings)
    root = Path(__file__).parents[2]
    manifest = json.loads((root / "tools/leaf-dev/example/leaf.json").read_text())
    manifest["identity"] = []
    manifest["collection"] = settings
    with pytest.raises(CliError, match="identity"):
        validate_manifest(manifest)
    assert stream.requests == []


def test_cached_short_page_requires_terminal_evidence():
    from dogopencli.result_policy import AcquisitionEvidence

    result = collect(
        ShortPageNative(sizes=(2,), mode="page_number"),
        Script(
            numbered([{"id": "one"}], None, 0, 2),
            numbered([], None, 1, 2),
            numbered([], None, 2, 2),
        ),
        short_page_settings(),
    )
    record = result.evidence.record()
    del record["attempts"][-1]["termination_reason"]
    with pytest.raises(CliError, match="termination"):
        AcquisitionEvidence.from_record(record)


def test_short_page_never_uses_total_to_excuse_wrong_empty_page_echo():
    source = ShortPageNative(sizes=(2,), mode="page_number")
    source.contract = replace(source.contract, one_based=True)
    with pytest.raises(CliError, match="page echo"):
        collect(source, Script(numbered([], 0, 0, 2)), short_page_settings())


def test_short_page_width_fallback_restarts_and_shares_budget():
    source = ShortPageNative(sizes=(4, 2), mode="page_number")
    stream = Script(
        numbered([{"id": "one"}] * 2, 0, 0, 4),
        numbered([], None, 1, 4),
        numbered([], None, 2, 4),
        numbered([{"id": "one"}, {"id": "two"}], 999, 0, 2),
        numbered([], None, 1, 2),
        numbered([], None, 2, 2),
    )
    result = collect(source, stream, short_page_settings(sizes=(4, 2)))
    assert result.complete and result.rebuilt
    assert stream.requests == [
        {"pageNo": 0, "pageSize": 4},
        {"pageNo": 1, "pageSize": 4},
        {"pageNo": 2, "pageSize": 4},
        {"pageNo": 0, "pageSize": 2},
        {"pageNo": 1, "pageSize": 2},
        {"pageNo": 2, "pageSize": 2},
    ]
    assert len(result.evidence.attempts) == 2
    assert result.evidence.attempts[0]["complete"] is False
    assert result.evidence.attempts[1]["termination_reason"] == "two_empty_batches"


def test_short_page_independent_source_evidence_survives_replay():
    from dogopencli.collect import collect_sources
    from dogopencli.result_policy import AcquisitionEvidence

    source = ShortPageNative(sizes=(2,), mode="page_number")

    class SourceStream(Script):
        def close(self):
            pass

    stream = SourceStream(
        numbered([{"id": "one"}], None, 0, 2),
        numbered([], None, 1, 2),
        numbered([], None, 2, 2),
    )
    settings = short_page_settings()
    policy = {key: settings[key] for key in ("paging", "primary_id")}
    result = collect_sources(
        {"base": (source, "owned")},
        lambda capability: stream,
        lambda records, parameters: records["base"],
        {},
        {
            "provider": "general",
            "primary_id": settings["primary_id"],
            "sources": {"base": policy},
        },
        domain="payment",
        leaf_id="payment.fake",
    )
    replay = AcquisitionEvidence.from_record(result.evidence.record())
    assert replay == result.evidence
    assert (
        replay.sources["base"]["acquisition"]["coverage_basis"]
        == "qualified_short_page"
    )
