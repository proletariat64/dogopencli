"""Qualified native scopes cannot duplicate identities or erase other snapshots."""

import json
from pathlib import Path

import duckdb
import pytest
from fake_cdp import FakeBrowser
from integration.leaves.liquidity.test_cash_queries_cli import native_row, page

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def installed(run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(
        f'[auth]\nprofile="{tmp_path / "chrome"}"\ncdp_url="http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    def install(leaf):
        source = ROOT / "leaf_packages/liquidity" / leaf
        cli("plugins", "install", str(source))
        relation = json.loads((source / "leaf.json").read_text())["dataset"]["relation"]

        def rows():
            with duckdb.connect(str(tmp_path / "duckdog.duckdb"), read_only=True) as db:
                return [
                    parse(r[0])
                    for r in db.execute(f'SELECT _record FROM "{relation}"').fetchall()
                ]

        return cli, browser, rows

    try:
        yield install
    finally:
        cdp.set_transport_factory(None)


def test_strategy_type_snapshot_cannot_overlap_category(installed):
    from integration.leaves.liquidity.test_operations_strategy_rules_cli import native

    leaf = "operations.strategy_rules"
    cli, browser, rows = installed(leaf)
    record = {
        "id": "R",
        "strategyCategory": "SUB_STRATEGY",
        "strategyType": "PRINCIPAL_PLANNING",
    }
    browser.business_script.append(native([record]))
    cli("liquidity", "sync", leaf, "--category", "SUB_STRATEGY")
    browser.business_script.append(native([{**record, "version": 2}]))
    cli(
        "liquidity",
        "sync",
        leaf,
        "--category",
        "SUB_STRATEGY",
        "--strategy-type",
        "PRINCIPAL_PLANNING",
        code=1,
    )
    assert rows() == [record]


def test_blacklist_sync_accepts_native_empty_swift(installed):
    from integration.leaves.liquidity.test_reference_blacklist_bank_cli import (
        page as blacklist_page,
    )
    from integration.leaves.liquidity.test_reference_blacklist_bank_cli import row

    cli, browser, rows = installed("reference.blacklist.bank")
    record = row(swift="")
    browser.business_script.extend(
        [
            blacklist_page([record]),
            blacklist_page([record]),
            blacklist_page([], total=1),
        ]
    )
    cli("liquidity", "sync", "reference.blacklist.bank")
    assert rows() == [record]


@pytest.mark.parametrize("narrowed", [[], [{"id": "A", "userGroupCode": "A"}]])
def test_group_snapshot_rejects_narrower_scope_without_erasure(installed, narrowed):
    leaf = "cash.group_balances"
    cli, browser, rows = installed(leaf)
    records = [{"id": "A", "userGroupCode": "A"}, {"id": "B", "userGroupCode": "B"}]
    browser.business_script.append(page(leaf, records))
    cli("liquidity", "sync", leaf)
    browser.business_script.append(page(leaf, narrowed))
    cli("liquidity", "sync", leaf, "--group-code", "A", code=1)
    assert sorted(rows(), key=lambda r: r["id"]) == records


def test_waterlevel_display_filter_does_not_fork_native_snapshot(installed):
    leaf = "cash.waterlevels"
    cli, browser, rows = installed(leaf)
    records = [native_row(leaf, n) for n in range(2)]
    browser.business_script.append(page(leaf, records))
    cli("liquidity", "sync", leaf, "--account-alias", "synthetic")
    updated = [{**r, "curAvlBal": 99} for r in records]
    browser.business_script.append(page(leaf, updated))
    cli("liquidity", "sync", leaf, "--account-alias", "synthetic", "--currency", "USD")
    assert sorted(rows(), key=lambda r: r["currency"]) == sorted(
        updated, key=lambda r: r["currency"]
    )


def test_statement_selectors_share_native_record_identity(installed):
    leaf = "cash.statements.end_of_day"
    cli, browser, rows = installed(leaf)
    record = native_row(leaf)
    args = [
        "liquidity",
        "sync",
        leaf,
        "--entity",
        "Z21",
        "--currency",
        "USD",
        "--from-date",
        "2026-10-01",
        "--to-date",
        "2026-10-01",
    ]
    browser.business_script.append(page(leaf, [record]))
    cli(*args, "--account-alias", "synthetic", "--account-alias", "other")
    updated = {**record, "textAmount": "2.0000"}
    browser.business_script.append(page(leaf, [updated]))
    cli(*args, "--account-alias", "synthetic")
    assert rows() == [updated]


def test_intraday_statement_sync_blocks_unqualified_cross_day_identity(installed):
    cli, browser, _ = installed("cash.statements.intraday")
    result = cli(
        "liquidity",
        "sync",
        "cash.statements.intraday",
        "--account-alias",
        "A",
        "--currency",
        "USD",
        "--from-date",
        "2026-10-01",
        "--to-date",
        "2026-10-02",
        code=1,
    )
    assert "SYNC_UNSUPPORTED" in json.dumps(result)
    assert not browser.business_requests


def test_forecast_default_entity_matches_explicit_native_entity(installed):
    from integration.leaves.liquidity.test_forecast_cashflows_cli import (
        page as forecast_page,
    )
    from integration.leaves.liquidity.test_forecast_cashflows_cli import row

    leaf = "forecast.cashflows"
    cli, browser, rows = installed(leaf)
    args = [
        "liquidity",
        "sync",
        leaf,
        "--account-alias",
        "ACCOUNT",
        "--currency",
        "USD",
        "--from-date",
        "20260308",
        "--to-date",
        "20260308",
    ]
    record = row(entity="Z21")
    browser.business_script.append(forecast_page([record]))
    cli(*args)
    updated = {**record, "amountStr": "99"}
    browser.business_script.append(forecast_page([updated]))
    cli(*args, "--inst-id", "Z21")
    assert rows() == [updated]


@pytest.mark.parametrize(
    "leaf", ["forecast.account_cashflows", "forecast.account_demands_intraday"]
)
def test_account_sync_requires_explicit_ownership_even_for_all(installed, leaf):
    cli, browser, _ = installed(leaf)
    result = cli(
        "liquidity",
        "sync",
        leaf,
        "--alias",
        "ACCOUNT",
        "--from-date",
        "20261019",
        "--to-date",
        "20261019",
        code=1,
    )
    assert "SYNC_UNSUPPORTED" in json.dumps(result)
    cli("sync", "--all", code=1)
    assert not browser.business_requests


def test_intraday_account_observations_retain_two_days(installed, tmp_path):
    from integration.leaves.liquidity.test_forecast_accounts_cli import response
    from integration.leaves.liquidity.test_forecast_accounts_cli import (
        rows as account_rows,
    )

    from dogopencli.sync_store import SyncStore

    leaf = "forecast.account_demands_intraday"
    cli, browser, rows = installed(leaf)
    first = account_rows(leaf)
    second = [{**r, "inflowAmount": "2"} for r in first]
    for day, records in [("20261019", first), ("20261020", second)]:
        browser.business_script.append(response(leaf, records))
        cli(
            "liquidity",
            "sync",
            leaf,
            "--alias",
            "ACCOUNT",
            "--entity",
            "ENTITY",
            "--bank",
            "BANK",
            "--from-date",
            day,
            "--to-date",
            day,
        )
    assert len(rows()) == 96
    assert {r["inflowAmount"] for r in rows()} == {"2"}
    with SyncStore(tmp_path / "duckdog.duckdb") as store:
        assert len(store.records(store.targets()[0]["id"], observations=True)) == 192


def test_prefund_all_enrolls_both_status_views_without_erasure(installed):
    from integration.leaves.liquidity.test_operations_cli import page as operation_page
    from integration.leaves.liquidity.test_operations_cli import record

    cli, browser, rows = installed("operations.prefunds")

    def handler(body, _):
        statuses = parse(body["preFundingOrderQueryVO"])["statusList"]
        row = record("prefunds", 0 if "APPROVED" in statuses else 1)
        row["status"] = statuses[0]
        return operation_page("prefunds", [row])

    browser.business_handler = handler
    result = cli("sync", "--all")
    assert len(result["data"]["targets"]) == 2
    assert len(rows()) == 2
    browser.business_handler = lambda body, _: operation_page("prefunds", [])
    cli(
        "liquidity",
        "sync",
        "operations.prefunds",
        "--status",
        "CLOSED",
        "--status",
        "APPROVED",
        "--status",
        "APPROVED",
    )
    assert len(rows()) == 1
    assert rows()[0]["status"] == "SUBMITTED"
