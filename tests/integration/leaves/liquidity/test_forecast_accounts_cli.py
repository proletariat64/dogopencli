"""Installed account forecasts and leaf-owned ordered ownership resolution."""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.result_policy import AcquisitionEvidence

ROOT = Path(__file__).resolve().parents[4]
NAMES = (
    "forecast.account_demands",
    "forecast.account_cashflows",
    "forecast.account_demands_intraday",
)
FLAGS = ("--alias", "ACCOUNT", "--from-date", "20261019", "--to-date", "20261019")
EXPLICIT = (*FLAGS, "--entity", "ENTITY", "--bank", "BANK")


def adapter(name):
    path = ROOT / "leaf_packages/liquidity" / name / "adapter.py"
    module = ModuleType("account_leaf")
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module


def row(name, identity="1", **extra):
    if name.endswith("intraday"):
        return {
            "statisticalDate": "00:00",
            "inflowAmount": "1.0000000000000001",
            "outflowAmount": None,
            **extra,
        }
    common = {
        "entity": "ENTITY",
        "expectValueDate": "20261019",
        "currency": "USD",
        "unknown": {"values": [None, "", False, Decimal("0.0000000000000001")]},
    }
    if name.endswith("cashflows"):
        return {
            **common,
            "bankAccountAliasName": "ACCOUNT",
            "bankId": "BANK",
            "bankAccountFlowDateSourceTypeStr": "SOURCE",
            "originalBizNo": identity,
            "expectValueTime": "00:00:00",
            **extra,
        }
    return {**common, "id": identity, "aliasName": "ACCOUNT", "bankID": "BANK", **extra}


def rows(name):
    if name.endswith("intraday"):
        return [
            row(name, statisticalDate=f"{h:02}:{m:02}")
            for h in range(24)
            for m in (0, 15, 30, 45)
        ]
    return [row(name)]


def response(name, records, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": records
            if name.endswith("intraday")
            else {
                "data": records,
                "totalCount": len(records) if total is None else total,
            },
        },
    }


@pytest.fixture(params=NAMES)
def installed(request, run_cli, tmp_path, monkeypatch):
    name = request.param[0] if isinstance(request.param, tuple) else request.param
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
    if isinstance(request.param, tuple):
        duckdb = pytest.importorskip("duckdb")
        database = config / "accounts.duckdb"
        with duckdb.connect(str(database)) as connection:
            connection.execute(
                "CREATE TABLE accounts "
                "(aliasName VARCHAR, instId VARCHAR, bankId VARCHAR)"
            )
            connection.execute(
                "INSERT INTO accounts VALUES ('ACCOUNT', 'ENTITY', 'BANK')"
            )
        with (config / "config.toml").open("a") as stream:
            stream.write(
                f'\n[duckdog]\npath = "{database}"\n[duckdog.selectors]\n'
                '"liquidity/cash/accounts" = "accounts"\n'
            )
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        status, output, error = run_cli(["liquidity", action, name, *args])
        assert status == code, output + error
        return parse(output)

    status, output, error = run_cli(
        ["plugins", "install", str(ROOT / "leaf_packages/liquidity" / name)]
    )
    assert status == 0, output + error
    try:
        yield name, cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def context(result):
    return next(
        item
        for item in result["meta"]["acquisition"]["attempts"]
        if item.get("kind") == "account_context"
    )


def test_explicit_context_preserves_native_values_and_refresh_offline(installed):
    name, cli, browser, _ = installed
    cli("list", "-h")
    assert not browser.transports
    native = rows(name)
    browser.business_script.append(response(name, native))
    live = cli("list", *EXPLICIT, "--live", "--require-complete", "--limit", "0")
    assert live["data"] == native
    assert context(live)["source"] == "explicit"
    body = browser.business_requests[0]
    assert {
        key: body[key]
        for key in ("aliasName", "entity", "bankId", "startDate", "endDate")
    } == {
        "aliasName": "ACCOUNT",
        "entity": "ENTITY",
        "bankId": "BANK",
        "startDate": "20261019",
        "endDate": "20261019",
    }
    assert ("rowStart" not in body) == name.endswith("intraday")
    browser.business_script.append(response(name, native))
    saved = cli("refresh", *EXPLICIT, "--require-complete", "--limit", "0")
    count = len(browser.business_requests)
    offline = cli("list", "--require-complete", "--limit", "0")
    assert offline["data"] == native and context(offline) == context(saved)
    assert len(browser.business_requests) == count


