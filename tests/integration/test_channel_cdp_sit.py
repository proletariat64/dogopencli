"""Public-CLI SIT for the Channel CDP query path and source switching (issue #7).

Drives ``dogopencli payment channel list`` and ``dogopencli refresh payment
channel`` through dogopencli.cli.main with ``sources.payment_channel.kind``
set to ``cdp`` and the browser/CDP external boundary replaced by the scripted
stand-ins in ``fake_cdp.py``. Every request passes command registration, the
shared allowlist, the channel plugin parser, the bounded collector and
SQLite. All rows are synthetic and sanitized; no real Chrome, network,
credentials or production data is involved.

The production Channel backend defect is an external dependency: real full
UAT waits for the backend fix (issue #10). This file passing does not claim
production has recovered.
"""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_cdp import PAYMENT_URL, SSO_URL, FakeBrowser

import dogopencli.collect as collect_mod
from dogopencli.browser import cdp
from dogopencli.browser.coordination import acquire_browser_control
from dogopencli.errors import CliError
from dogopencli.plugins import get_capability
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport

CDP_URL = "http://127.0.0.1:9222"
PAGE_SIZE = 100
PRECISE_AMOUNT = "0.1234567890123456789"


def channel_row(ability_id, **overrides):
    row = {
        "abilityId": ability_id,
        "payoutType": "EXTERNAL",
        "status": "ENABLE",
        "financialInstCode": "CITILD",
        "debitAccountName": f"ACCT-{ability_id}",
        "debitAccountNo": str(900000 + ability_id),
        "clearingSystemName": "BOOK RTP",
        "debitCurrency": "USD",
        "creditCurrency": "CNY",
        "debitInstCountryCode": "GB",
        "configVersion": "v1",
        "chargeAmount": {
            "amount": Decimal("0.10"),
            "cent": 10,
            "centFactor": 100,
            "currency": "USD",
            "currencyCode": "USD",
        },
        "futureUnknownField": {"keep": ["as-is", 1]},
    }
    row.update(overrides)
    return row


