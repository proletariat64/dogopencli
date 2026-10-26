"""Declared native Get shapes and exact identity paths at the installed CLI."""

import json
from copy import deepcopy
from decimal import Decimal
from zipfile import ZipFile

import pytest

pytest_plugins = ["integration.test_get_sdk"]


def package(tmp_path, *, shape=None, paths=None, binding=False):
    root = tmp_path / "native-shape"
    root.mkdir()
    identity = {"description": "Native member identity"}
    identity["paths" if paths is not None else "fields"] = (
        paths if paths is not None else ["id"]
    )
    operation = {
        "description": "Read a native root",
        "parameters": [],
        "lookup": {"name": "reference", "description": "Native business reference"},
        "result_identity": identity,
    }
    if shape is not None:
        operation["result_shape"] = shape
    manifest = {
        "domain": "payment",
        "name": "synthetic.shapes",
        "adapter": "adapter.py:adapter",
        "operations": {"get": operation},
        "fields": [],
        "identity": [],
        "summary": "Native Get shapes",
        "purpose": "Preserve qualified native roots",
        "identity_description": "No List identity",
        "limitations": [],
        "examples": [],
    }
    if binding:
        operation["list_binding"] = {"identity_field": "reference"}
        manifest.update(
            identity=["reference"],
            dataset={"relation": "synthetic_shapes"},
            collection={
                "provider": "general",
                "paging": {"mode": "page_number", "page_sizes": [2]},
                "primary_id": {"type": "field", "fields": ["reference"]},
            },
        )
        manifest["operations"]["list"] = {
            "description": "Read native references",
            "parameters": [],
        }
    (root / "leaf.json").write_text(json.dumps(manifest))
    (
        root / "adapter.py"
    ).write_text("""from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse

class Detail:
    name = "payment.synthetic.shapes.get"
    page_url = "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
    contract = EndpointContract(
        method="GET", host="iglobalfundcontrol.alipay.com",
        path="/api/synthetic/detail", page_size=0, one_based=False,
        allowed_body_keys=frozenset({"reference"}),
    )
    def request_body(self, parameters, identity):
        return {"reference": identity}
    def parse_detail(self, body, parameters, identity):
        value = parse(body)
        if not isinstance(value, dict) or type(value.get("success")) is not bool:
            raise CliError("INVALID_RESPONSE", "invalid native status")
        if not value["success"]:
            raise CliError("BUSINESS_QUERY_FAILED", "rejected native inquiry")
        if value.get("reference") != identity:
            raise CliError("INVALID_RESPONSE", "native reference contradicts lookup")
        return value.get("data")

class Inquiry:
    name = "payment.synthetic.shapes.list"
    page_url = Detail.page_url
    contract = EndpointContract(
        method="GET", host="iglobalfundcontrol.alipay.com",
        path="/api/synthetic/list", page_size=2, one_based=False,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
    )
    def page_body(self, scope, position, page_size):
        return {"pageNo": position, "pageSize": page_size}
    def parse_page(self, body):
        value = parse(body)
        return ParsedPage(value["rows"], 0, 2, len(value["rows"]), 1)

class Adapter:
    def detail_capability(self, parameters): return Detail()
    def capability(self, parameters): return Inquiry()
    def scope(self, parameters): return "all"
    def filter(self, records, parameters): return records

adapter = Adapter()
""")
    return root


def install(cli, root, tmp_path, kind="directory"):
    cli("domain", "enable", "payment")
    if kind == "zip":
        archive_path = tmp_path / "native-shape.zip"
        with ZipFile(archive_path, "w") as archive:
            for path in root.iterdir():
                archive.write(path, path.name)
        root = archive_path
    cli("plugins", "install", str(root))


def reply(value, reference="REF", **extra):
    return {
        "status": 200,
        "body": {"success": True, "reference": reference, "data": value, **extra},
    }


def native(identity=0):
    return {
        "id": identity,
        "amount": Decimal("0.1234567890123456789012345"),
        "unknown": {"nested": [None, False, 0, "", {"success": False}]},
    }


