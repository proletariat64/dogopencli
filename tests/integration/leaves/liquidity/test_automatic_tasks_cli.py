"""Installed automatic-operation List through the public CLI and fake CDP."""

import json
import shutil
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

ROOT = Path(__file__).resolve().parents[4]
LEAF = "operations.automatic_tasks"
FLAGS = ("--from-time", "2026-10-23T00:00:00", "--to-time", "2026-10-23T23:59:59")


def row(index=0, **values):
    return {
        "taskId": f"TASK-{index}",
        "gmtCreate": "2026-10-23 12:34:56",
        "lastModifiedTime": "2026-10-24 00:42:01",
        "endTime": "",
        "decisionStatus": "SUCCESS",
        "operationStatus": "PENDING",
        "completionStatus": "UNFINISHED",
        "successfulDecisionAmount": "0.123456789012345678901",
        "successfulOperationAmount": "0.0000",
        "amount": "12345678901234567890.000000000000000001",
        "currency": "USD",
        "operationStrategyName": "NATIVE_OPERATION_STRATEGY",
        "subStrategyName": "NATIVE_SUB_STRATEGY",
        "unknown": {
            "children": [None, False, "1.0000", Decimal("0.123456789012345678901")]
        },
        **values,
    }


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


@pytest.fixture(params=["directory"])
def installed(request, run_cli, tmp_path, monkeypatch):
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
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        status, output, error = run_cli(["liquidity", action, LEAF, *args])
        assert status == code, output + error
        return parse(output)

    try:
        source = tmp_path / "source"
        shutil.copytree(ROOT / "leaf_packages/liquidity" / LEAF, source)
        candidate = source
        if request.param == "one-page-budget":
            manifest = json.loads((source / "leaf.json").read_text())
            manifest["collection"]["max_pages"] = 1
            (source / "leaf.json").write_text(json.dumps(manifest))
        if request.param == "zip":
            candidate = tmp_path / "candidate.zip"
            with ZipFile(candidate, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(source))
        status, output, error = run_cli(["plugins", "install", str(candidate)])
        assert status == 0, output + error
        shutil.rmtree(source)
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def test_native_tasks_preserve_values_and_bound_post_json_scope(installed):
    cli, browser, _ = installed
    records = [row(9), row(2)]
    browser.business_script.append(page(records))
    result = cli("list", "--live", *FLAGS, "--limit", "0", "--require-complete")
    assert result["data"] == records
    assert result["meta"]["complete"] is True
    assert browser.business_requests == [
        {
            "tntInstId": "GUAPW3SG",
            "rowStart": 0,
            "pageSize": 10,
            "minDate": "2026-10-23 00:00:00",
            "maxDate": "2026-10-23 23:59:59",
        }
    ]
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions and all(
        "/riskActionTask/listQuery.json" in e and 'method: "POST"' in e
        for e in expressions
    )


