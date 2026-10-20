"""Installed B17 outflow case library preserves two-read retained stability."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.leaves.registry import Registry
from dogopencli.transport import QueryRequest, validate_request

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["directory", "zip"])
def installed(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for name in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(name, raising=False)
    browser = FakeBrowser(
        href="https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/productPTRManagement/caseLibrary"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(operation, *args, code=0):
        status, output, error = run_cli(["payment", operation, "ptr.cases", *args])
        assert status == code, output + error
        return parse(output)

    try:
        status, output, error = run_cli(["domain", "enable", "payment"])
        assert status == 0, output + error
        package = ROOT / "leaf_packages/payment/ptr.cases"
        if request.param == "zip":
            target = tmp_path / "candidate.zip"
            with ZipFile(target, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        archive.write(path, path.relative_to(package))
            package = target
        status, output, error = run_cli(["plugins", "install", str(package)])
        assert status == 0, output + error
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def row(identity="CASE-2", **fields):
    return {
        "id": identity,
        "caseName": "Exact,*",
        "caseType": "OUTFLOW",
        "creditorCurrency": "USD",
        "verifyResult": False,
        "gmtModified": 0,
        "fundOutAbilityBaselineVO": {
            "financialInstCode": "BANK",
            "debtorAccountAliasName": "ALIAS",
            "debtorCurrency": "USD",
            "supportObo": None,
            "unknown": ["not retained"],
        },
        "creditorAmount": {
            "amount": Decimal("0.123456789012345678901"),
            "cent": 12345678901234567890,
            "centFactor": 100,
            "currency": "USD",
            "currencyCode": "USD",
            "currencyValue": "840",
            "unknown": "not retained",
        },
        "debtorAmount": None,
        "unknown": ["not retained"],
        **fields,
    }


def reply(rows, *, total=None, page=0, size=5000):
    return {
        "status": 200,
        "body": {
            "success": True,
            "resultDataList": rows,
            "pageNo": page,
            "pageSize": size,
            "totalCount": len(rows) if total is None else total,
        },
    }


def expected(rows):
    result = deepcopy(rows)
    for record in result:
        record.pop("unknown", None)
        record["fundOutAbilityBaselineVO"].pop("unknown", None)
        if record.get("creditorAmount") is not None:
            record["creditorAmount"].pop("unknown", None)
    return sorted(result, key=lambda record: record["id"])


def stable(browser, rows):
    browser.business_script.extend([reply(rows), reply(deepcopy(rows))])


def test_two_read_projection_refresh_offline_and_help(installed):
    cli, browser, config = installed
    files = sorted(
        path.relative_to(config) for path in config.rglob("*") if path.is_file()
    )
    cli("list", "--help")
    assert not browser.business_requests
    assert files == sorted(
        path.relative_to(config) for path in config.rglob("*") if path.is_file()
    )
    rows = [row(), row("CASE-10")]
    second = deepcopy(rows[::-1])
    second[0]["unknown"] = "changed ignored field"
    second[0]["fundOutAbilityBaselineVO"]["unknown"] = False
    second[0]["creditorAmount"]["unknown"] = 7
    browser.business_script.extend([reply(rows), reply(second)])
    live = cli("list", "--live", "--require-complete", "--limit", "0")
    assert live["data"] == expected(rows)
    assert browser.business_requests == [{"pageNo": 0, "pageSize": 5000}] * 2
    acquisition = live["meta"]["acquisition"]
    trace = acquisition["attempts"][-1]
    assert trace["kind"] == "custom_query"
    assert trace["queries"]["cases"]["calls"] == 2
    assert trace["queries"]["cases"]["succeeded"] == 2
    assert len(trace["queries"]["cases"]["collections"]) == 2
    assert not (config / "leaf-cache.sqlite3").exists()
    stable(browser, rows)
    refreshed = cli("refresh", "--require-complete")
    assert refreshed["meta"]["published"] is True
    before = len(browser.business_requests)
    offline = cli("list", "--limit", "0")
    assert offline["data"] == expected(rows)
    assert len(browser.business_requests) == before
    assert offline["meta"]["acquisition"] == refreshed["meta"]["acquisition"]


def test_exact_filters_after_both_complete_reads(installed):
    cli, browser, _ = installed
    rows = [row("A"), row("B", caseName="Other"), row("C", caseName="Exact")]
    stable(browser, rows)
    result = cli(
        "list",
        "--live",
        "--name",
        "Exact,*",
        "--name",
        "Other",
        "--channel",
        "BANK",
        "--debtor-currency",
        "USD",
        "--fields",
        "id,caseName",
        "--offset",
        "1",
        "--limit",
        "1",
    )
    assert result["data"] == [{"id": "B", "caseName": "Other"}]
    assert len(browser.business_requests) == 2
    stable(browser, rows)
    assert cli("list", "--live", "--name", "Exact*", "--limit", "0")["data"] == []


@pytest.mark.parametrize("change", ["content", "amount", "baseline", "total"])
def test_unstable_retained_contents_preserve_capture(installed, change):
    cli, browser, config = installed
    original = [row()]
    stable(browser, original)
    cli("refresh")
    database = config / "leaf-cache.sqlite3"
    before = database.read_bytes()
    changed = deepcopy(original)
    if change == "content":
        changed[0]["caseName"] = "changed"
    elif change == "amount":
        changed[0]["creditorAmount"]["amount"] = Decimal("0.123456789012345678902")
    elif change == "baseline":
        changed[0]["fundOutAbilityBaselineVO"]["financialInstCode"] = "OTHER"
    else:
        changed.append(row("NEW"))
    browser.business_script.extend([reply(original), reply(changed)])
    result = cli("refresh", code=1)
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert database.read_bytes() == before
    assert cli("list", "--limit", "0")["data"] == expected(original)


@pytest.mark.parametrize(
    "failure,error",
    [
        (reply([row(), row()]), "INCOMPLETE_RESULT"),
        (reply([row()], total=5001), "INCOMPLETE_RESULT"),
        (reply([row()], total=2), "INCOMPLETE_RESULT"),
        (reply([row()], page=1), "INVALID_RESPONSE"),
        (reply([row()], size=True), "INVALID_RESPONSE"),
        (reply([row(creditorAmount={"amount": True})]), "INVALID_RESPONSE"),
        (
            {"status": 200, "body": {"success": False, "errorContext": "PRIVATE"}},
            "BUSINESS_QUERY_FAILED",
        ),
        ({"status": 401, "body": {}}, "AUTH_REQUIRED"),
    ],
)
def test_second_failure_is_not_partial_success(installed, failure, error):
    cli, browser, config = installed
    browser.business_script.extend([reply([row()]), failure])
    result = cli("list", "--live", code=1)
    assert result["data"] is None
    assert result["error"]["code"] == error
    assert len(browser.business_requests) == 2
    stable(browser, [row()])
    cli("refresh")
    database = config / "leaf-cache.sqlite3"
    before = database.read_bytes()
    browser.business_script.extend([reply([row()]), failure])
    failed_refresh = cli("refresh", code=1)
    assert failed_refresh["error"]["code"] == error
    assert failed_refresh["meta"]["published"] is False
    assert database.read_bytes() == before


def test_empty_refresh_preserves_capture(installed):
    cli, browser, config = installed
    stable(browser, [row()])
    cli("refresh")
    database = config / "leaf-cache.sqlite3"
    before = database.read_bytes()
    stable(browser, [])
    result = cli("refresh")
    assert result["meta"]["published"] is False
    assert database.read_bytes() == before


def test_request_contract_rejects_extra_fields_and_execution(installed):
    _, _, config = installed
    leaf = Registry(config / "config.toml").scan().get("payment", "ptr.cases")
    capability = leaf.adapter.query_capability("list", "cases", {})
    body = capability.page_body("outflow-library", 0, 5000)
    contract = capability.contract

    def request(body):
        return QueryRequest(
            capability.name, contract.method, contract.host, contract.path, body
        )

    validate_request(request(body), contract)
    for forbidden in (
        replace(request(body), method="POST"),
        replace(request(body), path="/api/ptr/case/execute.json"),
        replace(request(body), host="other.invalid"),
    ):
        with pytest.raises(CliError):
            validate_request(forbidden, contract)
    for forbidden in (
        {**body, "caseName": "x"},
        {**body, "pageNo": 1},
        {**body, "pageSize": 1000},
        {**body, "execute": True},
    ):
        with pytest.raises(CliError):
            validate_request(request(forbidden), contract)
