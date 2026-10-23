"""Nine accepted native Get contracts at the installed CLI boundary."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
CASES = {
    "cash.pools": ("id", "id", "id", "/cashPoolDetail.json", "POST", "json"),
    "investment.holdings": (
        "orderId",
        "orderId",
        "investmentNo",
        "/queryIncrementOrderDetail.json",
        "POST",
        "form",
    ),
    "investment.transactions": (
        "orderId",
        "orderId",
        "orderId",
        "/queryIncrementOrderDetail.json",
        "POST",
        "form",
    ),
    "investment.compound_ledger": (
        "compoundOrderNo",
        "orderNo",
        "orderNo",
        "/compoundOrderDetail.json",
        "POST",
        "form",
    ),
    "rules.notification": (
        "id",
        "id",
        None,
        "/messageNoticeConfigDetail.json",
        "GET",
        "query",
    ),
    "rules.transfer": (
        "ruleId",
        "ruleId",
        "ruleId",
        "/queryTransferRuleDetail.json",
        "GET",
        "query",
    ),
    "risk.events": (
        "riskEventId",
        "id",
        "id",
        "/api/risk/event/detail.json",
        "POST",
        "form",
    ),
    "risk.anomalies": (
        "riskEventId",
        "id",
        "id",
        "/api/risk/event/detail.json",
        "POST",
        "form",
    ),
    "risk.sla": (
        "slaConfigId",
        "slaConfigId",
        "slaConfigId",
        "/api/risk/sla/slaConfigDetailQuery.json",
        "POST",
        "form",
    ),
}
BOUND = [leaf for leaf, case in CASES.items() if case[2] is not None]


@pytest.fixture(params=CASES)
def installed(request, run_cli, tmp_path, monkeypatch):
    leaf, kind = (
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
        package = ROOT / "leaf_packages/liquidity" / leaf
        if kind == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        archive.write(path, path.relative_to(package))
            package = archive_path
        cli("plugins", "install", str(package))
        yield leaf, cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def detail(leaf, identity="one"):
    result = {
        CASES[leaf][1]: identity,
        "amount": Decimal("0.12345678901234567890123456789"),
        "success": "native-value",
        "unknown": {"children": [None, False, 0, "", "1.0000", {"native": True}]},
        "tntInstId": "GUAPW3SG",
    }
    if leaf in ("risk.events", "risk.anomalies"):
        result["riskMode"] = "RISK_EVENT" if leaf == "risk.events" else "RISK_ALERT"
    if leaf == "risk.sla":
        result["version"] = "07"
    return result


def envelope(leaf, value):
    if leaf == "rules.notification":
        return {"resultFlag": True, "result": {"success": True, "data": value}}
    if leaf == "rules.transfer":
        return {"success": True, "result": {"success": True, "transferRuleVO": value}}
    return {"success": True, "data": value}


def reply(value, status=200):
    return {"status": status, "body": value}


def list_flags(leaf):
    if leaf == "investment.holdings":
        return ("--date", "2026-09-25")
    if leaf in ("risk.events", "risk.anomalies"):
        return ("--from-date", "20260925", "--to-date", "20260926")
    return ()


def rows(leaf):
    values = [
        {CASES[leaf][2]: identity, "listValue": identity, "tntInstId": "GUAPW3SG"}
        for identity in ("one", "two", "three")
    ]
    if leaf in ("risk.events", "risk.anomalies"):
        for value in values:
            value.update(
                riskMode="RISK_EVENT" if leaf == "risk.events" else "RISK_ALERT",
                gmtCreate="2026-09-25 12:00:00（GMT+08）",
            )
    return values


def list_envelope(leaf, records):
    if leaf == "rules.transfer":
        return {
            "resultFlag": True,
            "result": {
                "success": True,
                "transferRuleVOS": records,
                "ruleCount": len(records),
            },
        }
    return {"success": True, "data": {"data": records, "totalCount": len(records)}}


def expected_request(leaf, identity):
    result = {CASES[leaf][0]: identity}
    if leaf in ("cash.pools", "rules.notification", "rules.transfer"):
        result["tntInstId"] = "GUAPW3SG"
    if leaf == "cash.pools":
        result.update(inUse="Y", cashPoolCategory="BANK")
    return result


@pytest.mark.parametrize(
    "installed",
    [(leaf, kind) for leaf in CASES for kind in ("directory", "zip")],
    indirect=True,
)
def test_native_get_preserves_full_root_and_qualified_request(installed):
    leaf, cli, browser, config = installed
    get_help = cli("liquidity", "get", leaf, "--help")
    assert get_help["data"]["arguments"][0]["lookup_name"] == CASES[leaf][0]
    assert not browser.business_requests
    before = sorted(
        str(path.relative_to(config)) for path in config.rglob("*") if path.is_file()
    )
    native = detail(leaf)
    browser.business_script.append(reply(envelope(leaf, native)))
    result = cli("liquidity", "get", leaf, "one")
    assert result["data"] == native
    assert result["meta"]["query"] == {"identity": "one", "parameters": {}}
    assert result["meta"]["detail_scope"] == "native_root"
    assert not {"complete", "reported_total", "acquisition"} & result["meta"].keys()
    assert browser.business_requests == [expected_request(leaf, "one")]
    expression = next(
        expression
        for transport in browser.transports
        for expression in transport.expressions
        if "fetch(" in expression
    )
    assert CASES[leaf][3] in expression
    assert f'method: "{CASES[leaf][4]}"' in expression
    if CASES[leaf][5] == "form":
        assert "application/x-www-form-urlencoded" in expression
        assert "body: new URLSearchParams(payload).toString()" in expression
    elif CASES[leaf][5] == "json":
        assert "application/json" in expression
        assert "body: JSON.stringify(payload)" in expression
    else:
        assert "new URLSearchParams(payload)" in expression
        assert "body:" not in expression.split("const text", 1)[0]
    assert (
        sorted(
            str(path.relative_to(config))
            for path in config.rglob("*")
            if path.is_file()
        )
        == before
    )
    browser.business_script.append(reply(envelope(leaf, native)))
    assert cli("liquidity", "get", leaf, "one", "--fields", CASES[leaf][1])["data"] == {
        CASES[leaf][1]: "one"
    }


def test_native_get_rejects_bad_shape_identity_scope_and_business(installed):
    leaf, cli, browser, _ = installed
    key = CASES[leaf][1]
    for invalid in (
        None,
        [],
        {},
        {key: True},
        {key: 1},
        {key: "two"},
        {key: ""},
        {**detail(leaf), "tntInstId": "OTHER"},
    ):
        browser.business_script.append(reply(envelope(leaf, invalid)))
        result = cli("liquidity", "get", leaf, "one", code=1)
        assert result["error"]["code"] == "INVALID_RESPONSE"
    marker = "resultFlag" if leaf == "rules.notification" else "success"
    for flag, code in [
        (False, "BUSINESS_QUERY_FAILED"),
        ("true", "INVALID_RESPONSE"),
        (1, "INVALID_RESPONSE"),
    ]:
        body = envelope(leaf, detail(leaf))
        body[marker] = flag
        browser.business_script.append(reply(body))
        assert cli("liquidity", "get", leaf, "one", code=1)["error"]["code"] == code
    native = detail(leaf)
    native["success"] = False
    browser.business_script.append(reply(envelope(leaf, native)))
    assert cli("liquidity", "get", leaf, "one")["data"] == native
    if leaf in ("rules.transfer", "rules.notification"):
        body = envelope(leaf, detail(leaf))
        body["result"]["success"] = False
        browser.business_script.append(reply(body))
        assert (
            cli("liquidity", "get", leaf, "one", code=1)["error"]["code"]
            == "BUSINESS_QUERY_FAILED"
        )
    browser.business_script.append(reply({}, status=401))
    assert (
        cli("liquidity", "get", leaf, "one", code=1)["error"]["code"] == "AUTH_REQUIRED"
    )


@pytest.mark.parametrize(
    "installed", ["risk.events", "risk.anomalies", "risk.sla"], indirect=True
)
def test_risk_detail_checks_mode_and_native_version(installed):
    leaf, cli, browser, _ = installed
    native = detail(leaf)
    native["version" if leaf == "risk.sla" else "riskMode"] = (
        7 if leaf == "risk.sla" else "OTHER"
    )
    browser.business_script.append(reply(envelope(leaf, native)))
    assert (
        cli("liquidity", "get", leaf, "one", code=1)["error"]["code"]
        == "INVALID_RESPONSE"
    )


@pytest.mark.parametrize("installed", BOUND, indirect=True)
def test_bound_selected_window_uses_native_source_and_preserves_saved_list(installed):
    leaf, cli, browser, _ = installed
    records = rows(leaf)
    flags = list_flags(leaf)
    browser.business_script.append(reply(list_envelope(leaf, records)))
    cli("liquidity", "refresh", leaf, *flags, "--require-complete")
    before = cli("liquidity", "list", leaf, "--limit", "0")
    native = detail(leaf, "two")
    browser.business_script.extend(
        [reply(list_envelope(leaf, records)), reply(envelope(leaf, native))]
    )
    count = len(browser.business_requests)
    result = cli(
        "liquidity",
        "list",
        leaf,
        *flags,
        "--live",
        "--with-detail",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        "listValue",
        "--require-complete",
    )
    assert result["data"] == [{"record": {"listValue": "two"}, "detail": native}]
    assert browser.business_requests[count + 1 :] == [expected_request(leaf, "two")]
    assert result["meta"]["complete"] is True
    browser.business_script.append(reply(envelope(leaf, native)))
    assert cli("liquidity", "get", leaf, "two")["data"] == native
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert before["data"] == after["data"]
    assert before["meta"]["fetched_at"] == after["meta"]["fetched_at"]
    browser.business_script.append(reply(list_envelope(leaf, records)))
    count = len(browser.business_requests)
    assert (
        cli(
            "liquidity",
            "list",
            leaf,
            *flags,
            "--live",
            "--with-detail",
            "--offset",
            "3",
        )["data"]
        == []
    )
    assert len(browser.business_requests) == count + 1


@pytest.mark.parametrize("installed", BOUND, indirect=True)
def test_bound_detail_failure_is_atomic_and_does_not_change_cache(installed):
    leaf, cli, browser, _ = installed
    records = rows(leaf)
    flags = list_flags(leaf)
    browser.business_script.append(reply(list_envelope(leaf, records)))
    cli("liquidity", "refresh", leaf, *flags, "--require-complete")
    before = cli("liquidity", "list", leaf, "--limit", "0")
    bad = deepcopy(detail(leaf, "two"))
    bad[CASES[leaf][1]] = "wrong"
    browser.business_script.extend(
        [
            reply(list_envelope(leaf, records)),
            reply(envelope(leaf, detail(leaf))),
            reply(envelope(leaf, bad)),
        ]
    )
    result = cli(
        "liquidity",
        "list",
        leaf,
        *flags,
        "--live",
        "--with-detail",
        "--limit",
        "0",
        code=1,
    )
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result.get("data") is None
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert before["data"] == after["data"]
    assert before["meta"]["fetched_at"] == after["meta"]["fetched_at"]


@pytest.mark.parametrize("installed", ["rules.notification"], indirect=True)
def test_get_only_does_not_restore_list_or_create_storage(installed):
    leaf, cli, browser, config = installed
    assert cli("liquidity", "list", leaf, code=2)["error"]
    assert not browser.business_requests
    assert not (config / "leaf-cache.sqlite3").exists()
    assert not (config / "duckdog.duckdb").exists()


@pytest.mark.parametrize("lookup", ["", " \t "])
def test_blank_get_lookup_is_usage_error_before_business_request(installed, lookup):
    leaf, cli, browser, _ = installed
    result = cli("liquidity", "get", leaf, lookup, code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


@pytest.mark.parametrize("installed", ["risk.sla"], indirect=True)
@pytest.mark.parametrize("version", ["missing", "null"])
def test_sla_detail_preserves_optional_missing_or_null_version(installed, version):
    leaf, cli, browser, _ = installed
    native = detail(leaf)
    if version == "missing":
        native.pop("version")
    else:
        native["version"] = None
    browser.business_script.append(reply(envelope(leaf, native)))
    result = cli("liquidity", "get", leaf, "one")
    assert result["data"] == native
    assert browser.business_requests == [expected_request(leaf, "one")]
