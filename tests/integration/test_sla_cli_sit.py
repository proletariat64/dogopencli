"""Public-CLI SIT for the SLA baseline CDP query path (issue #6).

Drives ``dogopencli payment sla baselines list``, ``... get --id`` and
``dogopencli refresh payment sla`` through dogopencli.cli.main with the
browser/CDP external boundary replaced by the scripted stand-ins in
``fake_cdp.py``. Every request passes command registration, the shared
allowlist, the SLA plugin parsers, the bounded collector and SQLite. All
rows are synthetic and sanitized; no real Chrome, network, credentials or
production data is involved.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_cdp import PAYMENT_URL, SSO_URL, FakeBrowser

import dogopencli.collect as collect_mod
from dogopencli.browser import cdp
from dogopencli.browser.coordination import acquire_browser_control
from dogopencli.errors import CliError
from dogopencli.plugins import get_capability
from dogopencli.plugins.payment.sla import SLA_DETAIL
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport

CDP_URL = "http://127.0.0.1:9222"
LIST_PATH = "/api/fundOutSlaBaseline/queryFundOutSlaBaseline"
DETAIL_PATH = "/api/fundOutSlaBaseline/getFundOutSlaBaselineDetail"
PRECISE_TEXT = "0.1234567890123456789"


def sla_row(baseline_id, **overrides):
    row = {
        "id": str(baseline_id),
        "bizCategory": "ACQUIRING",
        "creditorCurrency": "USD",
        "regionCode": "US",
        "status": "ACTIVATED",
        "timezone": "Asia/Shanghai",
        "creditorMinAmount": "0.10",
        "creditorMaxAmount": "999999999.99",
        "debitorSuccessSla": "86400",
        "creditorSuccessSla": "172800",
        "holidayLimit": "Y",
        "serviceLevelLimit": [],
        "creator": "synthetic-creator",
        "lastOperator": "synthetic-operator",
        "gmtCreate": 1694000000000,
        "gmtModified": 1694100000000,
        "futureUnknownField": {"keep": ["as-is", 1]},
    }
    row.update(overrides)
    return row


def sla_detail(baseline_id, **overrides):
    detail = sla_row(
        baseline_id,
        riskRuleCode=f"RISK-{baseline_id}",
        detailOnlyDecimal=PRECISE_TEXT,
    )
    detail.update(overrides)
    return detail


def list_page(
    records,
    page_no=0,
    page_size=5000,
    total_count=None,
    success=True,
    omit_list=False,
):
    body = {
        "success": success,
        "errorContext": {"errorStack": [{"errorName": "SUCCESS"}]},
        "pageNo": page_no,
        "pageSize": page_size,
        "totalCount": len(records) if total_count is None else total_count,
        "showButton": False,
        "sofaTracerId": "synthetic-trace",
    }
    if not omit_list:
        body["resultDataList"] = records
    if not success:
        body["errorContext"] = {
            "errorStack": [{"errorName": "PARAM_ILLEGAL", "errorSpecific": "0400"}]
        }
    return {"status": 200, "body": body}


def detail_outcome(baseline_id, found=True, success=True):
    if not success:
        return {
            "status": 200,
            "body": {"success": False, "resultData": None},
        }
    result = sla_detail(baseline_id) if found else None
    return {"status": 200, "body": {"success": True, "resultData": result}}


def refresh_handler(rows, fail_details=(), null_details=()):
    details = {row["id"]: sla_detail(row["id"]) for row in rows}

    def handle(payload: dict, call_index: int):
        if "slaBaselineId" in payload:
            baseline_id = payload["slaBaselineId"]
            if baseline_id in fail_details:
                return detail_outcome(baseline_id, success=False)
            if baseline_id in null_details:
                return detail_outcome(baseline_id, found=False)
            return {
                "status": 200,
                "body": {"success": True, "resultData": details[baseline_id]},
            }
        return list_page(rows, page_no=payload["pageNo"], page_size=payload["pageSize"])

    return handle


@pytest.fixture
def sla_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    profile = tmp_path / "chrome-profile"
    cache_path = tmp_path / "cache.sqlite3"
    config_path = tmp_path / "config.toml"

    def write_config(ttl_hours: float | int = 72) -> None:
        config_path.write_text(
            "[cache]\n"
            f'path = "{cache_path}"\n'
            f"ttl_hours = {ttl_hours}\n"
            "\n"
            "[auth]\n"
            f'profile = "{profile}"\n'
            f'cdp_url = "{CDP_URL}"\n'
            "\n"
            "[sources.payment_sla]\n"
            'kind = "cdp"\n'
        )
        monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config_path))

    write_config()
    state = FakeBrowser()
    cdp.set_transport_factory(state.transport)
    yield SimpleNamespace(
        state=state,
        profile=profile,
        tmp_path=tmp_path,
        cache_path=cache_path,
        write_config=write_config,
    )
    cdp.set_transport_factory(None)


@pytest.fixture
def sample_sla_rows() -> list[dict]:
    return [
        sla_row(101),
        sla_row(102, status="OFFLINE"),
        sla_row(
            103,
            bizCategory="REMITTANCE",
            creditorCurrency="EUR",
            regionCode="SG",
            status="DRAFT",
        ),
        sla_row(104, bizCategory="REMITTANCE", regionCode="HK"),
    ]


def refresh(run_cli, *extra: str):
    return run_cli(["refresh", "payment", "sla", *extra])


def listing(run_cli, *extra: str):
    return run_cli(["payment", "sla", "baselines", "list", *extra])


def getting(run_cli, *extra: str):
    return run_cli(["payment", "sla", "baselines", "get", *extra])


def refreshed(run_cli, sla_setup, rows) -> None:
    sla_setup.state.business_handler = refresh_handler(rows)
    code, _, _ = refresh(run_cli)
    assert code == 0
    sla_setup.state.business_handler = None


def business_expressions(state: FakeBrowser) -> list[str]:
    return [
        expression
        for transport in state.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]


def test_refresh_then_list_and_get_offline(
    run_cli, envelope, sla_setup, sample_sla_rows
):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    assert sla_setup.cache_path.is_file()
    assert sla_setup.cache_path.stat().st_mode & 0o777 == 0o600

    requests_before = list(sla_setup.state.business_requests)
    code, out, err = listing(run_cli)
    assert code == 0
    assert err == ""
    result = envelope(out)
    rows = result["data"]
    assert [row["id"] for row in rows] == ["101", "102", "103", "104"]
    assert all("riskRuleCode" not in row for row in rows)
    meta = result["meta"]
    assert meta["source"] == "cache"
    assert meta["backend"] == "cdp"
    assert meta["simulated"] is False
    assert meta["complete"] is True
    assert meta["stale"] is False
    assert meta["matched_total"] == 4
    assert meta["returned_count"] == 4
    assert meta["has_more"] is False

    code, out, err = getting(run_cli, "--id", "103")
    assert code == 0
    result = envelope(out)
    detail = result["data"]
    assert detail["id"] == "103"
    # The offline detail comes from the collected detail, not the list row.
    assert detail["riskRuleCode"] == "RISK-103"
    assert result["meta"]["source"] == "cache"
    assert result["meta"]["matched_total"] == 1
    # Offline list and get issued zero business requests.
    assert sla_setup.state.business_requests == requests_before


def test_refresh_collects_list_then_serial_details_in_id_order(run_cli, sla_setup):
    rows = [sla_row(100), sla_row(9), sla_row(10), sla_row(2)]
    refreshed(run_cli, sla_setup, rows)
    payloads = sla_setup.state.business_requests
    assert payloads[0] == {"pageNo": 0, "pageSize": 5000}
    assert payloads[1:] == [
        {"slaBaselineId": baseline_id} for baseline_id in ("2", "9", "10", "100")
    ]
    expressions = business_expressions(sla_setup.state)
    assert f'fetch("https://iglobalfundcontrol.alipay.com{LIST_PATH}' in expressions[0]
    assert 'method: "POST"' in expressions[0]
    for expression in expressions[1:]:
        assert (
            f'fetch("https://iglobalfundcontrol.alipay.com{DETAIL_PATH}' in expression
        )
        assert 'method: "GET"' in expression


def test_allowlist_rejects_unregistered_requests(sla_setup):
    list_capability = get_capability("payment.sla.baselines.list")
    list_transport = CdpQueryTransport(
        sla_setup.state.transport(CDP_URL), list_capability, page_url=PAYMENT_URL
    )
    detail_transport = CdpQueryTransport(
        sla_setup.state.transport(CDP_URL), SLA_DETAIL, page_url=PAYMENT_URL
    )

    def forged(**changes):
        base = {
            "capability": "payment.sla.baselines.list",
            "method": "POST",
            "host": "iglobalfundcontrol.alipay.com",
            "path": LIST_PATH,
            "body": {"pageNo": 0, "pageSize": 5000},
        }
        base.update(changes)
        return QueryRequest(**base)

    def forged_detail(**changes):
        base = {
            "capability": SLA_DETAIL.name,
            "method": "GET",
            "host": "iglobalfundcontrol.alipay.com",
            "path": DETAIL_PATH,
            "body": {"slaBaselineId": "1"},
        }
        base.update(changes)
        return QueryRequest(**base)

    cases = [
        (list_transport, forged(host="evil.example.com")),
        (list_transport, forged(host="ifundcontrol.alipay.com")),
        (list_transport, forged(path="/api/fundOutSlaBaseline/saveFundOutSlaBaseline")),
        (list_transport, forged(method="GET")),
        (list_transport, forged(body={"pageNo": 0, "pageSize": 5000, "export": True})),
        (list_transport, forged(capability="payment.cost.list")),
        # The detail endpoint is not reachable through the list contract.
        (
            list_transport,
            forged(method="GET", path=DETAIL_PATH, body={"slaBaselineId": "1"}),
        ),
        # The list endpoint is not reachable through the detail contract.
        (detail_transport, forged(capability=SLA_DETAIL.name)),
        (
            detail_transport,
            forged_detail(body={"slaBaselineId": "1", "slaBaselineName": "x"}),
        ),
        (detail_transport, forged_detail(method="POST")),
        (detail_transport, forged_detail(host="ifundcontrol.alipay.com")),
    ]
    for transport, bad in cases:
        with pytest.raises(CliError) as caught:
            transport.execute(bad)
        assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert sla_setup.state.business_requests == []


def test_zero_total_omitted_list_key_publishes_empty(run_cli, envelope, sla_setup):
    sla_setup.state.business_script.append(list_page([], omit_list=True))
    code, out, _ = refresh(run_cli)
    assert code == 0
    assert envelope(out)["data"]["row_count"] == 0
    code, out, _ = listing(run_cli)
    assert code == 0
    result = envelope(out)
    assert result["data"] == []
    assert result["meta"]["matched_total"] == 0
    assert result["meta"]["complete"] is True


def test_explicit_null_list_is_not_swallowed_as_empty(run_cli, envelope, sla_setup):
    body = {
        "success": True,
        "pageNo": 0,
        "pageSize": 5000,
        "totalCount": 0,
        "resultDataList": None,
    }
    sla_setup.state.business_script.append({"status": 200, "body": body})
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "INVALID_RESPONSE"
    code, out, _ = listing(run_cli)
    assert envelope(out)["error"]["code"] == "CACHE_MISS"


def test_zero_total_with_rows_is_invalid(run_cli, envelope, sla_setup):
    sla_setup.state.business_script.append(list_page([sla_row(1)], total_count=0))
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not sla_setup.cache_path.exists()


def test_business_failure_is_not_swallowed_as_empty(run_cli, envelope, sla_setup):
    sla_setup.state.business_script.append(list_page([], success=False))
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert not sla_setup.cache_path.exists()
    code, out, _ = listing(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_MISS"


def test_detail_failure_keeps_old_snapshot(
    run_cli, envelope, sla_setup, sample_sla_rows
):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    sla_setup.state.business_handler = refresh_handler(
        sample_sla_rows, fail_details=("103",)
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    sla_setup.state.business_handler = None
    code, out, _ = listing(run_cli)
    assert code == 0
    assert envelope(out)["meta"]["matched_total"] == 4
    code, out, _ = getting(run_cli, "--id", "103")
    assert code == 0
    assert envelope(out)["data"]["riskRuleCode"] == "RISK-103"


def test_missing_detail_keeps_old_snapshot(
    run_cli, envelope, sla_setup, sample_sla_rows
):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    sla_setup.state.business_handler = refresh_handler(
        sample_sla_rows, null_details=("102",)
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["error"]["code"] == "NOT_FOUND"
    assert "102" in result["error"]["message"]
    sla_setup.state.business_handler = None
    code, out, _ = listing(run_cli)
    assert code == 0
    assert envelope(out)["meta"]["matched_total"] == 4


def test_get_not_found_offline(run_cli, envelope, sla_setup, sample_sla_rows):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    code, out, _ = getting(run_cli, "--id", "999")
    assert code == 1
    result = envelope(out)
    assert result["data"] is None
    assert result["error"]["code"] == "NOT_FOUND"
    assert "999" in result["error"]["message"]


def test_get_live_detail_and_not_found_vs_failure(run_cli, envelope, sla_setup):
    sla_setup.state.business_script.append(detail_outcome("55"))
    code, out, _ = getting(run_cli, "--id", "55", "--live")
    assert code == 0
    result = envelope(out)
    assert result["data"]["id"] == "55"
    assert result["data"]["riskRuleCode"] == "RISK-55"
    meta = result["meta"]
    assert meta["source"] == "live"
    assert meta["backend"] == "cdp"
    assert meta["simulated"] is False
    assert meta["snapshot_id"] is None
    assert sla_setup.state.business_requests == [{"slaBaselineId": "55"}]
    assert not sla_setup.cache_path.exists()

    # success=true with resultData=null is NOT_FOUND, distinct from failure.
    sla_setup.state.business_script.append(detail_outcome("66", found=False))
    code, out, _ = getting(run_cli, "--id", "66", "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "NOT_FOUND"

    sla_setup.state.business_script.append(detail_outcome("77", success=False))
    code, out, _ = getting(run_cli, "--id", "77", "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert not sla_setup.cache_path.exists()


def test_filters_exact_or_and(run_cli, envelope, sla_setup, sample_sla_rows):
    refreshed(run_cli, sla_setup, sample_sla_rows)

    code, out, _ = listing(run_cli, "--biz-category", "REMITTANCE")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 2
    assert {row["id"] for row in result["data"]} == {"103", "104"}

    code, out, _ = listing(run_cli, "--status", "OFFLINE", "--status", "DRAFT")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 2
    assert {row["status"] for row in result["data"]} == {"OFFLINE", "DRAFT"}

    code, out, _ = listing(
        run_cli, "--biz-category", "REMITTANCE", "--region-code", "HK"
    )
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 1
    assert result["data"][0]["id"] == "104"

    code, out, _ = listing(run_cli, "--creditor-currency", "EUR")
    assert code == 0
    assert envelope(out)["meta"]["matched_total"] == 1


def test_biz_legal_entity_offline_rejected(
    run_cli, envelope, sla_setup, sample_sla_rows
):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    code, out, _ = listing(run_cli, "--biz-legal-entity", "ALIPAY SG")
    assert code == 2
    result = envelope(out)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert "unverified" in result["error"]["message"]


def test_biz_legal_entity_live_passthrough_only(
    run_cli, envelope, sla_setup, sample_sla_rows
):
    sla_setup.state.business_script.append(list_page(sample_sla_rows))
    code, out, err = listing(run_cli, "--live", "--biz-legal-entity", "ALIPAY SG")
    assert code == 0
    payload = sla_setup.state.business_requests[0]
    assert payload["bizLegalEntity"] == "ALIPAY SG"
    assert payload["pageNo"] == 0
    assert payload["pageSize"] == 5000
    assert "unverified" in err
    assert envelope(out)["meta"]["source"] == "live"
    assert not sla_setup.cache_path.exists()


def test_live_rejects_multi_value_filter(run_cli, envelope, sla_setup):
    code, out, _ = listing(run_cli, "--live", "--status", "A", "--status", "B")
    assert code == 2
    assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert sla_setup.state.business_requests == []


def test_id_ordering_numeric_ascending(run_cli, envelope, sla_setup):
    rows = [sla_row(100), sla_row(9), sla_row(10), sla_row(2)]
    refreshed(run_cli, sla_setup, rows)
    code, out, _ = listing(run_cli, "--all")
    assert code == 0
    assert [row["id"] for row in envelope(out)["data"]] == ["2", "9", "10", "100"]


def test_display_params(run_cli, envelope, sla_setup, sample_sla_rows):
    refreshed(run_cli, sla_setup, sample_sla_rows)

    code, out, _ = listing(run_cli, "--limit", "2", "--offset", "1")
    assert code == 0
    result = envelope(out)
    assert [row["id"] for row in result["data"]] == ["102", "103"]
    assert result["meta"]["matched_total"] == 4
    assert result["meta"]["has_more"] is True

    code, out, _ = listing(run_cli, "--all", "--fields", "id,status")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["returned_count"] == 4
    assert all(set(row) == {"id", "status"} for row in result["data"])

    code, out, _ = getting(run_cli, "--id", "101", "--fields", "id,riskRuleCode")
    assert code == 0
    assert set(envelope(out)["data"]) == {"id", "riskRuleCode"}

    for extra in (
        ["--all", "--limit", "5"],
        ["--limit", "0"],
        ["--offset", "-1"],
        ["--fields", " , "],
    ):
        code, out, _ = listing(run_cli, *extra)
        assert code == 2, extra
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_table_format_marks_quality(run_cli, sla_setup, sample_sla_rows):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    code, out, _ = listing(run_cli, "--format", "table", "--limit", "2")
    assert code == 0
    assert "source: cache" in out
    assert "backend: cdp" in out
    assert "simulated: false" in out
    assert "complete: true" in out
    assert "stale: false" in out
    assert "bizCategory" in out

    code, out, _ = getting(run_cli, "--id", "101", "--format", "table")
    assert code == 0
    assert "source: cache" in out
    assert "riskRuleCode" not in out  # default columns only


def test_stale_and_require_fresh(run_cli, envelope, sla_setup, sample_sla_rows):
    sla_setup.write_config(ttl_hours=0)
    refreshed(run_cli, sla_setup, sample_sla_rows)
    code, out, _ = listing(run_cli)
    assert code == 0
    assert envelope(out)["meta"]["stale"] is True
    code, out, _ = listing(run_cli, "--require-fresh")
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_STALE"
    code, out, _ = getting(run_cli, "--id", "101", "--require-fresh")
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_STALE"
    code, out, _ = listing(run_cli, "--require-complete")
    assert code == 0


def test_cache_miss_is_explicit(run_cli, envelope, sla_setup):
    code, out, _ = listing(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["data"] is None
    assert result["error"]["code"] == "CACHE_MISS"
    assert "refresh payment sla" in result["error"]["message"]

    code, out, _ = getting(run_cli, "--id", "101")
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_MISS"


def test_live_list_never_writes_cache_or_falls_back(
    run_cli, envelope, sla_setup, sample_sla_rows
):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    cache_bytes = sla_setup.cache_path.read_bytes()
    sla_setup.state.business_script.append(list_page(sample_sla_rows[:1]))
    code, out, _ = listing(run_cli, "--live")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["source"] == "live"
    assert result["meta"]["matched_total"] == 1
    assert sla_setup.cache_path.read_bytes() == cache_bytes

    sla_setup.state.business_script.append(list_page([], success=False))
    code, out, _ = listing(run_cli, "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    code, out, _ = listing(run_cli)
    assert code == 0
    assert envelope(out)["meta"]["matched_total"] == 4


def test_live_incomplete_marked_and_require_complete(
    run_cli, envelope, sla_setup, sample_sla_rows
):
    duplicated = sample_sla_rows + [sample_sla_rows[0]]
    sla_setup.state.business_script.extend(
        [
            list_page(duplicated, page_size=5000, total_count=5),
            list_page(duplicated, page_size=10000, total_count=5),
        ]
    )
    code, out, _ = listing(run_cli, "--live")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["complete"] is False
    assert result["meta"]["matched_total"] == 4

    sla_setup.state.business_script.extend(
        [
            list_page(duplicated, page_size=5000, total_count=5),
            list_page(duplicated, page_size=10000, total_count=5),
        ]
    )
    code, out, _ = listing(run_cli, "--live", "--require-complete")
    assert code == 1
    assert envelope(out)["error"]["code"] == "INCOMPLETE_RESULT"


def test_seconds_strings_decimals_and_unknown_fields_preserved(
    run_cli, envelope, sla_setup, sample_sla_rows
):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    code, out, _ = listing(run_cli, "--limit", "1")
    assert code == 0
    row = envelope(out)["data"][0]
    assert row["debitorSuccessSla"] == "86400"
    assert row["creditorSuccessSla"] == "172800"
    assert row["creditorMinAmount"] == "0.10"
    assert row["futureUnknownField"] == {"keep": ["as-is", 1]}
    assert row["serviceLevelLimit"] == []

    code, out, _ = getting(run_cli, "--id", "101")
    assert code == 0
    detail = envelope(out)["data"]
    assert detail["detailOnlyDecimal"] == PRECISE_TEXT
    assert PRECISE_TEXT in out


def test_detail_collection_bounded_by_remaining_budget(
    run_cli, envelope, sla_setup, sample_sla_rows, monkeypatch
):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    requests_before = len(sla_setup.state.business_requests)
    clock = [0.0]
    monkeypatch.setattr(collect_mod, "_monotonic", lambda: clock[0])

    def handle(payload: dict, call_index: int):
        # The budget is exhausted by the time the list has been collected.
        clock[0] = 1e9
        return list_page(sample_sla_rows)

    sla_setup.state.business_handler = handle
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "TIMEOUT"
    # Only the list page was requested; no detail fetch ran over budget.
    assert len(sla_setup.state.business_requests) == requests_before + 1
    sla_setup.state.business_handler = None
    code, out, _ = listing(run_cli)
    assert code == 0
    assert envelope(out)["meta"]["matched_total"] == 4


def test_auth_required_from_probe(run_cli, envelope, sla_setup):
    sla_setup.state.href = SSO_URL
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"
    assert sla_setup.state.business_requests == []
    code, out, _ = listing(run_cli, "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"
    code, out, _ = getting(run_cli, "--id", "1", "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"


def test_browser_unavailable(run_cli, envelope, sla_setup):
    sla_setup.state.running = False
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BROWSER_UNAVAILABLE"


def test_browser_busy_maps_to_locked(run_cli, envelope, sla_setup):
    lock = acquire_browser_control(sla_setup.profile, shared=False)
    try:
        code, out, _ = refresh(run_cli)
        assert code == 1
        result = envelope(out)
        assert result["error"]["code"] == "LOCKED"
        assert result["error"]["retryable"] is True
    finally:
        lock.release()


def test_refresh_replaces_without_merging_old_rows(
    run_cli, envelope, sla_setup, sample_sla_rows
):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    refreshed(run_cli, sla_setup, [sla_row(201), sla_row(202)])
    code, out, _ = listing(run_cli, "--all")
    result = envelope(out)
    assert result["meta"]["matched_total"] == 2
    assert [row["id"] for row in result["data"]] == ["201", "202"]
    code, out, _ = getting(run_cli, "--id", "101")
    assert code == 1
    assert envelope(out)["error"]["code"] == "NOT_FOUND"


def test_credentials_never_leave_the_browser(run_cli, sla_setup, sample_sla_rows):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    code, out, err = listing(run_cli, "--all")
    assert code == 0
    code, get_out, get_err = getting(run_cli, "--id", "101")
    assert code == 0
    secret = "FAKE-CTOKEN-SECRET"
    for text in (out, err, get_out, get_err):
        assert secret not in text
        assert "ctoken" not in text
    cache_bytes = sla_setup.cache_path.read_bytes()
    assert secret.encode() not in cache_bytes
    assert b"ctoken" not in cache_bytes
    for expression in business_expressions(sla_setup.state):
        assert secret not in expression
    allowed_list = {
        "bizCategory",
        "bizLegalEntity",
        "creditorCurrency",
        "regionCode",
        "status",
        "pageNo",
        "pageSize",
    }
    for payload in sla_setup.state.business_requests:
        assert set(payload) <= allowed_list or set(payload) <= {"slaBaselineId"}


def test_machine_output_envelope(run_cli, envelope, sla_setup, sample_sla_rows):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    code, out, _ = listing(run_cli)
    assert code == 0
    result = json.loads(out)
    assert set(result) == {"data", "error", "meta"}
    assert set(result["meta"]) == {
        "source",
        "backend",
        "simulated",
        "scope",
        "snapshot_id",
        "dataset_id",
        "fetched_at",
        "loaded_at",
        "stale",
        "complete",
        "dataset_complete",
        "source_observed_from",
        "source_observed_to",
        "matched_total",
        "returned_count",
        "has_more",
    }
    # table errors go to stderr with the business exit code
    sla_setup.write_config(ttl_hours=0)
    code, out, err = listing(run_cli, "--require-fresh", "--format", "table")
    assert code == 1
    assert out == ""
    assert "CACHE_STALE" in err


def test_last_sla_detail_after_deadline_preserves_cache(
    run_cli, envelope, sla_setup, sample_sla_rows, monkeypatch
):
    refreshed(run_cli, sla_setup, sample_sla_rows)
    clock = [0.0]
    monkeypatch.setattr(collect_mod, "_monotonic", lambda: clock[0])
    monkeypatch.setattr(collect_mod, "REFRESH_BUDGET_SECONDS", 1.0)
    handler = refresh_handler([sla_row(999)])

    def delayed(payload, index):
        if "slaBaselineId" in payload:
            clock[0] += 60.0
        return handler(payload, index)

    sla_setup.state.business_handler = delayed
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "TIMEOUT"
    code, out, _ = listing(run_cli)
    assert code == 0
    assert len(envelope(out)["data"]) == len(sample_sla_rows)


def test_live_detail_quality_flags_describe_single_id(run_cli, envelope, sla_setup):
    sla_setup.state.business_script.append(detail_outcome("101"))
    code, out, _ = getting(
        run_cli, "--live", "--id", "101", "--require-fresh", "--require-complete"
    )
    assert code == 0
    meta = envelope(out)["meta"]
    assert meta["complete"] is True and meta["stale"] is False
    assert meta["query"] == {"capability": "payment.sla.baselines.get", "id": "101"}