def test_live_directory_fallback_precedes_record_inquiry(installed):
    name, cli, browser, _ = installed
    native = rows(name)
    directory = [
        {
            "aliasName": "ACCOUNT",
            "currency": "USD",
            "instId": "ENTITY",
            "bankId": "BANK",
        }
    ]

    def handler(body, _):
        if "bankAccountQueryVO" in body:
            vo = json.loads(body["bankAccountQueryVO"])
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": 99999,
                    "result": {
                        "success": True,
                        "bankAccountPropertyVOList": directory
                        if vo["rowStart"] == 0
                        else [],
                    },
                },
            }
        if "bankAccountBaseLineQuery" in body:
            vo = json.loads(body["bankAccountBaseLineQuery"])
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": len(directory),
                    "result": {
                        "success": True,
                        "data": directory if vo["rowStart"] == 0 else [],
                    },
                },
            }
        return response(name, native)

    browser.business_handler = handler
    got = cli("list", *FLAGS, "--live", "--require-complete", "--limit", "0")
    assert got["data"] == native
    info = context(got)
    assert [note["source"] for note in info["sources"]] == ["duckdog", "cache", "live"]
    assert (
        info["source"] == "live"
        and "historical ownership is not established" in info["ownership_reference"]
    )
    assert browser.business_requests[-1]["entity"] == "ENTITY"


