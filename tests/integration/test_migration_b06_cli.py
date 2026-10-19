"""Installed B06 inquiry packages through the public CLI and fake CDP."""

import json
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
LEAVES = ("rules.transfer", "rules.waterlevel")


@pytest.fixture(params=LEAVES)
def installed(request, run_cli, tmp_path, monkeypatch):
    leaf, source_format = (
        request.param
        if isinstance(request.param, tuple)
        else (request.param, "directory")
    )
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    monkeypatch.delenv("DOGOPENCLI_CONFIG", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    try:
        cli("domain", "enable", "liquidity")
        package = ROOT / "leaf_packages/liquidity" / leaf
        if source_format == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(package))
            package = archive_path
        cli("plugins", "install", str(package))
        yield leaf, cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def native_rows(leaf):
    field = {
        "rules.transfer": "ruleId",
        "rules.waterlevel": "bufferId",
    }[leaf]
    return [
        {
            field: "a",
            "aliasName": "ACCOUNT",
            "currency": "USD",
            "amount": Decimal("0.123456789012345678901"),
            "zero": 0,
            "bizConditions": {"unknown": [None, "", False, "1.0000"]},
        },
        {field: "b", "aliasName": "ACCOUNT", "currency": "EUR"},
    ]


def page(leaf, rows, total=None):
    node = {"success": True}
    if leaf == "rules.transfer":
        node.update(
            transferRuleVOS=rows, ruleCount=len(rows) if total is None else total
        )
    else:
        node.update(dataValue=rows, count=len(rows) if total is None else total)
    return {"status": 200, "body": {"resultFlag": True, "result": node}}


@pytest.mark.parametrize(
    "installed",
    [(leaf, kind) for leaf in LEAVES for kind in ("directory", "zip")],
    indirect=True,
    ids=[f"{leaf}-{kind}" for leaf in LEAVES for kind in ("directory", "zip")],
)
def test_list_live_refresh_offline_and_full_scope(installed):
    leaf, cli, browser, _ = installed
    rows = native_rows(leaf)
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"
    assert not browser.business_requests
    browser.business_script.append(page(leaf, rows))
    live = cli(
        "liquidity", "list", leaf, "--live", "--limit", "1", "--fields", "currency"
    )
    assert live["data"] == [{"currency": "USD"}]
    assert live["meta"]["collected_total"] == 2
    assert live["meta"]["complete"] is True
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(leaf, rows))
    flags = ("--currency", "USD") if leaf == "rules.waterlevel" else ()
    refreshed = cli("liquidity", "refresh", leaf, *flags, "--require-complete")
    offline = cli("liquidity", "list", leaf)
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    if flags:
        assert cli("liquidity", "list", leaf, *flags)["data"] == rows[:1]
        assert cli("liquidity", "list", leaf, "--currency", "usd")["data"] == []
        assert (
            cli("liquidity", "list", leaf, "--currency", "USD", "--currency", "EUR")[
                "data"
            ]
            == rows
        )
    vo = json.loads(
        browser.business_requests[0][
            "transferRuleQueryRequest"
            if leaf == "rules.transfer"
            else "bankAccountBufferQueryVO"
        ]
    )
    assert vo["rowStart"] == 0 and vo["pageSize"] == 5000
    assert vo["tntInstId"] == "GUAPW3SG"
    assert set(browser.business_requests[0]) == {
        "tntInstId",
        "transferRuleQueryRequest"
        if leaf == "rules.transfer"
        else "bankAccountBufferQueryVO",
    }
    if leaf == "rules.transfer":
        assert vo["debitEntity"] == vo["creditEntity"] == []
    else:
        assert vo["startCreditDate"] is vo["endCreditDate"] is None
    expressions = [
        expression
        for transport in browser.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    endpoint = (
        "/transferRuleQuery.json"
        if leaf == "rules.transfer"
        else "/bankAccountBufferQuery.json"
    )
    assert expressions
    assert all(
        endpoint in expression
        and "GET" in expression
        and "new URLSearchParams(payload)" in expression
        for expression in expressions
    )
    before = len(browser.business_requests)
    cli("liquidity", "list", leaf)
    assert len(browser.business_requests) == before


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "business",
        "auth",
        "missing_id",
        "duplicate",
        "conflict",
        "short",
        "invalid_total",
    ],
)
def test_rejected_refresh_preserves_rows_and_capture(installed, failure):
    leaf, cli, browser, _ = installed
    rows = native_rows(leaf)
    browser.business_script.append(page(leaf, rows))
    saved = cli("liquidity", "refresh", leaf)
    candidate = page(leaf, rows)
    expected_code = 1
    if failure == "empty":
        candidate = page(leaf, [])
        expected_code = 0
    elif failure == "business":
        candidate["body"]["result"]["success"] = False
    elif failure == "auth":
        candidate = {"status": 403, "body": {}}
    elif failure == "missing_id":
        candidate = page(leaf, [{"currency": "USD"}])
    elif failure == "duplicate":
        candidate = page(leaf, [rows[0], rows[0]])
    elif failure == "conflict":
        candidate = page(leaf, [rows[0], {**rows[0], "currency": "EUR"}])
    elif failure == "short":
        candidate = page(leaf, rows[:1], total=2)
    else:
        candidate = page(leaf, rows, total=True)
    browser.business_script.append(candidate)
    rejected = cli(
        "liquidity", "refresh", leaf, "--require-complete", code=expected_code
    )
    assert rejected["meta"]["published"] is False
    if failure in ("duplicate", "conflict", "short"):
        assert rejected["error"]["code"] == "INCOMPLETE_RESULT"
    offline = cli("liquidity", "list", leaf)
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("installed", ["rules.waterlevel"], indirect=True)
def test_waterlevel_pagination_and_changed_total(installed):
    leaf, cli, browser, _ = installed
    rows = [{"bufferId": str(i)} for i in range(5001)]
    browser.business_script.extend(
        [page(leaf, rows[:5000], 5001), page(leaf, rows[5000:], 5001)]
    )
    result = cli("liquidity", "refresh", leaf, "--require-complete", "--limit", "1")
    assert result["meta"]["collected_total"] == 5001
    assert [
        json.loads(body["bankAccountBufferQueryVO"])["rowStart"]
        for body in browser.business_requests
    ] == [0, 5000]
    browser.business_script.extend(
        [page(leaf, rows[:5000], 5001), page(leaf, rows[5000:], 5002)]
    )
    assert (
        cli("liquidity", "refresh", leaf, code=1)["error"]["code"] == "INVALID_RESPONSE"
    )
    assert len(cli("liquidity", "list", leaf, "--limit", "0")["data"]) == 5001


