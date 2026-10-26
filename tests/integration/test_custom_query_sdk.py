"""Custom Get dispatch and mixed standard/custom operations at the CLI boundary."""

import json
from copy import deepcopy

from integration.test_get_sdk import get_only_package
from integration.test_list_detail_sdk import context_package

pytest_plugins = ["integration.test_get_sdk"]


def custom_get(package, maximum=3):
    path = package / "leaf.json"
    manifest = json.loads(path.read_text())
    detail = manifest["operations"]["get"]
    detail.update(
        execution="custom",
        queries={
            "native": {
                "kind": "detail",
                "result_identity": deepcopy(detail["result_identity"]),
            }
        },
        max_requests=maximum,
        budget_seconds=60,
    )
    path.write_text(json.dumps(manifest))
    path = package / "adapter.py"
    source = path.read_text().replace(
        "def detail_capability(self, parameters): return Detail()",
        "def query_capability(self, operation, name, parameters): return Detail()\n"
        "    def query_get(self, parameters, identity, query):\n"
        "        from dogopencli.leaves.query import CustomGetResult\n"
        "        from dogopencli.result_policy import AcquisitionEvidence\n"
        "        data = query.detail('native', identity)\n"
        "        return CustomGetResult(data, AcquisitionEvidence.for_collection(\n"
        "            complete=True, reported_total=None, collected_total=1,\n"
        "            arrivals=1, total_semantics='unknown',\n"
        "            coverage_basis='qualified_single_response',\n"
        "        ))",
    )
    path.write_text(source)
    return package


def test_custom_get_preserves_native_root_and_query_facts_without_storage(
    detail_cli, tmp_path
):
    cli, browser, config = detail_cli
    cli("plugins", "install", str(custom_get(get_only_package(tmp_path))))
    record = {
        "reference": "REF",
        "account": "ACCOUNT",
        "nativeId": 7,
        "unknown": [None, False, {"amount": "1.0000"}],
    }
    browser.business_script.append({"status": 200, "body": record})
    result = cli("payment", "get", "synthetic.detail", "REF", "--id", "ACCOUNT")
    assert result["data"] == record
    assert result["meta"]["detail_scope"] == "custom"
    assert result["meta"]["query_evidence"]["request_count"] == 1
    assert not (config / "leaf-cache.sqlite3").exists()
    assert not (config / "duckdog.duckdb").exists()


def test_standard_list_custom_get_binding_limits_only_selected_window(
    detail_cli, tmp_path
):
    cli, browser, _ = detail_cli
    cli("plugins", "install", str(custom_get(context_package(tmp_path), maximum=1)))
    rows = [
        {"reference": "REF-one", "account": "ACCOUNT-one"},
        {"reference": "REF-two", "account": "ACCOUNT-two"},
    ]
    detail = {"reference": "REF-two", "account": "ACCOUNT-two", "nativeId": 2}
    browser.business_script.extend(
        [{"status": 200, "body": {"rows": rows}}, {"status": 200, "body": detail}]
    )
    result = cli(
        "payment",
        "list",
        "synthetic.detail",
        "--live",
        "--with-detail",
        "--offset",
        "1",
        "--limit",
        "1",
    )
    assert result["data"] == [{"record": rows[1], "detail": detail}]
    assert result["meta"]["detail_scope"] == "custom"
    assert browser.business_requests[1:] == [
        {"reference": "REF-two", "account": "ACCOUNT-two", "region": "EU"}
    ]


def test_custom_get_binding_cannot_reset_request_budget_for_each_row(
    detail_cli, tmp_path
):
    cli, browser, config = detail_cli
    cli("plugins", "install", str(custom_get(context_package(tmp_path), maximum=1)))
    rows = [
        {"reference": "REF-one", "account": "ACCOUNT-one"},
        {"reference": "REF-two", "account": "ACCOUNT-two"},
    ]
    browser.business_script.extend(
        [
            {"status": 200, "body": {"rows": rows}},
            {
                "status": 200,
                "body": {**rows[0], "nativeId": 1},
            },
        ]
    )
    failed = cli(
        "payment",
        "list",
        "synthetic.detail",
        "--live",
        "--with-detail",
        "--limit",
        "0",
        code=1,
    )
    assert failed["data"] is None
    assert failed["error"]["code"] == "TIMEOUT"
    assert failed["meta"]["detail_row"] == 2
    assert len(browser.business_requests) == 2
    assert not (config / "leaf-cache.sqlite3").exists()