@pytest.mark.parametrize(
    "change", ["any", "blank", "many", "bad_day", "reversed", "missing"]
)
def test_scope_rejected_before_browser(installed, change):
    _, cli, browser, _ = installed
    flags = list(EXPLICIT)
    if change == "any":
        flags[1] = "any"
    elif change == "blank":
        flags[1] = " "
    elif change == "many":
        flags[1] = "A,B"
    elif change == "bad_day":
        flags[3] = "20260230"
    elif change == "reversed":
        flags[3] = "20261020"
    else:
        flags = []
    assert cli("list", *flags, "--live", code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize(
    "failure", ["business", "auth", "malformed", "scope", "incomplete"]
)
def test_failed_acquisition_preserves_published_capture(installed, failure):
    name, cli, browser, _ = installed
    native = rows(name)
    browser.business_script.append(response(name, native))
    saved = cli("refresh", *EXPLICIT, "--require-complete", "--limit", "0")
    changed = deepcopy(native)
    reply = response(name, changed)
    expected = "INVALID_RESPONSE"
    if failure == "business":
        reply["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "auth":
        reply = {"status": 403, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "malformed":
        reply["body"]["data"] = None
    elif failure == "scope":
        if name.endswith("intraday"):
            changed[0]["statisticalDate"] = "00:01"
        else:
            changed[0]["entity"] = "OTHER"
    else:
        if name.endswith("intraday"):
            reply = response(name, changed[:-1])
        else:
            reply = response(name, changed, total=2)
        expected = "INCOMPLETE_RESULT"
    browser.business_script.append(reply)
    assert (
        cli("refresh", *EXPLICIT, "--require-complete", code=1)["error"]["code"]
        == expected
    )
    offline = cli("list", "--limit", "0")
    assert (
        offline["data"] == native
        and offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    )


@pytest.mark.parametrize("name", NAMES)
def test_resolver_order_constraints_multiple_match_and_explicit_shortcut(name):
    module = adapter(name)
    native = module.values(
        {
            "alias": "ACCOUNT",
            "entity": "ENTITY",
            "from_date": "20261019",
            "to_date": "20261019",
        }
    )
    called = []

    class Tools:
        def account_directory(self, source):
            called.append(source)
            if source == "duckdog":
                return {
                    "records": [
                        {"aliasName": "ACCOUNT", "instId": "OTHER", "bankId": "WRONG"}
                    ],
                    "quality": {},
                }
            return {
                "records": [
                    {"aliasName": "ACCOUNT", "instId": "ENTITY", "bankId": "BANK"},
                    {"aliasName": "ACCOUNT", "instId": "ENTITY", "bankId": "SECOND"},
                ],
                "quality": {"warnings": [{"code": "SOURCE_NOTICE"}]},
            }

        def collect(self, *_):
            pytest.fail("matched cache must avoid live directory")

    resolved, info = module.resolve(native, Tools())
    assert called == ["duckdog", "cache"]
    assert resolved["entity"] == "ENTITY" and resolved["bankId"] == "BANK"
    assert info["source"] == "cache"
    assert [warning["code"] for warning in info["warnings"]] == [
        "SOURCE_NOTICE",
        "ACCOUNT_CONTEXT_MULTIPLE_MATCHES",
    ]
    called.clear()
    assert module.resolve(resolved, Tools())[1]["source"] == "explicit"
    assert not called


@pytest.mark.parametrize("name", NAMES)
def test_missing_directory_ownership_and_corrupt_source_are_not_swallowed(name):
    module = adapter(name)
    native = module.values(
        {"alias": "ACCOUNT", "from_date": "20261019", "to_date": "20261019"}
    )

    class Missing:
        def account_directory(self, source):
            return None

        def collect(self, *_):
            return SimpleNamespace(
                records=[],
                evidence=AcquisitionEvidence.for_collection(
                    complete=True, reported_total=None, collected_total=0, arrivals=0
                ),
            )

    with pytest.raises(CliError) as failure:
        module.resolve(native, Missing())
    assert failure.value.code == "SOURCE_DATA_MISSING"

    class Broken(Missing):
        def account_directory(self, source):
            raise CliError("CONFIG_ERROR", "broken configured source")

    with pytest.raises(CliError) as failure:
        module.resolve(native, Broken())
    assert failure.value.code == "CONFIG_ERROR"


def seed_accounts(config, records, *, complete=True, simulated=False):
    from dogopencli.cache import Cache, SnapshotMeta
    from dogopencli.jsonutil import canonical

    evidence = AcquisitionEvidence.for_collection(
        complete=complete,
        reported_total=len(records) if complete else len(records) + 1,
        collected_total=len(records),
        arrivals=len(records),
    )
    Cache(config / "leaf-cache.sqlite3").publish(
        SnapshotMeta(
            namespace="leaf:liquidity.cash.accounts",
            capability="liquidity.cash.accounts",
            scope="",
            source_kind="live",
            snapshot_id="synthetic-accounts",
            dataset_id=None,
            simulated=simulated,
            backend_complete=complete,
            dataset_complete=complete,
            fetched_at="2026-10-19T00:00:00+00:00",
            loaded_at="2026-10-19T00:00:00+00:00",
            source_observed_from=None,
            source_observed_to=None,
            row_count=len(records),
            acquisition=evidence.record(),
        ),
        ((i, canonical(record)) for i, record in enumerate(records)),
    )


def test_real_saved_account_directory_is_read_without_live_directory(installed):
    name, cli, browser, config = installed
    seed_accounts(
        config,
        [
            {
                "aliasName": "ACCOUNT",
                "instId": "ENTITY",
                "bankId": "BANK",
                "currency": "USD",
                "source_metadata": {"raw": {}},
            }
        ],
    )
    native = rows(name)
    browser.business_script.append(response(name, native))
    got = cli("list", *FLAGS, "--live", "--require-complete", "--limit", "0")
    assert got["data"] == native
    assert context(got)["source"] == "cache"
    assert (
        context(got)["directory_quality"]["fetched_at"] == "2026-10-19T00:00:00+00:00"
    )
    assert len(browser.business_requests) == 1
    assert "bankAccountQueryVO" not in browser.business_requests[0]


def test_incomplete_saved_directory_quality_is_not_upgraded(installed):
    name, cli, browser, config = installed
    seed_accounts(
        config,
        [
            {
                "aliasName": "ACCOUNT",
                "instId": "ENTITY",
                "bankId": "BANK",
                "currency": "USD",
            }
        ],
        complete=False,
    )
    browser.business_script.append(response(name, rows(name)))
    got = cli("list", *FLAGS, "--live", "--limit", "0")
    assert got["meta"]["complete"] is False
    assert "ACCOUNT_DIRECTORY_INCOMPLETE" in got["meta"]["acquisition"]["reasons"]
    assert context(got)["directory_quality"]["dataset_complete"] is False


def test_broken_configured_account_cache_is_fatal_before_live_directory(installed):
    _, cli, browser, config = installed
    seed_accounts(config, ["malformed native object"])
    got = cli("list", *FLAGS, "--live", code=1)
    assert got["error"]["code"] == "INVALID_RESPONSE"
    assert not browser.business_requests


@pytest.mark.parametrize(
    "installed", [(name, "duckdog") for name in NAMES], indirect=True
)
def test_real_duckdog_directory_wins_over_cache(installed):
    name, cli, browser, config = installed
    seed_accounts(
        config,
        [
            {
                "aliasName": "ACCOUNT",
                "instId": "CACHE-ENTITY",
                "bankId": "CACHE-BANK",
                "currency": "USD",
            }
        ],
    )
    browser.business_script.append(response(name, rows(name)))
    got = cli("list", *FLAGS, "--live", "--require-complete", "--limit", "0")
    assert context(got)["source"] == "duckdog"
    assert [note["source"] for note in context(got)["sources"]] == ["duckdog"]
    assert browser.business_requests[0]["entity"] == "ENTITY"
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("change", ["endpoint", "method", "extra", "width"])
def test_account_records_default_deny_requests(name, change):
    from dataclasses import replace

    from dogopencli.transport import QueryRequest, validate_request

    module = adapter(name)
    capability = module.RecordsInquiry()
    scope = module.canonical(
        {
            "aliasName": "ACCOUNT",
            "entity": "ENTITY",
            "bankId": "BANK",
            "startDate": "20261019",
            "endDate": "20261019",
        }
    )
    body = capability.page_body(scope, 0, 0 if name.endswith("intraday") else 5000)
    contract = capability.contract
    request = QueryRequest(
        capability.name, contract.method, contract.host, contract.path, body
    )
    validate_request(request, contract)
    if change == "endpoint":
        request = replace(request, path="/mutation.json")
    elif change == "method":
        request = replace(request, method="GET")
    elif change == "extra":
        body["action"] = "save"
    else:
        body["pageSize"] = 10
    with pytest.raises(CliError) as failure:
        validate_request(request, contract)
    assert failure.value.code == "REQUEST_NOT_ALLOWED"


@pytest.mark.parametrize(
    "installed", ["forecast.account_demands_intraday"], indirect=True
)
def test_intraday_two_dates_are_refused_without_browser(installed):
    name, cli, browser, _ = installed
    flags = list(EXPLICIT)
    flags[5] = "20261020"
    assert cli("list", *flags, "--live", code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


def test_simulated_saved_ownership_is_rejected_without_production_publication(
    installed,
):
    name, cli, browser, config = installed
    native = rows(name)
    browser.business_script.append(response(name, native))
    saved = cli("refresh", *EXPLICIT, "--require-complete", "--limit", "0")
    seed_accounts(
        config,
        [
            {
                "aliasName": "ACCOUNT",
                "instId": "ENTITY",
                "bankId": "BANK",
                "currency": "USD",
            }
        ],
        simulated=True,
    )
    before = len(browser.business_requests)
    for action, flags in (("list", ("--live",)), ("refresh", ())):
        rejected = cli(action, *FLAGS, *flags, code=1)
        assert rejected["error"]["code"] == "INVALID_RESPONSE"
        assert "simulated account directory" in rejected["error"]["message"]
        info = rejected["meta"]["account_context"]
        assert info["source"] == "cache"
        assert info["directory_quality"]["simulated"] is True
        assert info["sources"][-1]["status"] == "simulated_source_rejected"
        assert not any(note["source"] == "live" for note in info["sources"])
        if action == "refresh":
            assert rejected["meta"]["published"] is False
    assert len(browser.business_requests) == before
    offline = cli("list", "--limit", "0")
    assert offline["data"] == native
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def live_catalogs(browser, name, cash, baseline, *, detail=None, baseline_total=None):
    def handler(body, _):
        if "bankAccountQueryVO" in body:
            vo = json.loads(body["bankAccountQueryVO"])
            data = cash[vo["rowStart"] : vo["rowStart"] + vo["pageSize"]]
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "result": {"success": True, "bankAccountPropertyVOList": data},
                },
            }
        if "bankAccountBaseLineQuery" in body:
            vo = json.loads(body["bankAccountBaseLineQuery"])
            data = baseline[vo["rowStart"] : vo["rowStart"] + vo["pageSize"]]
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": len(baseline)
                    if baseline_total is None
                    else baseline_total,
                    "result": {"success": True, "data": data},
                },
            }
        if set(body) == {"tntInstId", "aliasName"}:
            assert detail is not None, "unnecessary ownership detail query"
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "result": {"success": True, "data": detail},
                },
            }
        return response(name, rows(name))

    browser.business_handler = handler


