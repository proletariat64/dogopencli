"""Flat List source declarations and installed runtime publication boundaries."""

import json
from copy import deepcopy
from decimal import Decimal
from zipfile import ZipFile

import pytest

pytest_plugins = ["integration.test_get_sdk"]

FLAGS = ("--left-scope", "LEFT", "--right-scope", "RIGHT")
COMMAND = ("payment", "synthetic.sources")


def package(tmp_path):
    root = tmp_path / "source-package"
    root.mkdir()
    manifest = {
        "domain": "payment",
        "name": "synthetic.sources",
        "adapter": "adapter.py:adapter",
        "operations": {
            "list": {
                "description": "Independent synthetic source scopes",
                "parameters": [
                    {
                        "name": name,
                        "type": "string",
                        "required": True,
                        "description": "Native source scope",
                    }
                    for name in ("left-scope", "right-scope")
                ],
            }
        },
        "fields": [],
        "identity": ["parentRef"],
        "summary": "Synthetic source assembly",
        "purpose": "Preserve independent source records",
        "identity_description": "Parent references present in either source",
        "limitations": [],
        "examples": [],
        "dataset": {"relation": "synthetic_sources"},
        "collection": {
            "provider": "general",
            "primary_id": {"type": "field", "fields": ["parentRef"]},
            "sources": {
                "left": {
                    "paging": {"mode": "offset", "page_sizes": [2]},
                    "primary_id": {"type": "hash", "fields": ["parentRef", "day"]},
                },
                "right": {
                    "paging": {"mode": "offset", "page_sizes": [2]},
                    "primary_id": {"type": "field", "fields": ["id"]},
                },
            },
        },
    }
    (root / "leaf.json").write_text(json.dumps(manifest))
    (root / "revision.txt").write_text("v1")
    (root / "adapter.py").write_text("""from pathlib import Path
from dogopencli.contracts import EndpointContract
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse

class Inquiry:
    page_url = "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
    def __init__(self, name, scope, revision):
        self.name = "payment.synthetic.sources." + name
        self.contract = EndpointContract(
            method="GET", host="iglobalfundcontrol.alipay.com",
            path="/api/synthetic/" + revision + "/sources/" + name,
            page_size=2, one_based=False,
            allowed_body_keys=frozenset({"scope", "rowStart", "pageSize"}),
            fixed_body_values=(("scope", scope), ("pageSize", 2)),
        )
    def page_body(self, scope, position, page_size):
        return {"scope": scope, "rowStart": position, "pageSize": page_size}
    def parse_rows(self, body):
        value = parse(body)
        if not isinstance(value, dict) or type(value.get("success")) is not bool:
            raise CliError("INVALID_RESPONSE", "invalid source success")
        if not value["success"]:
            raise CliError("BUSINESS_QUERY_FAILED", "source rejected")
        return value.get("rows"), value.get("total")

class Adapter:
    def source_capability(self, name, parameters):
        return Inquiry(name, self.source_scope(name, parameters),
                       Path(__file__).with_name("revision.txt").read_text())
    def source_scope(self, name, parameters):
        return parameters[name + "_scope"]
    def scope(self, parameters): return canonical(parameters)
    def filter(self, records, parameters): return records
    def assemble(self, records_by_source, parameters):
        parents = {}
        for name, rows in records_by_source.items():
            for row in rows:
                parent = parents.setdefault(row["parentRef"],
                    {"parentRef": row["parentRef"], "left": [], "right": []})
                parent[name].append(row)
        return list(parents.values())

adapter = Adapter()
""")
    return root


def install(cli, root, tmp_path, kind="directory"):
    cli("domain", "enable", "payment")
    if kind == "zip":
        archive_path = tmp_path / "sources.zip"
        with ZipFile(archive_path, "w") as archive:
            for path in root.iterdir():
                archive.write(path, path.name)
        root = archive_path
    cli("plugins", "install", str(root))


def query(cli, action, *arguments, code=0):
    return cli(COMMAND[0], action, COMMAND[1], *arguments, code=code)


def response(rows, total=None, success=True):
    return {
        "status": 200,
        "body": {
            "success": success,
            "rows": rows,
            "total": len(rows) if total is None else total,
        },
    }


def sources():
    return (
        [
            {
                "parentRef": "A",
                "day": "2026-10-01",
                "amount": Decimal("0.1234567890123456789"),
                "unknown": {"nested": [None, False, "", 0]},
            }
        ],
        [{"id": "cash-one", "parentRef": "B", "amount": "1.0000"}],
    )


