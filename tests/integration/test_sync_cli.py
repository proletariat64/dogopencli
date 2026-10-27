"""Durable synchronization through installed public commands and fake CDP."""

import json

import pytest
from test_leaf_pilots_cli import pilots as pilots


def test_status_missing_store_is_read_only(run_cli, tmp_path):
    before = set(tmp_path.rglob("*"))
    code, output, _ = run_cli(["sync", "status"])
    assert code == 0, output
    assert json.loads(output)["data"]["targets"] == []
    assert set(tmp_path.rglob("*")) == before


def test_settings_sync_replaces_and_preserves_after_incomplete(
    run_cli, pilots, tmp_path
):
    import duckdb
    from test_leaf_pilots_cli import native_page

    pilots.business_script.append(native_page("payment", [{"id": "first"}]))
    code, output, _ = run_cli(["payment", "sync", "sla.baselines"])
    assert code == 0, output
    with duckdb.connect(str(tmp_path / "duckdog.duckdb"), read_only=True) as db:
        assert db.execute("SELECT _record FROM payment_sla_baselines").fetchall() == [
            ('{"id":"first"}',)
        ]
    pilots.business_script.append(native_page("payment", []))
    code, output, _ = run_cli(["sync"])
    assert code == 0, output
    with duckdb.connect(str(tmp_path / "duckdog.duckdb"), read_only=True) as db:
        assert db.execute("SELECT count(*) FROM payment_sla_baselines").fetchone() == (
            0,
        )


@pytest.fixture
def cash_sync(run_cli, tmp_path, monkeypatch):
    from pathlib import Path

    from fake_cdp import FakeBrowser

    from dogopencli.browser import cdp
    from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL

    config = tmp_path / "config.toml"
    config.write_text(
        f'[auth]\nprofile="{tmp_path / "chrome"}"\ncdp_url="http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)
    try:
        source = (
            Path(__file__).resolve().parents[2]
            / "leaf_packages/liquidity/cash.balances"
        )
        assert run_cli(["plugins", "install", str(source)])[0] == 0

        def handler(body, _):
            if "bankAccountQueryVO" in body:
                query = json.loads(body["bankAccountQueryVO"])
                rows = (
                    []
                    if query["rowStart"]
                    else [
                        {
                            "aliasName": "ACCOUNT",
                            "instId": "ALIPAYGM",
                            "currency": "USD",
                            "bankId": "BANK",
                        }
                    ]
                )
                return {
                    "status": 200,
                    "body": {
                        "resultFlag": True,
                        "count": len(rows),
                        "result": {"success": True, "bankAccountPropertyVOList": rows},
                    },
                }
            return {
                "status": 200,
                "body": {
                    "success": True,
                    "data": [
                        {
                            "id": "native",
                            "data": "ACCOUNT",
                            "statisticalDate": body["queryStartDate"][:4]
                            + "-"
                            + body["queryStartDate"][4:6]
                            + "-"
                            + body["queryStartDate"][6:],
                            "balance": "3.4",
                        }
                    ],
                },
            }

        browser.business_handler = handler
        yield browser
    finally:
        cdp.set_transport_factory(None)


def test_daily_history_chunk_resume_and_explicit_reconcile(
    run_cli, tmp_path, monkeypatch
):
    from pathlib import Path

    from fake_cdp import FakeBrowser

    from dogopencli.browser import cdp
    from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL

    config = tmp_path / "config.toml"
    config.write_text(
        f'[auth]\nprofile="{tmp_path / "chrome"}"\ncdp_url="http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)
    try:
        source = (
            Path(__file__).resolve().parents[2]
            / "leaf_packages/liquidity/cash.balances"
        )
        assert run_cli(["plugins", "install", str(source)])[0] == 0

        def handler(body, _):
            if "bankAccountQueryVO" in body:
                query = json.loads(body["bankAccountQueryVO"])
                rows = (
                    []
                    if query["rowStart"]
                    else [
                        {
                            "aliasName": "ACCOUNT",
                            "instId": "ALIPAYGM",
                            "currency": "USD",
                            "bankId": "BANK",
                        }
                    ]
                )
                return {
                    "status": 200,
                    "body": {
                        "resultFlag": True,
                        "count": len(rows),
                        "result": {"success": True, "bankAccountPropertyVOList": rows},
                    },
                }
            return {
                "status": 200,
                "body": {
                    "success": True,
                    "data": [
                        {
                            "id": "native",
                            "data": "ACCOUNT",
                            "statisticalDate": body["queryStartDate"][:4]
                            + "-"
                            + body["queryStartDate"][4:6]
                            + "-"
                            + body["queryStartDate"][6:],
                            "balance": "3.4",
                        }
                    ],
                },
            }

        browser.business_handler = handler
        args = [
            "liquidity",
            "sync",
            "cash.balances",
            "--from-date",
            "2026-10-01",
            "--to-date",
            "2026-10-03",
        ]
        code, output, _ = run_cli(args)
        assert code == 0, output
        requests = [r for r in browser.business_requests if "balanceType" in r]
        assert [r["queryStartDate"] for r in requests] == [
            "20261001",
            "20261002",
            "20261003",
        ]
        count = len(browser.business_requests)
        code, output, _ = run_cli(["sync"])
        assert code == 0, output
        assert len(browser.business_requests) == count
        assert run_cli(args)[0] == 0
        assert len(browser.business_requests) > count
    finally:
        cdp.set_transport_factory(None)


def test_all_enrolls_settings_and_reports_unsupported_without_hiding_success(
    run_cli, pilots
):
    from test_leaf_pilots_cli import native_page

    assert run_cli(["plugins", "uninstall", "liquidity.reference.entities"])[0] == 0
    pilots.business_handler = lambda body, _: (
        native_page(
            "collection", [{"itemId": "C", "itemType": "FUND_IN_CHANNEL_TRANS_FEE"}]
        )
        if "costTypeCode" in body
        else native_page("payment", [{"id": "P"}])
    )
    code, output, _ = run_cli(["sync", "--all"])
    assert code == 1, output  # FX requires an explicit native time scope.
    rows = json.loads(output)["data"]["targets"]
    assert {r["leaf"] for r in rows if r["state"] == "complete"} == {
        "collection.cost",
        "payment.sla.baselines",
    }, output
    assert any(r["leaf"] == "fx.trade" and r["state"] == "failed" for r in rows)
    code, output, _ = run_cli(["sync", "status"])
    assert code == 0, output
    assert len(json.loads(output)["data"]["targets"]) == 3
    assert any(t["state"] == "blocked" for t in json.loads(output)["data"]["targets"])
    assert run_cli(["sync"])[0] == 1


def test_all_bootstraps_any_from_owned_entities_without_external_selector(
    run_cli, pilots
):
    from pathlib import Path

    from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL

    pilots.href = LIQUIDITY_STARTUP_URL
    for name in ("collection.cost", "payment.sla.baselines", "fx.trade"):
        assert run_cli(["plugins", "uninstall", name])[0] == 0
    source = (
        Path(__file__).resolve().parents[2] / "leaf_packages/liquidity/cash.balances"
    )
    assert run_cli(["plugins", "install", str(source)])[0] == 0

    def handler(body, _):
        if "entityMaintQueryVO" in body:
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": 1,
                    "result": {"entityMaintVOList": [{"instId": "ALIPAYGM"}]},
                },
            }
        if "bankAccountQueryVO" in body:
            query = json.loads(body["bankAccountQueryVO"])
            rows = (
                []
                if query["rowStart"]
                else [
                    {
                        "aliasName": "ACCOUNT",
                        "instId": "ALIPAYGM",
                        "currency": "USD",
                        "bankId": "BANK",
                    }
                ]
            )
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": len(rows),
                    "result": {"success": True, "bankAccountPropertyVOList": rows},
                },
            }
        if "balanceType" in body:
            return {"status": 200, "body": {"success": True, "data": []}}
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": {
                    "data": [
                        {
                            "balId": "B",
                            "entity": "ALIPAYGM",
                            "aliasName": "ACCOUNT",
                            "currency": "USD",
                            "curBalance": 1,
                        }
                    ],
                    "totalCount": 1,
                },
            },
        }

    pilots.business_handler = handler
    code, output, _ = run_cli(["sync", "--all"])
    assert code == 0, output
    results = json.loads(output)["data"]["targets"]
    assert {(row["leaf"], row["variant"]) for row in results} == {
        ("liquidity.reference.entities", "default"),
        ("liquidity.cash.balances", "daily"),
        ("liquidity.cash.balances", "latest"),
    }


