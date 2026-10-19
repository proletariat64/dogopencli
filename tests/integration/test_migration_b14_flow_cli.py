"""Installed payment flow rules retain native values and exact local scope."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
LEAVES = ("rules.cost_reduction", "rules.retry")


@pytest.fixture(
    params=[(leaf, source) for leaf in LEAVES for source in ("directory", "zip")]
)
def installed(request, run_cli, tmp_path, monkeypatch):
    leaf, source = request.param
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for key in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(key, raising=False)
    browser = FakeBrowser(
        href="https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(operation, *args, code=0):
        status, output, error = run_cli(["payment", operation, leaf, *args])
        assert status == code, output + error
        return parse(output)

    try:
        status, output, error = run_cli(["domain", "enable", "payment"])
        assert status == 0, output + error
        package = ROOT / "leaf_packages/payment" / leaf
        if source == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        archive.write(path, path.relative_to(package))
            package = archive_path
        status, output, error = run_cli(["plugins", "install", str(package)])
        assert status == 0, output + error
        yield leaf, cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def records(leaf):
    key = "groupId" if leaf == LEAVES[0] else "ruleId"
    rows = []
    for identity, name, status, entities in [
        ("2", "Name-A", "ACTIVE", ["ENTITY-A", "ENTITY-B"]),
        ("10", "Name-B", "ACTIVE", ["ENTITY-B"]),
        ("30", "Name-A", "INACTIVE", ["ENTITY-A"]),
        ("40", "*", "ACTIVE", ["ENTITY-A,ENTITY-B"]),
        ("50", None, "ACTIVE", None),
    ]:
        rows.append(
            {
                key: identity,
                "ruleName": name,
                "status": status,
                "legalEntity": entities,
                "bizLegalEntityList": entities,
                "businessCategory": "BUSINESS",
                "businessCategoryList": ["BUSINESS"],
                "creditCurrency": "USD",
                "creditorCurrencyList": ["USD"],
                "debtorInstList": ["BANK"],
                "creditorCountryList": ["US"],
                "debtorAccountNoList": ["000123"],
                "clearingNetworkList": ["NETWORK"],
                "creditorMarket": "US",
                "needObo": ["YES"],
                "needFvt": ["NO"],
                "communicationMode": "API",
                "integrationMode": "DIRECT",
                "unknown": {
                    "children": [None, False, 0, "", Decimal("0.123456789012345678901")]
                },
            }
        )
    return rows


def identity(leaf):
    return "groupId" if leaf == LEAVES[0] else "ruleId"


def reply(rows, total=None, page=0, size=1000):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "businessDataList": rows,
                "totalCount": len(rows) if total is None else total,
                "pageNo": page,
                "pageSize": size,
                "totalPageNo": 0,
            },
        },
    }


def test_native_live_refresh_offline_and_static_help(installed):
    leaf, cli, browser, config = installed
    before = sorted(p.relative_to(config) for p in config.rglob("*") if p.is_file())
    cli("list", "--help")
    assert not browser.business_requests
    assert before == sorted(
        p.relative_to(config) for p in config.rglob("*") if p.is_file()
    )
    native = records(leaf)
    browser.business_script.append(reply(native))
    result = cli("list", "--live", "--require-complete", "--limit", "0")
    expected = sorted(native, key=lambda row: row[identity(leaf)])
    assert result["data"] == expected
    assert browser.business_requests == [{"pageNo": 0, "pageSize": 1000}]
    endpoint = (
        "/api/fundOut/costCutFlow/query"
        if leaf == LEAVES[0]
        else "/api/fundOut/flowOperation/exceptionRetryRule/page"
    )
    expressions = [
        x
        for transport in browser.transports
        for x in transport.expressions
        if "fetch(" in x
    ]
    assert any(
        "ifundcontrolprodops.alipay.com" + endpoint in x
        and 'method: "GET"' in x
        and "new URLSearchParams(payload)" in x
        for x in expressions
    )
    assert all("body:" not in x.split("const text", 1)[0] for x in expressions)
    browser.business_script.append(reply(native))
    saved = cli("refresh", "--require-complete")
    assert saved["meta"]["published"] is True
    before = len(browser.business_requests)
    assert cli("list", "--limit", "0")["data"] == expected
    assert len(browser.business_requests) == before


def test_exact_or_and_array_filters_precede_projection_and_window(installed):
    leaf, cli, browser, _ = installed
    key = identity(leaf)
    browser.business_script.append(reply(records(leaf)))
    result = cli(
        "list",
        "--live",
        "--entity",
        "ENTITY-A",
        "--entity",
        "ENTITY-B",
        "--currency",
        "USD",
        "--status",
        "ACTIVE",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        key,
    )
    assert result["data"] == [{key: "2"}]
    assert browser.business_requests == [{"pageNo": 0, "pageSize": 1000}]
    browser.business_script.append(reply(records(leaf)))
    cli("refresh", "--require-complete")
    assert [row[key] for row in cli("list", "--name", "*", "--limit", "0")["data"]] == [
        "40"
    ]
    assert [
        row[key]
        for row in cli("list", "--entity", "ENTITY-A,ENTITY-B", "--limit", "0")["data"]
    ] == ["40"]
    for value in ("ENTITY-A, ENTITY-B", "entity-a", " ENTITY-A ", "*"):
        assert cli("list", "--entity", value)["data"] == []
    assert [
        row[key]
        for row in cli(
            "list", "--name", "Name-A", "--entity", "ENTITY-A", "--limit", "0"
        )["data"]
    ] == ["2", "30"]
    extra = (
        ("--obo", "YES", "--fvt", "NO", "--market", "US")
        if leaf == LEAVES[0]
        else (
            "--bank",
            "BANK",
            "--region",
            "US",
            "--bank-account",
            "000123",
            "--clearing-network",
            "NETWORK",
            "--communication-mode",
            "API",
            "--integration-mode",
            "DIRECT",
        )
    )
    assert (
        len(
            cli(
                "list",
                *extra,
                "--business-line",
                "BUSINESS",
                "--currency",
                "USD",
                "--limit",
                "0",
            )["data"]
        )
        == 5
    )


def test_declared_array_filter_does_not_treat_scalar_as_a_member_array(installed):
    leaf, cli, browser, _ = installed
    rows = records(leaf)
    field = "legalEntity" if leaf == LEAVES[0] else "bizLegalEntityList"
    rows[0][field] = "ENTITY-A"
    browser.business_script.append(reply(rows))
    assert [
        row[identity(leaf)]
        for row in cli("list", "--live", "--entity", "ENTITY-A", "--limit", "0")["data"]
    ] == ["30"]


@pytest.mark.parametrize("value", ["", " "])
def test_blank_local_filter_fails_before_business_query(installed, value):
    leaf, cli, browser, _ = installed
    assert cli("list", "--live", "--currency", value, code=2)["data"] is None
    assert not browser.business_requests


@pytest.mark.parametrize(
    "failure",
    [
        "success",
        "success-type",
        "rows",
        "identity",
        "page",
        "size",
        "total",
        "page-count-placeholder",
        "auth",
        "duplicate",
        "gap",
        "capacity",
    ],
)
def test_failure_never_replaces_previous_capture(installed, failure):
    leaf, cli, browser, _ = installed
    native = records(leaf)
    browser.business_script.append(reply(native))
    cli("refresh", "--require-complete")
    before = cli("list", "--limit", "0")
    response = reply(deepcopy(native))
    doc = response["body"]["data"]
    if failure == "success":
        response["body"]["success"] = False
    if failure == "success-type":
        response["body"]["success"] = "true"
    if failure == "rows":
        doc["businessDataList"] = None
    if failure == "identity":
        doc["businessDataList"][0][identity(leaf)] = 12
    if failure == "page":
        doc["pageNo"] = 1
    if failure == "size":
        doc["pageSize"] = 10
    if failure == "total":
        doc["totalCount"] = True
    if failure == "page-count-placeholder":
        doc["totalPageNo"] = True
    if failure == "auth":
        response["status"] = 401
    if failure == "duplicate":
        doc["businessDataList"][1] = deepcopy(doc["businessDataList"][0])
    if failure == "gap":
        doc["totalCount"] += 1
    if failure == "capacity":
        doc["totalCount"] = 1001
    browser.business_script.append(response)
    assert cli("refresh", "--require-complete", code=1)["data"] is None
    after = cli("list", "--limit", "0")
    assert before["data"] == after["data"]
    assert before["meta"]["fetched_at"] == after["meta"]["fetched_at"]


@pytest.mark.parametrize("page", [0])
def test_explicit_empty_page_preserves_prior_capture(installed, page):
    leaf, cli, browser, _ = installed
    browser.business_script.append(reply(records(leaf)))
    cli("refresh", "--require-complete")
    before = cli("list", "--limit", "0")
    browser.business_script.append(reply([], page=page))
    assert cli("refresh", "--require-complete")["meta"]["published"] is False
    after = cli("list", "--limit", "0")
    assert before["data"] == after["data"]
    assert before["meta"]["fetched_at"] == after["meta"]["fetched_at"]


def test_exact_fixed_capacity_is_accepted_without_extra_page(installed):
    leaf, cli, browser, _ = installed
    rows = [{identity(leaf): str(index)} for index in range(1000)]
    browser.business_script.append(reply(rows))
    result = cli("list", "--live", "--require-complete", "--limit", "0")
    assert result["data"] == sorted(rows, key=lambda row: row[identity(leaf)])
    assert result["meta"]["complete"] is True
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize("leaf", LEAVES)
def test_endpoint_request_allowlist(leaf, monkeypatch):
    import importlib.util
    import sys

    from dogopencli.errors import CliError
    from dogopencli.transport import QueryRequest, validate_request

    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    spec = importlib.util.spec_from_file_location(
        "b14_" + leaf.replace(".", "_"),
        ROOT / "leaf_packages/payment" / leaf / "adapter.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    capability = module.adapter.capability({})
    for body in (
        {"pageNo": 1, "pageSize": 1000},
        {"pageNo": 0, "pageSize": 10},
        {"pageNo": 0, "pageSize": 1000, "status": "ACTIVE"},
    ):
        with pytest.raises(CliError) as error:
            validate_request(
                QueryRequest(
                    capability.name,
                    "GET",
                    capability.contract.host,
                    capability.contract.path,
                    body,
                ),
                capability.contract,
            )
        assert error.value.code == "REQUEST_NOT_ALLOWED"
    for scope, page, size in [
        ("filtered", 1, 1000),
        ("all", True, 1000),
        ("all", 1, True),
        ("all", 1, 1000),
    ]:
        with pytest.raises(CliError):
            capability.page_body(scope, page, size)
