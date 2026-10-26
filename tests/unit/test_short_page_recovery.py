"""Stable sparse datasets, hint repair, scoped FIFO and successful publication."""

import json
from argparse import Namespace
from contextlib import contextmanager
from dataclasses import replace

import pytest

from dogopencli.collect import collect_list
from dogopencli.collection_state import latest_holes, state_key
from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import BUSINESS_QUERY_FAILED, CliError
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.registry import Leaf
from dogopencli.result_policy import (
    AcquisitionEvidence,
    check_complete,
    evaluate_result,
    prepare_result,
)
from dogopencli.transport import OriginMetadata, TransportResponse

ORIGIN = OriginMetadata("fixture", True, None, None, None, None, None)


class Native:
    name = "liquidity.fixture.list"

    def __init__(self, size=8, mode="offset", one_based=False):
        self.mode = mode
        self.contract = EndpointContract(
            method="GET",
            host="fixture.invalid",
            path="/accounts",
            page_size=size,
            one_based=one_based,
            allowed_body_keys=frozenset({"rowStart", "pageNo", "pageSize"}),
            allowed_page_sizes=tuple(range(1, size + 1)),
            total_semantics="unknown",
        )

    def page_body(self, scope, position, size):
        return {
            "rowStart" if self.mode == "offset" else "pageNo": position,
            "pageSize": size,
        }

    def parse_rows(self, raw):
        doc = parse(raw)
        if not doc["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend refusal", meta=doc.get("error")
            )
        return doc["rows"], doc["total"]

    def parse_page(self, raw):
        rows, total = self.parse_rows(raw)
        doc = parse(raw)
        return ParsedPage(rows, doc["page"], doc["size"], total, None)

    def pagination_hole(self, error):
        return (error.meta or {}).get("record_hole")


class Dataset:
    def __init__(self, capability, length=25, holes=(), errors=None):
        self.capability = capability
        self.rows = [
            {"id": f"private-account-{n}", "amount": "1.000", "unknown": [False, None]}
            for n in range(length)
        ]
        for position in holes:
            self.rows[position] = None
        self.errors = errors or {}
        self.requests = []
        self.fail = None
        self.shuffle = False

    def execute(self, request, *, timeout):
        body = request.body
        size = body["pageSize"]
        start = body.get("rowStart")
        if start is None:
            start = (body["pageNo"] - self.capability.contract.one_based) * size
        self.requests.append((start, size))
        if self.fail:
            raise self.fail
        error = next(
            (self.errors[p] for p in range(start, start + size) if p in self.errors),
            None,
        )
        rows = [row for row in self.rows[start : start + size] if row is not None]
        if self.shuffle and size < self.capability.contract.page_size:
            rows = list(reversed(rows))
        doc = {
            "success": error is None,
            "rows": rows,
            "total": "unreliable",
            "size": size,
            "page": body.get("pageNo"),
        }
        if error:
            doc["error"] = {"record_hole": error}
        return TransportResponse(200, canonical(doc).encode(), ORIGIN)

    def close(self):
        pass


def settings(capability):
    return {
        "provider": "general",
        "paging": {
            "mode": capability.mode,
            "page_sizes": [capability.contract.page_size],
            "termination": "short_page",
        },
        "primary_id": {"type": "field", "fields": ["id"]},
    }


def acquire(source, dataset, state=None, scope="private-scope", **kwargs):
    return collect_list(
        source,
        dataset,
        scope,
        settings(source),
        domain="liquidity",
        leaf_id="liquidity.fixture",
        state_file=state,
        **kwargs,
    )


