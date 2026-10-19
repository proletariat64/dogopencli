"""Two independently installed native metric inquiries; all records are synthetic."""

import json
import runpy
import shutil
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import CliError

pytest_plugins = ["integration.test_leaf_handbook"]
ROOT = Path(__file__).resolve().parents[2]
SOURCES = [
    ROOT / "leaf_packages/liquidity/risk.deposit_concentration",
    ROOT / "leaf_packages/liquidity/risk.credit_usage",
]
pytestmark = pytest.mark.parametrize("sample_source", SOURCES, indirect=True)


@pytest.fixture
def metric_handbook(handbook, sample_source):
    cli, browser, config = handbook
    browser.href = LIQUIDITY_STARTUP_URL
    manifest = json.loads((sample_source / "leaf.json").read_text())
    module = runpy.run_path(str(sample_source / "adapter.py"))
    return cli, browser, config, manifest, module


def rows(metric):
    return [
        {
            "id": 101,
            "metricName": metric,
            "metricLabel": "",
            "metricNameDescription": "Synthetic native description",
            "reportDate": "20260101",
            "reportTime": "2026-01-01 14:00:00",
            "reportTimeOnlyHourAndMinuter": "14:00",
            "balanceByUsd": "0.00",
            "totalAmount": "1,234.5678",
            "value": "0.00",
            "gmtCreate": "",
            "gmtModified": "",
            "bankAmountList": [
                {"bankId": "BRANCH_B", "amount": "0.00"},
                {"bankId": "BRANCH_A", "amount": "1234.5678"},
            ],
            "unknown": {"values": [False, None, Decimal("0.1234567890123456789")]},
        },
        {
            "id": 102,
            "metricName": metric,
            "metricLabel": "SYNTHETIC_GROUP",
            "reportDate": "20260101",
            "reportTime": "2026-01-01 07:00:00",
            "value": "0",
        },
    ]


def reply(records, *, success=True):
    return {"status": 200, "body": {"success": success, "data": records}}


def test_independent_metric_help_live_refresh_offline_and_empty_binding(
    metric_handbook,
):
    cli, browser, config, manifest, module = metric_handbook
    leaf = manifest["name"]
    for action in ("list", "refresh"):
        cli("liquidity", action, leaf, "-h")
    cli("liquidity", "describe", leaf)
    assert not browser.business_requests
    assert not (config / "leaf-cache.sqlite3").exists()
    assert manifest["operations"].keys() == {"list"}
    native = rows(module["METRIC"])
    browser.business_script.append(reply(native))
    live = cli(
        "liquidity", "list", leaf, "--live", "--require-complete", "--limit", "0"
    )
    assert live["data"] == native
    assert type(live["data"][0]["id"]) is int
    assert type(live["data"][0]["unknown"]["values"][2]) is Decimal
    assert browser.business_requests == [
        {"tntInstId": "GUAPW3SG", "metricName": module["METRIC"]}
    ]
    assert live["meta"]["complete"] is True
    assert live["meta"]["reported_total"] is None
    assert live["meta"]["acquisition"]["coverage_basis"] == "qualified_single_response"
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(reply(native))
    saved = cli("liquidity", "refresh", leaf, "--require-complete")
    assert saved["meta"]["published"] is True
    count = len(browser.business_requests)
    offline = cli("liquidity", "list", leaf, "--limit", "0")
    assert offline["data"] == native
    assert offline["meta"]["acquisition"] == saved["meta"]["acquisition"]
    assert len(browser.business_requests) == count
    with duckdb.connect(str(config / "duckdog.duckdb"), read_only=True) as db:
        assert db.execute(
            f"SELECT count(*) FROM {manifest['dataset']['relation']}"
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "business",
        "shape",
        "id_bool",
        "id_string",
        "id_missing",
        "metric",
        "mixed_metric",
        "duplicate",
        "conflict",
        "auth",
    ],
)
def test_metric_rejected_refresh_retains_previous_capture(metric_handbook, failure):
    cli, browser, _, manifest, module = metric_handbook
    leaf = manifest["name"]
    native = rows(module["METRIC"])
    browser.business_script.append(reply(native))
    cli("liquidity", "refresh", leaf, "--require-complete")
    before = cli("liquidity", "list", leaf, "--limit", "0")
    candidate = rows(module["METRIC"])
    expected = "INVALID_RESPONSE"
    if failure == "empty":
        candidate, expected = [], None
    elif failure == "business":
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "shape":
        candidate = {}
    elif failure == "id_bool":
        candidate[0]["id"] = True
    elif failure == "id_string":
        candidate[0]["id"] = "101"
    elif failure == "id_missing":
        del candidate[0]["id"]
    elif failure == "metric":
        for record in candidate:
            record["metricName"] = "UNREQUESTED_METRIC"
    elif failure == "mixed_metric":
        candidate[1]["metricName"] = "UNREQUESTED_METRIC"
    elif failure in {"duplicate", "conflict"}:
        candidate = [candidate[0], dict(candidate[0])]
        if failure == "conflict":
            candidate[1]["value"] = "99.00"
        expected = "INCOMPLETE_RESULT"
    elif failure == "auth":
        expected = "AUTH_REQUIRED"
    response = (
        {"status": 401, "body": {}}
        if failure == "auth"
        else reply(candidate, success=failure != "business")
    )
    browser.business_script.append(response)
    result = cli(
        "liquidity", "refresh", leaf, "--require-complete", code=1 if expected else 0
    )
    if expected:
        assert result["error"]["code"] == expected
    else:
        assert result["meta"]["published"] is False
    count = len(browser.business_requests)
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"] == native
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]
    assert len(browser.business_requests) == count


