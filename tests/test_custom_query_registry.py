"""Custom query declarations and install-time entry point validation."""

import copy
import json

import pytest

from dogopencli.errors import CliError
from dogopencli.leaves.package import prepare_package
from dogopencli.leaves.registry import Registry, validate_manifest


def manifest():
    return {
        "domain": "liquidity",
        "name": "sample",
        "adapter": "adapter.py:adapter",
        "operations": {"list": custom_operation()},
        "dataset": {"relation": "sample_rows"},
        "fields": [],
        "identity": ["alias"],
        "summary": "Samples",
        "purpose": "Query samples",
        "identity_description": "Native alias",
        "limitations": [],
        "examples": [],
    }


def custom_operation():
    return {
        "description": "Query samples",
        "parameters": [],
        "execution": "custom",
        "max_requests": 100,
        "budget_seconds": 60,
        "queries": {
            "accounts": {
                "kind": "list",
                "collection": {
                    "provider": "general",
                    "paging": {"mode": "offset", "page_sizes": [100, 10]},
                    "primary_id": {"type": "field", "fields": ["alias"]},
                },
            },
            "detail": {
                "kind": "detail",
                "result_identity": {"fields": ["alias"], "description": "Native alias"},
            },
        },
    }


ADAPTER = """
class Adapter:
    def scope(self, parameters): raise AssertionError('scope invoked')
    def filter(self, records, parameters): raise AssertionError('filter invoked')
    def query_capability(self, operation, name, parameters):
        raise AssertionError('query capability invoked')
    def query_list(self, parameters, query): raise AssertionError('List invoked')
    def query_get(self, parameters, identity, query):
        raise AssertionError('Get invoked')
    def detail_capability(self, parameters): raise AssertionError('detail invoked')
    def capability(self, parameters): raise AssertionError('capability invoked')
adapter = Adapter()
"""


def write_leaf(tmp_path, value=None, source=ADAPTER):
    folder = tmp_path / "plugins" / "liquidity" / "sample"
    folder.mkdir(parents=True)
    (folder / "leaf.json").write_text(json.dumps(value or manifest()))
    (folder / "adapter.py").write_text(source)
    return folder


def test_static_verification_does_not_import_custom_adapter(tmp_path):
    folder = write_leaf(tmp_path, source="raise AssertionError('adapter imported')")
    with prepare_package(folder) as package:
        assert package.manifest == manifest()


@pytest.mark.parametrize("action", ["list", "get", "both"])
def test_install_binds_custom_methods_without_invoking_them(tmp_path, action):
    value = manifest()
    if action != "list":
        detail = custom_operation()
        detail.update(
            lookup={"name": "alias", "description": "Native alias"},
            result_identity={"paths": [["account", "alias"]], "description": "Alias"},
        )
        value["operations"]["get"] = detail
    if action == "get":
        del value["operations"]["list"]
        del value["dataset"]
    folder = write_leaf(tmp_path, value)
    assert Registry(tmp_path / "config.toml")._load(folder).manifest == value


@pytest.mark.parametrize("custom_action", ["list", "get"])
def test_install_supports_mixed_execution_modes(tmp_path, custom_action):
    value = manifest()
    detail = {
        "description": "Native detail",
        "parameters": [],
        "lookup": {"name": "alias", "description": "Alias"},
        "result_identity": {"fields": ["alias"], "description": "Alias"},
    }
    value["operations"]["get"] = detail
    if custom_action == "get":
        detail.update(custom_operation())
        value["operations"]["list"] = {"description": "List", "parameters": []}
        value["collection"] = custom_operation()["queries"]["accounts"]["collection"]
    folder = write_leaf(tmp_path, value)
    assert Registry(tmp_path / "config.toml")._load(folder).manifest == value


@pytest.mark.parametrize("entry", ["query_capability", "query_list", "scope", "filter"])
@pytest.mark.parametrize("failure", ["missing", "signature"])
def test_install_rejects_missing_or_incompatible_custom_entries(
    tmp_path, entry, failure
):
    source = ADAPTER + (
        f"\nAdapter.{entry} = None\n"
        if failure == "missing"
        else f"\nAdapter.{entry} = lambda self: None\n"
    )
    folder = write_leaf(tmp_path, source=source)
    with pytest.raises(CliError) as raised:
        Registry(tmp_path / "config.toml")._load(folder)
    assert raised.value.code == "INVALID_LEAF"


