"""Durable synchronization through installed public commands and fake CDP."""

import json
import shutil
from pathlib import Path

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


def _cash_source(tmp_path):
    """Fake CDP explicitly models range-invariant rows; production stays on HOLD."""
    source = tmp_path / "range-invariant-cash-fixture"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "leaf_packages/liquidity/cash.balances",
        source,
    )
    path = source / "leaf.json"
    manifest = json.loads(path.read_text())
    daily = next(
        profile for profile in manifest["sync"] if profile["variant"] == "daily"
    )
    daily.pop("unsupported_reason", None)
    daily["evidence"] = "Offline fixture guarantees range-invariant daily values."
    path.write_text(json.dumps(manifest))
    return source


@pytest.fixture
def cash_sync(run_cli, tmp_path, monkeypatch):

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
        source = _cash_source(tmp_path)
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
        source = _cash_source(tmp_path)
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
    run_cli, pilots, tmp_path
):

    from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL

    pilots.href = LIQUIDITY_STARTUP_URL
    for name in ("collection.cost", "payment.sla.baselines", "fx.trade"):
        assert run_cli(["plugins", "uninstall", name])[0] == 0
    source = _cash_source(tmp_path)
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

    pilots.business_script.append(
        native_page("payment", [{"id": "scoped", "bizCategory": "NATIVE"}])
    )
    code, output, _ = run_cli(
        ["payment", "sync", "sla.baselines", "--biz-category", "NATIVE"]
    )
    assert code == 0, output
    assert pilots.business_requests[-1]["bizCategory"] == "NATIVE"
    targets = json.loads(run_cli(["sync", "status"])[1])["data"]["targets"]
    assert len(targets) == 1 and targets[0]["row_count"] == 1


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


def test_settings_query_scopes_cannot_mix_one_identity_family(
    run_cli, pilots, tmp_path
):
    import duckdb
    from test_leaf_pilots_cli import native_page

    pilots.business_script.append(
        native_page("payment", [{"id": "shared", "value": "old"}])
    )
    assert run_cli(["payment", "sync", "sla.baselines"])[0] == 0
    pilots.business_script.append(
        native_page("payment", [{"id": "shared", "value": "new"}])
    )
    code, output, _ = run_cli(
        ["payment", "sync", "sla.baselines", "--biz-category", "NATIVE"]
    )
    assert code == 1, output
    assert "one authoritative settings query scope" in output
    with duckdb.connect(str(tmp_path / "duckdog.duckdb"), read_only=True) as db:
        assert db.execute("SELECT _record FROM payment_sla_baselines").fetchall() == [
            ('{"id":"shared","value":"old"}',)
        ]
    targets = json.loads(run_cli(["sync", "status"])[1])["data"]["targets"]
    assert sorted(t["row_count"] for t in targets) == [0, 1]


def test_explicit_native_scope_resolves_blocked_automatic_enrollment(run_cli, pilots):
    from test_leaf_pilots_cli import native_page

    from dogopencli.domain_contracts import FX_STARTUP_URL

    pilots.href = FX_STARTUP_URL

    for leaf in (
        "payment.sla.baselines",
        "collection.cost",
        "liquidity.reference.entities",
    ):
        assert run_cli(["plugins", "uninstall", leaf])[0] == 0
    assert run_cli(["sync", "--all"])[0] == 1
    pilots.business_script.append(native_page("fx", [{"uniqueId": "T"}]))
    code, output, _ = run_cli(
        [
            "fx",
            "sync",
            "trade",
            "--transact-from",
            "2026-10-01",
            "--transact-to",
            "2026-10-02",
        ]
    )
    assert code == 0, output
    status = json.loads(run_cli(["sync", "status"])[1])["data"]
    assert len(status["targets"]) == 1
    assert status["targets"][0]["state"] == "covered_as_observed"
    count = len(pilots.business_requests)
    code, output, _ = run_cli(["sync"])
    assert code == 0, output
    assert len(pilots.business_requests) == count