@pytest.mark.parametrize("kind", ["directory", "zip"])
@pytest.mark.parametrize("shape", [None, "object", "array"])
def test_native_shape_preserves_types_projection_and_storage(
    detail_cli, tmp_path, shape, kind
):
    cli, browser, config = detail_cli
    install(cli, package(tmp_path, shape=shape), tmp_path, kind)
    before = sorted(path.relative_to(config) for path in config.rglob("*"))
    value = [native(0), native(-1)] if shape == "array" else native()
    browser.business_script.append(reply(value))
    result = cli("payment", "get", "synthetic.shapes", "REF", "--require-complete")
    assert result["data"] == value
    assert result["meta"]["returned_count"] == (2 if shape == "array" else 1)
    assert result["meta"]["detail_scope"] == "native_root"
    assert result["meta"]["complete"] is True
    assert result["meta"]["dataset_complete"] is True
    assert (
        result["meta"]["acquisition"]["coverage_basis"] == "qualified_single_response"
    )
    assert result["meta"]["reported_total"] is None
    assert result["meta"]["publication"]["status"] == "not_requested"
    assert browser.business_requests == [{"reference": "REF"}]
    browser.business_script.append(reply(value))
    projected = cli("payment", "get", "synthetic.shapes", "REF", "--fields", "amount")
    expected = (
        [{"amount": row["amount"]} for row in value]
        if shape == "array"
        else {"amount": value["amount"]}
    )
    assert projected["data"] == expected
    assert projected["meta"]["returned_count"] == result["meta"]["returned_count"]
    assert sorted(path.relative_to(config) for path in config.rglob("*")) == before
    assert not (config / "leaf-cache.sqlite3").exists()
    assert not (config / "duckdog.duckdb").exists()


def test_qualified_empty_array_stays_empty_after_projection(detail_cli, tmp_path):
    cli, browser, _ = detail_cli
    install(cli, package(tmp_path, shape="array"), tmp_path)
    browser.business_script.append(reply([]))
    result = cli("payment", "get", "synthetic.shapes", "REF", "--fields", "id")
    assert result["data"] == []
    assert result["meta"]["returned_count"] == 0


def test_array_nested_identity_retains_order_and_scalar_types(detail_cli, tmp_path):
    cli, browser, _ = detail_cli
    install(cli, package(tmp_path, shape="array", paths=[["detail", "id"]]), tmp_path)
    value = [
        {"detail": {"id": 0}, "version": "first"},
        {"detail": {"id": "0"}, "version": "second"},
    ]
    browser.business_script.append(reply(value))
    assert cli("payment", "get", "synthetic.shapes", "REF")["data"] == value


def test_fields_identity_treats_dot_as_a_literal_key(detail_cli, tmp_path):
    cli, browser, _ = detail_cli
    root = package(tmp_path)
    path = root / "leaf.json"
    manifest = json.loads(path.read_text())
    manifest["operations"]["get"]["result_identity"]["fields"] = ["native.id"]
    path.write_text(json.dumps(manifest))
    install(cli, root, tmp_path)
    value = {"native.id": -1, "native": {"id": False}}
    browser.business_script.append(reply(value))
    assert cli("payment", "get", "synthetic.shapes", "REF")["data"] == value


def test_nested_path_may_repeat_literal_segment_names(detail_cli, tmp_path):
    cli, browser, _ = detail_cli
    install(cli, package(tmp_path, paths=[["data", "data", "id"]]), tmp_path)
    value = {"data": {"data": {"id": -1}}, "unknown": [False, None]}
    browser.business_script.append(reply(value))
    assert cli("payment", "get", "synthetic.shapes", "REF")["data"] == value