@pytest.mark.parametrize("failure", ["missing", "signature"])
def test_custom_get_requires_compatible_get_entry(tmp_path, failure):
    value = manifest()
    detail = value["operations"].pop("list")
    detail.update(
        lookup={"name": "alias", "description": "Native alias"},
        result_identity={"fields": ["alias"], "description": "Native alias"},
    )
    value["operations"]["get"] = detail
    del value["dataset"]
    source = ADAPTER + (
        "\nAdapter.query_get = None\n"
        if failure == "missing"
        else "\nAdapter.query_get = lambda self, parameters: None\n"
    )
    folder = write_leaf(tmp_path, value, source)
    with pytest.raises(CliError) as raised:
        Registry(tmp_path / "config.toml")._load(folder)
    assert raised.value.code == "INVALID_LEAF"


@pytest.mark.parametrize("field", ["queries", "max_requests", "budget_seconds"])
def test_custom_requires_declared_queries_and_shared_bounds(field):
    value = manifest()
    del value["operations"]["list"][field]
    with pytest.raises(CliError, match="custom execution requires"):
        validate_manifest(value)


@pytest.mark.parametrize("execution", [None, "standard"])
def test_standard_cannot_accidentally_activate_custom_queries(execution):
    value = manifest()
    if execution is None:
        del value["operations"]["list"]["execution"]
    else:
        value["operations"]["list"]["execution"] = execution
    with pytest.raises(CliError, match="standard execution"):
        validate_manifest(value)


@pytest.mark.parametrize(
    ("location", "replacement"),
    [
        (("max_requests",), 0),
        (("max_requests",), 10001),
        (("max_requests",), True),
        (("budget_seconds",), 1801),
        (("budget_seconds",), 0),
        (("queries",), {}),
        (("queries", "unsafe-name"), {"kind": "detail"}),
        (("collector",), "custom"),
        (("queries", "accounts", "collection", "provider"), "not_registered"),
        (("queries", "accounts", "collection", "sources"), {}),
        (("queries", "accounts", "collection", "paging", "page_sizes"), [10, 100]),
        (("queries", "accounts", "collection", "paging", "page_sizes"), [0]),
        (("queries", "detail", "result_identity", "fields"), []),
        (("queries", "detail", "result_identity", "description"), ""),
        (("queries", "detail", "result_identity", "paths"), [["alias"]]),
        (("queries", "detail", "collection"), {}),
        (("queries", "accounts", "result_shape"), "array"),
    ],
)
def test_rejects_invalid_or_ambiguous_custom_declarations(location, replacement):
    value = manifest()
    target = value["operations"]["list"]
    for key in location[:-1]:
        target = target[key]
    target[location[-1]] = copy.deepcopy(replacement)
    with pytest.raises(CliError) as raised:
        validate_manifest(value)
    assert raised.value.code == "INVALID_LEAF"


def test_custom_list_cannot_also_declare_standard_collection():
    value = manifest()
    value["collection"] = value["operations"]["list"]["queries"]["accounts"][
        "collection"
    ]
    with pytest.raises(CliError, match="custom List cannot declare"):
        validate_manifest(value)


def test_inquiry_requires_explicit_shape_without_fake_native_identity():
    value = manifest()
    op = value["operations"]["list"]
    op["queries"] = {"native": {"kind": "inquiry", "result_shape": "object"}}
    op["account_directory"] = True
    validate_manifest(value)
    op["queries"]["native"]["result_identity"] = {"fields": ["id"], "description": "ID"}
    with pytest.raises(CliError):
        validate_manifest(value)


@pytest.mark.parametrize("mode", ["standard", "array", "undeclared", "internal"])
def test_request_identity_only_allows_declared_context_custom_object_get(mode):
    value = manifest()
    get = custom_operation()
    get.update(
        lookup={"name": "route", "description": "Route reference"},
        result_identity={
            "request_fields": ["route", "account"],
            "description": "Exact request scope",
        },
        parameters=[
            {
                "name": "account",
                "type": "string",
                "required": True,
                "description": "Account",
            }
        ],
    )
    value["operations"]["get"] = get
    validate_manifest(value)
    if mode == "standard":
        for key in ("queries", "max_requests", "budget_seconds"):
            del get[key]
        get["execution"] = "standard"
    elif mode == "array":
        get["result_shape"] = "array"
    elif mode == "undeclared":
        get["result_identity"]["request_fields"].append("undeclared")
    else:
        get["queries"]["detail"]["result_identity"] = get["result_identity"]
    with pytest.raises(CliError):
        validate_manifest(value)


@pytest.mark.parametrize("query", [{"kind": "list"}, {"kind": "inquiry"}])
def test_custom_query_missing_required_kind_fields_rejected_before_import(
    tmp_path, query
):
    value = manifest()
    value["operations"]["list"]["queries"] = {"native": query}
    folder = write_leaf(
        tmp_path, value, source="raise AssertionError('adapter imported')"
    )
    with pytest.raises(CliError) as caught:
        with prepare_package(folder):
            pass
    assert caught.value.code == "INVALID_LEAF"