def test_follow_extends_and_rechecks_only_recent_history(
    run_cli, cash_sync, monkeypatch
):
    from datetime import datetime, timezone

    from dogopencli import sync

    monkeypatch.setattr(
        sync, "now", lambda: datetime(2026, 10, 3, 8, tzinfo=timezone.utc)
    )
    args = [
        "liquidity",
        "sync",
        "cash.balances",
        "--from-date",
        "2026-10-01",
        "--to-date",
        "2026-10-02",
        "--follow",
    ]
    code, output, _ = run_cli(args)
    assert code == 0, output
    cash_sync.business_requests.clear()
    code, output, _ = run_cli(["sync"])
    assert code == 0, output
    assert [
        r["queryStartDate"] for r in cash_sync.business_requests if "balanceType" in r
    ] == ["20261002", "20261003"]
    cash_sync.business_requests.clear()
    monkeypatch.setattr(
        sync, "now", lambda: datetime(2026, 10, 4, 8, tzinfo=timezone.utc)
    )
    assert run_cli(["sync"])[0] == 0
    assert [
        r["queryStartDate"] for r in cash_sync.business_requests if "balanceType" in r
    ] == ["20261003", "20261004"]


def test_interior_failure_stays_visible_and_plain_sync_repairs_it(run_cli, cash_sync):
    handler = cash_sync.business_handler

    def failed(body, transport):
        if body.get("queryStartDate") == "20261002":
            return {"status": 200, "body": {"success": False}}
        return handler(body, transport)

    cash_sync.business_handler = failed
    code, output, _ = run_cli(
        [
            "liquidity",
            "sync",
            "cash.balances",
            "--from-date",
            "2026-10-01",
            "--to-date",
            "2026-10-03",
        ]
    )
    assert code == 1, output
    code, output, _ = run_cli(["sync", "status"])
    assert code == 0, output
    target = json.loads(output)["data"]["targets"][0]
    assert target["gaps"] == [{"from_date": "2026-10-02", "to_date": "2026-10-02"}]
    assert target["row_count"] == 2
    cash_sync.business_handler = handler
    cash_sync.business_requests.clear()
    code, output, _ = run_cli(["sync"])
    assert code == 0, output
    assert [
        r["queryStartDate"] for r in cash_sync.business_requests if "balanceType" in r
    ] == ["20261002"]
    status = json.loads(run_cli(["sync", "status"])[1])["data"]["targets"][0]
    assert status["gaps"] == [] and status["row_count"] == 3


