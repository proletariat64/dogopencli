"""Get SDK acceptance through installed packages and native transport."""

import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse


@pytest.fixture
def detail_cli(run_cli, tmp_path, monkeypatch):
    root = tmp_path / "config"
    root.mkdir()
    (root / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(root))
    for name in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(name, raising=False)
    browser = FakeBrowser()
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    yield cli, browser, root
    cdp.set_transport_factory(None)


def get_only_package(tmp_path):
    package = tmp_path / "detail-package"
    package.mkdir()
    manifest = {
        "domain": "payment",
        "name": "synthetic.detail",
        "adapter": "adapter.py:adapter",
        "operations": {
            "get": {
                "description": "Native detail by business reference",
                "parameters": [
                    {
                        "name": "id",
                        "type": "string",
                        "required": True,
                        "description": "Account context",
                    }
                ],
                "lookup": {"name": "reference", "description": "Business reference"},
                "result_identity": {
                    "fields": ["nativeId"],
                    "description": "Native detail identity",
                },
            }
        },
        "fields": [],
        "identity": [],
        "summary": "Detail",
        "purpose": "Read detail",
        "identity_description": "No List identity",
        "limitations": [],
        "examples": [],
    }
    (package / "leaf.json").write_text(json.dumps(manifest))
    (
        package / "adapter.py"
    ).write_text("""from dogopencli.contracts import EndpointContract
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
class Detail:
    name = "payment.synthetic.detail.get"
    page_url = "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
    contract = EndpointContract(
        method="GET", host="iglobalfundcontrol.alipay.com",
        path="/api/synthetic/detail", page_size=0, one_based=False,
        allowed_body_keys=frozenset({"reference", "account"}),
    )
    def request_body(self, parameters, identity):
        return {"reference": identity, "account": parameters["id"]}
    def parse_detail(self, body, parameters, identity):
        document = parse(body)
        if (
            document.get("reference") != identity
            or document.get("account") != parameters["id"]
        ):
            raise CliError("INVALID_RESPONSE", "detail scope differs")
        return document
class Adapter:
    def detail_capability(self, parameters): return Detail()
adapter = Adapter()
""")
    return package


@pytest.mark.parametrize("source_format", ["directory", "zip"])
def test_get_only_native_detail_without_list_or_storage(
    detail_cli, tmp_path, source_format
):
    cli, browser, root = detail_cli
    package = get_only_package(tmp_path)
    if source_format == "zip":
        archive_path = tmp_path / "candidate.zip"
        with ZipFile(archive_path, "w") as archive:
            for path in package.iterdir():
                archive.write(path, path.name)
        package = archive_path
    cli("plugins", "install", str(package))
    assert not (root / "duckdog.duckdb").exists()
    assert not (root / "leaf-cache.sqlite3").exists()
    cli("payment", "get", "synthetic.detail", "REF-1", code=2)
    assert not browser.business_requests
    native = {
        "nativeId": 71,
        "reference": "REF-1",
        "account": "ACCOUNT",
        "nested": {"unknown": [None, False, "1.0000"]},
    }
    browser.business_script.append({"status": 200, "body": native})
    result = cli("payment", "get", "synthetic.detail", "REF-1", "--id", "ACCOUNT")
    assert result["data"] == native
    assert browser.business_requests == [{"reference": "REF-1", "account": "ACCOUNT"}]
    assert result["meta"]["query"] == {
        "identity": "REF-1",
        "parameters": {"id": "ACCOUNT"},
    }
    assert result["meta"]["returned_count"] == 1
    assert result["meta"]["complete"] is True
    assert result["meta"]["dataset_complete"] is True
    assert result["meta"]["reported_total"] is None
    assert (
        result["meta"]["acquisition"]["coverage_basis"] == "qualified_single_response"
    )
    assert not (root / "duckdog.duckdb").exists()
    assert not (root / "leaf-cache.sqlite3").exists()


@pytest.mark.parametrize(
    "invalid",
    [
        "lookup",
        "result_identity",
        "empty_identity",
        "binding_without_list",
        "unknown_context",
    ],
)
def test_install_rejects_invalid_get_declarations(detail_cli, tmp_path, invalid):
    cli, browser, root = detail_cli
    package = get_only_package(tmp_path)
    path = package / "leaf.json"
    manifest = json.loads(path.read_text())
    operation = manifest["operations"]["get"]
    if invalid in ("lookup", "result_identity"):
        operation.pop(invalid)
    elif invalid == "empty_identity":
        operation["result_identity"]["fields"] = []
    else:
        operation["list_binding"] = {"identity_field": "reference"}
        if invalid == "unknown_context":
            manifest["operations"]["list"] = {"description": "List", "parameters": []}
            manifest["dataset"] = {"relation": "synthetic_details"}
            operation["list_binding"]["parameters"] = {"typo": "account"}
    path.write_text(json.dumps(manifest))
    result = cli("plugins", "install", str(package), code=1)
    assert result["error"]["code"] == "INVALID_LEAF"
    assert not browser.business_requests
    assert not (root / "duckdog.duckdb").exists()


