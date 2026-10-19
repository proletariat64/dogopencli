"""Selected-window List plus Detail through the installed public CLI."""

import json

import pytest
from integration.test_get_sdk import get_only_package, native_package

pytest_plugins = ["integration.test_get_sdk"]


def sla_list(rows, total=None, page_size=10000):
    return {
        "success": True,
        "pageNo": 0,
        "pageSize": page_size,
        "totalCount": len(rows) if total is None else total,
        "resultDataList": rows,
    }


@pytest.mark.parametrize("config_position", ["before-command", "after-with-detail"])
def test_with_detail_respects_explicit_config_directory(
    detail_cli, tmp_path, monkeypatch, config_position
):
    cli, browser, root = detail_cli
    cli("plugins", "install", str(native_package("payment", "sla.baselines")))
    fallback = tmp_path / "other-config"
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(fallback))
    row = {"id": "selected", "listOnly": True}
    detail = {"id": "selected", "nested": {"detailOnly": True}}
    browser.business_script.extend(
        [
            {"status": 200, "body": sla_list([row])},
            {"status": 200, "body": {"success": True, "resultData": detail}},
        ]
    )
    command = ["payment", "list", "sla.baselines", "--live", "--with-detail"]
    config_option = ["--config-dir", str(root)]
    result = cli(
        *(
            config_option + command
            if config_position == "before-command"
            else command + config_option
        )
    )
    assert result["data"] == [{"record": row, "detail": detail}]
    assert browser.business_requests[1:] == [{"slaBaselineId": "selected"}]
    assert not fallback.exists()


def test_detail_selection_follows_local_filter_window_and_record_projection(detail_cli):
    cli, browser, root = detail_cli
    cli("plugins", "install", str(native_package("payment", "sla.baselines")))
    rows = [
        {"id": "skip", "status": "OFF", "amount": "list-zero"},
        {"id": "first", "status": "ON", "amount": "list-one"},
        {"id": "second", "status": "ON", "amount": "list-two"},
        {"id": "third", "status": "ON", "amount": "list-three"},
    ]
    detail = {"id": "second", "amount": "detail-two", "nested": [False, None]}
    browser.business_script.extend(
        [
            {"status": 200, "body": sla_list(rows)},
            {"status": 200, "body": {"success": True, "resultData": detail}},
        ]
    )
    result = cli(
        "payment",
        "list",
        "sla.baselines",
        "--live",
        "--with-detail",
        "--status",
        "ON",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        "amount",
    )
    assert result["data"] == [{"record": {"amount": "list-two"}, "detail": detail}]
    assert browser.business_requests[1:] == [{"slaBaselineId": "second"}]
    assert result["meta"]["matched_total"] == 3
    assert result["meta"]["returned_count"] == 1
    assert result["meta"]["has_more"] is True
    assert result["meta"]["detail_scope"] == "native_root"
    assert result["meta"]["detail_count"] == 1
    assert not (root / "leaf-cache.sqlite3").exists()


def context_package(tmp_path):
    package = get_only_package(tmp_path)
    path = package / "leaf.json"
    manifest = json.loads(path.read_text())
    manifest["operations"]["list"] = {
        "description": "List references",
        "parameters": [],
    }
    manifest["dataset"] = {"relation": "synthetic_details"}
    manifest["identity"] = ["reference"]
    detail = manifest["operations"]["get"]
    detail["parameters"].append(
        {
            "name": "region",
            "type": "string",
            "required": True,
            "description": "Region",
            "default": "EU",
        }
    )
    detail["list_binding"] = {
        "identity_field": "reference",
        "parameters": {"id": "account"},
    }
    path.write_text(json.dumps(manifest))
    path = package / "adapter.py"
    source = path.read_text().replace('"account"}),', '"account", "region"}),')
    source = source.replace(
        '"account": parameters["id"]}',
        '"account": parameters["id"], "region": parameters["region"]}',
    )
    source = source.replace(
        "class Adapter:",
        """class List:
    name = "payment.synthetic.detail.list"
    page_url = Detail.page_url
    contract = EndpointContract(
        method="GET", host="iglobalfundcontrol.alipay.com",
        path="/api/synthetic/list", page_size=500, one_based=False,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
    )
    def page_body(self, scope, page, size): return {"pageNo": page, "pageSize": size}
    def identity_key(self, row): return row["reference"]
    def parse_page(self, body):
        from dogopencli.contracts import ParsedPage
        rows = parse(body)["rows"]
        return ParsedPage(rows, 0, 500, len(rows), 1)
class Adapter:
    from dogopencli.collect import collect_scope
    collector = staticmethod(collect_scope)
    def capability(self, parameters): return List()
    def scope(self, parameters): return ""
    def filter(self, rows, parameters): return rows
""",
    )
    path.write_text(source)
    return package