def test_live_baseline_only_alias_resolves_with_independent_catalog_coverage(installed):
    name, cli, browser, _ = installed
    browser.business_script.append(response(name, rows(name)))
    saved = cli("refresh", *EXPLICIT, "--require-complete")
    cash = [
        {
            "aliasName": "UNRELATED",
            "currency": "USD",
            "instId": "OTHER",
            "bankId": "OTHER",
        }
    ]
    baseline = [
        {
            "aliasName": "ACCOUNT",
            "currency": "USD",
            "instId": "ENTITY",
            "bankId": "BANK",
        }
    ]
    live_catalogs(browser, name, cash, baseline)
    got = cli("list", *FLAGS, "--live", "--limit", "0")
    assert got["data"] == rows(name)
    quality = context(got)["directory_quality"]
    assert set(quality["sources"]) == {"cash", "baseline"}
    assert quality["sources"]["baseline"]["reported_total"] == 1
    assert quality["sources"]["cash"]["reported_total"] is None
    assert quality["ownership_detail_coverage"] == {
        "required": 0,
        "attempted": 0,
        "succeeded": 0,
    }
    assert not any(
        set(body) == {"tntInstId", "aliasName"} for body in browser.business_requests
    )

    assert got["meta"]["complete"] is False
    assert "ACCOUNT_SOURCE_MISMATCH" in got["meta"]["acquisition"]["reasons"]
    assert quality["list_coverage"] == {
        "complete": False,
        "matched": 0,
        "cash_only": 1,
        "baseline_only": 1,
    }
    assert (
        cli("list", *FLAGS, "--live", "--require-complete", code=1)["error"]["code"]
        == "INCOMPLETE_RESULT"
    )
    rejected = cli("refresh", *FLAGS, code=1)
    assert rejected["error"]["code"] == "INCOMPLETE_RESULT"
    assert rejected["meta"]["published"] is False
    offline = cli("list", "--limit", "0")
    assert offline["data"] == rows(name)
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "change", ["entity_conflict", "bank_conflict", "present_null", "present_empty"]
)
def test_live_catalog_context_conflicts_and_present_null_authority(installed, change):
    name, cli, browser, _ = installed
    cash = [
        {
            "aliasName": "ACCOUNT",
            "currency": "USD",
            "instId": "ENTITY",
            "bankId": "BANK",
        }
    ]
    baseline = deepcopy(cash)
    expected = "INVALID_RESPONSE"
    if change == "entity_conflict":
        baseline[0]["instId"] = "OTHER"
    elif change == "bank_conflict":
        baseline[0]["bankId"] = "OTHER"
    else:
        baseline[0]["instId"] = None if change == "present_null" else ""
        expected = "SOURCE_DATA_MISSING"
    live_catalogs(browser, name, cash, baseline)
    got = cli("list", *FLAGS, "--live", code=1)
    assert got["error"]["code"] == expected
    assert not any("startDate" in body for body in browser.business_requests)
    assert not any(
        set(body) == {"tntInstId", "aliasName"} for body in browser.business_requests
    )


