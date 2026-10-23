"""Installed request-bound accuracy preserves native scope and atomicity."""

import json
import shutil
import sqlite3
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "leaf_packages/liquidity/forecast.accuracy"
FLAGS = ["--account-alias", "ACCOUNT", "--record-date", "2026-03-08"]
BASE_VO = "bankCashForecastRecordQueryVo"
METRIC_VO = "bankAccountDetailCashFlowQueryVO"


def row(index=0, **overrides):
    return {
        "id": str(index),
        "bankAccountAliasName": "ACCOUNT",
        "currency": "USD",
        "valueDate": "20260309",
        "baseValueDate": "20260308",
        "recordCreateTime": "123456",
        "forecastBalance": "0.00",
        "cashFlowTransIn": Decimal("0.123456789012345678901"),
        "cashFlowTransOut": "",
        "forecastTaskId": "TASK",
        "forecastBatchNo": 1,
        "forecastRuleId": None,
        "accountNo": "NUMBER",
        "instId": "ENTITY",
        "bankId": "BANK",
        "tntInstId": "GUAPW3SG",
        "gmtCreate": 1772971200000,
        "unknown": {"nested": True},
        **overrides,
    }


def base(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "dataValue": rows,
                "count": len(rows) if total is None else total,
            },
        },
    }


def metric(**values):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "bankAccountDetailDayVO": {
                    "cashFlowAccuracy": "1",
                    "realizedBalance": "0.00",
                    "flowAccuracy": "",
                    "unknown": "excluded legacy field",
                    **values,
                },
            },
        },
    }


def details(rows, count=0):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"success": True, "dataValue": rows, "count": count},
        },
    }


def test_occurrences_keep_duplicates_money_and_unknown_coverage(installed):
    cli, browser, config = installed
    occurrence = {
        "cashFlowAmount": {
            "amount": Decimal("1.234567890123456789"),
            "cent": 123,
            "currency": "USD",
            "unknown": {"precision": None},
        },
        "detailAmount": "1,234.567890123456789",
        "match": False,
        "pageNo": 0,
        "pageSize": 0,
        "rowStart": 0,
        "startindex": 0,
        "totalSize": 0,
        "detailMemo": "",
        "unknown": [None, 0, ""],
    }
    browser.business_script.extend(
        [base([row()]), metric(), details([occurrence] * 101)]
    )
    result = cli("list", "--live", *FLAGS, "--limit", "0")
    assert result["data"][0]["cashflow_details"] == [occurrence] * 101
    assert result["meta"]["dataset_complete"] is False
    assert result["meta"]["warnings"][0]["code"] == "INCOMPLETE_RESULT"
    assert not (config / "leaf-cache.sqlite3").exists()
    detail_context = parse(browser.business_requests[-1][METRIC_VO])
    assert detail_context == {
        "tntInstId": "GUAPW3SG",
        "forecastRecordId": "0",
        "aliasName": "ACCOUNT",
        "accountNo": "NUMBER",
        "instId": "ENTITY",
        "bankId": "BANK",
        "currency": "USD",
        "valueDate": "20260309",
        "gmtCreate": 1772971200000,
    }
    evidence = result["meta"]["acquisition"]["attempts"][0]
    assert evidence["occurrence_arrivals"] == 101
    assert evidence["occurrence_reported_total"] is None
    assert evidence["occurrence_responses"][0]["native_count"] == 0