@pytest.mark.parametrize(
    "mode,one_based", [("offset", False), ("page_number", False), ("page_number", True)]
)
@pytest.mark.parametrize("holes", [(), (0, 3, 4, 15, 16), (23, 24)])
def test_sparse_traversal_retains_exact_rows_and_exits_success(mode, one_based, holes):
    source = Native(mode=mode, one_based=one_based)
    data = Dataset(source, holes=holes)
    result = acquire(source, data)
    assert result.records == [row for row in data.rows if row is not None]
    assert result.complete
    attempt = result.evidence.attempts[-1]
    # Successful empty positions after the last actual row are terminal, rather
    # than interior holes. No backend total is used to infer hidden tail rows.
    interior = [p for p in holes if p < attempt["source_end"]]
    assert attempt["hole_count"] == len(interior)
    assert result.pages == len(data.requests)
    assert attempt["termination_reason"] == "two_empty_batches"
    assert all(w == source.contract.page_size for _, w in data.requests[-2:])
    replay = AcquisitionEvidence.from_record(result.evidence.record())
    assert replay == result.evidence
    check_complete(replay, require_complete=True)
    decision = evaluate_result(replay, mode="refresh", require_complete=True)
    assert decision.exit_code == 0 and decision.publishable and decision.error is None
    if interior:
        assert decision.warnings[0]["code"] == "PAGINATION_HOLES_BYPASSED"


def test_warm_accounts_shaped_query_reuses_only_verified_hole(tmp_path):
    source = Native(size=1000)
    state = tmp_path / "collection-state.json"
    first = Dataset(source, length=3736, holes=(2066,))
    cold = acquire(source, first, state)
    second = Dataset(source, length=3736, holes=(2066,))
    warm = acquire(source, second, state)
    assert warm.records == cold.records
    assert len(second.requests) < len(first.requests)
    assert warm.evidence.attempts[-1]["history_matched"] == 1
    assert (2066, 1) in second.requests
    stored = (tmp_path / "collection-state.holes.json").read_text()
    assert "private-account" not in stored and "private-scope" not in stored
    assert warm.evidence.attempts[-1]["history_saved"]


@pytest.mark.parametrize("change", ["repaired", "shifted", "new"])
def test_hints_never_skip_repaired_shifted_or_new_records(tmp_path, change):
    source = Native()
    state = tmp_path / "collection-state.json"
    acquire(source, Dataset(source, holes=(3,)), state)
    holes = {"repaired": (), "shifted": (5,), "new": (3, 10)}[change]
    data = Dataset(source, holes=holes)
    result = acquire(source, data, state)
    assert result.records == [r for r in data.rows if r is not None]
    assert result.evidence.attempts[-1]["history_matched"] == (change == "new")
    assert result.evidence.attempts[-1]["hole_count"] == len(holes)


def test_fifo_records_no_holes_and_never_resurrects_older_history(tmp_path):
    source = Native()
    state = tmp_path / "collection-state.json"
    for _ in range(5):
        acquire(source, Dataset(source, holes=(3,)), state)
    acquire(source, Dataset(source), state)
    history = json.loads((tmp_path / "collection-state.holes.json").read_text())
    entries = next(iter(history["histories"].values()))
    assert len(entries) == 5 and entries[-1]["holes"] == []
    key = state_key("liquidity.fixture", source, "private-scope", (8,))
    assert latest_holes(state, key, settings(source)) == []
    changed = Dataset(source, holes=(5,))
    result = acquire(source, changed, state)
    assert result.evidence.attempts[-1]["history_checked"] == 0


def test_history_is_scoped_and_failed_latest_query_blocks_old_hints(tmp_path):
    source = Native()
    state = tmp_path / "collection-state.json"
    acquire(source, Dataset(source, holes=(3,)), state)
    other = acquire(source, Dataset(source), state, scope="other-filter")
    assert other.evidence.attempts[-1]["history_checked"] == 0
    broken = Dataset(source)
    broken.fail = CliError(BUSINESS_QUERY_FAILED, "unknown business failure")
    with pytest.raises(CliError):
        acquire(source, broken, state)
    result = acquire(source, Dataset(source, holes=(3,)), state)
    assert result.evidence.attempts[-1]["history_checked"] == 0


