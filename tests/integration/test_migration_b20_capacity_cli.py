"""Installed B20 capacity List: explicit requested sets and native values."""

import shutil
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.leaves.registry import Registry
from dogopencli.transport import QueryRequest, validate_request

ROOT = Path(__file__).resolve().parents[2]
LEAF = "risk.account_capacity"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
FIELDS = (
    "aliasName",
    "currency",
    "accountAvailableBalance",
    "availableIod",
    "availableResource",
    "cashPoolSupportAvailableResource",
    "outFlowCapacity",
    "totalIod",
    "usedIod",
    "valueTime",
)


@pytest.fixture
def installed(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for key in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(key, raising=False)
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(action, *flags, code=0):
        status, output, error = run_cli(["liquidity", action, LEAF, *flags])
        assert status == code, output + error
        return parse(output)

    try:
        source = tmp_path / "source"
        shutil.copytree(SOURCE, source)
        package = source
        if getattr(request, "param", "directory") == "zip":
            package = tmp_path / "capacity.zip"
            with ZipFile(package, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(source))
        status, output, error = run_cli(["plugins", "install", str(package)])
        assert status == 0, output + error
        shutil.rmtree(source)
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def native(alias, **values):
    return {
        "aliasName": alias,
        "currency": "USD",
        "accountAvailableBalance": "1.000000000000000000000001",
        "availableIod": None,
        "availableResource": "-0.0000000000000000001",
        "cashPoolSupportAvailableResource": "",
        "outFlowCapacity": Decimal("2.345678901234567890123"),
        "totalIod": 0,
        "usedIod": False,
        "valueTime": "2026-01-01 12:34:56",
        "unassignedField": {"nested": [None, False, "", 0]},
        **values,
    }


def response(record):
    return {"status": 200, "body": {"success": True, "data": record}}


def flags(*aliases):
    return [part for alias in aliases for part in ("--account-alias", alias)]


def scripted(browser, rows):
    def handler(body, _):
        assert set(body) == {"aliasName"}
        return response(rows[body["aliasName"]])

    browser.business_handler = handler


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_requested_set_native_projection_complete_refresh_offline(installed):
    cli, browser, config = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.transports
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    rows = {alias: native(alias) for alias in ("A", "B")}
    scripted(browser, rows)
    expected = [{field: rows[alias][field] for field in FIELDS} for alias in ("A", "B")]
    live = cli("list", "--live", *flags("B", "A"), "--limit", "0", "--require-complete")
    assert live["data"] == expected
    assert live["meta"]["scope"] == {"aliasName": ["A", "B"]}
    assert live["meta"]["reported_total"] is None
    assert live["meta"]["total_semantics"] == "requested_accounts"
    assert live["meta"]["complete"] is True
    assert live["meta"]["dataset_complete"] is True
    assert live["meta"]["requested_count"] == live["meta"]["resolved_count"] == 2
    assert live["meta"]["collected_total"] == live["meta"]["unique_count"] == 2
    assert live["meta"]["acquisition"]["duplicate_count"] == 0
    assert browser.business_requests == [{"aliasName": "A"}, {"aliasName": "B"}]
    assert not (config / "leaf-cache.sqlite3").exists()
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    saved = cli("refresh", *flags("B", "A"), "--require-complete")
    count = len(browser.business_requests)
    offline = cli("list", "--limit", "0", "--require-complete")
    assert offline["data"] == expected
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert offline["meta"]["acquisition"] == saved["meta"]["acquisition"]
    assert len(browser.business_requests) == count
    trace = saved["meta"]["acquisition"]["attempts"][-1]
    assert trace["queries"]["capacity"] == {
        "kind": "detail",
        "calls": 2,
        "requests": 2,
        "succeeded": 2,
    }
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions and all(
        "/api/fund/capacity/queryFundCapacityByAliasName.json" in expression
        and 'method: "GET"' in expression
        for expression in expressions
    )


@pytest.mark.parametrize("size", [1, 10])
def test_minimum_maximum_sets_fully_acquired_before_display_window(installed, size):
    cli, browser, _ = installed
    aliases = [f"A{i:02}" for i in range(size)]
    scripted(browser, {alias: native(alias) for alias in aliases})
    result = cli(
        "list",
        "--live",
        *flags(*reversed(aliases)),
        "--limit",
        "1",
        "--fields",
        "aliasName,availableResource,outFlowCapacity",
        "--require-complete",
    )
    assert result["data"] == [
        {
            "aliasName": aliases[0],
            "availableResource": "-0.0000000000000000001",
            "outFlowCapacity": Decimal("2.345678901234567890123"),
        }
    ]
    assert result["meta"]["requested_count"] == size
    assert result["meta"]["resolved_count"] == size
    assert browser.business_requests == [{"aliasName": alias} for alias in aliases]


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        flags(" "),
        flags(""),
        flags("A", "A"),
        flags(*map(str, range(11))),
        ["--account-alias", "A", "--tenant", "OTHER"],
    ],
)
def test_invalid_account_sets_fail_before_browser(installed, arguments):
    cli, browser, _ = installed
    assert (
        cli("list", "--live", *arguments, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    )
    assert not browser.transports
    assert not browser.business_requests


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("auth", "AUTH_REQUIRED"),
        ("business", "BUSINESS_QUERY_FAILED"),
        ("json", "INVALID_RESPONSE"),
        ("marker_missing", "INVALID_RESPONSE"),
        ("marker_string", "INVALID_RESPONSE"),
        ("data_missing", "INVALID_RESPONSE"),
        ("data_null", "INVALID_RESPONSE"),
        ("data_array", "INVALID_RESPONSE"),
        ("data_empty", "INVALID_RESPONSE"),
        ("alias_missing", "INVALID_RESPONSE"),
        ("alias_blank", "INVALID_RESPONSE"),
        ("alias_other", "INVALID_RESPONSE"),
    ],
)
def test_failure_after_first_account_is_atomic_and_preserves_cache(
    installed, failure, expected
):
    cli, browser, _ = installed
    rows = {alias: native(alias) for alias in ("A", "B", "C")}
    scripted(browser, rows)
    saved = cli("refresh", *flags("A", "B", "C"), "--require-complete")
    previous = cli("list", "--limit", "0")
    rejected = response(deepcopy(rows["B"]))
    document = rejected["body"]
    if failure == "auth":
        rejected = {"status": 401, "body": {}}
    elif failure == "business":
        document.update(success=False, errorCode="099", message="PRIVATE")
    elif failure == "json":
        rejected["body"] = "broken-json"
    elif failure == "marker_missing":
        del document["success"]
    elif failure == "marker_string":
        document["success"] = "true"
    elif failure == "data_missing":
        del document["data"]
    elif failure == "data_null":
        document["data"] = None
    elif failure == "data_array":
        document["data"] = [rows["B"]]
    elif failure == "data_empty":
        document["data"] = {}
    elif failure == "alias_missing":
        del document["data"]["aliasName"]
    elif failure == "alias_blank":
        document["data"]["aliasName"] = " "
    else:
        document["data"]["aliasName"] = "OTHER"

    def handler(body, _):
        return (
            rejected if body["aliasName"] == "B" else response(rows[body["aliasName"]])
        )

    browser.business_handler = handler
    for action, options in (("list", ["--live"]), ("refresh", [])):
        start = len(browser.business_requests)
        result = cli(action, *options, *flags("C", "B", "A"), code=1)
        assert result["error"]["code"] == expected
        assert result.get("data") in (None, [])
        assert "PRIVATE" not in str(result)
        assert browser.business_requests[start:] == [
            {"aliasName": "A"},
            {"aliasName": "B"},
        ]
        evidence = result["meta"]["query_evidence"]["queries"]["capacity"]
        assert evidence["succeeded"] == 1 and evidence["calls"] == 2
        if action == "refresh":
            assert result["meta"]["published"] is False
    offline = cli("list", "--limit", "0", "--require-complete")
    assert offline["data"] == previous["data"]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_local_alias_selection_projection_and_changed_coverage(installed):
    cli, browser, _ = installed
    scripted(browser, {alias: native(alias) for alias in ("A", "B")})
    saved = cli("refresh", *flags("B", "A"))
    count = len(browser.business_requests)
    reordered = cli("list", *flags("A", "B"), "--require-complete")
    assert reordered["meta"]["complete"] is True
    selected = cli("list", *flags("B"), "--fields", "aliasName,currency")
    assert selected["data"] == [{"aliasName": "B", "currency": "USD"}]
    assert selected["meta"]["complete"] is False
    assert selected["meta"]["source_acquisition"]["scope_complete"] is True
    assert (
        cli("list", *flags("B"), "--require-complete", code=1)["error"]["code"]
        == "INCOMPLETE_RESULT"
    )
    assert cli("list", *flags("UNKNOWN"))["data"] == []
    assert len(browser.business_requests) == count
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert cli("get", "A", code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not cli("describe")["data"]["operations"].get("get")


def test_optional_fields_remain_absent_and_values_keep_native_types(installed):
    cli, browser, _ = installed
    scripted(
        browser,
        {"A": {"aliasName": "A", "availableResource": {"unknown": [None, False]}}},
    )
    result = cli("list", "--live", *flags("A"))
    assert result["data"] == [
        {"aliasName": "A", "availableResource": {"unknown": [None, False]}}
    ]


@pytest.mark.parametrize(
    "change", ["path", "method", "tenant", "date", "paging", "mutation"]
)
def test_closed_native_contract_rejects_injected_requests(installed, change):
    _, _, config = installed
    adapter = Registry(config / "config.toml").scan().get("liquidity", LEAF).adapter
    inquiry = adapter.query_capability("list", "capacity", {"account_alias": ["A"]})
    contract = inquiry.contract
    request = QueryRequest(
        inquiry.name,
        contract.method,
        contract.host,
        contract.path,
        inquiry.request_body({}, "A"),
    )
    validate_request(request, contract)
    if change == "path":
        request = replace(request, path="/mutation.json")
    elif change == "method":
        request = replace(request, method="POST")
    else:
        request.body[
            {
                "tenant": "tntInstId",
                "date": "queryDate",
                "paging": "pageSize",
                "mutation": "action",
            }[change]
        ] = "unverified"
    with pytest.raises(CliError) as error:
        validate_request(request, contract)
    assert error.value.code == "REQUEST_NOT_ALLOWED"


def test_help_and_describe_do_not_activate_adapter_or_storage(installed):
    cli, browser, config = installed
    leaf = Registry(config / "config.toml").scan().get("liquidity", LEAF)
    (leaf.path / "adapter.py").write_text(
        "raise AssertionError('adapter activation')\n"
    )
    cli("list", "--help")
    cli("refresh", "-h")
    cli("describe")
    assert not browser.transports
    assert not browser.business_requests
    assert not (config / "leaf-cache.sqlite3").exists()
