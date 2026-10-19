"""Qualified unknown totals and flat source collection keep native evidence."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pytest

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.collect import collect_list, collect_sources
from dogopencli.contracts import EndpointContract
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse
from dogopencli.result_policy import AcquisitionEvidence, check_complete
from dogopencli.transport import OriginMetadata, TransportResponse

ORIGIN = OriginMetadata("fixture", True, None, None, None, None, None)


class Native:
    name = "payment.sample.list"

    def __init__(self, sizes=(2,)):
        self.contract = EndpointContract(
            method="POST",
            host="fixture.invalid",
            path="/query",
            page_size=sizes[0],
            one_based=False,
            allowed_body_keys=frozenset({"rowStart", "pageSize"}),
            allowed_page_sizes=sizes,
        )

    def page_body(self, scope, position, size):
        return {"rowStart": position, "pageSize": size}

    def parse_rows(self, raw):
        value = parse(raw)
        if value.get("success") is False:
            raise CliError("BUSINESS_QUERY_FAILED", "source refused inquiry")
        return value["rows"], value["total"]


class Script:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.closed = False

    def execute(self, request, *, timeout):
        assert timeout > 0
        self.requests.append(request.body)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return TransportResponse(200, canonical(response).encode(), ORIGIN)

    def close(self):
        self.closed = True


def response(rows, total=None):
    return {"success": True, "rows": rows, "total": total}


def policy(mode="offset", sizes=(2,)):
    return {
        "provider": "general",
        "paging": {"mode": mode, "page_sizes": list(sizes)},
        "primary_id": {"type": "field", "fields": ["id"]},
    }


def run(native, script, settings):
    return collect_list(
        native,
        script,
        "owned-scope",
        settings,
        domain="payment",
        leaf_id="payment.sample",
    )


def test_single_response_preserves_unknown_total_and_ignores_request_width():
    rows = [
        {
            "id": str(i),
            "amount": Decimal("0.123456789012345678901"),
            "raw": [None, False],
        }
        for i in range(3)
    ]
    native = Native()
    native.contract = replace(native.contract, total_semantics="unknown")
    stream = Script(response(rows))
    result = run(native, stream, policy("single_response"))
    assert result.records == rows
    assert result.complete is True
    assert result.total_count is None
    assert stream.requests == [{"rowStart": 0, "pageSize": 2}]
    meta = result.evidence.meta()
    assert meta["reported_total"] is None
    assert meta["coverage_ratio"] is None
    assert meta["missing_count"] is None
    assert meta["acquisition"]["coverage_basis"] == "qualified_single_response"
    assert meta["acquisition"]["arrivals"] == 3
    assert meta["acquisition"]["unique_count"] == 3
    assert AcquisitionEvidence.from_record(result.evidence.record()) == result.evidence


@pytest.mark.parametrize("total", [None, -1, True, "3"])
def test_existing_offset_mode_still_rejects_missing_or_bad_native_total(total):
    with pytest.raises(CliError, match="invalid native List records or total"):
        run(Native(), Script(response([{"id": "one"}], total)), policy())


@pytest.mark.parametrize("rows", [[], [{"id": "one"}]])
def test_qualified_single_response_can_be_empty_without_fabricated_total(rows):
    result = run(Native(), Script(response(rows)), policy("single_response"))
    assert result.records == rows
    assert result.complete
    assert result.evidence.reported_total is None
    assert result.evidence.collected_total == len(rows)


def test_single_response_does_not_read_or_write_learned_widths(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("single_response cannot learn or reuse page widths")

    monkeypatch.setattr("dogopencli.collection_state.preferred_page_size", unexpected)
    monkeypatch.setattr("dogopencli.collection_state.remember_page_size", unexpected)
    state_file = tmp_path / "collection-state.json"
    result = collect_list(
        Native(),
        Script(response([{"id": "one"}])),
        "qualified",
        policy("single_response"),
        domain="payment",
        leaf_id="payment.sample",
        state_file=state_file,
    )
    assert result.complete
    assert not state_file.exists()


@pytest.mark.parametrize(
    "rows", [[{"id": "one"}] * 2, [{"id": "one", "v": 1}, {"id": "one", "v": 2}]]
)
def test_unknown_total_does_not_hide_duplicate_or_conflicting_identities(rows):
    result = run(Native(), Script(response(rows)), policy("single_response"))
    assert not result.complete
    assert result.evidence.duplicate_count == 1
    with pytest.raises(CliError) as rejected:
        check_complete(result.evidence, require_complete=True)
    assert rejected.value.code == "INCOMPLETE_RESULT"


@pytest.mark.parametrize(
    "rows,total", [([{}], None), ([None], None), (None, None), ([{"id": "one"}], 1)]
)
def test_qualified_response_rejects_invalid_shape_identity_and_unexpected_total(
    rows, total
):
    with pytest.raises(CliError):
        run(Native(), Script(response(rows, total)), policy("single_response"))


@pytest.mark.parametrize("fault", ["unproven", "fallback"])
def test_single_response_requires_verified_identity_and_one_width(fault):
    settings = policy("single_response")
    if fault == "unproven":
        settings["primary_id"] = {"type": "unproven", "fields": []}
    else:
        settings["paging"]["page_sizes"] = [2, 1]
    stream = Script()
    with pytest.raises(CliError):
        run(Native(), stream, settings)
    assert stream.requests == []


def source_setup(*, second=None, first=None):
    natives = {name: Native() for name in ("left", "right")}
    streams = {
        "left": Script(
            first
            or response([{"id": "l", "value": Decimal("0.123456789012345678901")}], 1)
        ),
        "right": Script(second or response([{"id": "r", "unknown": [False, None]}], 1)),
    }
    declared = {
        "provider": "general",
        "primary_id": {"type": "field", "fields": ["parent"]},
        "sources": {
            name: {key: value for key, value in policy().items() if key != "provider"}
            for name in natives
        },
    }
    sources = {
        name: (native, name + "-private-scope") for name, native in natives.items()
    }
    assembled = []

    def assemble(rows, parameters):
        assembled.append((rows, parameters))
        return [{"parent": "one", **rows}]

    def transport(native):
        return streams[
            next(name for name, candidate in natives.items() if candidate is native)
        ]

    return sources, streams, declared, assembled, assemble, transport


def collect(setup, **kwargs):
    sources, _, declared, _, assemble, transport = setup
    return collect_sources(
        sources,
        transport,
        assemble,
        {"selection": "native"},
        declared,
        domain="payment",
        leaf_id="payment.sample",
        **kwargs,
    )


def test_sources_preserve_children_separate_quality_scope_and_cache_evidence(tmp_path):
    setup = source_setup()
    result = collect(setup, state_file=tmp_path / "collection-state.json")
    assert len(setup[3]) == 1
    assert setup[3][0][1] == {"selection": "native"}
    assert result.records[0]["left"][0]["value"] == Decimal("0.123456789012345678901")
    assert result.records[0]["right"][0]["unknown"] == [False, None]
    assert result.pages == 2
    assert result.complete and result.total_count is None
    evidence = result.evidence
    assert evidence.total_semantics == "assembled_roots"
    assert evidence.coverage_basis == "validated_sources"
    assert evidence.reported_total is None
    assert evidence.collected_total == 1
    for name, value in evidence.sources.items():
        assert value["scope"] == name + "-private-scope"
        assert value["acquisition"]["reported_total"] == 1
        assert value["acquisition"]["collected_total"] == 1
        assert setup[1][name].closed
    assert "private-scope" not in (tmp_path / "collection-state.json").read_text()
    snapshot = SnapshotMeta(
        namespace="leaf:payment.sample",
        capability="payment.sample",
        scope="aggregate",
        source_kind="cdp",
        snapshot_id="sample",
        dataset_id=None,
        simulated=False,
        backend_complete=True,
        dataset_complete=True,
        fetched_at="2026-10-19T00:00:00Z",
        loaded_at="2026-10-19T00:00:00Z",
        source_observed_from=None,
        source_observed_to=None,
        row_count=1,
        acquisition=evidence.record(),
    )
    cache = Cache(tmp_path / "cache.sqlite3")
    cache.publish(snapshot, [(1, canonical(result.records[0]))])
    saved, rows = cache.read(snapshot.namespace)
    assert saved.acquisition == evidence.record()
    assert (
        AcquisitionEvidence.from_record(saved.acquisition).sources == evidence.sources
    )
    assert parse(rows[0][1]) == result.records[0]


@pytest.mark.parametrize("max_pages", [1, 2])
def test_sources_share_logical_page_budget_and_do_not_assemble_on_exhaustion(max_pages):
    setup = source_setup(first=response([{"id": "one"}, {"id": "two"}], 3))
    setup[1]["left"].responses.append(response([{"id": "three"}], 3))
    with pytest.raises(CliError) as rejected:
        collect(setup, max_pages=max_pages)
    assert rejected.value.code == "TIMEOUT"
    assert len(setup[1]["left"].requests) == max_pages
    assert setup[1]["right"].requests == []
    assert setup[3] == []
    assert setup[1]["left"].closed


def test_sources_share_one_deadline(monkeypatch):
    import dogopencli.collect as engine

    now = [0.0]
    monkeypatch.setattr(engine, "_monotonic", lambda: now[0])
    setup = source_setup()
    execute = setup[1]["left"].execute

    def slow(request, *, timeout):
        result = execute(request, timeout=timeout)
        now[0] += 2
        return result

    setup[1]["left"].execute = slow
    with pytest.raises(CliError) as rejected:
        collect(setup, budget_seconds=1)
    assert rejected.value.code == "TIMEOUT"
    assert setup[1]["right"].requests == []
    assert setup[3] == []


def test_source_width_fallback_also_consumes_the_global_page_budget():
    setup = source_setup(first=response([{"id": "one"}], 2))
    sources, streams, declared, _, _, _ = setup
    native, scope = sources["left"]
    native.contract = replace(native.contract, page_size=4, allowed_page_sizes=(4, 2))
    declared["sources"]["left"]["paging"]["page_sizes"] = [4, 2]
    streams["left"].responses.append(response([{"id": "one"}, {"id": "two"}], 2))
    with pytest.raises(CliError) as rejected:
        collect(setup, max_pages=2)
    assert rejected.value.code == "TIMEOUT"
    assert rejected.value.meta["source"] == "right"
    assert streams["left"].requests == [
        {"rowStart": 0, "pageSize": 4},
        {"rowStart": 0, "pageSize": 2},
    ]
    assert streams["right"].requests == []
    assert setup[3] == []


@pytest.mark.parametrize(
    "second",
    [
        {"success": False},
        response([{"id": "one"}], 2),
        response([{"id": "one"}] * 2, 2),
        response([{"id": "one", "v": 1}, {"id": "one", "v": 2}], 2),
    ],
)
def test_failed_or_incomplete_required_source_never_becomes_empty_children(second):
    setup = source_setup(second=second)
    with pytest.raises(CliError) as rejected:
        collect(setup)
    assert rejected.value.meta["source"] == "right"
    assert rejected.value.meta["sources"]["left"]["acquisition"]["reported_total"] == 1
    assert "right" in rejected.value.meta["sources"]
    assert setup[3] == []
    assert all(stream.closed for stream in setup[1].values())


def test_successful_empty_source_is_preserved_as_empty_children():
    setup = source_setup(second=response([], 0))
    result = collect(setup)
    assert result.records[0]["right"] == []
    assert result.evidence.sources["right"]["acquisition"]["reported_total"] == 0


@pytest.mark.parametrize("assembled", [[{"parent": "one"}] * 2, [{}], None, [None]])
def test_aggregate_identity_and_shape_must_be_valid(assembled):
    setup = source_setup()
    values = list(setup)
    values[4] = lambda rows, parameters: assembled
    with pytest.raises(CliError):
        collect(tuple(values))


@pytest.mark.parametrize(
    "fault",
    [
        "scope",
        "incomplete",
        "nested",
        "fake_total",
        "root_incomplete",
        "missing_sources",
    ],
)
def test_cached_source_evidence_cannot_drop_or_invent_required_quality(fault):
    record = deepcopy(collect(source_setup()).evidence.record())
    source = record["sources"]["right"]
    if fault == "scope":
        source.pop("scope")
    elif fault == "incomplete":
        source["acquisition"]["scope_complete"] = False
    elif fault == "nested":
        source["acquisition"]["sources"] = {}
    elif fault == "fake_total":
        record["reported_total"] = 2
    elif fault == "missing_sources":
        record.pop("sources")
        record.pop("coverage_basis")
    else:
        record["scope_complete"] = False
    with pytest.raises(CliError):
        AcquisitionEvidence.from_record(record)