def test_explicit_record_errors_recover_multiple_contiguous_holes():
    source = Native()
    data = Dataset(source, errors={3: "missing-A", 4: "missing-B", 5: "missing-B"})
    result = acquire(source, data)
    assert result.complete
    assert result.records == [
        r for n, r in enumerate(data.rows) if n not in data.errors
    ]
    assert result.evidence.attempts[-1]["hole_count"] == 3
    assert result.evidence.arrivals == len(result.records)


def test_every_probe_consumes_the_shared_budget(tmp_path):
    source = Native()
    data = Dataset(source, holes=(3,))
    state = tmp_path / "collection-state.json"
    with pytest.raises(CliError) as error:
        acquire(source, data, state, max_pages=3)
    assert error.value.code == "TIMEOUT" and len(data.requests) == 3
    entry = next(
        iter(
            json.loads((tmp_path / "collection-state.holes.json").read_text())[
                "histories"
            ].values()
        )
    )[-1]
    assert entry["status"] == "failed"


def test_unqualified_probe_widths_and_cross_width_changes_are_not_excused():
    source = Native()
    source.contract = replace(source.contract, allowed_page_sizes=(8,))
    with pytest.raises(CliError, match="smaller widths"):
        acquire(source, Dataset(source, holes=(3,)))
    source = Native()
    data = Dataset(source, holes=(3,))
    data.shuffle = True
    with pytest.raises(CliError, match="changed across"):
        acquire(source, data)


def test_fixed_width_normal_final_short_page_needs_two_empty_batches():
    source = Native()
    source.contract = replace(source.contract, allowed_page_sizes=(8,))
    data = Dataset(source, length=11)
    result = acquire(source, data)
    assert result.complete and result.records == data.rows
    assert data.requests == [(0, 8), (8, 8), (16, 8), (24, 8)]


@pytest.mark.parametrize(
    "code", ["AUTH_REQUIRED", "INVALID_RESPONSE", "BUSINESS_QUERY_FAILED"]
)
def test_non_record_failures_never_become_holes(code):
    source = Native()
    data = Dataset(source)
    data.fail = CliError(code, "unclassified failure")
    with pytest.raises(CliError) as error:
        acquire(source, data)
    assert error.value.code == code and len(data.requests) == 1


def test_corrupt_latest_history_does_not_fall_back_to_valid_old_record(tmp_path):
    source = Native()
    state = tmp_path / "collection-state.json"
    acquire(source, Dataset(source, holes=(3,)), state)
    path = tmp_path / "collection-state.holes.json"
    document = json.loads(path.read_text())
    history = next(iter(document["histories"].values()))
    history.append({"status": "complete", "policy": settings(source), "holes": "bad"})
    path.write_text(json.dumps(document))
    result = acquire(source, Dataset(source, holes=(3,)), state)
    assert result.evidence.attempts[-1]["history_checked"] == 0


@pytest.mark.parametrize("kind", [[], {}, False, None])
def test_invalid_hole_kind_is_ignored_without_aborting_inquiry(tmp_path, kind):
    source = Native()
    state = tmp_path / "collection-state.json"
    acquire(source, Dataset(source, holes=(3,)), state)
    path = tmp_path / "collection-state.holes.json"
    document = json.loads(path.read_text())
    latest = next(iter(document["histories"].values()))[-1]
    latest["holes"][0]["kind"] = kind
    path.write_text(json.dumps(document))
    result = acquire(source, Dataset(source, holes=(3,)), state)
    assert result.complete and result.evidence.attempts[-1]["history_checked"] == 0


def test_deadline_before_first_request_records_failed_latest_query(tmp_path):
    source = Native()
    state = tmp_path / "collection-state.json"
    acquire(source, Dataset(source, holes=(3,)), state)
    data = Dataset(source, holes=(3,))
    with pytest.raises(CliError) as error:
        acquire(source, data, state, _deadline=-1)
    assert error.value.code == "TIMEOUT" and data.requests == []
    key = state_key("liquidity.fixture", source, "private-scope", (8,))
    assert latest_holes(state, key, settings(source)) == []
    history = json.loads((tmp_path / "collection-state.holes.json").read_text())
    assert history["histories"][key][-1]["status"] == "failed"


