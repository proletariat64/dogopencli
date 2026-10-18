"""Installed B06 inquiry packages through the public CLI and fake CDP."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
LEAVES = ("rules.notification", "rules.transfer", "rules.waterlevel")


@pytest.fixture(params=LEAVES)
def installed(request, run_cli, tmp_path, monkeypatch):
    leaf = request.param
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
        cli("plugins", "install", str(ROOT / "leaf_packages/liquidity" / leaf))
        yield leaf, cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def native_rows(leaf):
    field = {
        "rules.notification": "id",
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


def detail(leaf, value):
    container = {
        "rules.notification": "data",
        "rules.transfer": "transferRuleVO",
        "rules.waterlevel": "dataValue",
    }[leaf]
    marker = "success" if leaf == "rules.transfer" else "resultFlag"
    # count=0 is native envelope plumbing, not the detail row count.
    return {
        "status": 200,
        "body": {
            marker: True,
            "result": {"success": True, "count": 0, container: value},
        },
    }


def test_native_details_preserve_shape_fields_and_request(installed):
    leaf, cli, browser, _ = installed
    rows = native_rows(leaf)
    value = rows if leaf == "rules.waterlevel" else rows[0]
    identity = "ACCOUNT" if leaf == "rules.waterlevel" else "a"
    field = {
        "rules.notification": "id",
        "rules.transfer": "ruleId",
        "rules.waterlevel": "aliasName",
    }[leaf]
    browser.business_script.append(detail(leaf, value))
    result = cli("liquidity", "get", leaf, identity)
    assert result["data"] == value
    assert result["meta"]["returned_count"] == (2 if isinstance(value, list) else 1)
    assert result["meta"]["collected_total"] == result["meta"]["returned_count"]
    assert browser.business_requests == [{field: identity, "tntInstId": "GUAPW3SG"}]
    browser.business_script.append(detail(leaf, value))
    projected = cli("liquidity", "get", leaf, identity, "--fields", "currency")
    assert projected["data"] == (
        [{"currency": "USD"}, {"currency": "EUR"}]
        if isinstance(value, list)
        else {"currency": "USD"}
    )


@pytest.mark.parametrize(
    "failure", ["echo", "tenant", "shape", "outer", "inner", "auth"]
)
def test_detail_rejects_invalid_or_failed_responses(installed, failure):
    leaf, cli, browser, _ = installed
    rows = native_rows(leaf)
    value = rows if leaf == "rules.waterlevel" else rows[0]
    identity = "ACCOUNT" if leaf == "rules.waterlevel" else "a"
    response = detail(leaf, value)
    if failure == "echo":
        rows[0][
            {
                "rules.notification": "id",
                "rules.transfer": "ruleId",
                "rules.waterlevel": "aliasName",
            }[leaf]
        ] = "wrong"
    elif failure == "tenant":
        rows[0]["tntInstId"] = "OTHER"
    elif failure == "shape":
        response = detail(leaf, [1] if isinstance(value, list) else [])
    elif failure == "outer":
        response["body"]["success" if leaf == "rules.transfer" else "resultFlag"] = (
            False
        )
    elif failure == "inner":
        response["body"]["result"]["success"] = False
    else:
        response = {"status": 401, "body": {}}
    browser.business_script.append(response)
    result = cli("liquidity", "get", leaf, identity, code=1)
    assert result["data"] is None
    expected = (
        "AUTH_REQUIRED"
        if failure == "auth"
        else "BUSINESS_QUERY_FAILED"
        if failure in ("outer", "inner")
        else "INVALID_RESPONSE"
    )
    assert result["error"]["code"] == expected


def require_list(installed):
    if installed[0] == "rules.notification":
        pytest.skip("notification remains get-only")
    return installed


def test_list_live_refresh_offline_and_full_scope(installed):
    leaf, cli, browser, _ = require_list(installed)
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
    leaf, cli, browser, _ = require_list(installed)
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
    offline = cli("liquidity", "list", leaf)
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_waterlevel_pagination_and_changed_total(installed):
    leaf, cli, browser, _ = require_list(installed)
    if leaf != "rules.waterlevel":
        pytest.skip("transfer is a single inquiry")
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


def test_get_only_and_array_validation(installed):
    leaf, cli, browser, _ = installed
    if leaf == "rules.notification":
        cli("liquidity", "list", leaf, code=2)
        cli("liquidity", "refresh", leaf, code=2)
        assert not browser.business_requests
    elif leaf == "rules.waterlevel":
        browser.business_script.append(detail(leaf, []))
        result = cli("liquidity", "get", leaf, "ACCOUNT")
        assert result["data"] == [] and result["meta"]["returned_count"] == 0
        row = native_rows(leaf)[0]
        browser.business_script.append(detail(leaf, [row, row]))
        assert (
            cli("liquidity", "get", leaf, "ACCOUNT", code=1)["error"]["code"]
            == "INVALID_RESPONSE"
        )
        row.pop("bufferId")
        browser.business_script.append(detail(leaf, [row]))
        assert (
            cli("liquidity", "get", leaf, "ACCOUNT", code=1)["error"]["code"]
            == "INVALID_RESPONSE"
        )


@pytest.mark.parametrize("change", ["endpoint", "tenant", "extra", "nested"])
def test_transport_default_deny(installed, change):
    from dataclasses import replace

    from dogopencli.errors import CliError
    from dogopencli.leaves.registry import Registry
    from dogopencli.transport import QueryRequest, validate_request

    leaf, _, _, config = installed
    adapter = Registry(config / "config.toml").scan().get("liquidity", leaf).adapter
    capability = adapter.capability({})
    if leaf == "rules.notification":
        body = {"id": "a", "tntInstId": "GUAPW3SG"}
    elif leaf == "rules.transfer":
        body = capability.page_body("", 0, 5000)
    else:
        body = capability.page_body("", 0)
    contract = capability.contract
    request = QueryRequest(
        capability.name, contract.method, contract.host, contract.path, body
    )
    validate_request(request, contract)
    if change == "endpoint":
        request = replace(request, path="/mutation.json")
    elif change == "tenant":
        body["tntInstId"] = "OTHER"
    elif change == "extra":
        body["action"] = "edit"
    elif leaf == "rules.notification":
        body["version"] = 1
    else:
        key = (
            "transferRuleQueryRequest"
            if leaf == "rules.transfer"
            else "bankAccountBufferQueryVO"
        )
        nested = json.loads(body[key])
        if leaf == "rules.waterlevel":
            nested["startCreditDate"] = "20260101"
        else:
            nested["rowStart"] = 5000
        body[key] = json.dumps(nested)
    with pytest.raises(CliError) as error:
        validate_request(request, contract)
    assert error.value.code == "REQUEST_NOT_ALLOWED"


def test_array_without_declared_identity_does_not_claim_uniqueness(installed):
    leaf, cli, browser, config = installed
    if leaf != "rules.waterlevel":
        pytest.skip("array detail host contract")
    manifest = config / "plugins/liquidity/rules.waterlevel/leaf.json"
    value = json.loads(manifest.read_text())
    value["identity"] = []
    manifest.write_text(json.dumps(value))
    rows = native_rows(leaf)
    browser.business_script.append(detail(leaf, rows))
    result = cli("liquidity", "get", leaf, "ACCOUNT")
    assert result["data"] == rows
    assert result["meta"]["acquisition"]["unique_count"] is None
    assert result["meta"]["acquisition"]["duplicate_count"] is None
    assert result["meta"]["acquisition"]["total_semantics"] == "occurrences"