@pytest.mark.parametrize(
    "change",
    [
        "endpoint",
        "method",
        "tenant",
        "extra",
        "nested",
        "nested_tenant",
        "nested_size",
        "nested_extra",
    ],
)
def test_transport_default_deny(installed, change):
    from dataclasses import replace

    from dogopencli.errors import CliError
    from dogopencli.leaves.registry import Registry
    from dogopencli.transport import QueryRequest, validate_request

    leaf, _, _, config = installed
    adapter = Registry(config / "config.toml").scan().get("liquidity", leaf).adapter
    capability = adapter.capability({})
    body = capability.page_body("", 0, 5000)
    contract = capability.contract
    request = QueryRequest(
        capability.name, contract.method, contract.host, contract.path, body
    )
    validate_request(request, contract)
    if change == "endpoint":
        request = replace(request, path="/mutation.json")
    elif change == "method":
        request = replace(request, method="POST")
    elif change == "tenant":
        body["tntInstId"] = "OTHER"
    elif change == "extra":
        body["action"] = "edit"
    else:
        key = (
            "transferRuleQueryRequest"
            if leaf == "rules.transfer"
            else "bankAccountBufferQueryVO"
        )
        nested = json.loads(body[key])
        if change == "nested_tenant":
            nested["tntInstId"] = "OTHER"
        elif change == "nested_size":
            nested["pageSize"] = 100
        elif change == "nested_extra":
            nested["action"] = "edit"
        elif leaf == "rules.waterlevel":
            nested["startCreditDate"] = "20260101"
        else:
            nested["rowStart"] = 5000
        body[key] = json.dumps(nested)
    with pytest.raises(CliError) as error:
        validate_request(request, contract)
    assert error.value.code == "REQUEST_NOT_ALLOWED"


def test_waterlevel_get_remains_unregistered(installed):
    leaf, cli, browser, _ = installed
    if leaf != "rules.waterlevel":
        pytest.skip("transfer Get is covered by the SDK acceptance suite")
    cli("liquidity", "get", leaf, "NATIVE_ID", code=2)
    assert not browser.business_requests