@pytest.fixture
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
        href="https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        result, output, error = run_cli(
            ["liquidity", action, "forecast.accuracy", *args]
        )
        assert result == code, output + error
        return parse(output)

    try:
        source = tmp_path / "source"
        shutil.copytree(SOURCE, source)
        if getattr(request, "param", "directory") == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(source))
            source = archive_path
        result, output, error = run_cli(["plugins", "install", str(source)])
        assert result == 0, output + error
        if getattr(request, "param", "directory") == "directory":
            shutil.rmtree(source)
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def test_bound_native_projection_and_composed_scope(installed):
    cli, browser, config = installed
    cli("list", "--help")
    cli("describe")
    assert not browser.transports
    native = [row(9), row(2, forecastBalance="1.234567890123456789")]
    browser.business_script.extend(
        [base(native), metric(), details([]), metric(realizedBalance=None), details([])]
    )
    live = cli("list", "--live", *FLAGS, "--limit", "0")
    rows = live["data"]
    assert [item["id"] for item in rows] == ["9", "2"]
    assert rows[0]["forecastBalance"] == "0.00"
    assert rows[0]["cashFlowTransIn"] == native[0]["cashFlowTransIn"]
    assert len(rows[0]["accuracy"]) == 11
    assert set(rows[0]) == {
        "id",
        "bankAccountAliasName",
        "currency",
        "valueDate",
        "baseValueDate",
        "recordCreateTime",
        "forecastBalance",
        "cashFlowTransIn",
        "cashFlowTransOut",
        "forecastTaskId",
        "forecastBatchNo",
        "forecastRuleId",
        "accuracy",
        "cashflow_details",
    }
    assert rows[0]["accuracy"]["flowAccuracy"] == ""
    assert rows[1]["accuracy"]["realizedBalance"] is None
    assert "unknown" not in rows[0]["accuracy"]
    assert parse(browser.business_requests[0][BASE_VO]) == {
        "tntInstId": "GUAPW3SG",
        "recordStartTime": "000000",
        "recordEndTime": "235959",
        "rowStart": 0,
        "pageSize": 5000,
        "aliasName": ["ACCOUNT"],
        "valueStartDay": "20260308",
        "valueEndDay": "20260308",
    }
    for request, original in zip(browser.business_requests[1::2], native, strict=True):
        assert parse(request[METRIC_VO]) == {
            "forecastRecordId": original["id"],
            "aliasName": "ACCOUNT",
            "accountNo": "NUMBER",
            "instId": "ENTITY",
            "bankId": "BANK",
            "currency": "USD",
            "valueDate": "20260309",
            "forecastBalance": "0"
            if original["id"] == "9"
            else original["forecastBalance"],
        }
    assert all(record["cashflow_details"] == [] for record in rows)
    assert live["meta"]["complete"] is False
    assert live["meta"]["acquisition"]["attempts"][0]["occurrence_succeeded"] == 2
    browser.business_script.extend(
        [base(native), metric(), details([]), metric(realizedBalance=None), details([])]
    )
    incomplete = cli("refresh", *FLAGS, code=1)
    assert incomplete["error"]["code"] == "INCOMPLETE_RESULT"
    assert incomplete["meta"]["published"] is False
    assert not (config / "leaf-cache.sqlite3").exists()


