"""Installed entity whitelist List with native scope and local exact filters."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import canonical, parse

ROOT = Path(__file__).resolve().parents[2]
LEAF = "reference.whitelist.entity"


@pytest.fixture(params=["directory", "zip"])
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

    def cli(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    try:
        cli("domain", "enable", "liquidity")
        package = ROOT / "leaf_packages/liquidity" / LEAF
        if request.param == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        archive.write(path, path.relative_to(package))
            package = archive_path
        cli("plugins", "install", str(package))
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def records():
    return [
        {
            "instId": "2",
            "instCode": "F1",
            "status": "INVALID",
            "tntInstId": "",
            "unknown": {
                "children": [None, False, 0, "", Decimal("0.123456789012345678901")]
            },
        },
        {"instId": "10", "instCode": "F1", "status": "VALID"},
        {"instId": "A", "instCode": "F2", "status": "INVALID", "tntInstId": "GUAPW3SG"},
        {"instId": "*", "instCode": None, "status": "FUTURE"},
    ]


def reply(rows, total=None):
    total = len(rows) if total is None else total
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": total,
            "result": {"success": True, "data": rows, "count": total},
        },
    }


def request(offset=0, width=5000):
    return {
        "tntInstId": "GUAPW3SG",
        "instFilterConfigQuery": canonical(
            {
                "tntInstId": "GUAPW3SG",
                "timezone": "GMT+08",
                "rowStart": offset,
                "pageSize": width,
            }
        ),
    }


def test_native_live_refresh_offline_preserve_arrival_order_and_values(installed):
    cli, browser, config = installed
    before = sorted(p.relative_to(config) for p in config.rglob("*") if p.is_file())
    cli("liquidity", "list", LEAF, "--help")
    assert not browser.business_requests
    assert before == sorted(
        p.relative_to(config) for p in config.rglob("*") if p.is_file()
    )
    native = records()
    browser.business_script.append(reply(native))
    live = cli(
        "liquidity", "list", LEAF, "--live", "--require-complete", "--limit", "0"
    )
    assert live["data"] == native
    assert browser.business_requests == [request()]
    expressions = [
        x
        for transport in browser.transports
        for x in transport.expressions
        if "fetch(" in x
    ]
    assert any(
        "/instFilterConfigQuery.json" in x
        and 'method: "GET"' in x
        and "new URLSearchParams(payload)" in x
        for x in expressions
    )
    browser.business_script.append(reply(native))
    assert (
        cli("liquidity", "refresh", LEAF, "--require-complete")["meta"]["published"]
        is True
    )
    count = len(browser.business_requests)
    assert (
        cli("liquidity", "list", LEAF, "--require-complete", "--limit", "0")["data"]
        == native
    )
    assert len(browser.business_requests) == count


def test_exact_repeat_or_and_filters_apply_before_window_and_projection(installed):
    cli, browser, _ = installed
    browser.business_script.append(reply(records()))
    result = cli(
        "liquidity",
        "list",
        LEAF,
        "--live",
        "--entity",
        "2",
        "--entity",
        "10",
        "--financial-code",
        "F1",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        "instId",
    )
    assert result["data"] == [{"instId": "10"}]
    assert browser.business_requests == [request()]
    browser.business_script.append(reply(records()))
    cli("liquidity", "refresh", LEAF)
    assert cli(
        "liquidity", "list", LEAF, "--financial-code", "F1", "--status", "INVALID"
    )["data"] == [records()[0]]
    assert cli("liquidity", "list", LEAF, "--entity", "*")["data"] == [records()[3]]
    for value in ("2,10", "f1", " F1 "):
        assert cli("liquidity", "list", LEAF, "--financial-code", value)["data"] == []


@pytest.mark.parametrize(
    "flags", [("--entity", " "), ("--financial-code", ""), ("--status", "FUTURE")]
)
def test_invalid_filters_fail_before_business_query(installed, flags):
    cli, browser, _ = installed
    assert cli("liquidity", "list", LEAF, "--live", *flags, code=2)["data"] is None
    assert not browser.business_requests


@pytest.mark.parametrize(
    "fault",
    [
        "outer-false",
        "outer-type",
        "inner-false",
        "inner-type",
        "outer-count",
        "count-type",
        "rows",
        "identity",
        "tenant",
        "null-tenant",
        "auth",
        "duplicate",
        "short",
    ],
)
def test_invalid_or_incomplete_refresh_preserves_saved_capture(installed, fault):
    cli, browser, _ = installed
    browser.business_script.append(reply(records()))
    cli("liquidity", "refresh", LEAF, "--require-complete")
    saved = cli("liquidity", "list", LEAF, "--limit", "0")
    response = reply(deepcopy(records()))
    doc, result = response["body"], response["body"]["result"]
    if fault == "outer-false":
        doc["resultFlag"] = False
    if fault == "outer-type":
        doc["resultFlag"] = "true"
    if fault == "inner-false":
        result["success"] = False
    if fault == "inner-type":
        result["success"] = 1
    if fault == "outer-count":
        doc["count"] += 1
    if fault == "count-type":
        result["count"] = True
    if fault == "rows":
        result["data"] = None
    if fault == "identity":
        result["data"][0]["instId"] = 0
    if fault == "tenant":
        result["data"][0]["tntInstId"] = "OTHER"
    if fault == "null-tenant":
        result["data"][0]["tntInstId"] = None
    if fault == "auth":
        response["status"] = 401
    if fault == "duplicate":
        result["data"][1] = deepcopy(result["data"][0])
    if fault == "short":
        result["count"] += 1
        doc["count"] += 1
    browser.business_script.extend(
        [response] * (2 if fault in ("duplicate", "short") else 1)
    )
    assert (
        cli("liquidity", "refresh", LEAF, "--require-complete", code=1)["data"] is None
    )
    after = cli("liquidity", "list", LEAF, "--limit", "0")
    assert after["data"] == saved["data"]
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_short_large_response_restarts_smaller_and_uses_offsets(installed):
    cli, browser, _ = installed
    rows = [{"instId": str(index)} for index in range(1001)]
    browser.business_script.extend(
        [reply(rows[:1000], 1001), reply(rows[:1000], 1001), reply(rows[1000:], 1001)]
    )
    result = cli(
        "liquidity", "list", LEAF, "--live", "--require-complete", "--limit", "0"
    )
    assert result["data"] == rows
    assert browser.business_requests == [
        request(),
        request(0, 1000),
        request(1000, 1000),
    ]


def test_empty_complete_refresh_preserves_saved_data(installed):
    cli, browser, _ = installed
    browser.business_script.append(reply(records()))
    cli("liquidity", "refresh", LEAF)
    saved = cli("liquidity", "list", LEAF, "--limit", "0")
    browser.business_script.append(reply([]))
    assert (
        cli("liquidity", "refresh", LEAF, "--require-complete")["meta"]["published"]
        is False
    )
    after = cli("liquidity", "list", LEAF, "--limit", "0")
    assert saved["data"] == after["data"]
    assert saved["meta"]["fetched_at"] == after["meta"]["fetched_at"]


def test_nested_json_query_allowlist(monkeypatch):
    import importlib.util
    import sys

    from dogopencli.errors import CliError
    from dogopencli.transport import QueryRequest, validate_request

    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    spec = importlib.util.spec_from_file_location(
        "b18_entity", ROOT / "leaf_packages/liquidity" / LEAF / "adapter.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    capability = module.adapter.capability({})
    for changed in [
        {"currentArea": "1"},
        {"tntInstId": "OTHER"},
        {"timezone": "GMT+00"},
        {"pageSize": 10},
    ]:
        body = request()
        body["instFilterConfigQuery"] = canonical(
            {**parse(body["instFilterConfigQuery"]), **changed}
        )
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
    for position, size in [(True, 5000), (1, 5000), (-1000, 1000), (0, True), (0, 10)]:
        with pytest.raises(CliError):
            capability.page_body(module.SCOPE, position, size)