def channel_page(
    records,
    page_num,
    page_size=PAGE_SIZE,
    total_count=None,
    total_pages=None,
    success=True,
    inner_success=True,
):
    if total_count is None:
        total_count = len(records)
    if total_pages is None:
        total_pages = -(-total_count // page_size)
    document = {"success": success, "status": success, "data": None}
    if success:
        document["resultObj"] = {
            "success": inner_success,
            "code": "IPAY_RS_100000200" if inner_success else "IPAY_RS_510090020",
            "pageNum": page_num,
            "pageSize": page_size,
            "totalCount": total_count,
            "totalPages": total_pages,
            "payoutAbilityVOList": records,
        }
    return {"status": 200, "body": document}


def paging_handler(pages: dict[int, list], total: int):
    def handle(payload: dict, call_index: int):
        page_num = payload["pageNum"]
        page_size = payload["pageSize"]
        rows = pages.get(page_num)
        assert rows is not None, f"unexpected request page {page_num}"
        return channel_page(rows, page_num, page_size, total_count=total)

    return handle


@pytest.fixture
def cdp_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    profile = tmp_path / "chrome-profile"
    cache_path = tmp_path / "cache.sqlite3"
    config_path = tmp_path / "config.toml"

    def write_config(
        kind: str = "cdp",
        dataset: Path | None = None,
        dataset_id: str | None = None,
        ttl_hours: float | int = 72,
    ) -> None:
        lines = [
            "[cache]",
            f'path = "{cache_path}"',
            f"ttl_hours = {ttl_hours}",
            "",
            "[auth]",
            f'profile = "{profile}"',
            f'cdp_url = "{CDP_URL}"',
            "",
            "[sources.payment_channel]",
            f'kind = "{kind}"',
        ]
        if dataset is not None:
            lines.append(f'path = "{dataset}"')
        if dataset_id is not None:
            lines.append(f'dataset_id = "{dataset_id}"')
        lines += ["", "[sources.payment_sla]", 'kind = "cdp"']
        config_path.write_text("\n".join(lines) + "\n")
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


def refresh(run_cli, *extra: str):
    return run_cli(["refresh", "payment", "channel", *extra])


def listing(run_cli, *extra: str):
    return run_cli(["payment", "channel", "list", *extra])


def refreshed(run_cli, cdp_setup, rows) -> None:
    cdp_setup.state.business_handler = paging_handler({1: rows}, len(rows))
    code, _, _ = refresh(run_cli)
    assert code == 0
    cdp_setup.state.business_handler = None


def test_cdp_refresh_multi_page_then_list_offline(run_cli, envelope, cdp_setup):
    rows = [channel_row(n) for n in range(1, 206)]
    cdp_setup.state.business_handler = paging_handler(
        {1: rows[:100], 2: rows[100:200], 3: rows[200:]}, 205
    )
    code, out, err = refresh(run_cli)
    assert code == 0, (out, err)
    assert "page 1/3" in err and "page 3/3" in err
    result = envelope(out)
    assert result["data"]["row_count"] == 205
    meta = result["meta"]
    assert meta["backend"] == "cdp"
    assert meta["simulated"] is False
    assert meta["complete"] is True
    assert meta["dataset_complete"] is True
    assert meta["scope"] == "EXTERNAL"
    assert meta["dataset_id"] is None
    # One-based pages of the default size 100, and no rebuild page size.
    assert cdp_setup.state.business_requests == [
        {"payoutType": "EXTERNAL", "pageNum": n, "pageSize": 100} for n in (1, 2, 3)
    ]
    assert cdp_setup.cache_path.stat().st_mode & 0o777 == 0o600

    cdp_setup.state.business_handler = None
    requests_before = list(cdp_setup.state.business_requests)
    code, out, err = listing(run_cli)
    assert code == 0
    assert err == ""
    result = envelope(out)
    meta = result["meta"]
    assert meta["source"] == "cache"
    assert meta["backend"] == "cdp"
    assert meta["simulated"] is False
    assert meta["complete"] is True
    assert meta["stale"] is False
    assert meta["matched_total"] == 205
    assert meta["returned_count"] == 100
    assert meta["has_more"] is True
    assert [row["seqid"] for row in result["data"]] == list(range(1, 101))
    # Offline read: zero new business requests.
    assert cdp_setup.state.business_requests == requests_before

    code, out, _ = listing(run_cli, "--limit", "5", "--offset", "5")
    assert code == 0
    result = envelope(out)
    assert [row["seqid"] for row in result["data"]] == [6, 7, 8, 9, 10]
    assert result["meta"]["matched_total"] == 205


def test_empty_result_zeroed_page_echo_is_not_an_error(run_cli, envelope, cdp_setup):
    cdp_setup.state.business_script.append(
        channel_page([], 0, total_count=0, total_pages=0)
    )
    code, out, _ = refresh(run_cli)
    assert code == 0
    assert envelope(out)["data"]["published"] is False
    assert not cdp_setup.cache_path.exists()
    code, out, _ = listing(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_MISS"


def test_outer_business_failure(run_cli, envelope, cdp_setup):
    cdp_setup.state.business_script.append(
        {"status": 200, "body": {"success": False, "status": False}}
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert not cdp_setup.cache_path.exists()


def test_inner_business_failure(run_cli, envelope, cdp_setup):
    cdp_setup.state.business_script.append(channel_page([], 1, inner_success=False))
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert not cdp_setup.cache_path.exists()


def test_failed_page_keeps_old_cache(run_cli, envelope, cdp_setup):
    rows = [channel_row(n) for n in (1, 2, 3)]
    refreshed(run_cli, cdp_setup, rows)
    fresh = [channel_row(n) for n in range(1, 102)]
    cdp_setup.state.business_script.extend(
        [
            channel_page(fresh[:100], 1, total_count=101),
            channel_page([], 2, total_count=101, success=False),
        ]
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    code, out, _ = listing(run_cli, "--limit", "0")
    assert code == 0
    assert envelope(out)["meta"]["matched_total"] == 3


def test_cross_page_identical_occurrences_preserved_without_rebuild(
    run_cli, envelope, cdp_setup, no_sleep
):
    rows = [channel_row(n) for n in (1, 2, 3)]
    refreshed(run_cli, cdp_setup, rows)
    fresh = [channel_row(n) for n in range(1, 102)]
    cdp_setup.state.business_handler = paging_handler(
        {1: fresh[:100], 2: [fresh[100], fresh[0]]}, 102
    )
    code, out, err = refresh(run_cli, "--require-complete")
    assert code == 0
    result = envelope(out)
    assert result["error"] is None
    assert result["meta"]["published"] is True
    assert result["meta"]["complete"] is True
    evidence = result["meta"]["acquisition"]
    assert evidence["total_semantics"] == "occurrences"
    assert evidence["arrivals"] == 102
    assert evidence["collected_total"] == 102
    assert evidence["unique_count"] is None
    assert evidence["duplicate_count"] is None
    assert "INCOMPLETE_RESULT" not in err
    # Channel has no 10000 rebuild clause: only the default page size ran.
    assert [p["pageSize"] for p in cdp_setup.state.business_requests[1:]] == [100, 100]
    code, out, err = listing(run_cli, "--limit", "0", "--require-complete")
    assert code == 0
    listed = envelope(out)
    assert listed["meta"]["matched_total"] == 102
    assert sum(record["abilityId"] == 1 for record in listed["data"]) == 2
    assert "INCOMPLETE_RESULT" not in err


def test_no_progress_keeps_old_cache(run_cli, envelope, cdp_setup):
    rows = [channel_row(n) for n in (1, 2, 3)]
    refreshed(run_cli, cdp_setup, rows)
    fresh = [channel_row(n) for n in range(1, 202)]
    cdp_setup.state.business_handler = paging_handler(
        {1: fresh[:100], 2: [], 3: fresh[100:]}, 201
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert "no progress" in result["error"]["message"]
    code, out, _ = listing(run_cli, "--limit", "0")
    assert envelope(out)["meta"]["matched_total"] == 3


def test_total_change_keeps_old_cache(run_cli, envelope, cdp_setup):
    rows = [channel_row(n) for n in (1, 2, 3)]
    refreshed(run_cli, cdp_setup, rows)
    fresh = [channel_row(n) for n in range(1, 102)]

    def handler(payload: dict, call_index: int):
        page_num = payload["pageNum"]
        total = 101 if page_num == 1 else 102
        return channel_page(
            fresh[:100] if page_num == 1 else [fresh[100]],
            page_num,
            payload["pageSize"],
            total_count=total,
        )

    cdp_setup.state.business_handler = handler
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "INVALID_RESPONSE"
    code, out, _ = listing(run_cli, "--limit", "0")
    assert envelope(out)["meta"]["matched_total"] == 3


def test_clamped_last_page_echo_detected(run_cli, envelope, cdp_setup):
    rows = [channel_row(n) for n in (1, 2, 3)]
    refreshed(run_cli, cdp_setup, rows)
    fresh = [channel_row(n) for n in range(1, 102)]

    def handler(payload: dict, call_index: int):
        page_num = payload["pageNum"]
        # Backend clamps an out-of-range page to the previous one and
        # re-returns its rows; the echo must be recognized, not accepted.
        echoed = 1 if page_num == 2 else page_num
        body_rows = fresh[:100] if page_num == 1 else [fresh[100]]
        return channel_page(body_rows, echoed, payload["pageSize"], total_count=101)

    cdp_setup.state.business_handler = handler
    code, out, _ = refresh(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert "echo" in result["error"]["message"]
    code, out, _ = listing(run_cli, "--limit", "0")
    assert envelope(out)["meta"]["matched_total"] == 3


def test_refresh_replaces_without_merging_old_rows(run_cli, envelope, cdp_setup):
    refreshed(run_cli, cdp_setup, [channel_row(n) for n in (1, 2, 3)])
    refreshed(run_cli, cdp_setup, [channel_row(201), channel_row(202)])
    code, out, _ = listing(run_cli, "--limit", "0")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 2
    assert {row["abilityId"] for row in result["data"]} == {201, 202}


@pytest.mark.parametrize("second_version", ["v1", "v2"])
def test_business_key_and_version_do_not_prove_channel_row_identity(
    run_cli,
    envelope,
    cdp_setup,
    second_version,
):
    rows = [
        channel_row(701, configVersion="v1"),
        channel_row(701, configVersion=second_version, status="DISABLE"),
        channel_row(702),
    ]
    cdp_setup.state.business_handler = paging_handler({1: rows}, len(rows))
    code, out, err = listing(run_cli, "--live", "--limit", "0")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["matched_total"] == 3
    assert result["meta"]["complete"] is False
    assert result["error"] is None
    assert result["meta"]["acquisition"]["reasons"] == ["BUSINESS_CONSISTENCY_UNPROVEN"]
    assert result["meta"]["acquisition"]["unique_count"] is None
    assert result["meta"]["acquisition"]["duplicate_count"] is None
    assert "BUSINESS_CONSISTENCY_UNPROVEN" in err
    versions = [(row["abilityId"], row["configVersion"]) for row in result["data"]]
    assert sorted(versions) == [(701, "v1"), (701, second_version), (702, "v1")]
    assert [row["seqid"] for row in result["data"]] == [1, 2, 3]
    code, out, _ = listing(run_cli, "--live", "--require-complete")
    assert code == 1
    assert envelope(out)["data"] is None
    assert envelope(out)["error"]["code"] == "INCOMPLETE_RESULT"


def test_channel_cross_page_occurrences_publish_partial_and_strict_keeps_cache(
    run_cli, envelope, cdp_setup
):
    refreshed(run_cli, cdp_setup, [channel_row(900)])
    original = cdp_setup.cache_path.read_bytes()
    rows = [channel_row(n) for n in range(100)]
    cdp_setup.state.business_handler = paging_handler(
        {1: rows, 2: [channel_row(0, status="DISABLE")]}, 101
    )
    code, out, _ = refresh(run_cli, "--require-complete")
    assert code == 1
    assert envelope(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert envelope(out)["meta"]["published"] is False
    assert cdp_setup.cache_path.read_bytes() == original
    code, out, _ = listing(run_cli, "--limit", "0")
    assert code == 0
    assert [row["abilityId"] for row in envelope(out)["data"]] == [900]
    code, out, _ = listing(run_cli, "--live", "--require-complete")
    assert code == 1
    assert envelope(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert envelope(out)["data"] is None
    assert cdp_setup.cache_path.read_bytes() == original

    code, out, err = refresh(run_cli)
    result = envelope(out)
    assert code == 0
    assert result["meta"]["published"] is True
    assert result["meta"]["complete"] is False
    assert result["data"]["row_count"] == 101
    assert result["error"] is None
    assert "BUSINESS_CONSISTENCY_UNPROVEN" in err
    code, out, err = listing(run_cli, "--limit", "0")
    rows = envelope(out)["data"]
    assert code == 0
    assert len(rows) == 101
    assert len([row for row in rows if row["abilityId"] == 0]) == 2
    assert all(row["abilityId"] != 900 for row in rows)
    assert "INCOMPLETE_RESULT" in err


def test_candidate_seqids_are_content_deterministic(run_cli, envelope, cdp_setup):
    rows = [channel_row(n) for n in range(1, 151)]
    cdp_setup.state.business_handler = paging_handler(
        {1: rows[:100], 2: rows[100:]}, 150
    )
    assert refresh(run_cli)[0] == 0
    first = {
        row["abilityId"]: row["seqid"]
        for row in envelope(listing(run_cli, "--limit", "0")[1])["data"]
    }
    # Same candidate content in a different page order assigns the same ids.
    cdp_setup.state.business_handler = paging_handler({1: rows[50:], 2: rows[:50]}, 150)
    assert refresh(run_cli)[0] == 0
    second = {
        row["abilityId"]: row["seqid"]
        for row in envelope(listing(run_cli, "--limit", "0")[1])["data"]
    }
    assert first == second


def test_all_registered_scenes(run_cli, envelope, cdp_setup):
    for scope in ("EXTERNAL", "LIQUIDITY", "MANUAL", "SETTLEMENT"):
        rows = [channel_row(1, payoutType=scope)]
        cdp_setup.state.business_handler = paging_handler({1: rows}, 1)
        code, _, _ = refresh(run_cli, "--payout-type", scope)
        assert code == 0, scope
        assert cdp_setup.state.business_requests[-1]["payoutType"] == scope
        cdp_setup.state.business_handler = None
        code, out, _ = listing(run_cli, "--payout-type", scope)
        assert code == 0, scope
        result = envelope(out)
        assert result["meta"]["query"]["scope"] == scope
        assert result["meta"]["matched_total"] == 1


def test_unrefreshed_scope_is_cache_miss(run_cli, envelope, cdp_setup):
    refreshed(run_cli, cdp_setup, [channel_row(1)])
    code, out, _ = listing(run_cli, "--payout-type", "LIQUIDITY")
    assert code == 0
    assert envelope(out)["data"] == []
    assert envelope(out)["meta"]["requested_coverage"] is False


def test_unregistered_scope_rejected(run_cli, envelope, cdp_setup):
    code, out, _ = listing(run_cli, "--payout-type", "OTHER")
    assert code == 2
    assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert cdp_setup.state.business_requests == []


def test_live_sends_filters_and_never_writes_cache(run_cli, envelope, cdp_setup):
    rows = [channel_row(1)]
    cdp_setup.state.business_handler = paging_handler({1: rows}, 1)
    code, out, _ = listing(
        run_cli,
        "--live",
        "--status",
        "ENABLE",
        "--debit-currency",
        "USD",
        "--debit-currency",
        "EUR",
        "--debit-account-name",
        "ACCT-1",
    )
    assert code == 0
    payload = cdp_setup.state.business_requests[0]
    assert payload == {
        "payoutType": "EXTERNAL",
        "pageNum": 1,
        "pageSize": 100,
        "status": "ENABLE",
        "debitCurrencyList": ["USD", "EUR"],
        "debitAccountNameList": ["ACCT-1"],
    }
    result = envelope(out)
    meta = result["meta"]
    assert meta["source"] == "live"
    assert meta["backend"] == "cdp"
    assert meta["simulated"] is False
    assert meta["complete"] is True
    assert meta["matched_total"] == 1
    assert result["data"][0]["seqid"] == 1
    assert not cdp_setup.cache_path.exists()


def test_live_rejects_multi_value_scalar(run_cli, envelope, cdp_setup):
    for extra in (
        ["--status", "ENABLE", "--status", "DISABLE"],
        ["--financial-inst-id", "CITILD", "--financial-inst-id", "SCBLSG"],
        ["--debit-inst-country-code", "GB", "--debit-inst-country-code", "SG"],
    ):
        code, out, _ = listing(run_cli, "--live", *extra)
        assert code == 2, extra
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert cdp_setup.state.business_requests == []


def test_live_never_falls_back_to_cache(run_cli, envelope, cdp_setup):
    refreshed(run_cli, cdp_setup, [channel_row(n) for n in (1, 2, 3)])
    cdp_setup.state.business_script.append(
        {"status": 200, "body": {"success": False, "status": False}}
    )
    code, out, _ = listing(run_cli, "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    code, out, _ = listing(run_cli)
    assert code == 0
    assert envelope(out)["meta"]["matched_total"] == 3


def test_live_incomplete_marked_and_require_complete(
    run_cli, envelope, cdp_setup, no_sleep
):
    rows = [channel_row(n) for n in (1, 2)]

    def handler(payload: dict, call_index: int):
        return channel_page(rows + [rows[0]], 1, total_count=4)

    cdp_setup.state.business_handler = handler
    code, out, err = listing(run_cli, "--live")
    assert code == 0
    result = envelope(out)
    assert result["meta"]["complete"] is False
    assert result["meta"]["matched_total"] == 3
    assert result["meta"]["missing_count"] == 1
    assert result["meta"]["acquisition"]["reasons"] == ["COUNT_SHORTFALL"]
    assert result["meta"]["acquisition"]["unique_count"] is None
    assert result["meta"]["acquisition"]["duplicate_count"] is None
    assert "INCOMPLETE_RESULT" in err
    code, out, _ = listing(run_cli, "--live", "--require-complete")
    assert code == 1
    assert envelope(out)["error"]["code"] == "INCOMPLETE_RESULT"


@pytest.mark.parametrize("version_gap", [False, True])
def test_partial_refresh_preserves_evidence_and_strict_refresh_is_atomic(
    run_cli,
    envelope,
    cdp_setup,
    version_gap,
):
    refreshed(run_cli, cdp_setup, [channel_row(900)])
    before = cdp_setup.cache_path.read_bytes()
    if version_gap:
        rows = [channel_row(1), channel_row(1, configVersion="v2", status="DISABLE")]
        total = 2
        reason = "BUSINESS_CONSISTENCY_UNPROVEN"
    else:
        rows = [channel_row(1), channel_row(2)]
        total = 3
        reason = "COUNT_SHORTFALL"
    cdp_setup.state.business_handler = paging_handler({1: rows}, total)
    code, out, _ = refresh(run_cli, "--require-complete")
    assert code == 1
    rejected = envelope(out)
    assert rejected["data"] is None
    assert rejected["error"]["code"] == "INCOMPLETE_RESULT"
    assert rejected["meta"]["published"] is False
    assert rejected["meta"]["acquisition"]["reasons"] == [reason]
    assert cdp_setup.cache_path.read_bytes() == before

    code, out, err = refresh(run_cli)
    assert code == 0, out
    published = envelope(out)
    assert published["error"] is None
    assert published["data"]["published"] is True
    assert published["meta"]["published"] is True
    assert published["meta"]["complete"] is False
    assert published["meta"]["reported_total"] == total
    assert published["meta"]["collected_total"] == 2
    assert published["meta"]["acquisition"]["reasons"] == [reason]
    assert reason in err
    retained = cdp_setup.cache_path.read_bytes()
    requests = len(cdp_setup.state.business_requests)
    cdp_setup.state.running = False
    for flags in (
        (
            "--limit",
            "0",
        ),
        ("--limit", "1", "--fields", "abilityId"),
    ):
        code, out, err = listing(run_cli, *flags)
        assert code == 0, out
        cached = envelope(out)
        assert cached["meta"]["complete"] is False
        assert cached["meta"]["collected_total"] == 2
        assert cached["meta"]["acquisition"]["reasons"] == [reason]
        assert all(record["abilityId"] != 900 for record in cached["data"])
        assert reason in err
    code, out, _ = listing(run_cli, "--require-complete")
    assert code == 1
    assert envelope(out)["data"] is None
    assert envelope(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert cdp_setup.cache_path.read_bytes() == retained
    assert len(cdp_setup.state.business_requests) == requests


def test_source_switching_isolates_caches(
    run_cli, envelope, cdp_setup, dataset_factory, sample_channel_rows
):
    dataset = dataset_factory(sample_channel_rows)
    cdp_setup.write_config(kind="snapshot", dataset=dataset)
    assert refresh(run_cli)[0] == 0
    code, out, _ = listing(run_cli)
    assert code == 0
    result = envelope(out)
    assert result["meta"]["backend"] == "snapshot"
    assert result["meta"]["simulated"] is True
    assert result["meta"]["complete"] is False
    assert result["meta"]["matched_total"] == 8

    # Switching to cdp never reads the snapshot cache.
    cdp_setup.write_config(kind="cdp")
    code, out, _ = listing(run_cli)
    assert code == 0
    assert envelope(out)["meta"]["backend"] == "snapshot"

    refreshed(run_cli, cdp_setup, [channel_row(1), channel_row(2)])
    code, out, _ = listing(run_cli)
    assert code == 0
    result = envelope(out)
    assert result["meta"]["backend"] == "cdp"
    assert result["meta"]["simulated"] is False
    assert result["meta"]["complete"] is True
    assert result["meta"]["matched_total"] == 2

    # Switching back serves the untouched snapshot cache; the cdp refresh
    # did not overwrite the simulated marker or the snapshot rows.
    cdp_setup.write_config(kind="snapshot", dataset=dataset)
    code, out, _ = listing(run_cli)
    assert code == 0
    result = envelope(out)
    assert result["meta"]["backend"] == "cdp"
    assert result["meta"]["simulated"] is False
    assert result["meta"]["complete"] is True
    assert result["meta"]["matched_total"] == 2

    # A configured dataset identity that disagrees with the cache demands a
    # refresh instead of silently serving the cached rows.
    cdp_setup.write_config(kind="snapshot", dataset=dataset, dataset_id="f" * 64)
    code, out, _ = listing(run_cli)
    assert code == 0
    assert envelope(out)["meta"]["backend"] == "cdp"


def test_snapshot_live_and_scope_still_fail(
    run_cli, envelope, cdp_setup, dataset_factory, sample_channel_rows
):
    dataset = dataset_factory(sample_channel_rows)
    cdp_setup.write_config(kind="snapshot", dataset=dataset)
    assert refresh(run_cli)[0] == 0
    code, out, _ = listing(run_cli, "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "LIVE_SOURCE_UNAVAILABLE"
    code, out, _ = listing(run_cli, "--payout-type", "LIQUIDITY")
    assert code == 1
    assert envelope(out)["error"]["code"] == "SOURCE_SCOPE_UNAVAILABLE"


def test_get_serializes_query_params_without_body(run_cli, envelope, cdp_setup):
    """GET branch regression via the SLA detail path (issue #6 leftover)."""
    refreshed(run_cli, cdp_setup, [channel_row(1)])

    def handler(payload: dict, call_index: int):
        if "slaBaselineId" in payload:
            baseline_id = payload["slaBaselineId"]
            return {
                "status": 200,
                "body": {
                    "success": True,
                    "resultData": {"id": baseline_id, "bizCategory": "ACQUIRING"},
                },
            }
        raise AssertionError(f"unexpected request: {payload}")

    cdp_setup.state.business_handler = handler
    code, out, _ = run_cli(
        ["payment", "sla", "baselines", "get", "--id", "55", "--live"]
    )
    assert code == 0
    assert envelope(out)["data"]["id"] == "55"
    get_expression = next(
        expression
        for transport in cdp_setup.state.transports
        for expression in transport.expressions
        if "getFundOutSlaBaselineDetail" in expression
    )
    assert 'method: "GET"' in get_expression
    assert "URLSearchParams(payload)" in get_expression
    assert "body: JSON.stringify" not in get_expression
    # The channel POST path still sends a JSON body.
    post_expression = next(
        expression
        for transport in cdp_setup.state.transports
        for expression in transport.expressions
        if "ability/search.json" in expression
    )
    assert 'method: "POST"' in post_expression
    assert "body: JSON.stringify" in post_expression


def test_allowlist_rejects_unregistered_requests(cdp_setup):
    capability = get_capability("payment.channel.list")
    transport = CdpQueryTransport(
        cdp_setup.state.transport(CDP_URL), capability, page_url=PAYMENT_URL
    )

    def forged(**changes):
        base = {
            "capability": capability.name,
            "method": "POST",
            "host": "ifundboss-api.alipay.com",
            "path": "/payout/api/ability/search.json",
            "body": {"payoutType": "EXTERNAL", "pageNum": 1, "pageSize": 100},
        }
        base.update(changes)
        return QueryRequest(**base)

    for bad in (
        forged(host="evil.example.com"),
        forged(host="iglobalfundcontrol.alipay.com"),
        forged(path="/payout/api/ability/save.json"),
        forged(method="GET"),
        forged(
            body={
                "payoutType": "EXTERNAL",
                "pageNum": 1,
                "pageSize": 100,
                "approve": True,
            }
        ),
        forged(capability="payment.cost.list"),
    ):
        with pytest.raises(CliError) as caught:
            transport.execute(bad)
        assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert cdp_setup.state.business_requests == []


def test_transient_statuses_retried_with_bounded_waits(run_cli, cdp_setup, no_sleep):
    rows = [channel_row(1)]
    cdp_setup.state.business_script.extend(
        [
            {"status": 429, "body": ""},
            {"status": 503, "body": ""},
            channel_page(rows, 1),
        ]
    )
    code, _, _ = refresh(run_cli)
    assert code == 0
    assert no_sleep == [1.0, 2.0]
    assert len(cdp_setup.state.business_requests) == 3


def test_retry_after_preferred_within_budget(run_cli, cdp_setup, no_sleep):
    cdp_setup.state.business_script.extend(
        [
            {"status": 429, "body": "", "retry_after": "3"},
            channel_page([channel_row(1)], 1),
        ]
    )
    code, _, _ = refresh(run_cli)
    assert code == 0
    assert no_sleep == [3.0]


def test_retries_exhausted_fail(run_cli, envelope, cdp_setup, no_sleep):
    cdp_setup.state.business_script.extend([{"status": 503, "body": ""}] * 3)
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert len(cdp_setup.state.business_requests) == 3
    assert not cdp_setup.cache_path.exists()


def test_network_failures_retried_then_timeout(run_cli, envelope, cdp_setup, no_sleep):
    cdp_setup.state.business_script.extend(
        [{"error": "AbortError: The operation was aborted"}] * 3
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    result = envelope(out)
    assert result["error"]["code"] == "TIMEOUT"
    assert result["error"]["retryable"] is True
    assert len(cdp_setup.state.business_requests) == 3


def test_unexpected_status_not_retried(run_cli, envelope, cdp_setup, no_sleep):
    cdp_setup.state.business_script.append({"status": 500, "body": ""})
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert len(cdp_setup.state.business_requests) == 1
    assert no_sleep == []


def test_http_401_maps_to_auth_required(run_cli, envelope, cdp_setup, no_sleep):
    cdp_setup.state.business_script.append({"status": 401, "body": ""})
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"
    assert len(cdp_setup.state.business_requests) == 1
    assert no_sleep == []


def test_refresh_budget_exhaustion(run_cli, envelope, cdp_setup, monkeypatch):
    monkeypatch.setattr(collect_mod, "REFRESH_BUDGET_SECONDS", 0.0)
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "TIMEOUT"
    assert cdp_setup.state.business_requests == []


def test_auth_required_from_probe(run_cli, envelope, cdp_setup):
    cdp_setup.state.href = SSO_URL
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"
    assert cdp_setup.state.business_requests == []
    code, out, _ = listing(run_cli, "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"


def test_browser_unavailable(run_cli, envelope, cdp_setup):
    cdp_setup.state.running = False
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "BROWSER_UNAVAILABLE"


def test_browser_busy_maps_to_locked(run_cli, envelope, cdp_setup):
    lock = acquire_browser_control(cdp_setup.profile, shared=False)
    try:
        code, out, _ = refresh(run_cli)
        assert code == 1
        result = envelope(out)
        assert result["error"]["code"] == "LOCKED"
        assert result["error"]["retryable"] is True
    finally:
        lock.release()


def test_credentials_never_leave_the_browser(run_cli, envelope, cdp_setup):
    refreshed(run_cli, cdp_setup, [channel_row(n) for n in (1, 2, 3)])
    code, out, err = listing(run_cli, "--limit", "0")
    assert code == 0
    secret = "FAKE-CTOKEN-SECRET"
    assert secret not in out and secret not in err
    assert "ctoken" not in out and "ctoken" not in err
    cache_bytes = cdp_setup.cache_path.read_bytes()
    assert secret.encode() not in cache_bytes
    assert b"ctoken" not in cache_bytes
    for transport in cdp_setup.state.transports:
        for expression in transport.expressions:
            assert secret not in expression
    allowed = {
        "payoutType",
        "financialInstId",
        "debitInstCountryCode",
        "status",
        "debitAccountNameList",
        "debitAccountNoList",
        "clearingSystemNameList",
        "debitCurrencyList",
        "creditCurrencyList",
        "pageNum",
        "pageSize",
    }
    for payload in cdp_setup.state.business_requests:
        assert set(payload) <= allowed


def test_decimal_precision_and_unknown_fields_preserved(run_cli, envelope, cdp_setup):
    rows = [
        channel_row(
            1,
            chargeAmount={
                "amount": Decimal(PRECISE_AMOUNT),
                "cent": 10,
                "centFactor": 100,
                "currency": "USD",
                "currencyCode": "USD",
            },
        )
    ]
    refreshed(run_cli, cdp_setup, rows)
    code, out, _ = listing(run_cli, "--limit", "1")
    assert code == 0
    assert PRECISE_AMOUNT in out
    row = envelope(out)["data"][0]
    assert str(row["chargeAmount"]["amount"]) == PRECISE_AMOUNT
    assert row["futureUnknownField"] == {"keep": ["as-is", 1]}


def test_cdp_source_rejects_leftover_dataset_id(run_cli, envelope, cdp_setup):
    cdp_setup.write_config(dataset_id="historical")
    code, out, _ = refresh(run_cli)
    assert code == 2
    assert envelope(out)["error"]["code"] == "CONFIG_ERROR"
    assert cdp_setup.state.business_requests == []


def test_wrong_channel_scope_never_publishes(run_cli, envelope, cdp_setup):
    cdp_setup.state.business_handler = paging_handler({1: [channel_row(1)]}, 1)
    code, out, _ = refresh(run_cli, "--payout-type", "LIQUIDITY")
    assert code == 1
    assert envelope(out)["error"]["code"] == "INVALID_RESPONSE"
    code, out, _ = listing(run_cli, "--payout-type", "LIQUIDITY")
    assert envelope(out)["error"]["code"] == "CACHE_MISS"


def test_live_filters_exclude_backend_nonmatches(run_cli, envelope, cdp_setup):
    rows = [channel_row(1, status="DISABLE"), channel_row(2)]
    cdp_setup.state.business_handler = paging_handler({1: rows}, 2)
    code, out, _ = listing(run_cli, "--live", "--status", "ENABLE")
    assert code == 0
    result = envelope(out)
    assert [row["abilityId"] for row in result["data"]] == [2]
    assert result["meta"]["matched_total"] == 1


def test_mid_query_login_redirect_is_auth_required(run_cli, envelope, cdp_setup):
    cdp_setup.state.business_script.append(
        {
            "status": 200,
            "body": "<html>login</html>",
            "redirected": True,
            "final_url": "https://ipaybuservice.alipay.com/login.htm?secret=PRIVATE",
        }
    )
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"
    assert "PRIVATE" not in out
    assert len(cdp_setup.state.business_requests) == 1


def test_cors_hidden_login_redirect_is_verified(run_cli, envelope, cdp_setup):
    def expired(payload, index):
        cdp_setup.state.href = "https://ipaybuservice.alipay.com/login.htm"
        return {"error": "TypeError: Failed to fetch"}

    cdp_setup.state.business_handler = expired
    code, out, _ = refresh(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"
    assert len(cdp_setup.state.business_requests) == 1


def test_temporary_cache_empty_preservation_limit_zero_and_prune(
    run_cli, envelope, cdp_setup
):
    rows = [channel_row(n) for n in range(1, 6)]
    refreshed(run_cli, cdp_setup, rows)
    code, out, _ = listing(run_cli, "--limit", "0", "--offset", "2")
    assert code == 0
    assert len(envelope(out)["data"]) == 3
    cdp_setup.state.business_script.append(
        channel_page([], 0, total_count=0, total_pages=0)
    )
    code, out, _ = refresh(run_cli)
    assert code == 0
    assert envelope(out)["data"]["published"] is False
    code, out, _ = listing(run_cli)
    assert code == 0
    assert len(envelope(out)["data"]) == 5
    code, out, _ = run_cli(["payment", "channel", "prune"])
    assert code == 0
    assert envelope(out)["data"]["pruned"] is True
    code, out, _ = listing(run_cli)
    assert envelope(out)["error"]["code"] == "CACHE_MISS"