def test_selected_detail_only_fills_absent_required_ownership(installed):
    name, cli, browser, _ = installed
    baseline = [
        {"aliasName": "ACCOUNT", "currency": "USD", "bankId": "BANK"},
        {"aliasName": "UNRELATED", "currency": "EUR"},
    ]
    detail = {
        "aliasName": "ACCOUNT",
        "currency": "USD",
        "instId": "ENTITY",
        "bankId": "BANK",
    }
    live_catalogs(browser, name, deepcopy(baseline), baseline, detail=detail)
    got = cli("list", *FLAGS, "--live", "--require-complete", "--limit", "0")
    assert got["data"] == rows(name)
    assert context(got)["directory_quality"]["ownership_detail_coverage"] == {
        "required": 1,
        "attempted": 1,
        "succeeded": 1,
    }
    details = [
        body
        for body in browser.business_requests
        if set(body) == {"tntInstId", "aliasName"}
    ]
    assert details == [{"tntInstId": "GUAPW3SG", "aliasName": "ACCOUNT"}]


def test_missing_baseline_key_falls_back_to_cash_before_detail(installed):
    name, cli, browser, _ = installed
    cash = [
        {
            "aliasName": "ACCOUNT",
            "currency": "USD",
            "instId": "ENTITY",
            "bankId": "BANK",
        }
    ]
    baseline = [{"aliasName": "ACCOUNT", "currency": "USD"}]
    live_catalogs(browser, name, cash, baseline)
    got = cli("list", *FLAGS, "--live", "--require-complete", "--limit", "0")
    assert got["data"] == rows(name)
    assert (
        context(got)["directory_quality"]["ownership_detail_coverage"]["attempted"] == 0
    )