def test_combined_context_mapping_and_get_defaults_match_direct_query(
    detail_cli, tmp_path
):
    cli, browser, _ = detail_cli
    cli("plugins", "install", str(context_package(tmp_path)))
    row = {"reference": "REF-1", "account": "ACCOUNT", "unknown": [1, False]}
    detail = {"nativeId": 9, "reference": "REF-1", "account": "ACCOUNT", "region": "EU"}
    browser.business_script.extend(
        [
            {"status": 200, "body": {"rows": [row]}},
            {"status": 200, "body": detail},
            {"status": 200, "body": detail},
        ]
    )
    combined = cli("payment", "list", "synthetic.detail", "--live", "--with-detail")
    direct = cli("payment", "get", "synthetic.detail", "REF-1", "--id", "ACCOUNT")
    assert combined["data"] == [{"record": row, "detail": detail}]
    assert direct["data"] == detail
    assert browser.business_requests[1:] == [
        {"reference": "REF-1", "account": "ACCOUNT", "region": "EU"},
        {"reference": "REF-1", "account": "ACCOUNT", "region": "EU"},
    ]


@pytest.mark.parametrize("account", [None, 7, True, ["ACCOUNT"], {"id": "ACCOUNT"}])
def test_invalid_mapped_context_fails_before_detail_request(
    detail_cli, tmp_path, account
):
    cli, browser, _ = detail_cli
    cli("plugins", "install", str(context_package(tmp_path)))
    row = {"reference": "REF-1", "account": account}
    browser.business_script.extend(
        [
            {"status": 200, "body": {"rows": [row]}},
            {
                "status": 200,
                "body": {"nativeId": 9, "reference": "REF-1", "account": account},
            },
        ]
    )
    result = cli(
        "payment", "list", "synthetic.detail", "--live", "--with-detail", code=1
    )
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result["data"] is None
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize(
    "action,options",
    [
        ("list", ["--with-detail"]),
        ("list", ["--live", "--with-details"]),
        ("get", ["known-id", "--with-detail"]),
        ("refresh", ["--with-detail"]),
        ("prune", ["--with-detail"]),
    ],
)
def test_invalid_composition_modes_do_not_query(detail_cli, action, options):
    cli, browser, _ = detail_cli
    cli("plugins", "install", str(native_package("payment", "sla.baselines")))
    result = cli("payment", action, "sla.baselines", *options, code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


@pytest.mark.parametrize(
    "window,expected",
    [
        (["--offset", "1", "--limit", "0"], ["b", "c"]),
        (["--offset", "4"], []),
    ],
)
def test_zero_limit_and_empty_output_window(detail_cli, window, expected):
    cli, browser, _ = detail_cli
    cli("plugins", "install", str(native_package("payment", "sla.baselines")))
    rows = [{"id": value, "unknown": {"same": True}} for value in ("a", "b", "c")]
    browser.business_script.append({"status": 200, "body": sla_list(rows)})
    for value in expected:
        browser.business_script.append(
            {
                "status": 200,
                "body": {"success": True, "resultData": {"id": value, "children": []}},
            }
        )
    result = cli("payment", "list", "sla.baselines", "--live", "--with-detail", *window)
    assert [row["record"]["id"] for row in result["data"]] == expected
    assert [row["detail"]["id"] for row in result["data"]] == expected
    assert browser.business_requests[1:] == [
        {"slaBaselineId": value} for value in expected
    ]


def test_later_detail_failure_is_atomic_and_preserves_saved_list(detail_cli):
    cli, browser, _ = detail_cli
    cli("plugins", "install", str(native_package("payment", "sla.baselines")))
    saved = [{"id": "saved", "status": "ON"}]
    browser.business_script.append({"status": 200, "body": sla_list(saved)})
    cli("payment", "refresh", "sla.baselines")
    before = cli("payment", "list", "sla.baselines")
    browser.business_script.extend(
        [
            {"status": 200, "body": sla_list([{"id": "a"}, {"id": "b"}, {"id": "c"}])},
            {"status": 200, "body": {"success": True, "resultData": {"id": "a"}}},
            {"status": 200, "body": {"success": False}},
        ]
    )
    result = cli("payment", "list", "sla.baselines", "--live", "--with-detail", code=1)
    assert result["data"] is None
    assert result["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert result["meta"]["detail_row"] == 2
    assert "row 2" in result["error"]["message"]
    assert browser.business_requests[-2:] == [
        {"slaBaselineId": "a"},
        {"slaBaselineId": "b"},
    ]
    after = cli("payment", "list", "sla.baselines")
    assert after["data"] == before["data"] == saved
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


@pytest.mark.parametrize("source_format", ["directory", "zip"])
@pytest.mark.parametrize(
    "domain,leaf,request_key,result_key",
    [
        ("payment", "sla.baselines", "slaBaselineId", "id"),
        ("liquidity", "rules.operation", "ruleId", "ruleId"),
        ("liquidity", "rules.realtime", "Id", "id"),
        ("liquidity", "risk.thresholds", "benchmarkId", "benchmarkId"),
    ],
)
def test_real_bindings_preserve_native_views_and_order(
    detail_cli, tmp_path, source_format, domain, leaf, request_key, result_key
):
    from decimal import Decimal
    from zipfile import ZipFile

    from integration.test_get_sdk import native_envelope

    from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL

    cli, browser, root = detail_cli
    package = native_package(domain, leaf)
    if source_format == "zip":
        archive_path = tmp_path / "native.zip"
        with ZipFile(archive_path, "w") as archive:
            for path in package.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.write(path, path.relative_to(package))
        package = archive_path
    cli("plugins", "install", str(package))
    if domain == "liquidity":
        browser.href = LIQUIDITY_STARTUP_URL
    rows = [
        {result_key: "17" if domain == "payment" else 17, "view": "list"},
        {result_key: "8", "view": "list"},
    ]
    details = [
        {
            result_key: row[result_key],
            "view": "detail",
            "amount": Decimal("0.123456789012345678901"),
            "nested": [None, False],
        }
        for row in rows
    ]
    if leaf == "sla.baselines":
        body = sla_list(rows)
    elif leaf == "rules.operation":
        body = {
            "resultFlag": True,
            "result": {"success": True, "dataValue": rows, "count": 2},
        }
    else:
        body = {"success": True, "data": {"data": rows, "totalCount": 2}}
    browser.business_script.append({"status": 200, "body": body})
    for detail in details:
        browser.business_script.append(
            {"status": 200, "body": native_envelope(leaf, detail)}
        )
    result = cli(domain, "list", leaf, "--live", "--with-detail")
    assert result["data"] == [
        {"record": rows[0], "detail": details[0]},
        {"record": rows[1], "detail": details[1]},
    ]
    expected = [{request_key: "17"}, {request_key: "8"}]
    if leaf == "rules.operation":
        for query in expected:
            query["tntInstId"] = "GUAPW3SG"
    assert browser.business_requests[1:] == expected
    assert result["meta"]["detail_count"] == 2
    assert result["meta"]["detail_scope"] == "native_root"
    assert not (root / "leaf-cache.sqlite3").exists()


@pytest.mark.parametrize("output_format", ["json", "text"])
def test_help_and_describe_explain_lookup_binding_and_coverage_without_activation(
    detail_cli, tmp_path, monkeypatch, run_cli, output_format
):
    cli, browser, root = detail_cli
    package = context_package(tmp_path)
    path = package / "adapter.py"
    path.write_text(
        'import os\nif os.environ.get("FORBID_ACTIVATION"):\n'
        '    raise RuntimeError("adapter activated")\n' + path.read_text()
    )
    cli("plugins", "install", str(package))
    monkeypatch.setenv("FORBID_ACTIVATION", "1")
    before = {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    for action in ("get", "list", "describe"):
        args = ["payment", action, "synthetic.detail", "--format", output_format]
        if action != "describe":
            args.append("--help")
        status, output, error = run_cli(args)
        assert status == 0, output + error
        if action == "get":
            assert "Business reference" in output
            assert "nativeId" in output
            assert "histories" in output
            assert "--id" in output
        else:
            assert "--with-detail" in output
            assert "record" in output and "detail" in output
            assert "--live" in output
            assert "window" in output
            assert "failure" in output
    after = {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    assert after == before
    assert not browser.business_requests
    assert not (root / "leaf-cache.sqlite3").exists()


def test_get_only_and_unbound_list_do_not_expose_or_accept_composition(
    detail_cli, tmp_path
):
    cli, browser, _ = detail_cli
    package = get_only_package(tmp_path)
    cli("plugins", "install", str(package))
    help_doc = cli("payment", "get", "synthetic.detail", "--help")["data"]
    assert "--with-detail" not in json.dumps(help_doc)
    cli(
        "payment",
        "get",
        "synthetic.detail",
        "REF-1",
        "--id",
        "ACCOUNT",
        "--with-detail",
        code=2,
    )
    cli("plugins", "uninstall", "payment.synthetic.detail")
    manifest_path = package / "leaf.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["operations"].pop("get")
    manifest["operations"]["list"] = {"description": "List", "parameters": []}
    manifest["dataset"] = {"relation": "synthetic_details"}
    manifest_path.write_text(json.dumps(manifest))
    path = package / "adapter.py"
    path.write_text(
        "class Adapter:\n"
        "    def capability(self, parameters): pass\n"
        '    def scope(self, parameters): return ""\n'
        "    def filter(self, rows, parameters): return rows\n"
        "    def collector(self, capability, transport, scope): pass\n"
        "adapter = Adapter()\n"
    )
    cli("plugins", "install", str(package))
    help_doc = cli("payment", "list", "synthetic.detail", "--help")["data"]
    assert "--with-detail" not in json.dumps(help_doc)
    cli("payment", "list", "synthetic.detail", "--live", "--with-detail", code=2)
    assert not browser.business_requests


def test_all_remaining_details_release_browser_targets_as_they_finish(detail_cli):
    cli, browser, _ = detail_cli
    cli("plugins", "install", str(native_package("payment", "sla.baselines")))
    rows = [{"id": str(index)} for index in range(8)]
    open_targets = []

    def respond(payload, index):
        open_targets.append(
            sum(len(t.created) - len(t.closed) for t in browser.transports)
        )
        body = (
            sla_list(rows)
            if index == 0
            else {"success": True, "resultData": {"id": payload["slaBaselineId"]}}
        )
        return {"status": 200, "body": body}

    browser.business_handler = respond
    result = cli(
        "payment", "list", "sla.baselines", "--live", "--with-detail", "--limit", "0"
    )
    assert len(result["data"]) == 8
    assert max(open_targets) <= 2
    assert all(len(t.closed) == len(t.created) for t in browser.transports)


def test_detail_success_retains_incomplete_list_evidence(detail_cli):
    cli, browser, _ = detail_cli
    cli("plugins", "install", str(native_package("payment", "sla.baselines")))
    browser.business_script.extend(
        [
            {"status": 200, "body": sla_list([{"id": "one"}], total=3)},
            {"status": 200, "body": sla_list([{"id": "one"}], total=3, page_size=5000)},
            {
                "status": 200,
                "body": {"success": True, "resultData": {"id": "one", "children": []}},
            },
        ]
    )
    result = cli("payment", "list", "sla.baselines", "--live", "--with-detail")
    assert result["meta"]["complete"] is False
    assert result["meta"]["dataset_complete"] is False
    assert result["meta"]["reported_total"] == 3
    assert result["meta"]["collected_total"] == 1
    assert result["meta"]["warnings"]
    assert "child pages are not acquired" in result["meta"]["detail_coverage"]


def test_shared_budget_exhaustion_fails_without_silent_window_truncation(
    detail_cli, monkeypatch
):
    cli, browser, _ = detail_cli
    cli("plugins", "install", str(native_package("payment", "sla.baselines")))
    clock = [100.0]
    monkeypatch.setattr("dogopencli.collect._monotonic", lambda: clock[0])

    def respond(payload, index):
        if index == 0:
            return {
                "status": 200,
                "body": sla_list([{"id": "a"}, {"id": "b"}, {"id": "c"}]),
            }
        clock[0] += 450.1
        return {
            "status": 200,
            "body": {"success": True, "resultData": {"id": payload["slaBaselineId"]}},
        }

    browser.business_handler = respond
    result = cli(
        "payment",
        "list",
        "sla.baselines",
        "--live",
        "--with-detail",
        "--limit",
        "0",
        code=1,
    )
    assert result["data"] is None
    assert result["error"]["code"] == "TIMEOUT"
    assert result["meta"]["detail_row"] == 2
    assert browser.business_requests[1:] == [
        {"slaBaselineId": "a"},
        {"slaBaselineId": "b"},
    ]


@pytest.mark.parametrize(
    "invalid",
    ["missing_context", "missing_identity", "boolean_identity", "empty_identity"],
)
def test_invalid_row_binding_is_rejected_before_detail(detail_cli, tmp_path, invalid):
    cli, browser, _ = detail_cli
    package = context_package(tmp_path)
    if invalid == "missing_identity":
        path = package / "leaf.json"
        manifest = json.loads(path.read_text())
        manifest["operations"]["get"]["list_binding"]["identity_field"] = "other"
        path.write_text(json.dumps(manifest))
    cli("plugins", "install", str(package))
    row = {"reference": "REF-1", "account": "ACCOUNT"}
    if invalid == "missing_context":
        row.pop("account")
    elif invalid == "boolean_identity":
        row["reference"] = True
    elif invalid == "empty_identity":
        row["reference"] = " "
    browser.business_script.append({"status": 200, "body": {"rows": [row]}})
    result = cli(
        "payment", "list", "synthetic.detail", "--live", "--with-detail", code=1
    )
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert len(browser.business_requests) == 1


def test_composition_option_name_is_reserved_at_install(detail_cli, tmp_path):
    cli, browser, _ = detail_cli
    package = context_package(tmp_path)
    path = package / "leaf.json"
    manifest = json.loads(path.read_text())
    manifest["operations"]["list"]["parameters"].append(
        {
            "name": "with-detail",
            "type": "string",
            "required": False,
            "description": "Collision",
        }
    )
    path.write_text(json.dumps(manifest))
    result = cli("plugins", "install", str(package), code=1)
    assert result["error"]["code"] == "INVALID_LEAF"
    assert not browser.business_requests


def test_unexpected_detail_failure_still_identifies_row_and_emits_no_partial_data(
    detail_cli, tmp_path
):
    cli, browser, _ = detail_cli
    package = context_package(tmp_path)
    path = package / "adapter.py"
    path.write_text(
        path.read_text().replace(
            "document = parse(body)",
            'if identity == "b": raise RuntimeError("parser failure")\n'
            "        document = parse(body)",
        )
    )
    cli("plugins", "install", str(package))
    browser.business_script.append(
        {
            "status": 200,
            "body": {
                "rows": [
                    {"reference": "a", "account": "ACCOUNT"},
                    {"reference": "b", "account": "ACCOUNT"},
                ]
            },
        }
    )
    browser.business_script.extend(
        {
            "status": 200,
            "body": {
                "nativeId": identity,
                "reference": identity,
                "account": "ACCOUNT",
            },
        }
        for identity in ("a", "b")
    )
    result = cli(
        "payment", "list", "synthetic.detail", "--live", "--with-detail", code=1
    )
    assert result["data"] is None
    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert result["meta"]["detail_row"] == 2