def test_sdk_conflict_keeps_last_arrival_and_reports_incomplete(installed):
    leaf, cli, browser, _ = installed
    rows = native_rows(leaf)
    changed = {**rows[0], "currency": "JPY"}
    browser.business_script.append(page(leaf, [rows[0], changed, rows[1]], total=3))
    result = cli("liquidity", "list", leaf, "--live", "--limit", "0")
    assert result["data"] == [changed, rows[1]]
    assert result["meta"]["complete"] is False
    assert result["meta"]["duplicate_count"] == 1


@pytest.mark.parametrize("identity", [None, "", " ", True, [], {}])
def test_invalid_native_identity_is_rejected(installed, identity):
    leaf, cli, browser, _ = installed
    field = "ruleId" if leaf == "rules.transfer" else "bufferId"
    browser.business_script.append(page(leaf, [{field: identity}]))
    result = cli("liquidity", "list", leaf, "--live", code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("installed", ["rules.waterlevel"], indirect=True)
def test_waterlevel_identity_preserves_string_and_integer_types(installed):
    leaf, cli, browser, _ = installed
    rows = [{"bufferId": 1}, {"bufferId": "1"}]
    browser.business_script.append(page(leaf, rows))
    result = cli("liquidity", "list", leaf, "--live", "--require-complete")
    assert result["data"] == rows
    assert result["meta"]["unique_count"] == 2


@pytest.mark.parametrize(
    "failure", ["tenant", "outer", "outer_type", "inner_type", "shape", "count", "rows"]
)
def test_invalid_native_envelope_is_rejected(installed, failure):
    leaf, cli, browser, _ = installed
    rows = native_rows(leaf)
    candidate = page(leaf, rows)
    node = candidate["body"]["result"]
    if failure == "tenant":
        rows[0]["tntInstId"] = "OTHER"
    elif failure == "outer":
        candidate["body"]["resultFlag"] = False
    elif failure == "outer_type":
        candidate["body"]["resultFlag"] = 1
    elif failure == "inner_type":
        node["success"] = 1
    elif failure == "shape":
        candidate["body"]["result"] = []
    elif failure == "count":
        node["ruleCount" if leaf == "rules.transfer" else "count"] = -1
    else:
        node["transferRuleVOS" if leaf == "rules.transfer" else "dataValue"] = [None]
    browser.business_script.append(candidate)
    result = cli("liquidity", "list", leaf, "--live", code=1)
    assert result["error"]["code"] == (
        "BUSINESS_QUERY_FAILED" if failure == "outer" else "INVALID_RESPONSE"
    )


@pytest.mark.parametrize(
    "scope,position,width",
    [
        ("OTHER", 0, 5000),
        ("", True, 5000),
        ("", -1, 5000),
        ("", 1, 5000),
        ("", 0, True),
        ("", 0, 100),
    ],
)
def test_unverified_page_inputs_are_rejected(installed, scope, position, width):
    from dogopencli.errors import CliError
    from dogopencli.leaves.registry import Registry

    leaf, _, browser, config = installed
    adapter = Registry(config / "config.toml").scan().get("liquidity", leaf).adapter
    with pytest.raises(CliError) as error:
        adapter.capability({}).page_body(scope, position, width)
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


@pytest.mark.parametrize("installed", ["rules.transfer"], indirect=True)
def test_transfer_single_capacity_shortfall_is_incomplete(installed):
    leaf, cli, browser, _ = installed
    browser.business_script.append(page(leaf, native_rows(leaf), total=5001))
    result = cli("liquidity", "refresh", leaf, "--require-complete", code=1)
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert len(browser.business_requests) == 1
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize("installed", ["rules.waterlevel"], indirect=True)
@pytest.mark.parametrize("failure", ["empty", "short", "duplicate", "conflict"])
def test_waterlevel_incomplete_pages_preserve_previous_cache(installed, failure):
    leaf, cli, browser, _ = installed
    original = native_rows(leaf)
    browser.business_script.append(page(leaf, original))
    saved = cli("liquidity", "refresh", leaf)
    rows = [{"bufferId": i} for i in range(5001)]
    first, last = rows[:5000], rows[5000:]
    if failure == "empty":
        first = []
    elif failure == "short":
        first = first[:-1]
    elif failure == "duplicate":
        last = [first[0]]
    else:
        last = [{**first[0], "currency": "JPY"}]
    browser.business_script.extend([page(leaf, first, 5001), page(leaf, last, 5001)])
    rejected = cli("liquidity", "refresh", leaf, "--require-complete", code=1)
    assert rejected["error"]["code"] == "INCOMPLETE_RESULT"
    offline = cli("liquidity", "list", leaf)
    assert offline["data"] == original
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