@pytest.mark.parametrize(
    "flags",
    [
        [],
        FLAGS[:2],
        [*FLAGS[:2], "--record-date", "2026-02-30"],
        ["--account-alias", " ", *FLAGS[2:]],
    ],
)
def test_invalid_scope_before_browser(installed, flags):
    cli, browser, _ = installed
    assert cli("list", "--live", *flags, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate",
        "count",
        "limit",
        "identity",
        "binding",
        "alias",
        "tenant",
        "balance",
        "total_type",
        "base_business",
        "metric_business",
        "metric_shape",
        "auth",
    ],
)
def test_atomic_failure_never_exposes_successful_prefix(installed, failure):
    cli, browser, _ = installed
    candidate = base([row(1), row(2)])
    data = candidate["body"]["result"]
    expected = "INVALID_RESPONSE"
    if failure == "duplicate":
        data["dataValue"] = [row(1), row(1)]
        expected = "INCOMPLETE_RESULT"
    elif failure == "count":
        data["count"] = 3
        expected = "INCOMPLETE_RESULT"
    elif failure == "limit":
        candidate = base([row(i) for i in range(101)])
        expected = "INCOMPLETE_RESULT"
    elif failure == "identity":
        data["dataValue"][1]["id"] = 2
    elif failure == "binding":
        data["dataValue"][1]["bankId"] = ""
    elif failure == "alias":
        data["dataValue"][1]["bankAccountAliasName"] = "OTHER"
    elif failure == "tenant":
        data["dataValue"][1]["tntInstId"] = "OTHER"
    elif failure == "balance":
        data["dataValue"][1]["forecastBalance"] = None
    elif failure == "total_type":
        data["count"] = True
    elif failure == "base_business":
        data["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    metric_fail = metric()
    if failure == "metric_business":
        metric_fail["body"]["result"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "metric_shape":
        metric_fail["body"]["result"]["bankAccountDetailDayVO"] = []
    elif failure == "auth":
        metric_fail = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    browser.business_script.extend([candidate, metric(), details([]), metric_fail])
    before = len(browser.business_requests)
    result = cli("refresh", *FLAGS, "--require-complete", code=1)
    assert result["error"]["code"] == expected
    assert result["meta"]["published"] is False
    assert len(browser.business_requests) - before == (
        4 if failure in {"metric_business", "metric_shape", "auth"} else 1
    )
    assert not result.get("data")


def test_empty_metric_is_preserved_as_unknown_projected_values(installed):
    cli, browser, _ = installed
    response = metric()
    response["body"]["result"]["bankAccountDetailDayVO"] = {}
    browser.business_script.extend([base([row()]), response, details([])])
    result = cli("list", "--live", *FLAGS)
    assert all(v is None for v in result["data"][0]["accuracy"].values())


def test_empty_refresh_does_not_publish(installed):
    cli, browser, _ = installed
    browser.business_script.append(base([]))
    assert cli("refresh", *FLAGS, "--require-complete")["meta"]["published"] is False


def test_undeclared_metric_payload_rejected_before_fetch(installed, run_cli, tmp_path):
    cli, browser, _ = installed
    code, output, error = run_cli(
        ["plugins", "uninstall", "liquidity.forecast.accuracy"]
    )
    assert code == 0, output + error
    source = tmp_path / "badrequest"
    shutil.copytree(SOURCE, source)
    path = source / "adapter.py"
    text = path.read_text()
    assert "inner = dict(parameters)" in text
    path.write_text(
        text.replace(
            "inner = dict(parameters)", 'inner = {**parameters, "mutation": "Y"}'
        )
    )
    code, output, error = run_cli(["plugins", "install", str(source)])
    assert code == 0, output + error
    browser.business_script.append(base([row()]))
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize("field", ["accuracy", "cashflow_details"])
def test_reserved_namespace_collision_fails_before_children(installed, field):
    cli, browser, _ = installed
    browser.business_script.append(base([row(**{field: None})]))
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize("source", ["metric", "occurrence_root", "occurrence_row"])
def test_contradictory_native_child_context_is_failure(installed, source):
    cli, browser, _ = installed
    metric_response = metric()
    occurrence_response = details([])
    if source == "metric":
        metric_response["body"]["result"]["bankAccountDetailDayVO"][
            "forecastRecordId"
        ] = "OTHER"
    elif source == "occurrence_root":
        occurrence_response["body"]["result"]["accountNo"] = "OTHER"
    else:
        occurrence_response["body"]["result"]["dataValue"] = [
            {"forecastRecordId": "OTHER"}
        ]
    browser.business_script.extend(
        [base([row()]), metric_response, occurrence_response]
    )
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert not result.get("data")


@pytest.mark.parametrize(
    "bad", [{"match": "false"}, {"cashFlowAmount": "1"}, {"detailAmount": 1}]
)
def test_malformed_known_occurrence_fields_fail(installed, bad):
    cli, browser, _ = installed
    browser.business_script.extend([base([row()]), metric(), details([bad])])
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("creation", [None, "absent"])
def test_detail_creation_context_preserves_null_and_omission(installed, creation):
    cli, browser, _ = installed
    original = row(gmtCreate=creation)
    if creation == "absent":
        del original["gmtCreate"]
    browser.business_script.extend([base([original]), metric(), details([])])
    result = cli("list", "--live", *FLAGS)
    assert result["data"][0]["cashflow_details"] == []
    context = parse(browser.business_requests[2][METRIC_VO])
    assert ("gmtCreate" in context) is (creation is None)
    if creation is None:
        assert context["gmtCreate"] is None


def test_display_limit_never_truncates_acquisition_or_occurrences(installed):
    cli, browser, _ = installed
    occurrences = [{"match": True, "detailAmount": "", "cashFlowAmount": None}] * 5001
    browser.business_script.extend(
        [base([row(1), row(2)]), metric(), details(occurrences), metric(), details([])]
    )
    result = cli("list", "--live", *FLAGS, "--limit", "1")
    assert len(result["data"]) == 1
    assert result["data"][0]["cashflow_details"] == occurrences
    assert len(browser.business_requests) == 5
    evidence = result["meta"]["acquisition"]["attempts"][0]
    assert evidence["occurrence_succeeded"] == 2
    assert evidence["occurrence_arrivals"] == 5001


@pytest.mark.parametrize("mode", ["strict", "refresh"])
def test_unknown_occurrence_boundary_rejects_strict_and_refresh(installed, mode):
    cli, browser, config = installed
    browser.business_script.extend([base([row()]), metric(), details([])])
    args = ["--live", "--require-complete"] if mode == "strict" else []
    result = cli("list" if mode == "strict" else "refresh", *args, *FLAGS, code=1)
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert not result.get("data")
    assert not (config / "leaf-cache.sqlite3").exists()


@pytest.mark.parametrize("failure", ["business", "auth", "shape", "outer", "inner"])
def test_later_occurrence_failure_retains_query_evidence(installed, failure):
    cli, browser, _ = installed
    response = details([])
    expected = "INVALID_RESPONSE"
    if failure == "business":
        response["body"]["result"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "auth":
        response = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "shape":
        response["body"]["result"]["dataValue"] = {}
    elif failure == "outer":
        response["body"]["resultFlag"] = "true"
    elif failure == "inner":
        response["body"]["result"]["success"] = 1
    browser.business_script.extend(
        [base([row(1), row(2)]), metric(), details([]), metric(), response]
    )
    result = cli("refresh", *FLAGS, code=1)
    assert result["error"]["code"] == expected
    assert result["meta"]["published"] is False
    evidence = result["meta"]["query_evidence"]
    assert evidence["queries"]["metric"]["succeeded"] == 2
    assert evidence["queries"]["occurrences"]["succeeded"] == 1
    assert evidence["queries"]["occurrences"]["error"]["code"] == expected


@pytest.mark.parametrize("installed", ["zip"], indirect=True)
def test_zip_candidate_preserves_new_business_section(installed):
    cli, browser, _ = installed
    browser.business_script.extend(
        [base([row()]), metric(), details([{"unknown": [0]}])]
    )
    result = cli("list", "--live", *FLAGS)
    assert result["data"][0]["cashflow_details"] == [{"unknown": [0]}]


def test_shared_request_budget_covers_metric_and_occurrences(
    installed, run_cli, tmp_path
):
    cli, browser, _ = installed
    result, output, error = run_cli(
        ["plugins", "uninstall", "liquidity.forecast.accuracy"]
    )
    assert result == 0, output + error
    source = tmp_path / "bounded"
    shutil.copytree(SOURCE, source)
    manifest = json.loads((source / "leaf.json").read_text())
    manifest["operations"]["list"]["max_requests"] = 4
    (source / "leaf.json").write_text(json.dumps(manifest))
    result, output, error = run_cli(["plugins", "install", str(source)])
    assert result == 0, output + error
    browser.business_script.extend(
        [base([row(1), row(2)]), metric(), details([]), metric()]
    )
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "TIMEOUT"
    assert len(browser.business_requests) == 4
    assert not result.get("data")


def test_changed_composition_cannot_replay_previous_contract(
    installed, run_cli, tmp_path
):
    cli, browser, config = installed
    source = tmp_path / "prior-contract"
    shutil.copytree(SOURCE, source)
    path = source / "adapter.py"
    # Model a separately accepted old contract, without retaining legacy source.
    previous = path.read_text().replace("complete=not rows,", "complete=True,")
    previous = previous.replace(
        '"cashflow_details": detail["dataValue"]',
        '"prior_details": detail["dataValue"]',
    )
    path.write_text(previous)
    code, output, error = run_cli(
        ["plugins", "uninstall", "liquidity.forecast.accuracy"]
    )
    assert code == 0, output + error
    code, output, error = run_cli(["plugins", "install", str(source)])
    assert code == 0, output + error
    browser.business_script.extend([base([row()]), metric(), details([])])
    saved = cli("refresh", *FLAGS)
    assert saved["meta"]["published"] is True
    # Preserve the prior capture across public uninstall, which deletes cache rows.
    backup = tmp_path / "saved-cache.sqlite3"
    with sqlite3.connect(config / "leaf-cache.sqlite3") as original:
        with sqlite3.connect(backup) as snapshot:
            original.backup(snapshot)
    code, output, error = run_cli(
        ["plugins", "uninstall", "liquidity.forecast.accuracy"]
    )
    assert code == 0, output + error
    code, output, error = run_cli(["plugins", "install", str(SOURCE)])
    assert code == 0, output + error
    with sqlite3.connect(backup) as snapshot:
        with sqlite3.connect(config / "leaf-cache.sqlite3") as restored:
            snapshot.backup(restored)
    count = len(browser.business_requests)
    browser.running = False
    result = cli("list", code=1)
    assert result["error"]["code"] == "CACHE_CONTRACT_CHANGED"
    assert len(browser.business_requests) == count


def test_deadline_remains_shared_across_dependent_sources(installed, monkeypatch):
    cli, browser, _ = installed
    clock = [1.0]
    monkeypatch.setattr("dogopencli.collect._monotonic", lambda: clock[0])
    responses = [base([row()]), metric()]

    def fetch(payload, index):
        if index == 1:
            clock[0] = 302.0
        return responses[index]

    browser.business_handler = fetch
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "TIMEOUT"
    assert len(browser.business_requests) == 2
    assert not result.get("data")


def test_maximum_client_parent_scope_gets_every_required_child(installed):
    cli, browser, _ = installed
    browser.business_script.append(base([row(index) for index in range(100)]))
    for _ in range(100):
        browser.business_script.extend([metric(), details([])])
    result = cli("list", "--live", *FLAGS, "--offset", "99", "--limit", "1")
    assert result["data"][0]["id"] == "99"
    assert len(browser.business_requests) == 201
    assert result["meta"]["acquisition"]["attempts"][0]["occurrence_succeeded"] == 100