def test_incomplete_baseline_catalog_does_not_become_complete_resolved_query(installed):
    name, cli, browser, _ = installed
    baseline = [
        {
            "aliasName": "ACCOUNT",
            "currency": "USD",
            "instId": "ENTITY",
            "bankId": "BANK",
        }
    ]
    live_catalogs(browser, name, [], baseline, baseline_total=2)
    got = cli("list", *FLAGS, "--live", "--limit", "0")
    assert got["data"] == rows(name)
    assert got["meta"]["complete"] is False
    assert (
        context(got)["directory_quality"]["sources"]["baseline"]["scope_complete"]
        is False
    )
    assert "ACCOUNT_DIRECTORY_INCOMPLETE" in got["meta"]["acquisition"]["reasons"]


def test_conflicting_identity_inside_one_catalog_is_hard_failure(installed):
    name, cli, browser, _ = installed
    baseline = [
        {
            "aliasName": "ACCOUNT",
            "currency": "USD",
            "instId": "ENTITY",
            "bankId": "BANK",
        },
        {
            "aliasName": "ACCOUNT",
            "currency": "USD",
            "instId": "ENTITY",
            "bankId": "CONFLICT",
        },
    ]
    live_catalogs(browser, name, [], baseline)
    got = cli("list", *FLAGS, "--live", code=1)
    assert got["error"]["code"] == "INVALID_RESPONSE"
    assert "conflicting native identity" in got["error"]["message"]
    assert not any("startDate" in body for body in browser.business_requests)
