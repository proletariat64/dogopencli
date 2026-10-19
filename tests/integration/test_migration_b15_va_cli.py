"""Native VA List/Get at independent directory and ZIP installation boundaries."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
LEAF = "va.rules"


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
    browser = FakeBrowser(
        href="https://ifundbossportal.alipay.com/voucher/VARuleManage"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    try:
        cli("domain", "enable", "collection")
        package = ROOT / "leaf_packages/collection" / LEAF
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
            "vaRuleId": value,
            "bankRuleId": 123,
            "countries": ["LIST-COUNTRY"],
            "unknown": {
                "children": [None, False, 0, "", Decimal("0.123456789012345678901")]
            },
        }
        for value in ("10", "2", "001", "A")
    ]


def native_detail(identity="2"):
    return {
        "vaRuleId": identity,
        "bankRuleId": 123,
        "assembleStrategy": "NATIVE",
        "assignInfo": {"unknown": [None, False, 0, Decimal("1.0000000000000000001")]},
        "clientEntity": "SYNTHETIC",
        "creditAreas": ["DETAIL-AREA"],
        "entity": "SYNTHETIC",
        "memo": "",
        "regionType": "NATIVE",
        "ruleStatus": "NATIVE",
        "sceneCodes": [],
        "vaWarningInfo": {"unknownSynthetic": [0, None]},
        "extension": {"preserved": True},
    }


def reply(detail, status=200):
    return {"status": status, "body": {"success": True, "resultObj": detail}}


def list_reply(rows, total=None, page=1, size=1000):
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


def test_full_native_list_refresh_offline_and_windowed_details(installed):
    cli, browser, _ = installed
    native = records()
    expected = [native[2], native[1], native[0], native[3]]
    cli("collection", "list", LEAF, "--help")
    cli("collection", "get", LEAF, "--help")
    assert not browser.business_requests
    browser.business_script.append(list_reply(native))
    assert (
        cli("collection", "list", LEAF, "--live", "--require-complete", "--limit", "0")[
            "data"
        ]
        == expected
    )
    assert browser.business_requests == [{"pageNo": 1, "pageSize": 1000}]
    browser.business_script.append(list_reply(native))
    cli("collection", "refresh", LEAF, "--require-complete")
    saved = cli("collection", "list", LEAF, "--limit", "0")
    detail = native_detail()
    browser.business_script.extend([list_reply(native), reply(detail)])
    combined = cli(
        "collection",
        "list",
        LEAF,
        "--live",
        "--with-detail",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        "vaRuleId",
    )
    assert combined["data"] == [{"record": {"vaRuleId": "2"}, "detail": detail}]
    assert browser.business_requests[-1] == {"vaRuleId": "2"}
    assert "countries" not in combined["data"][0]["detail"]
    after = cli("collection", "list", LEAF, "--limit", "0")
    assert after["data"] == saved["data"] == expected
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    browser.business_script.append(list_reply(native))
    before = len(browser.business_requests)
    assert (
        cli("collection", "list", LEAF, "--live", "--with-detail", "--offset", "4")[
            "data"
        ]
        == []
    )
    assert len(browser.business_requests) == before + 1


def test_independent_get_preserves_native_root_without_publication(installed):
    cli, browser, config = installed
    before = sorted(p.relative_to(config) for p in config.rglob("*") if p.is_file())
    detail = native_detail()
    browser.business_script.append(reply(detail))
    assert cli("collection", "get", LEAF, "2")["data"] == detail
    assert browser.business_requests == [{"vaRuleId": "2"}]
    expressions = [
        x
        for transport in browser.transports
        for x in transport.expressions
        if "fetch(" in x
    ]
    assert any(
        "ifundboss-api.alipay.com/ivostro/api/virtualAccountRule/detail.json" in x
        and 'method: "GET"' in x
        and "new URLSearchParams(payload)" in x
        for x in expressions
    )
    assert before == sorted(
        p.relative_to(config) for p in config.rglob("*") if p.is_file()
    )


@pytest.mark.parametrize("lookup", ["", " "])
def test_blank_get_lookup_fails_before_business_queries(installed, lookup):
    cli, browser, _ = installed
    assert cli("collection", "get", LEAF, lookup, code=2)["data"] is None
    assert not browser.business_requests


@pytest.mark.parametrize(
    "failure",
    [
        "refusal",
        "wrong-id",
        "numeric-id",
        "missing-field",
        "null-root",
        "array-root",
        "auth",
    ],
)
def test_get_failure_is_not_found_or_empty_success(installed, failure):
    cli, browser, _ = installed
    detail = native_detail()
    response = reply(detail)
    if failure == "refusal":
        response["body"]["success"] = False
    if failure == "wrong-id":
        detail["vaRuleId"] = "OTHER"
    if failure == "numeric-id":
        detail["vaRuleId"] = 2
    if failure == "missing-field":
        del detail["assignInfo"]
    if failure == "null-root":
        response["body"]["resultObj"] = None
    if failure == "array-root":
        response["body"]["resultObj"] = []
    if failure == "auth":
        response["status"] = 401
    browser.business_script.append(response)
    result = cli("collection", "get", LEAF, "2", code=1)
    assert result["data"] is None
    assert result["error"]["code"] == (
        "BUSINESS_QUERY_FAILED"
        if failure == "refusal"
        else "AUTH_REQUIRED"
        if failure == "auth"
        else "INVALID_RESPONSE"
    )


def test_optional_warning_and_explicit_null_business_fields_preserved(installed):
    cli, browser, _ = installed
    detail = native_detail()
    del detail["vaWarningInfo"]
    detail["assignInfo"] = None
    detail["clientEntity"] = None
    browser.business_script.append(reply(detail))
    assert cli("collection", "get", LEAF, "2")["data"] == detail


def test_second_selected_detail_refusal_is_atomic_and_preserves_saved_list(installed):
    cli, browser, _ = installed
    native = records()
    browser.business_script.append(list_reply(native))
    cli("collection", "refresh", LEAF, "--require-complete")
    saved = cli("collection", "list", LEAF, "--limit", "0")
    refusal = reply(None)
    refusal["body"]["success"] = False
    browser.business_script.extend(
        [list_reply(native), reply(native_detail("001")), refusal]
    )
    result = cli(
        "collection", "list", LEAF, "--live", "--with-detail", "--limit", "2", code=1
    )
    assert result["data"] is None
    assert browser.business_requests[-2:] == [{"vaRuleId": "001"}, {"vaRuleId": "2"}]
    after = cli("collection", "list", LEAF, "--limit", "0")
    assert after["data"] == saved["data"]
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "failure",
    [
        "refusal",
        "rows",
        "identity",
        "echo",
        "size",
        "total",
        "duplicate",
        "gap",
        "capacity",
    ],
)
def test_failed_or_incomplete_list_refresh_preserves_prior_capture(installed, failure):
    cli, browser, _ = installed
    native = records()
    browser.business_script.append(list_reply(native))
    cli("collection", "refresh", LEAF, "--require-complete")
    saved = cli("collection", "list", LEAF, "--limit", "0")
    response = list_reply(deepcopy(native))
    doc = response["body"]
    if failure == "refusal":
        doc["success"] = False
    if failure == "rows":
        doc["resultDataList"] = None
    if failure == "identity":
        doc["resultDataList"][0]["vaRuleId"] = True
    if failure == "echo":
        doc["pageNo"] = 0
    if failure == "size":
        doc["pageSize"] = 10
    if failure == "total":
        doc["totalCount"] = True
    if failure == "duplicate":
        doc["resultDataList"][1] = deepcopy(doc["resultDataList"][0])
    if failure == "gap":
        doc["totalCount"] += 1
    if failure == "capacity":
        doc["totalCount"] = 1001
    browser.business_script.append(response)
    assert (
        cli("collection", "refresh", LEAF, "--require-complete", code=1)["data"] is None
    )
    after = cli("collection", "list", LEAF, "--limit", "0")
    assert after["data"] == saved["data"]
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("missing", [False, True])
def test_native_zero_total_empty_response_does_not_publish(installed, missing):
    cli, browser, _ = installed
    browser.business_script.append(list_reply(records()))
    cli("collection", "refresh", LEAF)
    saved = cli("collection", "list", LEAF, "--limit", "0")
    response = list_reply([])
    if missing:
        del response["body"]["resultDataList"]
    browser.business_script.append(response)
    assert (
        cli("collection", "refresh", LEAF, "--require-complete")["meta"]["published"]
        is False
    )
    after = cli("collection", "list", LEAF, "--limit", "0")
    assert after["data"] == saved["data"]
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_closed_native_request_contracts(monkeypatch):
    import importlib.util
    import sys

    from dogopencli.errors import CliError
    from dogopencli.transport import QueryRequest, validate_request

    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    spec = importlib.util.spec_from_file_location(
        "b15_va", ROOT / "leaf_packages/collection/va.rules/adapter.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for capability, bodies in [
        (
            module.adapter.capability({}),
            [
                {"pageNo": 0, "pageSize": 1000},
                {"pageNo": 1, "pageSize": 1000, "bankRuleId": 123},
            ],
        ),
        (module.adapter.detail_capability({}), [{"vaRuleId": "2", "bankRuleId": 123}]),
    ]:
        for body in bodies:
            with pytest.raises(CliError) as error:
                validate_request(
                    QueryRequest(
                        capability.name,
                        capability.contract.method,
                        capability.contract.host,
                        capability.contract.path,
                        body,
                    ),
                    capability.contract,
                )
            assert error.value.code == "REQUEST_NOT_ALLOWED"