@pytest.mark.parametrize(
    "bounds",
    [
        (),
        ("2026-10-23T00:00:00",),
        ("2026-02-30T00:00:00", "2026-10-23T23:59:59"),
        ("2026-10-24T00:00:00", "2026-10-23T23:59:59"),
        ("2026-10-01T00:00:00", "2026-11-01T00:00:00"),
        ("2026-10-23 00:00:00", "2026-10-23T23:59:59"),
        ("2026-10-23T00:00:00+08:00", "2026-10-23T23:59:59"),
        ("2026-1-3T00:00:00", "2026-10-23T23:59:59"),
    ],
)
def test_invalid_created_bounds_fail_before_browser(installed, bounds):
    cli, browser, _ = installed
    options = [
        item
        for name, value in zip(("--from-time", "--to-time"), bounds, strict=False)
        for item in (name, value)
    ]
    assert (
        cli("list", "--live", *options, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    )
    assert not browser.transports


@pytest.mark.parametrize(
    "values",
    [
        {"taskId": None},
        {"taskId": 7},
        {"taskId": ""},
        {"taskId": " "},
        {"gmtCreate": None},
        {"gmtCreate": "2026-02-30 12:00:00"},
        {"gmtCreate": "2026-10-22 23:59:59"},
        {"gmtCreate": "2026-10-24 00:00:00"},
        {"gmtCreate": "2026-10-23T12:00:00"},
        {"tntInstId": "OTHER"},
    ],
)
def test_contradictory_native_identity_or_created_scope_is_rejected(installed, values):
    cli, browser, _ = installed
    browser.business_script.append(page([row(**values)]))
    assert cli("list", "--live", *FLAGS, code=1)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_full_acquisition_live_isolation_and_offline_replay(installed):
    cli, browser, _ = installed
    cli("list", "--help")
    cli("describe")
    assert not browser.transports
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    records = [row(i) for i in range(11)]
    browser.business_script.extend([page(records[:10], 11), page(records[10:], 11)])
    live = cli("list", "--live", *FLAGS, "--limit", "1", "--require-complete")
    assert live["data"] == records[:1]
    assert live["meta"]["collected_total"] == 11
    assert [body["rowStart"] for body in browser.business_requests] == [0, 10]
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.extend([page(records[:10], 11), page(records[10:], 11)])
    saved = cli("refresh", *FLAGS, "--require-complete")
    assert saved["meta"]["published"] is True
    browser.business_script.append(page([row(99)]))
    assert cli("list", "--live", *FLAGS)["data"] == [row(99)]
    count = len(browser.transports)
    browser.running = False
    offline = cli("list", "--limit", "0", "--require-complete")
    assert offline["data"] == records
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.transports) == count
    assert (
        cli("list", *FLAGS, "--to-time", "2026-10-24T00:00:00", code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert len(browser.transports) == count


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "short",
        "duplicate",
        "conflict",
        "zero_total",
        "auth",
        "business",
        "marker",
        "shape",
        "rows",
        "identity",
        "total_type",
        "total_negative",
        "total_missing",
        "json",
        "scope",
        "count_change",
        "interior_hole",
    ],
)
def test_empty_or_rejected_refresh_preserves_previous_capture(installed, failure):
    cli, browser, _ = installed
    records = [row(77)]
    browser.business_script.append(page(records))
    saved = cli("refresh", *FLAGS, "--require-complete")
    candidates = [page([row(88)])]
    code, expected = 1, "INVALID_RESPONSE"
    if failure == "empty":
        candidates, code = [page([])], 0
    elif failure == "short":
        candidates, expected = [page([row(88)], 2)], "INCOMPLETE_RESULT"
    elif failure == "duplicate":
        candidates, expected = [page([row(88), row(88)], 2)], "INCOMPLETE_RESULT"
    elif failure == "conflict":
        candidates, expected = (
            [page([row(88), row(88, amount="OTHER")], 2)],
            "INCOMPLETE_RESULT",
        )
    elif failure == "zero_total":
        candidates = [page([row(88)], 0)]
    elif failure == "auth":
        candidates, expected = [{"status": 401, "body": {}}], "AUTH_REQUIRED"
    elif failure == "business":
        candidates[0]["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        candidates[0]["body"]["success"] = 1
    elif failure == "shape":
        candidates[0]["body"]["data"] = []
    elif failure == "rows":
        candidates = [page([None])]
    elif failure == "identity":
        candidates[0]["body"]["data"]["data"][0].pop("taskId")
    elif failure == "total_type":
        candidates = [page([row(88)], True)]
    elif failure == "total_negative":
        candidates = [page([row(88)], -1)]
    elif failure == "total_missing":
        candidates[0]["body"]["data"].pop("totalCount")
    elif failure == "json":
        candidates = [{"status": 200, "body": "not JSON"}]
    elif failure == "scope":
        candidates = [page([row(88, gmtCreate="2026-10-24 00:00:00")])]
    elif failure == "count_change":
        candidates = [page([row(i) for i in range(10)], 11), page([row(10)], 12)]
        expected = "INVALID_RESPONSE"
    elif failure == "interior_hole":
        candidates = [
            page([row(i) for i in range(10)], 21),
            page([], 21),
            page([row(20)], 21),
        ]
        expected = "INCOMPLETE_RESULT"
    browser.business_script.extend(candidates)
    rejected = cli("refresh", *FLAGS, "--require-complete", code=code)
    assert rejected["meta"]["published"] is False
    if code:
        assert rejected["error"]["code"] == expected
    offline = cli("list", "--limit", "0")
    assert offline["data"] == records
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "options", [("--page-size", "1000"), ("--status", "SUCCESS"), ("--with-detail",)]
)
def test_unqualified_filters_and_composition_rejected_before_browser(
    installed, options
):
    cli, browser, _ = installed
    assert (
        cli("list", "--live", *FLAGS, *options, code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert not browser.transports


@pytest.mark.parametrize("installed", ["one-page-budget"], indirect=True)
def test_page_budget_rejection_preserves_prior_capture(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row(77)]))
    saved = cli("refresh", *FLAGS)
    records = [row(i) for i in range(10)]
    browser.business_script.append(page(records, 11))
    live = cli("list", "--live", *FLAGS, "--limit", "0", code=1)
    assert live["data"] is None
    assert live["error"]["code"] == "TIMEOUT"
    assert len(browser.business_requests) == 2
    browser.business_script.append(page(records, 11))
    rejected = cli("refresh", *FLAGS, code=1)
    assert rejected["error"]["code"] == "TIMEOUT"
    assert rejected["meta"]["published"] is False
    offline = cli("list", "--limit", "0")
    assert offline["data"] == [row(77)]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "change", ["method", "path", "extra", "tenant", "bounds", "width"]
)
def test_restricted_transport_rejects_unverified_request(installed, change):
    _, browser, config = installed
    parameters = {
        "from_time": "2026-10-23T00:00:00",
        "to_time": "2026-10-23T23:59:59",
    }
    adapter = Registry(config / "config.toml").scan().get("liquidity", LEAF).adapter
    capability = adapter.capability(parameters)
    body = capability.page_body(adapter.scope(parameters), 0, 10)
    request = QueryRequest(
        capability.name,
        "POST",
        "iliquidity.alipay.com",
        "/riskActionTask/listQuery.json",
        body,
    )
    validate_request(request, capability.contract)
    if change == "method":
        request = replace(request, method="GET")
    elif change == "path":
        request = replace(request, path="/riskActionTask/reportConfirm.json")
    elif change == "extra":
        body["action"] = "confirm"
    elif change == "tenant":
        body["tntInstId"] = "OTHER"
    elif change == "bounds":
        body["minDate"] = "2026-10-01 00:00:00"
    elif change == "width":
        body["pageSize"] = 1000
    with pytest.raises(CliError) as caught:
        validate_request(request, capability.contract)
    assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests
