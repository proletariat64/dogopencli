"""Public-CLI SIT for the Cost CDP query path (issue #5).

Drives ``dogopencli payment cost list`` and ``dogopencli refresh payment
cost`` through dogopencli.cli.main with the browser/CDP external boundary
replaced by the scripted stand-ins in ``fake_cdp.py``. Every request passes
command registration, the shared allowlist, the cost plugin parser, the
bounded collector and SQLite. All rows are synthetic and sanitized; no real
Chrome, network, credentials or production data is involved.
"""

import json
import threading
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_cdp import PAYMENT_URL, SSO_URL, FakeBrowser

import dogopencli.collect as collect_mod
from dogopencli.browser import cdp
from dogopencli.browser.coordination import acquire_browser_control
from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse
from dogopencli.plugins import get_capability
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport

CDP_URL = "http://127.0.0.1:9222"
COST_TYPE = "FUND_OUT_CHANNEL_TRANS_FEE"
PRECISE_AMOUNT = "0.1234567890123456789"


def cost_row(item_id, **overrides):
    row = {
        "itemId": str(item_id),
        "itemType": COST_TYPE,
        "mappingCode": f"MC-{item_id}",
        "legalEntity": "ALIPAY SG",
        "financialInst": "CITILD",
        "bankAccountAliasName": f"ACCT-{item_id}",
        "transCurrencyCode": "USD",
        "costCurrencyCode": "USD",
        "chargeBearer": "SHAR",
        "clearingNetworkName": "BOOK RTP",
        "isFvt": "N",
        "status": "ACTIVATED",
        "gmtCreate": 1694000000000,
        "gmtModified": 1694100000000,
        "costRateConfigList": [
            {
                "feeItemRateConfigId": f"FRC-{item_id}",
                "feeCalcBasisType": "CA1",
                "feeCalcScale": "TWO_DECIMAL_AFTER_POINTS",
                "feeRoundingMode": "HALF_UP",
                "progressType": "FULL_PROGRESS",
                "validStartTime": 1693500000000,
                "validEndTime": 1893500000000,
                "costRateVO": {
                    "feeItemRateConfigId": f"FRC-{item_id}",
                    "feeCalcBasisTypeCode": "CA1",
                    "status": "ACTIVATED",
                    "bottomAmount": {
                        "amount": Decimal("0.10"),
                        "cent": 10,
                        "centFactor": 100,
                        "currency": "USD",
                        "currencyCode": "USD",
                    },
                    "feeRateRatioValue": {
                        "amount": Decimal(PRECISE_AMOUNT),
                        "hundredthValue": Decimal("12.34567890123456789"),
                        "ratioUnit": "PERCENT",
                        "ratioUnitCode": "PERCENT",
                    },
                },
            }
        ],
        "futureUnknownField": {"keep": ["as-is", 1]},
    }
    row.update(overrides)
    return row


def cost_page(records, page_no=0, page_size=5000, total_count=None, success=True):
    body = {
        "success": success,
        "errorContext": {"errorStack": [{"errorName": "SUCCESS"}]},
        "pageNo": page_no,
        "pageSize": page_size,
        "totalCount": len(records) if total_count is None else total_count,
        "resultDataList": records,
        "permissions": [{"permissionCode": "SYNTHETIC_VIEW"}],
        "showButton": False,
        "sofaTracerId": "synthetic-trace",
    }
    if not success:
        body["errorContext"] = {
            "errorStack": [{"errorName": "PARAM_ILLEGAL", "errorSpecific": "0400"}]
        }
    return {"status": 200, "body": body}


def paging_handler(rows_by_page: dict[int, list], page_size: int, total: int):
    def handle(payload: dict, call_index: int):
        page_no = payload["pageNo"]
        assert payload["pageSize"] == page_size
        return cost_page(
            rows_by_page.get(page_no, []),
            page_no=page_no,
            page_size=page_size,
            total_count=total,
        )

    return handle


@pytest.fixture
def cost_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
            "[sources.payment_cost]\n"
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
def no_sleep(monkeypatch: pytest.MonkeyPatch):
    waits: list[float] = []
    monkeypatch.setattr(collect_mod, "_sleep", waits.append)
    return waits


@pytest.fixture
def sample_cost_rows() -> list[dict]:
    return [
        cost_row(101),
        cost_row(102, chargeBearer="CRED", status="OFFLINE"),
        cost_row(
            103,
            legalEntity="ALIPAY HK",
            financialInst="SCBLSG",
            bankAccountAliasName="ACCT-B",
            transCurrencyCode="EUR",
            clearingNetworkName="FX PAYOUT",
        ),
        cost_row(
            104,
            legalEntity="ALIPAY HK",
            financialInst="HSBCHK",
            bankAccountAliasName="ACCT-C",
            chargeBearer="DEBT",
            clearingNetworkName="BOOK",
        ),
        cost_row(105, bankAccountAliasName="ACCT-A"),
        cost_row(
            106,
            legalEntity="ALIPAY HK",
            financialInst="SCBLSG",
            bankAccountAliasName="ACCT-B",
            transCurrencyCode="EUR",
            chargeBearer="FVT",
            clearingNetworkName="FX PAYOUT",
        ),
        cost_row(
            107,
            legalEntity="ALIPAY UK",
            financialInst="HSBCHK",
            bankAccountAliasName="ACCT-E",
            transCurrencyCode="HKD",
            clearingNetworkName="BOOK",
        ),
        cost_row(108, bankAccountAliasName="ACCT-F", transCurrencyCode="GBP"),
    ]


def script_full(state: FakeBrowser, rows: list[dict]) -> None:
    state.business_script.append(cost_page(rows))


def refresh(run_cli, *extra: str):
    return run_cli(["refresh", "payment", "cost", *extra])


def listing(run_cli, *extra: str):
    return run_cli(["payment", "cost", "list", *extra])


def refreshed(run_cli, cost_setup, rows) -> None:
    script_full(cost_setup.state, rows)
    code, _, _ = refresh(run_cli)
    assert code == 0
    cost_setup.state.business_script.clear()


def test_refresh_then_list_offline(run_cli, envelope, cost_setup, sample_cost_rows):
    script_full(cost_setup.state, sample_cost_rows)
    code, out, err = refresh(run_cli)
    assert code == 0
    assert "published 8 rows" in err
    result = envelope(out)
    assert result["error"] is None
    assert result["data"]["published"] is True
    assert result["data"]["row_count"] == 8
    meta = result["meta"]
    assert meta["backend"] == "cdp"
    assert meta["simulated"] is False
    assert meta["complete"] is True
    assert meta["dataset_complete"] is True
    assert meta["scope"] == COST_TYPE
    assert meta["matched_total"] == 8
    assert cost_setup.cache_path.is_file()
    assert cost_setup.cache_path.stat().st_mode & 0o777 == 0o600

    requests_before = list(cost_setup.state.business_requests)
    code, out, err = listing(run_cli)
    assert code == 0
    assert err == ""
    result = envelope(out)
    rows = result["data"]
    assert len(rows) == 8
    assert [int(row["itemId"]) for row in rows] == list(range(101, 109))
    meta = result["meta"]
    assert meta["source"] == "cache"
    assert meta["backend"] == "cdp"
    assert meta["simulated"] is False
    assert meta["complete"] is True
    assert meta["stale"] is False
    assert meta["matched_total"] == 8
    assert meta["returned_count"] == 8
    assert meta["has_more"] is False
    assert meta["dataset_id"] is None
    assert meta["snapshot_id"] is not None
    assert meta["fetched_at"] is not None
    assert meta["loaded_at"] is not None
    # Offline read: zero business requests and zero new browser sessions.
    assert cost_setup.state.business_requests == requests_before
    assert len(cost_setup.state.transports) == 2  # auth probe + query session


def test_fixed_cost_type_and_zero_based_pagination(
    run_cli, cost_setup, sample_cost_rows
):
    script_full(cost_setup.state, sample_cost_rows)
    assert refresh(run_cli)[0] == 0
    assert cost_setup.state.business_requests == [
        {"costTypeCode": COST_TYPE, "pageNo": 0, "pageSize": 5000}
    ]


def test_allowlist_rejects_unregistered_requests(cost_setup):
    capability = get_capability("payment.cost.list")
    transport = CdpQueryTransport(
        cost_setup.state.transport(CDP_URL), capability, page_url=PAYMENT_URL
    )

    def forged(**changes):
        base = {
            "capability": capability.name,
            "method": "POST",
            "host": "iglobalfundcontrol.alipay.com",
            "path": "/api/fundCost/query.json",
            "body": {"costTypeCode": COST_TYPE, "pageNo": 0, "pageSize": 5000},
        }
        base.update(changes)
        return QueryRequest(**base)

    for bad in (
        forged(host="evil.example.com"),
        forged(host="ifundcontrol.alipay.com"),
        forged(path="/api/fundCost/save.json"),
        forged(path="/api/fundCost/detail.json"),
        forged(method="GET"),
        forged(
            body={
                "costTypeCode": "FX_FEE",
                "pageNo": 0,
                "pageSize": 5000,
                "approve": True,
            }
        ),
        forged(capability="payment.channel.list"),
    ):
        with pytest.raises(CliError) as caught:
            transport.execute(bad)
        assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert cost_setup.state.business_requests == []


def test_allowlist_rejects_other_cost_types_via_parser(
    run_cli, envelope, cost_setup, sample_cost_rows
):
    rows = sample_cost_rows + [cost_row(900, itemType="FX_FEE")]
    script_full(cost_setup.state, rows)
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "INVALID_RESPONSE"
    code, out, _ = listing(run_cli)
    assert envelope(out)["error"]["code"] == "CACHE_MISS"


def test_cache_filters_exact_or_and(run_cli, envelope, cost_setup, sample_cost_rows):
    refreshed(run_cli, cost_setup, sample_cost_rows)

    code, out, _ = listing(run_cli, "--legal-entity-code", "ALIPAY HK")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 3
    assert {row["legalEntity"] for row in result["data"]} == {"ALIPAY HK"}

    code, out, _ = listing(
        run_cli,
        "--trans-currency-code",
        "EUR",
        "--trans-currency-code",
        "HKD",
    )
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 3
    assert {row["transCurrencyCode"] for row in result["data"]} == {"EUR", "HKD"}

    code, out, _ = listing(
        run_cli,
        "--financial-inst-code",
        "CITILD",
        "--charge-bearer",
        "CRED",
    )
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 1
    assert result["data"][0]["itemId"] == "102"

    code, out, _ = listing(run_cli, "--clearing-network-name", "BOOK RTP")
    assert code == 0
    assert envelope(out)["meta"]["matched_total"] == 4


def test_bank_account_matches_alias_not_account_number(
    run_cli, envelope, cost_setup, sample_cost_rows
):
    refreshed(run_cli, cost_setup, sample_cost_rows)
    code, out, _ = listing(run_cli, "--bank-account", "ACCT-A")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 1
    assert result["data"][0]["bankAccountAliasName"] == "ACCT-A"

    code, out, _ = listing(run_cli, "--bank-account", "9001-000-FULL-ACCOUNT")
    assert code == 0
    result = envelope(out)
    assert result["data"] == []
    assert result["meta"]["matched_total"] == 0