def test_partial_settings_failure_retains_last_success(run_cli, pilots, tmp_path):
    from test_leaf_pilots_cli import native_page

    pilots.business_script.append(
        native_page(
            "collection", [{"itemId": "old", "itemType": "FUND_IN_CHANNEL_TRANS_FEE"}]
        )
    )
    assert run_cli(["collection", "sync", "cost"])[0] == 0
    partial = native_page(
        "collection", [{"itemId": "new", "itemType": "FUND_IN_CHANNEL_TRANS_FEE"}]
    )
    partial["body"]["totalCount"] = 1001
    pilots.business_script.append(partial)
    assert run_cli(["sync"])[0] == 1
    result = json.loads(run_cli(["sync", "status"])[1])["data"]["targets"][0]
    assert result["row_count"] == 1
    assert result["last_attempt"]["state"] == "failed"
    assert result["last_success"]["state"] == "complete"


def test_unknown_clock_rejects_follow_before_acquisition(run_cli, pilots):
    code, output, _ = run_cli(
        [
            "fx",
            "sync",
            "trade",
            "--transact-from",
            "2026-10-01",
            "--transact-to",
            "2026-10-02",
            "--follow",
        ]
    )
    assert code == 2, output
    assert pilots.business_requests == []


def test_uninstalled_saved_target_is_inactive_not_deleted(run_cli, pilots):
    from test_leaf_pilots_cli import native_page

    pilots.business_script.append(native_page("payment", [{"id": "saved"}]))
    assert run_cli(["payment", "sync", "sla.baselines"])[0] == 0
    assert run_cli(["plugins", "uninstall", "payment.sla.baselines"])[0] == 0
    target = json.loads(run_cli(["sync", "status"])[1])["data"]["targets"][0]
    assert target["state"] == "inactive" and target["row_count"] == 1
    assert run_cli(["sync"])[0] == 1


def test_local_only_settings_filter_rejected_before_query(run_cli, pilots):
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "leaf_packages/liquidity/reference.banks"
    )
    assert run_cli(["plugins", "install", str(source)])[0] == 0
    code, output, _ = run_cli(
        ["liquidity", "sync", "reference.banks", "--country", "US"]
    )
    assert code == 2, output
    assert "display-only" in output
    assert pilots.business_requests == []


def test_native_settings_filter_remains_valid_acquisition_scope(run_cli, pilots):
    from test_leaf_pilots_cli import native_page

    pilots.business_script.append(native_page("payment", [{"id": "wide"}]))
    assert run_cli(["payment", "sync", "sla.baselines"])[0] == 0
    pilots.business_script.append(
        native_page("payment", [{"id": "scoped", "bizCategory": "NATIVE"}])
    )
    code, output, _ = run_cli(
        ["payment", "sync", "sla.baselines", "--biz-category", "NATIVE"]
    )
    assert code == 0, output
    assert pilots.business_requests[-1]["bizCategory"] == "NATIVE"
    targets = json.loads(run_cli(["sync", "status"])[1])["data"]["targets"]
    assert len(targets) == 2 and [t["row_count"] for t in targets] == [1, 1]


def test_native_default_and_explicit_default_share_target(run_cli, cash_sync):
    args = [
        "liquidity",
        "sync",
        "cash.balances",
        "--from-date",
        "2026-10-01",
        "--to-date",
        "2026-10-01",
    ]
    assert run_cli(args)[0] == 0
    assert run_cli([*args, "--entity", "ALIPAYGM"])[0] == 0
    targets = json.loads(run_cli(["sync", "status"])[1])["data"]["targets"]
    assert len(targets) == 1 and targets[0]["row_count"] == 1


def test_native_timestamp_validation_precedes_chunk_normalization(run_cli, pilots):
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "leaf_packages/payment/ptr.orders"
    assert run_cli(["plugins", "install", str(source)])[0] == 0
    code, output, _ = run_cli(
        [
            "payment",
            "sync",
            "ptr.orders",
            "--updated-from",
            "2026-10-01T00:00:00.123+08:00",
            "--updated-to",
            "2026-10-02T00:00:00+08:00",
        ]
    )
    assert code == 2, output
    assert pilots.business_requests == []