@pytest.mark.parametrize(
    "fault",
    [
        "both_identity_forms",
        "neither_identity_form",
        "empty_paths",
        "empty_path",
        "empty_key",
        "blank_key",
        "duplicate_paths",
        "numeric_segment",
        "unknown_shape",
        "array_binding",
    ],
)
def test_invalid_native_shape_declarations_fail_install(detail_cli, tmp_path, fault):
    cli, browser, config = detail_cli
    root = (
        package(tmp_path, shape="array", binding=True)
        if fault == "array_binding"
        else (package(tmp_path, paths=[["detail", "id"]]))
    )
    path = root / "leaf.json"
    manifest = json.loads(path.read_text())
    operation = manifest["operations"]["get"]
    identity = operation["result_identity"]
    if fault == "both_identity_forms":
        identity["fields"] = ["id"]
    elif fault == "neither_identity_form":
        identity.pop("paths")
    elif fault == "empty_paths":
        identity["paths"] = []
    elif fault == "empty_path":
        identity["paths"] = [[]]
    elif fault in {"empty_key", "blank_key"}:
        identity["paths"] = [["" if fault == "empty_key" else " "]]
    elif fault == "duplicate_paths":
        identity["paths"] = [["detail", "id"], ["detail", "id"]]
    elif fault == "numeric_segment":
        identity["paths"] = [["detail", 0]]
    elif fault == "unknown_shape":
        operation["result_shape"] = "tree"
    path.write_text(json.dumps(manifest))
    result = cli("plugins", "install", str(root), code=1)
    assert result["error"]["code"] == "INVALID_LEAF"
    assert not browser.business_requests
    assert not (config / "leaf-cache.sqlite3").exists()
    assert not (config / "duckdog.duckdb").exists()


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        [None],
        [[]],
        [{}],
        [{"id": None}],
        [{"id": True}],
        [{"id": {}}],
        [{"id": []}],
        [{"id": " "}],
        [{"id": 1}, {"id": 1}],
    ],
)
def test_array_malformed_or_ambiguous_identity_fails(detail_cli, tmp_path, value):
    cli, browser, _ = detail_cli
    install(cli, package(tmp_path, shape="array"), tmp_path)
    browser.business_script.append(reply(value))
    result = cli("payment", "get", "synthetic.shapes", "REF", code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result["data"] is None


@pytest.mark.parametrize("kind", ["directory", "zip"])
def test_nested_identity_preserves_entire_root_and_exact_literal_keys(
    detail_cli, tmp_path, kind
):
    cli, browser, _ = detail_cli
    paths = [["quotationDetail", "quotationId"], ["literal.dot", "0"]]
    install(cli, package(tmp_path, paths=paths), tmp_path, kind)
    value = {
        "quotationDetail": {"quotationId": 0, "amount": Decimal("0.00000001")},
        "literal.dot": {"0": "SECOND"},
        "logs": [{"unknown": [None, False]}],
        "product": {"success": False},
    }
    browser.business_script.append(reply(value))
    assert cli("payment", "get", "synthetic.shapes", "REF")["data"] == value
    browser.business_script.append(reply(value))
    assert cli("payment", "get", "synthetic.shapes", "REF", "--fields", "logs")[
        "data"
    ] == {"logs": value["logs"]}


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"detail": None},
        {"detail": []},
        {"detail": {}},
        {"detail": {"id": None}},
        {"detail": {"id": True}},
        {"detail": {"id": []}},
        {"detail": {"id": {}}},
    ],
)
def test_nested_identity_failures_validate_before_projection(
    detail_cli, tmp_path, value
):
    cli, browser, _ = detail_cli
    install(cli, package(tmp_path, paths=[["detail", "id"]]), tmp_path)
    browser.business_script.append(reply({**value, "visible": "preserved"}))
    result = cli(
        "payment", "get", "synthetic.shapes", "REF", "--fields", "visible", code=1
    )
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result["data"] is None


@pytest.mark.parametrize("shape", [None, "array"])
@pytest.mark.parametrize("fault", ["business", "echo", "auth"])
def test_failures_never_turn_into_empty_success(detail_cli, tmp_path, shape, fault):
    cli, browser, _ = detail_cli
    install(cli, package(tmp_path, shape=shape), tmp_path)
    response = reply([native()] if shape == "array" else native())
    if fault == "business":
        response["body"]["success"] = False
    elif fault == "echo":
        response["body"]["reference"] = "WRONG"
    else:
        response["status"] = 401
    browser.business_script.append(response)
    result = cli("payment", "get", "synthetic.shapes", "REF", code=1)
    assert result["data"] is None
    assert (
        result["error"]["code"]
        == {
            "business": "BUSINESS_QUERY_FAILED",
            "echo": "INVALID_RESPONSE",
            "auth": "AUTH_REQUIRED",
        }[fault]
    )