def test_live_sends_scalar_filters_and_marks_source(
    run_cli, envelope, cost_setup, sample_cost_rows
):
    script_full(cost_setup.state, sample_cost_rows[:1])
    code, out, _ = listing(
        run_cli,
        "--live",
        "--legal-entity-code",
        "ALIPAY SG",
        "--bank-account",
        "ACCT-101",
        "--trans-currency-code",
        "USD",
        "--charge-bearer",
        "SHAR",
        "--clearing-network-name",
        "BOOK RTP",
        "--financial-inst-code",
        "CITILD",
    )
    assert code == 0
    payload = cost_setup.state.business_requests[0]
    assert payload == {
        "costTypeCode": COST_TYPE,
        "pageNo": 0,
        "pageSize": 5000,
        "legalEntityCode": "ALIPAY SG",
        "financialInstCode": "CITILD",
        "bankAccount": "ACCT-101",
        "transCurrencyCode": "USD",
        "chargeBearer": "SHAR",
        "clearingNetworkName": "BOOK RTP",
    }
    result = envelope(out)
    meta = result["meta"]
    assert meta["source"] == "live"
    assert meta["backend"] == "cdp"
    assert meta["simulated"] is False
    assert meta["complete"] is True
    assert meta["stale"] is False
    assert meta["snapshot_id"] is None
    assert meta["dataset_id"] is None
    assert meta["matched_total"] == 1
    assert not cost_setup.cache_path.exists()


def test_live_rejects_multi_value_filter(run_cli, envelope, cost_setup):
    code, out, _ = listing(
        run_cli,
        "--live",
        "--trans-currency-code",
        "USD",
        "--trans-currency-code",
        "EUR",
    )
    assert code == 2
    assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert cost_setup.state.business_requests == []


