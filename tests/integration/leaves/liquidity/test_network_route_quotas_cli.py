"""Installed route quota aggregate retains native arrays and request identity."""

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

ROOT = Path(__file__).resolve().parents[4]


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
            ["liquidity", operation, "network.route_quotas", *args]
        )
        assert status == code, output + error
        return parse(output)

    try:
        status, output, error = run_cli(["domain", "enable", "liquidity"])
        assert status == 0, output + error
        package = ROOT / "leaf_packages/liquidity/network.route_quotas"
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


def aggregate():
    dynamic = {
        "dateRange": {"begin": 0, "end": 1000},
        "individualLimit": {
            "currency": "USD",
            "hasLimit": True,
            "limit": Decimal("123456789.1234567890123456789"),
        },
    }
    static = {
        "quotaId": "",
        "bic": "BANK",
        "quotaSide": "DEBIT",
        "unknown": [False, None, "1.0000", 999999999999999999],
        "updateTimeSliceConfig": {"nested": [0, ""]},
    }
    return {
        "dynamicQuotas": [dynamic, deepcopy(dynamic)],
        "staticQuotas": [static, deepcopy(static)],
        "unknown": {"retained": True},
    }


def reply(data=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "count": 999,
                "data": aggregate() if data is None else data,
            },
        },
    }


def get(cli, *args, **kwargs):
    return cli("get", "ROUTE", "--account-alias", "ACCOUNT", *args, **kwargs)


def test_native_arrays_context_metadata_and_no_publication(installed):
    cli, browser, config = installed
    cli("get", "--help")
    assert not browser.business_requests
    assert not (config / "leaf-cache.sqlite3").exists()
    assert not (config / "duckdog.duckdb").exists()
    data = aggregate()
    browser.business_script.append(reply(data))
    result = get(cli)
    assert result["data"] == data
    assert "routeId" not in result["data"]
    assert "aliasName" not in result["data"]
    assert "tntInstId" not in result["data"]
    assert result["meta"]["query"] == {
        "identity": "ROUTE",
        "parameters": {"account_alias": "ACCOUNT", "tenant": "GUAPW3SG"},
    }
    assert result["meta"]["query_evidence"]["queries"]["quotas"]["succeeded"] == 1
    assert browser.business_requests == [
        {"routeId": "ROUTE", "aliasName": "ACCOUNT", "tntInstId": "GUAPW3SG"}
    ]
    assert not (config / "leaf-cache.sqlite3").exists()
    assert not (config / "duckdog.duckdb").exists()


@pytest.mark.parametrize("echo", ["missing", "empty", "matching"])
def test_optional_context_echo_and_empty_arrays(installed, echo):
    cli, browser, _ = installed
    data = {"dynamicQuotas": [], "staticQuotas": []}
    if echo == "empty":
        data.update(routeId="", aliasName=None, tntInstId="")
    elif echo == "matching":
        data.update(routeId="ROUTE", aliasName="ACCOUNT", tntInstId="GUAPW3SG")
    browser.business_script.append(reply(data))
    assert get(cli)["data"] == data


@pytest.mark.parametrize(
    "failure,error",
    [
        ("outer", "BUSINESS_QUERY_FAILED"),
        ("inner", "BUSINESS_QUERY_FAILED"),
        ("outer-type", "INVALID_RESPONSE"),
        ("inner-type", "INVALID_RESPONSE"),
        ("missing-array", "INVALID_RESPONSE"),
        ("member", "INVALID_RESPONSE"),
        ("root", "INVALID_RESPONSE"),
        ("routeId", "INVALID_RESPONSE"),
        ("aliasName", "INVALID_RESPONSE"),
        ("tntInstId", "INVALID_RESPONSE"),
        ("echo-type", "INVALID_RESPONSE"),
        ("auth", "AUTH_REQUIRED"),
    ],
)
def test_errors_do_not_return_partial_aggregate_or_publish(installed, failure, error):
    cli, browser, config = installed
    response = reply()
    result = response["body"]["result"]
    data = result["data"]
    if failure == "outer":
        response["body"]["resultFlag"] = False
    elif failure == "inner":
        result["success"] = False
        result["errorContext"] = "PRIVATE"
    elif failure == "outer-type":
        response["body"]["resultFlag"] = "true"
    elif failure == "inner-type":
        result["success"] = "true"
    elif failure == "missing-array":
        del data["staticQuotas"]
    elif failure == "member":
        data["dynamicQuotas"] = [None]
    elif failure == "root":
        result["data"] = []
    elif failure in {"routeId", "aliasName", "tntInstId"}:
        data[failure] = "WRONG"
    elif failure == "echo-type":
        data["routeId"] = 1
    else:
        response["status"] = 401
    browser.business_script.append(response)
    output = get(cli, code=1)
    assert output["data"] is None
    assert output["error"]["code"] == error
    assert "PRIVATE" not in str(output)
    assert not (config / "leaf-cache.sqlite3").exists()
    assert not (config / "duckdog.duckdb").exists()


@pytest.mark.parametrize(
    "args",
    [
        ["ROUTE"],
        ["ANY", "--account-alias", "ACCOUNT"],
        [" ", "--account-alias", "ACCOUNT"],
        ["ROUTE", "--account-alias", "ANY"],
        ["ROUTE", "--account-alias", " "],
        ["ROUTE", "--account-alias", "ACCOUNT", "--tenant", "OTHER"],
    ],
)
def test_invalid_context_fails_before_query(installed, args):
    cli, browser, _ = installed
    result = cli("get", *args, code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


def test_closed_transport_contract(installed):
    _, browser, config = installed
    leaf = (
        Registry(config / "config.toml").scan().get("liquidity", "network.route_quotas")
    )
    cap = leaf.adapter.query_capability("get", "quotas", {"account_alias": "ACCOUNT"})
    body = cap.request_body({"routeId": "ROUTE", "account_alias": "ACCOUNT"})
    request = QueryRequest(cap.name, "GET", cap.contract.host, cap.contract.path, body)
    validate_request(request, cap.contract)
    for invalid in (
        replace(request, method="POST"),
        replace(request, path="/updateWhaleRoute.json"),
        replace(request, body={**body, "tntInstId": "OTHER"}),
        replace(request, body={**body, "execute": True}),
    ):
        with pytest.raises(CliError):
            validate_request(invalid, cap.contract)
    assert not browser.business_requests
