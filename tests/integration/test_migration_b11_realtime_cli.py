"""Installed realtime LG preserves dependent context and unproven history coverage."""

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
        href="https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(operation, *args, code=0):
        status, output, error = run_cli(
            ["liquidity", operation, "network.realtime", *args]
        )
        assert status == code, output + error
        return parse(output)

    try:
        status, output, error = run_cli(["domain", "enable", "liquidity"])
        assert status == 0, output + error
        package = ROOT / "leaf_packages/liquidity/network.realtime"
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


def row(identity="NETWORK", **fields):
    return {
        "id": identity,
        "scene": "REALTIME",
        "version": 2,
        "creditAliasName": "CREDIT",
        "debitAliasName": "DEBIT",
        "fundAction": "TRANSFER",
        "routeId": "ROUTE",
        "networkStatus": "ENABLE",
        "runStatus": "READY",
        "gmtModified": 0,
        "singlePaymentLimit": Decimal("0.123456789012345678901"),
        "privateText": "omit",
        "dynamicStatistics": {"omit": True},
        **fields,
    }


def retained(record):
    return {
        key: value
        for key, value in record.items()
        if key not in {"privateText", "dynamicStatistics"}
    }


def success(data):
    return {"status": 200, "body": {"success": True, "data": data}}


def source(rows, total=None):
    return success({"data": rows, "totalCount": len(rows) if total is None else total})


def route_reply():
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "count": 999,
                "data": {
                    "dynamicQuotas": [
                        {"unknown": [None, False, Decimal("1.00000000000000001")]}
                    ],
                    "staticQuotas": [{"quotaId": ""}, {"quotaId": ""}],
                },
            },
        },
    }


def coverage(result):
    return result["meta"]["query_evidence"]["coverage"]


def test_list_settings_refresh_offline_and_declaration_only_help(installed):
    cli, browser, config = installed
    cli("list", "--help")
    cli("get", "--help")
    assert not browser.business_requests
    rows = [row("B"), row("A")]
    browser.business_script.append(source(rows))
    live = cli("list", "--live", "--require-complete", "--limit", "0")
    assert live["data"] == [retained(rows[1]), retained(rows[0])]
    assert live["meta"]["reported_total"] == 2
    assert browser.business_requests == [{"rowStart": 0, "pageSize": 5000}]
    assert not (config / "leaf-cache.sqlite3").exists()
    browser.business_script.append(source(rows))
    cli("refresh")
    count = len(browser.business_requests)
    assert cli("list", "--limit", "0")["data"] == live["data"]
    assert len(browser.business_requests) == count


def test_get_preserves_original_root_history_route_and_separate_coverage(installed):
    cli, browser, config = installed
    duckdog_before = (config / "duckdog.duckdb").read_bytes()
    root = row()
    history = [row("OLD", version=1), root]
    route = route_reply()
    browser.business_script.extend([success(root), success(history), route])
    result = cli("get", "NETWORK")
    assert result["data"] == {
        **retained(root),
        "operationHistory": [retained(item) for item in history],
        "routeDetails": route["body"]["result"]["data"],
    }
    assert browser.business_requests == [
        {"id": "NETWORK"},
        {
            "creditAliasName": ["CREDIT"],
            "debitAliasName": ["DEBIT"],
            "fundAction": "TRANSFER",
        },
        {"routeId": "ROUTE", "aliasName": "DEBIT", "tntInstId": "GUAPW3SG"},
    ]
    evidence = coverage(result)
    assert evidence["scope_complete"] is False
    assert "HISTORY_COVERAGE_UNPROVEN" in evidence["reasons"]
    components = evidence["attempts"][0]["components"]
    assert components["network"]["complete"] is True
    assert components["operationHistory"]["complete"] is False
    assert components["operationHistory"]["selected_root_relation"] == "matched"
    assert components["routeDetails"]["complete"] is True
    assert not (config / "leaf-cache.sqlite3").exists()
    assert (config / "duckdog.duckdb").read_bytes() == duckdog_before


@pytest.mark.parametrize("route_state", [None, "", "missing"])
def test_empty_history_stays_unproven_and_route_inapplicable_vs_unknown(
    installed, route_state
):
    cli, browser, _ = installed
    root = row(routeId=route_state)
    if route_state == "missing":
        del root["routeId"]
    browser.business_script.extend([success(root), success([])])
    result = cli("get", "NETWORK")
    assert result["data"]["operationHistory"] == []
    assert result["data"]["routeDetails"] is None
    evidence = coverage(result)
    assert "HISTORY_COVERAGE_UNPROVEN" in evidence["reasons"]
    component = evidence["attempts"][0]["components"]["routeDetails"]
    assert component["status"] == (
        "unverified" if route_state == "missing" else "inapplicable"
    )
    assert component["complete"] is (route_state != "missing")
    assert len(browser.business_requests) == 2


def test_missing_history_context_is_unverified_not_empty_success(installed):
    cli, browser, _ = installed
    root = row(scene="OTHER", routeId=None)
    browser.business_script.append(success(root))
    result = cli("get", "NETWORK")
    assert result["data"]["operationHistory"] is None
    assert "HISTORY_CONTEXT_UNVERIFIED" in coverage(result)["reasons"]
    assert len(browser.business_requests) == 1