def test_live_never_falls_back_to_cache(
    run_cli, envelope, cost_setup, sample_cost_rows
):
    refreshed(run_cli, cost_setup, sample_cost_rows)
    cost_setup.state.business_script.append(cost_page([], success=False))
    code, out, _ = listing(run_cli, "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    code, out, _ = listing(run_cli)
    assert code == 0
    assert envelope(out)["meta"]["matched_total"] == 8


def test_live_incomplete_marked_and_require_complete(
    run_cli, envelope, cost_setup, no_sleep
):
    rows = [cost_row(n) for n in range(1, 9)]
    duplicated = rows + [rows[0]]
    cost_setup.state.business_script.extend(
        [
            cost_page(duplicated, page_size=5000, total_count=9),
            cost_page(duplicated, page_size=10000, total_count=9),
        ]
    )
    code, out, _ = listing(run_cli, "--live")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["complete"] is False
    assert result["meta"]["matched_total"] == 8
    assert len(result["data"]) == 8
    assert [r["pageSize"] for r in cost_setup.state.business_requests] == [
        5000,
        10000,
    ]

    cost_setup.state.business_requests.clear()
    cost_setup.state.business_script.extend(
        [
            cost_page(duplicated, page_size=5000, total_count=9),
            cost_page(duplicated, page_size=10000, total_count=9),
        ]
    )
    code, out, _ = listing(run_cli, "--live", "--require-complete")
    assert code == 1
    assert envelope(out)["error"]["code"] == "INCOMPLETE_RESULT"


def test_multi_page_collection_is_zero_based(run_cli, envelope, cost_setup):
    rows = [cost_row(n) for n in range(1, 6001)]
    cost_setup.state.business_handler = paging_handler(
        {0: rows[:5000], 1: rows[5000:]}, 5000, 6000
    )
    code, out, err = refresh(run_cli)
    assert code == 0
    assert "page 1/2" in err and "page 2/2" in err
    assert envelope(out)["data"]["row_count"] == 6000
    assert [r["pageNo"] for r in cost_setup.state.business_requests] == [0, 1]
    assert [r["pageSize"] for r in cost_setup.state.business_requests] == [5000, 5000]
    cost_setup.state.business_handler = None
    code, out, _ = listing(run_cli)
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 6000
    assert result["meta"]["returned_count"] == 100
    assert result["meta"]["has_more"] is True
    assert [int(row["itemId"]) for row in result["data"]] == list(range(1, 101))


def test_business_failure_keeps_old_cache(
    run_cli, envelope, cost_setup, sample_cost_rows
):
    refreshed(run_cli, cost_setup, sample_cost_rows)
    cost_setup.state.business_script.append(cost_page([], success=False))
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    code, out, _ = listing(run_cli)
    assert code == 0
    assert envelope(out)["meta"]["matched_total"] == 8


def test_schema_error_keeps_old_cache(run_cli, envelope, cost_setup, sample_cost_rows):
    refreshed(run_cli, cost_setup, sample_cost_rows)
    cost_setup.state.business_script.append(
        {"status": 200, "body": {"success": True, "pageNo": 0}}
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "INVALID_RESPONSE"
    code, out, _ = listing(run_cli)
    assert envelope(out)["meta"]["matched_total"] == 8


def test_total_change_keeps_old_cache(run_cli, envelope, cost_setup, sample_cost_rows):
    refreshed(run_cli, cost_setup, sample_cost_rows)
    rows = [cost_row(n) for n in range(1, 6001)]

    def handler(payload: dict, call_index: int):
        page_no = payload["pageNo"]
        total = 6000 if page_no == 0 else 6001
        return cost_page(
            rows[:5000] if page_no == 0 else rows[5000:],
            page_no=page_no,
            page_size=5000,
            total_count=total,
        )

    cost_setup.state.business_handler = handler
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "INVALID_RESPONSE"
    code, out, _ = listing(run_cli)
    assert envelope(out)["meta"]["matched_total"] == 8


def test_first_failure_keeps_no_cache(run_cli, envelope, cost_setup):
    cost_setup.state.business_script.append(cost_page([], success=False))
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert not cost_setup.cache_path.exists()
    code, out, _ = listing(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_MISS"


def test_conflict_fails_without_rebuild(run_cli, envelope, cost_setup, no_sleep):
    rows = [cost_row(n) for n in range(1, 9)]
    conflicted = rows + [cost_row(1, status="OFFLINE")]
    cost_setup.state.business_script.append(cost_page(conflicted, total_count=9))
    code, out, _ = refresh(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert "conflict" in result["error"]["message"]
    assert len(cost_setup.state.business_requests) == 1


def test_no_progress_fails(run_cli, envelope, cost_setup, no_sleep):
    rows = [cost_row(n) for n in range(1, 5001)]
    cost_setup.state.business_handler = paging_handler(
        {0: rows, 1: [], 2: rows}, 5000, 15000
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert "no progress" in result["error"]["message"]


def test_pagination_echo_mismatch_fails(
    run_cli, envelope, cost_setup, sample_cost_rows
):
    cost_setup.state.business_script.append(
        cost_page(sample_cost_rows, page_no=1, page_size=5000)
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert "echo" in result["error"]["message"]


def test_rebuild_10000_once_on_coverage_gap(
    run_cli, envelope, cost_setup, sample_cost_rows, no_sleep
):
    duplicated = sample_cost_rows + [sample_cost_rows[0]]
    cost_setup.state.business_script.extend(
        [
            cost_page(duplicated, page_size=5000, total_count=9),
            cost_page(sample_cost_rows, page_size=10000, total_count=8),
        ]
    )
    code, out, _ = refresh(run_cli)
    assert code == 0
    assert envelope(out)["data"]["row_count"] == 8
    payloads = cost_setup.state.business_requests
    assert [p["pageSize"] for p in payloads] == [5000, 10000]
    assert [p["pageNo"] for p in payloads] == [0, 0]
    code, out, _ = listing(run_cli)
    assert envelope(out)["meta"]["matched_total"] == 8


def test_rebuild_on_empty_last_page_coverage_gap(
    run_cli, envelope, cost_setup, no_sleep
):
    rows = [cost_row(n) for n in range(1, 6001)]

    def handler(payload: dict, call_index: int):
        page_no = payload["pageNo"]
        page_size = payload["pageSize"]
        if page_size == 5000:
            body_rows = rows[:5000] if page_no == 0 else []
        else:
            body_rows = rows
        return cost_page(
            body_rows, page_no=page_no, page_size=page_size, total_count=6000
        )

    cost_setup.state.business_handler = handler
    code, out, _ = refresh(run_cli)
    assert code == 0
    assert envelope(out)["data"]["row_count"] == 6000
    payloads = cost_setup.state.business_requests
    assert [p["pageSize"] for p in payloads] == [5000, 5000, 10000]


def test_rebuild_happens_only_once(
    run_cli, envelope, cost_setup, sample_cost_rows, no_sleep
):
    refreshed(run_cli, cost_setup, sample_cost_rows)
    duplicated = sample_cost_rows + [sample_cost_rows[0]]
    cost_setup.state.business_script.extend(
        [
            cost_page(duplicated, page_size=5000, total_count=9),
            cost_page(duplicated, page_size=10000, total_count=9),
        ]
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert "incomplete" in result["error"]["message"]
    assert [p["pageSize"] for p in cost_setup.state.business_requests[1:]] == [
        5000,
        10000,
    ]
    code, out, _ = listing(run_cli)
    assert envelope(out)["meta"]["matched_total"] == 8


def test_transient_statuses_retried_with_bounded_waits(
    run_cli, cost_setup, sample_cost_rows, no_sleep
):
    cost_setup.state.business_script.extend(
        [
            {"status": 429, "body": ""},
            {"status": 503, "body": ""},
            cost_page(sample_cost_rows),
        ]
    )
    code, _, _ = refresh(run_cli)
    assert code == 0
    assert no_sleep == [1.0, 2.0]
    assert len(cost_setup.state.business_requests) == 3


def test_retry_after_preferred_within_budget(
    run_cli, cost_setup, sample_cost_rows, no_sleep
):
    cost_setup.state.business_script.extend(
        [
            {"status": 429, "body": "", "retry_after": "3"},
            cost_page(sample_cost_rows),
        ]
    )
    code, _, _ = refresh(run_cli)
    assert code == 0
    assert no_sleep == [3.0]


def test_retries_exhausted_fail(run_cli, envelope, cost_setup, no_sleep):
    cost_setup.state.business_script.extend([{"status": 503, "body": ""}] * 3)
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert len(cost_setup.state.business_requests) == 3
    assert not cost_setup.cache_path.exists()


def test_network_failures_retried_then_timeout(run_cli, envelope, cost_setup, no_sleep):
    cost_setup.state.business_script.extend(
        [{"error": "AbortError: The operation was aborted"}] * 3
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["error"]["code"] == "TIMEOUT"
    assert result["error"]["retryable"] is True
    assert len(cost_setup.state.business_requests) == 3


def test_unexpected_status_not_retried(run_cli, envelope, cost_setup, no_sleep):
    cost_setup.state.business_script.append({"status": 500, "body": ""})
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert len(cost_setup.state.business_requests) == 1
    assert no_sleep == []


def test_http_401_maps_to_auth_required(run_cli, envelope, cost_setup, no_sleep):
    cost_setup.state.business_script.append({"status": 401, "body": ""})
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"
    assert len(cost_setup.state.business_requests) == 1


def test_refresh_budget_exhaustion(
    run_cli, envelope, cost_setup, sample_cost_rows, monkeypatch
):
    monkeypatch.setattr(collect_mod, "REFRESH_BUDGET_SECONDS", 0.0)
    script_full(cost_setup.state, sample_cost_rows)
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "TIMEOUT"
    assert cost_setup.state.business_requests == []
    assert not cost_setup.cache_path.exists()


def test_page_budget_exceeded(run_cli, envelope, cost_setup, monkeypatch):
    monkeypatch.setattr(collect_mod, "MAX_PAGES", 1)
    rows = [cost_row(n) for n in range(1, 6001)]
    cost_setup.state.business_handler = paging_handler(
        {0: rows[:5000], 1: rows[5000:]}, 5000, 6000
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "TIMEOUT"
    assert len(cost_setup.state.business_requests) == 1


def test_auth_required_from_probe(run_cli, envelope, cost_setup, sample_cost_rows):
    cost_setup.state.href = SSO_URL
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"
    assert cost_setup.state.business_requests == []
    code, out, _ = listing(run_cli, "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"


def test_browser_unavailable(run_cli, envelope, cost_setup):
    cost_setup.state.running = False
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BROWSER_UNAVAILABLE"


def test_browser_busy_maps_to_locked(run_cli, envelope, cost_setup):
    lock = acquire_browser_control(cost_setup.profile, shared=False)
    try:
        code, out, _ = refresh(run_cli)
        assert code == 1
        result = envelope(out)
        assert result["error"]["code"] == "LOCKED"
        assert result["error"]["retryable"] is True
    finally:
        lock.release()


def test_id_ordering_numeric_ascending(run_cli, envelope, cost_setup):
    rows = [cost_row(100), cost_row(9), cost_row(10), cost_row(2)]
    refreshed(run_cli, cost_setup, rows)
    code, out, _ = listing(run_cli, "--all")
    assert code == 0
    assert [row["itemId"] for row in envelope(out)["data"]] == [
        "2",
        "9",
        "10",
        "100",
    ]


def test_display_params(run_cli, envelope, cost_setup, sample_cost_rows):
    refreshed(run_cli, cost_setup, sample_cost_rows)

    code, out, _ = listing(run_cli, "--limit", "3", "--offset", "2")
    assert code == 0
    result = envelope(out)
    assert [row["itemId"] for row in result["data"]] == ["103", "104", "105"]
    assert result["meta"]["matched_total"] == 8
    assert result["meta"]["has_more"] is True

    code, out, _ = listing(run_cli, "--all", "--fields", "itemId,status")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["returned_count"] == 8
    assert all(set(row) == {"itemId", "status"} for row in result["data"])

    for extra in (
        ["--all", "--limit", "5"],
        ["--limit", "0"],
        ["--offset", "-1"],
        ["--fields", " , "],
    ):
        code, out, _ = listing(run_cli, *extra)
        assert code == 2, extra
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_table_format_marks_quality(run_cli, cost_setup, sample_cost_rows):
    refreshed(run_cli, cost_setup, sample_cost_rows)
    code, out, _ = listing(run_cli, "--format", "table", "--limit", "2")
    assert code == 0
    assert "source: cache" in out
    assert "backend: cdp" in out
    assert "simulated: false" in out
    assert "complete: true" in out
    assert "stale: false" in out
    assert "itemId" in out


def test_stale_and_require_fresh(run_cli, envelope, cost_setup, sample_cost_rows):
    cost_setup.write_config(ttl_hours=0)
    refreshed(run_cli, cost_setup, sample_cost_rows)
    code, out, _ = listing(run_cli)
    assert code == 0
    assert envelope(out)["meta"]["stale"] is True
    code, out, _ = listing(run_cli, "--require-fresh")
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_STALE"
    code, out, _ = listing(run_cli, "--require-complete")
    assert code == 0


def test_cache_miss_is_explicit(run_cli, envelope, cost_setup):
    code, out, _ = listing(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["data"] is None
    assert result["error"]["code"] == "CACHE_MISS"
    assert "refresh payment cost" in result["error"]["message"]


def test_decimal_precision_and_unknown_fields_preserved(
    run_cli, envelope, cost_setup, sample_cost_rows
):
    refreshed(run_cli, cost_setup, sample_cost_rows)
    code, out, _ = listing(run_cli, "--limit", "1")
    assert code == 0
    assert PRECISE_AMOUNT in out
    row = envelope(out)["data"][0]
    ratio = row["costRateConfigList"][0]["costRateVO"]["feeRateRatioValue"]
    assert str(ratio["amount"]) == PRECISE_AMOUNT
    assert row["futureUnknownField"] == {"keep": ["as-is", 1]}
    assert row["costCurrencyCode"] == "USD"
    assert row["transCurrencyCode"] == "USD"


def test_empty_scope_publishes_empty_snapshot(run_cli, envelope, cost_setup):
    script_full(cost_setup.state, [])
    code, out, _ = refresh(run_cli)
    assert code == 0
    assert envelope(out)["data"]["row_count"] == 0
    code, out, _ = listing(run_cli)
    assert code == 0
    result = envelope(out)
    assert result["data"] == []
    assert result["meta"]["matched_total"] == 0
    assert result["meta"]["complete"] is True


def test_refresh_replaces_without_merging_old_rows(
    run_cli, envelope, cost_setup, sample_cost_rows
):
    refreshed(run_cli, cost_setup, sample_cost_rows)
    script_full(cost_setup.state, [cost_row(201), cost_row(202)])
    code, _, _ = refresh(run_cli)
    assert code == 0
    code, out, _ = listing(run_cli, "--all")
    result = envelope(out)
    assert result["meta"]["matched_total"] == 2
    assert [row["itemId"] for row in result["data"]] == ["201", "202"]


def test_credentials_never_leave_the_browser(
    run_cli, envelope, cost_setup, sample_cost_rows
):
    refreshed(run_cli, cost_setup, sample_cost_rows)
    code, out, err = listing(run_cli, "--all")
    assert code == 0
    secret = "FAKE-CTOKEN-SECRET"
    assert secret not in out and secret not in err
    assert "ctoken" not in out and "ctoken" not in err
    cache_bytes = cost_setup.cache_path.read_bytes()
    assert secret.encode() not in cache_bytes
    assert b"ctoken" not in cache_bytes
    for transport in cost_setup.state.transports:
        for expression in transport.expressions:
            assert secret not in expression
    allowed = {
        "costTypeCode",
        "legalEntityCode",
        "financialInstCode",
        "bankAccount",
        "transCurrencyCode",
        "chargeBearer",
        "clearingNetworkName",
        "pageNo",
        "pageSize",
    }
    for payload in cost_setup.state.business_requests:
        assert set(payload) <= allowed


def test_machine_output_envelope(run_cli, envelope, cost_setup, sample_cost_rows):
    refreshed(run_cli, cost_setup, sample_cost_rows)
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
    cost_setup.write_config(ttl_hours=0)
    code, out, err = listing(run_cli, "--require-fresh", "--format", "table")
    assert code == 1
    assert out == ""
    assert "CACHE_STALE" in err


def test_concurrent_reads_see_complete_snapshots(cost_setup):
    store = Cache(cost_setup.cache_path)

    def snapshot(ns: str, rows: int, marker: str) -> SnapshotMeta:
        return SnapshotMeta(
            namespace=ns,
            capability="payment.cost.list",
            scope=COST_TYPE,
            source_kind="cdp",
            snapshot_id=marker,
            dataset_id=None,
            simulated=False,
            backend_complete=True,
            dataset_complete=True,
            fetched_at="2026-09-11T00:00:00+00:00",
            loaded_at="2026-09-11T00:00:00+00:00",
            source_observed_from=None,
            source_observed_to=None,
            row_count=rows,
        )

    ns = "payment.cost.list:FUND_OUT_CHANNEL_TRANS_FEE:cdp"
    failures: list[str] = []
    writer_errors: list[BaseException] = []
    stop = threading.Event()

    def writer() -> None:
        try:
            for round_no in range(40):
                rows = 3 if round_no % 2 == 0 else 5
                keyed = [
                    (index, canonical({"seq": index, "round": round_no}))
                    for index in range(1, rows + 1)
                ]
                store.publish(snapshot(ns, rows, f"snap-{round_no}"), keyed)
        except BaseException as error:
            writer_errors.append(error)
        finally:
            stop.set()

    def reader() -> None:
        while not stop.is_set():
            meta, bodies = store.read(ns)
            if meta is None:
                continue
            if len(bodies) != meta.row_count:
                failures.append(f"row_count {meta.row_count} but {len(bodies)} records")
                return
            if [seq for seq, _ in bodies] != list(range(1, meta.row_count + 1)):
                failures.append("seqids are not continuous for one snapshot")
                return
            rounds = {parse(body)["round"] for _, body in bodies}
            if len(rounds) != 1:
                failures.append("records mix two published snapshots")
                return

    thread = threading.Thread(target=writer)
    thread.start()
    reader()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert writer_errors == []
    assert failures == []