NATIVE_GETS = [
    ("payment", "sla.baselines", "slaBaselineId", "id"),
    ("liquidity", "rules.operation", "ruleId", "ruleId"),
    ("liquidity", "rules.realtime", "Id", "id"),
    ("liquidity", "risk.thresholds", "benchmarkId", "benchmarkId"),
]


def native_package(domain, leaf):
    root = Path(__file__).parents[2]
    base = root / (
        "src/dogopencli/leaf_packages" if domain == "payment" else "leaf_packages"
    )
    return base / domain / leaf


def native_envelope(leaf, detail):
    if leaf == "sla.baselines":
        return {"success": True, "resultData": detail}
    if leaf == "rules.operation":
        return {"resultFlag": True, "result": {"success": True, "data": detail}}
    return {"success": True, "data": detail}


@pytest.mark.parametrize("domain,leaf,request_key,result_key", NATIVE_GETS)
@pytest.mark.parametrize("source_format", ["directory", "zip"])
def test_native_get_independent_lookup_and_preservation(
    detail_cli, tmp_path, domain, leaf, request_key, result_key, source_format
):
    from decimal import Decimal

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
    detail = {
        result_key: "71" if domain == "payment" else 71,
        "amount": Decimal("0.123456789012345678901"),
        "unknown": {"children": [False, None, "1.0000"]},
    }
    browser.business_script.append(
        {"status": 200, "body": native_envelope(leaf, detail)}
    )
    result = cli(domain, "get", leaf, "71")
    assert result["data"] == detail
    expected = {request_key: "71"}
    if leaf == "rules.operation":
        expected["tntInstId"] = "GUAPW3SG"
    assert browser.business_requests == [expected]
    assert result["meta"]["query"] == {"identity": "71", "parameters": {}}
    assert not (root / "leaf-cache.sqlite3").exists()
    if domain != "payment":
        browser.business_script.append(
            {"status": 200, "body": native_envelope(leaf, {result_key: True})}
        )
        assert (
            cli(domain, "get", leaf, "1", code=1)["error"]["code"] == "INVALID_RESPONSE"
        )


@pytest.mark.parametrize("domain,leaf,request_key,result_key", NATIVE_GETS)
@pytest.mark.parametrize(
    "failure", ["missing", "null", "empty", "array", "mismatch", "business", "auth"]
)
def test_native_get_failures_never_become_empty_success(
    detail_cli, domain, leaf, request_key, result_key, failure
):
    from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL

    cli, browser, root = detail_cli
    cli("plugins", "install", str(native_package(domain, leaf)))
    if domain == "liquidity":
        browser.href = LIQUIDITY_STARTUP_URL
    detail = {result_key: "71"}
    body = native_envelope(leaf, detail)
    expected = "INVALID_RESPONSE"
    status = 200
    if failure == "missing":
        if leaf == "sla.baselines":
            body.pop("resultData")
        elif leaf == "rules.operation":
            body["result"].pop("data")
        else:
            body.pop("data")
    elif failure in ("null", "empty", "array", "mismatch"):
        detail = {
            "null": None,
            "empty": {},
            "array": [],
            "mismatch": {result_key: "other"},
        }[failure]
        body = native_envelope(leaf, detail)
        if leaf == "sla.baselines" and failure == "null":
            expected = "NOT_FOUND"
    elif failure == "business":
        body = (
            {"resultFlag": False} if leaf == "rules.operation" else {"success": False}
        )
        expected = "BUSINESS_QUERY_FAILED"
    else:
        status, expected = 401, "AUTH_REQUIRED"
    browser.business_script.append({"status": status, "body": body})
    result = cli(domain, "get", leaf, "71", code=1)
    assert result["error"]["code"] == expected
    assert result["data"] is None
    assert not (root / "leaf-cache.sqlite3").exists()


def test_operation_get_rejects_echoed_tenant_mismatch(detail_cli):
    from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL

    cli, browser, _ = detail_cli
    cli("plugins", "install", str(native_package("liquidity", "rules.operation")))
    browser.href = LIQUIDITY_STARTUP_URL
    browser.business_script.append(
        {
            "status": 200,
            "body": native_envelope(
                "rules.operation", {"ruleId": "71", "tntInstId": "OTHER"}
            ),
        }
    )
    result = cli("liquidity", "get", "rules.operation", "71", code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("hook", ["request_body", "parse_detail"])
def test_invalid_detail_hook_rejected_before_business_query(detail_cli, tmp_path, hook):
    cli, browser, _ = detail_cli
    package = get_only_package(tmp_path)
    path = package / "adapter.py"
    source = path.read_text()
    if hook == "request_body":
        source = source.replace(
            "def request_body(self, parameters, identity):", "def request_body(self):"
        )
    else:
        source = source.replace(
            "def parse_detail(self, body, parameters, identity):",
            "def parse_detail(self):",
        )
    path.write_text(source)
    cli("plugins", "install", str(package))
    result = cli(
        "payment", "get", "synthetic.detail", "REF-1", "--id", "ACCOUNT", code=1
    )
    assert result["error"]["code"] == "INVALID_LEAF"
    assert not browser.business_requests