@pytest.mark.parametrize("identity", ["", " "])
def test_blank_lookup_fails_before_authentication(
    detail_cli, tmp_path, monkeypatch, identity
):
    cli, browser, _ = detail_cli
    install(cli, package(tmp_path), tmp_path)

    def forbidden(**kwargs):
        pytest.fail("blank lookup must fail before opening an inquiry session")

    monkeypatch.setattr("dogopencli.leaves.runtime.inquiry_session", forbidden)
    result = cli("payment", "get", "synthetic.shapes", identity, code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


@pytest.mark.parametrize("shape,paths", [("array", None), (None, [["detail", "id"]])])
def test_help_exposes_shape_and_identity_without_auth_or_storage(
    detail_cli, tmp_path, monkeypatch, shape, paths
):
    cli, browser, config = detail_cli
    install(cli, package(tmp_path, shape=shape, paths=paths), tmp_path)

    def forbidden(**kwargs):
        pytest.fail("help must not open an inquiry session")

    monkeypatch.setattr("dogopencli.leaves.runtime.inquiry_session", forbidden)
    description = cli("payment", "describe", "synthetic.shapes")["data"]
    assert description["operations"]["get"].get("result_shape", "object") == (
        shape or "object"
    )
    if paths:
        assert description["operations"]["get"]["result_identity"]["paths"] == paths
    if shape == "array":
        assert "array" in description["detail_guidance"]
    help_data = cli("payment", "get", "synthetic.shapes", "--help")["data"]
    constraints = " ".join(help_data["constraints"])
    assert f"native root {shape or 'object'}" in constraints
    if paths:
        assert json.dumps(paths[0]) in constraints
    if shape == "array":
        assert "--fields projects each member" in constraints
        assert "empty array stays empty" in constraints
    assert not browser.business_requests
    assert not (config / "leaf-cache.sqlite3").exists()


def test_nested_composition_failure_is_atomic_and_preserves_saved_list(
    detail_cli, tmp_path
):
    cli, browser, _ = detail_cli
    install(cli, package(tmp_path, paths=[["detail", "id"]], binding=True), tmp_path)
    rows = [{"reference": "ONE"}, {"reference": "TWO"}]
    source = {"status": 200, "body": {"rows": rows}}
    browser.business_script.append(deepcopy(source))
    cli("payment", "refresh", "synthetic.shapes", "--require-complete")
    saved = cli("payment", "list", "synthetic.shapes", "--limit", "0")
    browser.business_script.extend(
        [
            deepcopy(source),
            reply({"detail": {"id": 1}}, "ONE"),
            reply({"detail": {"id": False}}, "TWO"),
        ]
    )
    result = cli(
        "payment",
        "list",
        "synthetic.shapes",
        "--live",
        "--with-detail",
        "--limit",
        "0",
        code=1,
    )
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result["meta"]["detail_row"] == 2
    after = cli("payment", "list", "synthetic.shapes", "--limit", "0")
    assert after["data"] == saved["data"]
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def supplementary_package(tmp_path, *, binding=False):
    root = package(tmp_path, binding=binding)
    path = root / "leaf.json"
    manifest = json.loads(path.read_text())
    manifest["operations"]["get"].update(
        execution="custom",
        max_requests=10,
        budget_seconds=60,
        queries={
            "root": {
                "kind": "detail",
                "result_identity": {"fields": ["id"], "description": "Native root"},
            },
            "extra": {
                "kind": "detail",
                "result_identity": {
                    "fields": ["id"],
                    "description": "Supplementary detail",
                },
                "supplementary": True,
                "retained_errors": ["refused"],
            },
        },
    )
    path.write_text(json.dumps(manifest))
    with (root / "adapter.py").open("a") as source:
        source.write("""
from dogopencli.leaves.query import CustomGetResult, QueryRefused
from dogopencli.result_policy import AcquisitionEvidence
class Supplementary(Detail):
    def parse_detail(self, body, parameters, identity):
        if parse(body)["data"].get("refused"):
            raise QueryRefused(native_code="QUALIFIED_REFUSAL")
        return super().parse_detail(body, parameters, identity)
class Custom(Adapter):
    def query_capability(self, operation, name, parameters):
        return Supplementary() if name == "extra" else Detail()
    def query_get(self, parameters, identity, tools):
        root = tools.detail("root", identity)
        try:
            root["extra"] = tools.detail("extra", identity)
            complete = True
        except QueryRefused:
            root["extra"] = None
            complete = False
        return CustomGetResult(root, AcquisitionEvidence.for_collection(
            complete=complete, reported_total=None, collected_total=1,
            reasons=() if complete else ("EXTRA_REFUSED",),
            usable_incomplete=True,
        ))
adapter = Custom()
""")
    return root


def test_custom_get_qualified_gap_is_usable_and_strict_rejects(detail_cli, tmp_path):
    cli, browser, config = detail_cli
    install(cli, supplementary_package(tmp_path), tmp_path)
    for strict in (False, True):
        browser.business_script.extend(
            [reply({"id": "root"}), reply({"refused": True})]
        )
        result = cli(
            "payment",
            "get",
            "synthetic.shapes",
            "REF",
            *(("--require-complete",) if strict else ()),
            code=1 if strict else 0,
        )
        assert result["meta"]["complete"] is False
        assert result["meta"]["acquisition"]["reasons"] == ["EXTRA_REFUSED"]
        if strict:
            assert result["data"] is None
            assert result["error"]["code"] == "INCOMPLETE_RESULT"
        else:
            assert result["data"] == {"id": "root", "extra": None}
            assert result["meta"]["outcome"] == "warning"
    assert not (config / "leaf-cache.sqlite3").exists()


@pytest.mark.parametrize("strict", [False, True])
def test_selected_detail_gaps_propagate_without_cache_publication(
    detail_cli, tmp_path, strict
):
    cli, browser, config = detail_cli
    install(cli, supplementary_package(tmp_path, binding=True), tmp_path)
    browser.business_script.extend(
        [
            {
                "status": 200,
                "body": {"rows": [{"reference": "REF"}, {"reference": "OTHER"}]},
            },
            reply({"id": "root"}),
            reply({"refused": True}),
        ]
    )
    result = cli(
        "payment",
        "list",
        "synthetic.shapes",
        "--live",
        "--with-detail",
        "--limit",
        "1",
        *(("--require-complete",) if strict else ()),
        code=1 if strict else 0,
    )
    assert result["meta"]["complete"] is False
    assert result["meta"]["source_acquisition"]["scope_complete"] is True
    assert result["meta"]["detail_acquisition"][0]["scope_complete"] is False
    assert len(browser.business_requests) == 3
    if strict:
        assert result["data"] is None
        assert result["error"]["code"] == "INCOMPLETE_RESULT"
    else:
        assert result["data"] == [
            {"record": {"reference": "REF"}, "detail": {"id": "root", "extra": None}}
        ]
    assert not (config / "leaf-cache.sqlite3").exists()


@pytest.mark.parametrize(
    "declaration",
    [
        {"retained_errors": []},
        {"retained_errors": ["refused", "refused"]},
        {"supplementary": False},
        {"retained_errors": ["AUTH_REQUIRED"]},
    ],
)
def test_invalid_supplementary_retention_contract_is_rejected(
    detail_cli, tmp_path, declaration
):
    cli, browser, _ = detail_cli
    root = supplementary_package(tmp_path)
    path = root / "leaf.json"
    manifest = json.loads(path.read_text())
    manifest["operations"]["get"]["queries"]["extra"].update(declaration)
    path.write_text(json.dumps(manifest))
    result = cli("plugins", "install", str(root), code=1)
    assert result["error"]["code"] == "INVALID_LEAF"
    assert not browser.business_requests


def test_required_selected_detail_keeps_native_failure_after_adapter_catches_it(
    detail_cli, tmp_path
):
    cli, browser, config = detail_cli
    root = supplementary_package(tmp_path, binding=True)
    path = root / "leaf.json"
    manifest = json.loads(path.read_text())
    query = manifest["operations"]["get"]["queries"]["extra"]
    del query["supplementary"]
    del query["retained_errors"]
    path.write_text(json.dumps(manifest))
    install(cli, root, tmp_path)
    browser.business_script.extend(
        [
            {"status": 200, "body": {"rows": [{"reference": "REF"}]}},
            reply({"id": "root"}),
            reply({"refused": True}),
        ]
    )
    result = cli(
        "payment", "list", "synthetic.shapes", "--live", "--with-detail", code=1
    )
    assert result["data"] is None
    assert result["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert result["error"]["native_code"] == "QUALIFIED_REFUSAL"
    assert result["meta"]["detail_row"] == 1
    assert not (config / "leaf-cache.sqlite3").exists()


@pytest.mark.parametrize("strict", [False, True])
def test_custom_get_without_coverage_cannot_satisfy_acceptance(
    detail_cli, tmp_path, strict
):
    cli, browser, _ = detail_cli
    root = supplementary_package(tmp_path)
    manifest_path = root / "leaf.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["operations"]["get"]["queries"]["extra"]
    manifest_path.write_text(json.dumps(manifest))
    with (root / "adapter.py").open("a") as source:
        source.write("""
class Bare(Custom):
    def query_get(self, parameters, identity, tools):
        return tools.detail("root", identity)
adapter = Bare()
""")
    install(cli, root, tmp_path)
    browser.business_script.append(reply({"id": "root"}))
    result = cli(
        "payment",
        "get",
        "synthetic.shapes",
        "REF",
        *(("--require-complete",) if strict else ()),
        code=1,
    )
    assert result["data"] is None
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["meta"]["acquisition"]["reasons"] == ["COVERAGE_UNPROVEN"]
    assert result["meta"]["complete"] is False
    assert browser.business_requests == [{"reference": "REF"}]