@pytest.mark.parametrize("request_kind", ["other_metric", "other_tenant", "pageSize"])
def test_metric_transport_rejects_unverified_request(
    metric_handbook, sample_source, tmp_path, request_kind
):
    cli, browser, _, manifest, _ = metric_handbook
    leaf = manifest["name"]
    cli("plugins", "uninstall", f"liquidity.{leaf}")
    source = tmp_path / "tampered"
    shutil.copytree(sample_source, source)
    adapter = source / "adapter.py"
    replacement = {
        "other_metric": 'return {"tntInstId": TENANT, "metricName": "OTHER"}',
        "other_tenant": 'return {"tntInstId": "OTHER", "metricName": METRIC}',
        "pageSize": (
            'return {"tntInstId": TENANT, "metricName": METRIC, "pageSize": 50}'
        ),
    }[request_kind]
    adapter.write_text(
        adapter.read_text().replace(
            'return {"tntInstId": TENANT, "metricName": METRIC}', replacement
        )
    )
    cli("plugins", "install", str(source))
    result = cli("liquidity", "list", leaf, "--live", code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_metric_parser_and_request_boundaries(sample_source):
    module = runpy.run_path(str(sample_source / "adapter.py"))
    inquiry = module["CAPABILITY"]
    for body in (
        b"not-json",
        b"[]",
        b'{"success":1,"data":[]}',
        b'{"success":true,"data":[null]}',
        b'{"success":true,"data":[{"id":null}]}',
    ):
        with pytest.raises(CliError) as error:
            inquiry.parse_rows(body)
        assert error.value.code == "INVALID_RESPONSE"
    for scope, position, size in (
        ("OTHER", 0, 0),
        (module["SCOPE"], True, 0),
        (module["SCOPE"], 1, 0),
        (module["SCOPE"], 0, False),
        (module["SCOPE"], 0, 50),
    ):
        with pytest.raises(CliError) as error:
            inquiry.page_body(scope, position, size)
        assert error.value.code == "REQUEST_NOT_ALLOWED"


def test_two_metrics_keep_distinct_capture_namespaces(metric_handbook, sample_source):
    cli, browser, _, manifest, module = metric_handbook
    other = next(source for source in SOURCES if source != sample_source)
    other_manifest = json.loads((other / "leaf.json").read_text())
    other_module = runpy.run_path(str(other / "adapter.py"))
    cli("plugins", "install", str(other))
    first_rows = rows(module["METRIC"])
    browser.business_script.append(reply(first_rows))
    cli("liquidity", "refresh", manifest["name"], "--require-complete")
    before = cli("liquidity", "list", manifest["name"], "--limit", "0")
    missing = cli("liquidity", "list", other_manifest["name"], code=1)
    assert missing["error"]["code"] == "CACHE_MISS"
    other_rows = rows(other_module["METRIC"])
    browser.business_script.append(reply(other_rows))
    cli("liquidity", "refresh", other_manifest["name"], "--require-complete")
    count = len(browser.business_requests)
    first = cli("liquidity", "list", manifest["name"], "--limit", "0")
    second = cli("liquidity", "list", other_manifest["name"], "--limit", "0")
    assert first["data"] == before["data"] == first_rows
    assert first["meta"]["fetched_at"] == before["meta"]["fetched_at"]
    assert second["data"] == other_rows
    assert len(browser.business_requests) == count == 2
    assert manifest["dataset"]["relation"] != other_manifest["dataset"]["relation"]
    assert module["adapter"].scope({}) != other_module["adapter"].scope({})
