"""An unpaged qualified response needs no invented native page width."""

import json
from pathlib import Path

import pytest

from dogopencli.collect import collect_list
from dogopencli.contracts import EndpointContract
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.registry import validate_manifest
from dogopencli.transport import OriginMetadata, TransportResponse

SAMPLE = (
    Path(__file__).resolve().parents[2]
    / "tools/leaf-dev/example-single-response/leaf.json"
)


def declaration(mode="single_response", sizes=None):
    manifest = json.loads(SAMPLE.read_text())
    manifest["collection"]["paging"] = {
        "mode": mode,
        "page_sizes": [0] if sizes is None else sizes,
    }
    return manifest


class Unpaged:
    name = "collection.sample.response.list"

    def __init__(self, width=0):
        self.contract = EndpointContract(
            method="POST",
            host="fixture.invalid",
            path="/query",
            page_size=width,
            one_based=False,
            allowed_body_keys=frozenset({"query"}),
            fixed_body_values=(("query", "published"),),
            total_semantics="unknown",
        )

    def page_body(self, scope, position, size):
        assert scope == "published"
        assert position == 0
        assert size == 0
        return {"query": scope}

    def parse_rows(self, body):
        return parse(body)["rows"], None


class Script:
    def __init__(self, rows):
        self.rows = rows
        self.requests = []

    def execute(self, request, *, timeout):
        assert timeout > 0
        self.requests.append(request.body)
        return TransportResponse(
            200,
            canonical({"rows": self.rows}).encode(),
            OriginMetadata("fixture", True, None, None, None, None, None),
        )


def test_unpaged_response_is_one_request_without_learning(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("unpaged inquiry cannot learn or reuse page widths")

    monkeypatch.setattr("dogopencli.collection_state.preferred_page_size", unexpected)
    monkeypatch.setattr("dogopencli.collection_state.remember_page_size", unexpected)
    manifest = declaration()
    validate_manifest(manifest)
    rows = [{"id": i, "children": [False, None, "0.00"]} for i in range(3)]
    stream = Script(rows)
    progress = []
    state_file = tmp_path / "collection-state.json"
    result = collect_list(
        Unpaged(),
        stream,
        "published",
        manifest["collection"],
        domain="collection",
        leaf_id="collection.sample.response",
        state_file=state_file,
        progress=lambda done, total: progress.append((done, total)),
    )
    assert result.records == rows
    assert result.complete and result.pages == 1 and result.page_size == 0
    assert result.total_count is None
    assert stream.requests == [{"query": "published"}]
    assert progress == [(1, 1)]
    assert not state_file.exists()
    evidence = result.evidence.meta()
    assert evidence["reported_total"] is None
    assert evidence["acquisition"]["coverage_basis"] == "qualified_single_response"
    assert evidence["acquisition"]["arrivals"] == len(rows)
    assert evidence["acquisition"]["unique_count"] == len(rows)


@pytest.mark.parametrize("mode", ["offset", "page_number", "single"])
def test_ordinary_modes_reject_zero_width(mode):
    with pytest.raises(CliError):
        validate_manifest(declaration(mode))


@pytest.mark.parametrize("sizes", [[False], [-1], [100001], [2, 0]])
def test_unpaged_declaration_retains_size_validation(sizes):
    with pytest.raises(CliError):
        validate_manifest(declaration(sizes=sizes))


def test_unpaged_policy_rejects_positive_width_endpoint_before_request():
    stream = Script([])
    with pytest.raises(CliError) as rejected:
        collect_list(
            Unpaged(width=2),
            stream,
            "published",
            declaration()["collection"],
            domain="collection",
            leaf_id="collection.sample.response",
        )
    assert rejected.value.code == "REQUEST_NOT_ALLOWED"
    assert stream.requests == []