def test_changed_root_in_history_remains_explicit(installed):
    cli, browser, _ = installed
    browser.business_script.extend(
        [success(row(routeId=None)), success([row(routeId=None, version=3)])]
    )
    result = cli("get", "NETWORK")
    assert "SOURCE_CHANGED" in coverage(result)["reasons"]
    assert result["data"]["version"] == 2
    assert result["data"]["operationHistory"][0]["version"] == 3


@pytest.mark.parametrize(
    "failure,error",
    [
        ("root-id", "INVALID_RESPONSE"),
        ("history-scope", "INVALID_RESPONSE"),
        ("history-version", "INVALID_RESPONSE"),
        ("history-conflict", "INVALID_RESPONSE"),
        ("history-business", "BUSINESS_QUERY_FAILED"),
        ("route-context", "INVALID_RESPONSE"),
        ("route-shape", "INVALID_RESPONSE"),
        ("route-business", "BUSINESS_QUERY_FAILED"),
        ("route-auth", "AUTH_REQUIRED"),
    ],
)
def test_required_child_failure_aborts_whole_get_without_changing_saved_list(
    installed, failure, error
):
    cli, browser, config = installed
    browser.business_script.append(source([row()]))
    cli("refresh")
    database = config / "leaf-cache.sqlite3"
    before = database.read_bytes()
    root, history, route = success(row()), success([row()]), route_reply()
    if failure == "root-id":
        root["body"]["data"]["id"] = "WRONG"
    elif failure == "history-scope":
        history["body"]["data"][0]["debitAliasName"] = "WRONG"
    elif failure == "history-version":
        history["body"]["data"][0]["version"] = True
    elif failure == "history-conflict":
        history["body"]["data"].append(row(privateText="changed"))
    elif failure == "history-business":
        history["body"]["success"] = False
    elif failure == "route-context":
        route["body"]["result"]["data"]["aliasName"] = "WRONG"
    elif failure == "route-shape":
        del route["body"]["result"]["data"]["staticQuotas"]
    elif failure == "route-business":
        route["body"]["result"]["success"] = False
    else:
        route["status"] = 401
    browser.business_script.extend([root, history, route])
    result = cli("get", "NETWORK", code=1)
    assert result["data"] is None
    assert result["error"]["code"] == error
    assert database.read_bytes() == before


@pytest.mark.parametrize(
    "failure,error",
    [
        ("conflict", "INVALID_RESPONSE"),
        ("duplicate", "INCOMPLETE_RESULT"),
        ("gap", "INCOMPLETE_RESULT"),
        ("missing-id", "INVALID_RESPONSE"),
        ("business", "BUSINESS_QUERY_FAILED"),
        ("inner-business", "BUSINESS_QUERY_FAILED"),
        ("inner-type", "INVALID_RESPONSE"),
        ("empty", None),
    ],
)
def test_invalid_or_empty_source_preserves_snapshot(installed, failure, error):
    cli, browser, config = installed
    browser.business_script.append(source([row()]))
    cli("refresh")
    database = config / "leaf-cache.sqlite3"
    before = database.read_bytes()
    response = source([row()])
    data = response["body"]["data"]
    if failure == "conflict":
        data["data"].append(row(privateText="changed ignored field"))
        data["totalCount"] = 2
    elif failure == "duplicate":
        data["data"].append(deepcopy(row()))
        data["totalCount"] = 2
    elif failure == "gap":
        data["totalCount"] = 2
    elif failure == "missing-id":
        del data["data"][0]["id"]
    elif failure == "business":
        response["body"]["success"] = False
    elif failure == "inner-business":
        data["success"] = False
    elif failure == "inner-type":
        data["success"] = "true"
    else:
        response = source([])
    browser.business_script.append(response)
    result = cli("refresh", code=1 if error else 0)
    if error:
        assert result["error"]["code"] == error
    assert result["meta"]["published"] is False
    assert database.read_bytes() == before


def test_request_contracts_are_closed_and_scope_bound(installed):
    _, browser, config = installed
    leaf = Registry(config / "config.toml").scan().get("liquidity", "network.realtime")
    cap = leaf.adapter.capability({})
    body = cap.page_body("all", 0, 5000)
    request = QueryRequest(cap.name, "POST", cap.contract.host, cap.contract.path, body)
    validate_request(request, cap.contract)
    for invalid in (
        replace(request, body={**body, "rowStart": 1}),
        replace(request, body={**body, "pageSize": 10000}),
        replace(request, body={**body, "execute": True}),
    ):
        with pytest.raises(CliError):
            validate_request(invalid, cap.contract)
    history = leaf.adapter.query_capability("get", "history", {})
    with pytest.raises(CliError):
        history.request_body(
            {"creditAliasName": "ANY", "debitAliasName": "D", "fundAction": "TRANSFER"}
        )
    assert not browser.business_requests


def test_unproven_history_warns_and_strict_get_withholds_data(installed):
    cli, browser, _ = installed
    browser.business_script.extend([success(row(routeId=None)), success([])])
    result = cli("get", "NETWORK")
    assert result["meta"]["complete"] is False
    assert result["meta"]["warnings"][0]["code"] == "INCOMPLETE_RESULT"
    browser.business_script.extend([success(row(routeId=None)), success([])])
    failed = cli("get", "NETWORK", "--require-complete", code=1)
    assert failed["data"] is None
    assert failed["error"]["code"] == "INCOMPLETE_RESULT"
    assert "HISTORY_COVERAGE_UNPROVEN" in failed["meta"]["warnings"][0]["reason_codes"]