def test_status_detects_adapter_change_without_import_or_database_write(
    run_cli, pilots, tmp_path
):
    from test_leaf_pilots_cli import native_page

    pilots.business_script.append(native_page("payment", [{"id": "old"}]))
    assert run_cli(["payment", "sync", "sla.baselines"])[0] == 0
    adapter = tmp_path / "plugins/payment/sla.baselines/adapter.py"
    adapter.write_text(
        adapter.read_text() + "\nraise RuntimeError('must not import for status')\n"
    )
    database = tmp_path / "duckdog.duckdb"
    before = (database.stat().st_mtime_ns, database.stat().st_size)
    requests = len(pilots.business_requests)
    code, output, _ = run_cli(["sync", "status"])
    assert code == 0, output
    target = json.loads(output)["data"]["targets"][0]
    assert target["state"] == "blocked"
    assert target["row_count"] == 1
    assert (database.stat().st_mtime_ns, database.stat().st_size) == before
    assert len(pilots.business_requests) == requests


def test_explicit_sync_does_not_silently_change_durable_identity(
    run_cli, cash_sync, tmp_path
):
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
    manifest_path = tmp_path / "plugins/liquidity/cash.balances/leaf.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["sync"][1]["key_fields"].reverse()
    manifest_path.write_text(json.dumps(manifest))
    requests = len(cash_sync.business_requests)
    code, output, _ = run_cli(args)
    assert code == 1, output
    assert "SYNC_CONTRACT_CHANGED" in output
    assert len(cash_sync.business_requests) == requests
    target = json.loads(run_cli(["sync", "status"])[1])["data"]["targets"][0]
    assert target["row_count"] == 1 and target["state"] == "blocked"


def test_empty_selector_does_not_close_runtime_coverage(run_cli, cash_sync):
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
    cash_sync.business_handler = lambda body, _: {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": 0,
            "result": {"success": True, "bankAccountPropertyVOList": []},
        },
    }
    code, output, _ = run_cli(args)
    assert code == 1, output
    target = json.loads(run_cli(["sync", "status"])[1])["data"]["targets"][0]
    assert target["row_count"] == 1
    assert target["last_attempt"]["state"] == "failed"
    assert target["last_success"]["state"] == "complete"


def test_production_cash_daily_sync_remains_on_source_qualification_hold(
    run_cli, pilots
):
    source = (
        Path(__file__).resolve().parents[2] / "leaf_packages/liquidity/cash.balances"
    )
    assert run_cli(["plugins", "install", str(source)])[0] == 0
    code, output, _ = run_cli(
        [
            "liquidity",
            "sync",
            "cash.balances",
            "--from-date",
            "2026-10-25",
            "--to-date",
            "2026-10-27",
        ]
    )
    assert code == 1, output
    assert "Partition-invariant historical merge" in output
    assert pilots.business_requests == []


def test_blocked_reenrollment_preserves_saved_history_plan(
    run_cli, cash_sync, tmp_path
):
    manifest_path = tmp_path / "plugins/liquidity/cash.balances/leaf.json"
    manifest = json.loads(manifest_path.read_text())
    for profile in manifest["sync"]:
        profile["parameters"]["entity"] = ["ALIPAYGM"]
    manifest_path.write_text(json.dumps(manifest))
    code, output, _ = run_cli(["sync", "--all"])
    assert (
        next(
            t for t in json.loads(output)["data"]["targets"] if t["variant"] == "daily"
        )["state"]
        == "complete"
    )
    before = json.loads(run_cli(["sync", "status"])[1])["data"]
    daily = next(t for t in before["targets"] if t["variant"] == "daily")
    manifest_path = tmp_path / "plugins/liquidity/cash.balances/leaf.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["sync"][1]["unsupported_reason"] = "Source qualification withdrawn"
    manifest_path.write_text(json.dumps(manifest))
    assert run_cli(["sync", "--all"])[0] == 1
    after = json.loads(run_cli(["sync", "status"])[1])["data"]
    retained = next(t for t in after["targets"] if t["variant"] == "daily")
    assert retained["state"] == "blocked"
    assert retained["parameters"] == daily["parameters"]
    assert retained["row_count"] == daily["row_count"]
    assert retained["last_success"] == daily["last_success"]