def test_busy_history_writer_does_not_fail_completed_query(tmp_path):
    import fcntl

    source = Native()
    state = tmp_path / "collection-state.json"
    with (tmp_path / "collection-state.holes.json.lock").open("w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = acquire(source, Dataset(source, holes=(3,)), state)
    assert result.complete and result.evidence.attempts[-1]["history_saved"] is False


@pytest.mark.parametrize("custom_trace", [False, True])
def test_cached_termination_and_hole_metadata_are_validated(custom_trace):
    source = Native()
    result = acquire(source, Dataset(source, holes=(3,)))
    record = result.evidence.record()
    record["attempts"][-1]["terminal_batches"][1]["start"] += 1
    if custom_trace:
        record["attempts"].append({"kind": "custom_query", "request_count": 1})
    with pytest.raises(CliError, match="termination"):
        AcquisitionEvidence.from_record(record)
    record = acquire(source, Dataset(source, holes=(3,))).evidence.record()
    record["attempts"][-1]["hole_count"] = 0
    if custom_trace:
        record["attempts"].append({"kind": "custom_query", "request_count": 1})
    with pytest.raises(CliError, match="holes"):
        AcquisitionEvidence.from_record(record)


def test_refresh_offline_replays_successful_hole_notice(tmp_path, monkeypatch, capsys):
    from dogopencli.leaves import runtime

    source = Native()
    data = Dataset(source, holes=(3, 4))

    class Adapter:
        def capability(self, parameters):
            return source

        def scope(self, parameters):
            return "private-scope"

        def filter(self, records, parameters):
            return records

    @contextmanager
    def session(**kwargs):
        class Session:
            def transport(self, capability):
                return data

        yield Session()

    monkeypatch.setattr(runtime, "inquiry_session", session)
    leaf = Leaf(
        domain="liquidity",
        name="fixture",
        path=tmp_path,
        adapter=Adapter(),
        manifest={
            "adapter": "adapter.py:adapter",
            "operations": {"list": {"parameters": []}},
            "identity": ["id"],
            "collection": settings(source),
        },
    )
    args = Namespace(
        limit=0,
        offset=0,
        fields=None,
        require_complete=True,
        require_fresh=False,
        live=False,
        with_detail=False,
        explicit_parameters=set(),
    )
    config = tmp_path / "config.toml"
    refreshed, meta = runtime.execute(leaf, "refresh", {}, args, config)
    assert meta["published"] and meta["complete"]
    prepared = prepare_result(meta, require_complete=True)
    assert prepared["warnings"][0]["code"] == "PAGINATION_HOLES_BYPASSED"
    calls = len(data.requests)
    offline, replay = runtime.execute(leaf, "list", {}, args, config)
    assert offline == [row for row in data.rows if row is not None]
    assert refreshed["row_count"] == len(offline) and len(data.requests) == calls
    assert canonical(replay["acquisition"]) == canonical(meta["acquisition"])
    assert replay["warnings"][0]["code"] == "PAGINATION_HOLES_BYPASSED"
    assert capsys.readouterr().err == ""


def test_mixed_terminal_kinds_do_not_combine_into_one_end_proof():
    from dogopencli.short_page import ShortPageWalk, TerminalPage

    def read(start, width):
        if start == 0:
            return [{"id": "last"}]
        if start == 8:
            return []
        raise TerminalPage(
            {
                "kind": "repeated_short_page",
                "requested_page": start // width + 1,
                "native_page": 1,
                "native_rows": 1,
            }
        )

    walk = ShortPageWalk(
        read, lambda row: row["id"], size=8, sizes={8}, numbered=True, observations=[]
    )
    assert walk.run([]) == [{"id": "last"}]
    assert [item["start"] for item in walk.terminal_batches] == [16, 24]
    assert all("native_terminal" in item for item in walk.terminal_batches)