def expected(left, right):
    return [
        {"parentRef": "A", "left": left, "right": []},
        {"parentRef": "B", "left": [], "right": right},
    ]


@pytest.mark.parametrize("kind", ["directory", "zip"])
def test_source_runtime_refresh_offline_preserves_children_and_source_evidence(
    detail_cli, tmp_path, kind
):
    cli, browser, _ = detail_cli
    install(cli, package(tmp_path), tmp_path, kind)
    left, right = sources()
    browser.business_script.extend([response(left), response(right)])
    refreshed = query(cli, "refresh", *FLAGS, "--require-complete")
    assert refreshed["data"]["row_count"] == 2
    saved = query(cli, "list", "--limit", "0", "--require-complete")
    assert saved["data"] == expected(left, right)
    acquisition = saved["meta"]["acquisition"]
    assert acquisition["coverage_basis"] == "validated_sources"
    assert acquisition["reported_total"] is None
    assert acquisition["total_semantics"] == "assembled_roots"
    assert acquisition["sources"].keys() == {"left", "right"}
    for name in ("left", "right"):
        source = acquisition["sources"][name]
        assert source["scope"] == name.upper()
        assert source["acquisition"]["reported_total"] == 1
        assert source["acquisition"]["collected_total"] == 1
    assert browser.business_requests == [
        {"scope": "LEFT", "rowStart": 0, "pageSize": 2},
        {"scope": "RIGHT", "rowStart": 0, "pageSize": 2},
    ]
    count = len(browser.business_requests)
    replay = query(cli, "list", "--limit", "0", "--require-complete")
    assert replay["data"] == saved["data"]
    assert replay["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert replay["meta"]["acquisition"] == acquisition
    assert len(browser.business_requests) == count


@pytest.mark.parametrize("fault", ["business", "schema", "incomplete", "duplicate"])
def test_required_source_failure_is_atomic_and_keeps_prior_capture(
    detail_cli, tmp_path, fault
):
    cli, browser, _ = detail_cli
    install(cli, package(tmp_path), tmp_path)
    left, right = sources()
    browser.business_script.extend([response(left), response(right)])
    query(cli, "refresh", *FLAGS, "--require-complete")
    saved = query(cli, "list", "--limit", "0")
    bad = response(right)
    if fault == "business":
        bad["body"]["success"] = False
    elif fault == "schema":
        bad["body"]["rows"] = None
    elif fault == "incomplete":
        bad["body"]["total"] = 2
    else:
        bad = response(right * 2)
    browser.business_script.extend([response(left), bad])
    failed = query(cli, "refresh", *FLAGS, code=1)
    assert failed["data"] is None
    assert failed["meta"]["source"] == "right"
    assert "left" in failed["meta"]["sources"]
    replay = query(cli, "list", "--limit", "0")
    assert replay["data"] == saved["data"]
    assert replay["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_successful_empty_sources_do_not_replace_saved_parents(detail_cli, tmp_path):
    cli, browser, _ = detail_cli
    install(cli, package(tmp_path), tmp_path)
    left, right = sources()
    browser.business_script.extend([response(left), response(right)])
    query(cli, "refresh", *FLAGS, "--require-complete")
    saved = query(cli, "list", "--limit", "0")
    browser.business_script.extend([response([]), response([])])
    empty = query(cli, "refresh", *FLAGS, "--require-complete")
    assert empty["data"]["row_count"] == 0
    assert empty["data"]["published"] is False
    assert empty["meta"]["acquisition"]["coverage_basis"] == "validated_sources"
    replay = query(cli, "list", "--limit", "0")
    assert replay["data"] == saved["data"]
    assert replay["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_source_native_contract_change_invalidates_replay_without_queries(
    detail_cli, tmp_path
):
    cli, browser, config = detail_cli
    install(cli, package(tmp_path), tmp_path)
    left, right = sources()
    browser.business_script.extend([response(left), response(right)])
    query(cli, "refresh", *FLAGS, "--require-complete")
    installed = config / "plugins/payment/synthetic.sources"
    (installed / "revision.txt").write_text("v2")
    count = len(browser.business_requests)
    failed = query(cli, "list", code=1)
    assert failed["error"]["code"] == "CACHE_CONTRACT_CHANGED"
    assert len(browser.business_requests) == count


def test_global_page_budget_cannot_be_reused_for_each_source(detail_cli, tmp_path):
    cli, browser, config = detail_cli
    install(cli, package(tmp_path), tmp_path)
    left, right = sources()
    browser.business_script.extend([response(left), response(right)])
    query(cli, "refresh", *FLAGS)
    saved = query(cli, "list", "--limit", "0")
    manifest_path = config / "plugins/payment/synthetic.sources/leaf.json"
    original = manifest_path.read_text()
    manifest = json.loads(original)
    manifest["collection"]["max_pages"] = 1
    manifest_path.write_text(json.dumps(manifest))
    browser.business_script.append(response(left))
    count = len(browser.business_requests)
    failed = query(cli, "refresh", *FLAGS, code=1)
    assert failed["error"]["code"] == "TIMEOUT"
    assert failed["meta"]["source"] == "right"
    assert len(browser.business_requests) == count + 1
    manifest_path.write_text(original)
    assert query(cli, "list", "--limit", "0")["data"] == saved["data"]


@pytest.mark.parametrize(
    "fault",
    [
        "both_modes",
        "neither_mode",
        "empty_sources",
        "empty_name",
        "invalid_name",
        "nested_sources",
        "source_provider",
        "source_budget",
        "source_extra_key",
        "source_missing_identity",
        "source_unproven",
        "aggregate_unproven",
        "empty_source_fields",
        "source_field_multiple_keys",
        "source_empty_key",
        "source_missing_paging",
        "single_response_empty_widths",
        "single_response_multiple_widths",
        "single_response_bool_width",
        "single_response_too_large",
        "single_response_unproven",
    ],
)
def test_invalid_source_and_qualified_response_declarations_fail_static_install(
    detail_cli, tmp_path, fault
):
    cli, browser, config = detail_cli
    root = package(tmp_path)
    path = root / "leaf.json"
    manifest = json.loads(path.read_text())
    collection = manifest["collection"]
    source = collection["sources"]["right"]
    if fault == "both_modes":
        collection["paging"] = {"mode": "offset", "page_sizes": [2]}
    elif fault == "neither_mode":
        collection.pop("sources")
    elif fault == "empty_sources":
        collection["sources"] = {}
    elif fault in {"empty_name", "invalid_name"}:
        collection["sources"]["" if fault == "empty_name" else "not.a.source"] = (
            collection["sources"].pop("right")
        )
    elif fault == "nested_sources":
        source["sources"] = {"nested": deepcopy(source)}
    elif fault == "source_provider":
        source["provider"] = "general"
    elif fault == "source_budget":
        source["budget_seconds"] = 60
    elif fault == "source_extra_key":
        source["latest_by"] = "version"
    elif fault == "source_missing_identity":
        source.pop("primary_id")
    elif fault in {"source_unproven", "aggregate_unproven"}:
        owner = source if fault == "source_unproven" else collection
        owner["primary_id"] = {"type": "unproven", "fields": []}
    elif fault == "empty_source_fields":
        source["primary_id"]["fields"] = []
    elif fault == "source_field_multiple_keys":
        source["primary_id"]["fields"] = ["id", "other"]
    elif fault == "source_empty_key":
        source["primary_id"]["fields"] = [" "]
    elif fault == "source_missing_paging":
        source.pop("paging")
    else:
        source["paging"]["mode"] = "single_response"
        if fault == "single_response_unproven":
            source["primary_id"] = {"type": "unproven", "fields": []}
        else:
            source["paging"]["page_sizes"] = {
                "single_response_empty_widths": [],
                "single_response_multiple_widths": [2, 1],
                "single_response_bool_width": [True],
                "single_response_too_large": [100001],
            }[fault]
    path.write_text(json.dumps(manifest))
    failed = cli("plugins", "install", str(root), code=1)
    assert failed["error"]["code"] == "INVALID_LEAF"
    assert not browser.business_requests
    assert not (config / "leaf-cache.sqlite3").exists()
    assert not (config / "duckdog.duckdb").exists()


def test_progress_keeps_source_arrivals_separate_from_assembled_roots(
    detail_cli, tmp_path
):
    from dogopencli.progress import observe

    cli, browser, _ = detail_cli
    install(cli, package(tmp_path), tmp_path)
    left, right = sources()
    browser.business_script.extend([response(left), response(right)])
    latest = {}
    current = {}

    def receive(facts):
        current.update(facts)
        latest.setdefault(current.get("source"), {}).update(current)

    with observe(receive):
        result = query(cli, "refresh", *FLAGS, "--require-complete")
    assert result["data"]["row_count"] == 2
    for name in ("left", "right"):
        facts = latest["payment.synthetic.sources." + name]
        assert facts["source_pages"] == 1
        assert facts["source_rows_received"] == 1
        assert facts["source_total_rows"] == 1
        assert facts["request_attempts"] == 1
    assert "LEFT" not in repr(latest)
    assert "amount" not in repr(latest)
