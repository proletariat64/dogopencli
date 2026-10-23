"""Installed collection network configurations retain native values and scope."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAVES = ("clearing_system", "card_template")


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
    page = (
        "CollectionClearingSystemConfig"
        if leaf == LEAVES[0]
        else "CollectionCardTemplateConfig"
    )
    browser = FakeBrowser(href="https://ifundbossportal.alipay.com/voucher/" + page)
    cdp.set_transport_factory(browser.transport)

    def cli(operation, *args, code=0):
        status, output, error = run_cli(["collection", operation, leaf, *args])
        assert status == code, output + error
        return parse(output)

    try:
        status, output, error = run_cli(["domain", "enable", "collection"])
        assert status == 0, output + error
        package = ROOT / "leaf_packages/collection" / leaf
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


def records():
    return [
        {
            "id": "2",
            "supportedCountry": "SG",
            "supportedCurrency": "USD",
            "status": "ACTIVE",
            "supportedFinancialInst": "BANK-A",
            "templateName": "Name-A",
            "clearingNetworkId": "SYSTEM-A",
            "clearingNetworkType": "TYPE-A",
            "cardTemplateItemList": [
                {"unknown": [None, False, 0, "", Decimal("0.123456789012345678901")]}
            ],
        },
        {
            "id": "10",
            "supportedCountry": "US",
            "supportedCurrency": "USD",
            "status": "ACTIVE",
            "supportedFinancialInst": "BANK-B",
            "templateName": "Name-B",
            "clearingNetworkId": "SYSTEM-B",
            "clearingNetworkType": "TYPE-B",
            "unknown": {"native": True},
        },
        {
            "id": "30",
            "supportedCountry": "SG",
            "supportedCurrency": "EUR",
            "status": "INACTIVE",
            "templateName": "Name-A",
            "clearingNetworkId": "SYSTEM-A",
        },
        {
            "id": "40",
            "supportedCountry": "*",
            "supportedCurrency": "USD",
            "status": "ACTIVE",
        },
        {
            "id": "50",
            "supportedCountry": None,
            "supportedCurrency": "USD",
            "status": "ACTIVE",
        },
    ]


def reply(rows, total=None, page=1, size=1000):
    return {
        "status": 200,
        "body": {
            "success": True,
            "resultDataList": rows,
            "totalCount": len(rows) if total is None else total,
            "pageNo": page,
            "pageSize": size,
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
    native = records()
    browser.business_script.append(reply(native))
    result = cli("list", "--live", "--require-complete", "--limit", "0")
    expected = sorted(native, key=lambda row: row["id"])
    assert result["data"] == expected
    assert browser.business_requests == [{"pageNo": 1, "pageSize": 1000}]
    endpoint = "clearingNetworkInfo" if leaf == LEAVES[0] else "cardTemplate"
    expressions = [
        x
        for transport in browser.transports
        for x in transport.expressions
        if "fetch(" in x
    ]
    assert any(
        "ifundboss-api.alipay.com/ivostro/api/" + endpoint + "/pageList.json" in x
        and "application/json" in x
        for x in expressions
    )
    browser.business_script.append(reply(native))
    saved = cli("refresh", "--require-complete")
    assert saved["meta"]["published"] is True
    before = len(browser.business_requests)
    assert cli("list", "--limit", "0")["data"] == expected
    assert len(browser.business_requests) == before


def test_exact_or_and_filters_precede_projection_and_window(installed):
    leaf, cli, browser, _ = installed
    browser.business_script.append(reply(records()))
    result = cli(
        "list",
        "--live",
        "--bank-location",
        "SG",
        "--bank-location",
        "US",
        "--currency",
        "USD",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        "id",
    )
    assert result["data"] == [{"id": "2"}]
    assert browser.business_requests == [{"pageNo": 1, "pageSize": 1000}]
    browser.business_script.append(reply(records()))
    cli("refresh", "--require-complete")
    assert [
        row["id"] for row in cli("list", "--bank-location", "*", "--limit", "0")["data"]
    ] == ["40"]
    for value in ("SG,US", "sg", " SG "):
        assert cli("list", "--bank-location", value)["data"] == []
    named = "--system-name" if leaf == LEAVES[0] else "--template-name"
    assert [
        row["id"]
        for row in cli(
            "list", named, "SYSTEM-A" if leaf == LEAVES[0] else "Name-A", "--limit", "0"
        )["data"]
    ] == ["2", "30"]
    if leaf == LEAVES[1]:
        assert [row["id"] for row in cli("list", "--template-id", "10")["data"]] == [
            "10"
        ]


@pytest.mark.parametrize("value", ["", " "])
def test_blank_local_filter_fails_before_business_query(installed, value):
    _, cli, browser, _ = installed
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
        "auth",
        "duplicate",
        "gap",
        "capacity",
    ],
)
def test_failure_never_replaces_previous_capture(installed, failure):
    _, cli, browser, _ = installed
    native = records()
    browser.business_script.append(reply(native))
    cli("refresh", "--require-complete")
    before = cli("list", "--limit", "0")
    response = reply(deepcopy(native))
    doc = response["body"]
    if failure == "success":
        doc["success"] = False
    if failure == "success-type":
        doc["success"] = "true"
    if failure == "rows":
        doc["resultDataList"] = None
    if failure == "identity":
        doc["resultDataList"][0]["id"] = 12
    if failure == "page":
        doc["pageNo"] = 0
    if failure == "size":
        doc["pageSize"] = 10
    if failure == "total":
        doc["totalCount"] = True
    if failure == "auth":
        response["status"] = 401
    if failure == "duplicate":
        doc["resultDataList"][1] = deepcopy(doc["resultDataList"][0])
    if failure == "gap":
        doc["totalCount"] += 1
    if failure == "capacity":
        doc["totalCount"] = 1001
    browser.business_script.append(response)
    assert cli("refresh", "--require-complete", code=1)["data"] is None
    after = cli("list", "--limit", "0")
    assert before["data"] == after["data"]
    assert before["meta"]["fetched_at"] == after["meta"]["fetched_at"]


@pytest.mark.parametrize("page", [0, 1])
def test_explicit_empty_page_preserves_prior_capture(installed, page):
    _, cli, browser, _ = installed
    browser.business_script.append(reply(records()))
    cli("refresh", "--require-complete")
    before = cli("list", "--limit", "0")
    browser.business_script.append(reply([], page=page))
    assert cli("refresh", "--require-complete")["meta"]["published"] is False
    after = cli("list", "--limit", "0")
    assert before["data"] == after["data"]
    assert before["meta"]["fetched_at"] == after["meta"]["fetched_at"]


def test_exact_fixed_capacity_is_accepted_without_extra_page(installed):
    _, cli, browser, _ = installed
    rows = [{"id": str(index)} for index in range(1000)]
    browser.business_script.append(reply(rows))
    result = cli("list", "--live", "--require-complete", "--limit", "0")
    assert result["data"] == sorted(rows, key=lambda row: row["id"])
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
        "b13_" + leaf, ROOT / "leaf_packages/collection" / leaf / "adapter.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    capability = module.adapter.capability({})
    for body in (
        {"pageNo": 2, "pageSize": 1000},
        {"pageNo": 1, "pageSize": 10},
        {"pageNo": 1, "pageSize": 1000, "status": "ACTIVE"},
    ):
        with pytest.raises(CliError) as error:
            validate_request(
                QueryRequest(
                    capability.name,
                    "POST",
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
        ("all", 0, 1000),
    ]:
        with pytest.raises(CliError):
            capability.page_body(scope, page, size)
