"""Installed day-end balance contracts through public CLI and fake CDP."""

import shutil
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAF = "cash.balances"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
TENANT = "GUAPW3SG"


@pytest.fixture(params=["directory", "zip"])
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
        result, output, error = run_cli(["liquidity", action, LEAF, *args])
        assert result == code, output + error
        return parse(output)

    try:
        source = tmp_path / "source"
        shutil.copytree(SOURCE, source)
        if request.param == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(source))
            source = archive_path
        result, output, error = run_cli(["plugins", "install", str(source)])
        assert result == 0, output + error
        if request.param == "directory":
            shutil.rmtree(source)
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


FLAGS = [
    "--account-alias",
    "ACCOUNT",
    "--from-date",
    "2026-09-18",
    "--to-date",
    "20260918",
]


def row(**extra):
    return {
        "entity": "OTHER",
        "bankId": "BANK",
        "aliasName": "ACCOUNT",
        "accountNo": "0001",
        "currency": "USD",
        "valueDate": "20260918",
        "openBalance": "100.0000",
        "openAvlBalance": "90.00",
        "closeBalance": "120.1234567890123456789",
        "closeAvlBalance": "110.00",
        "timeZone": "Asia/Hong_Kong",
        "statementCreateTime": "2026-09-18 23:59:59",
        "updateTime": "2026-09-19 08:00:00",
        "source": "day",
        "unknown": {"nested": [None, False, 0]},
        **extra,
    }


def page(rows, start=0, total=None, **extra):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "data": rows,
                "totalCount": len(rows) if total is None else total,
                "rowStart": start,
                "pageSize": 500,
                **extra,
            },
        },
    }


def test_alias_bypasses_current_directory_preserves_native_and_replay(installed):
    cli, browser, config = installed
    browser.business_script.append(page([row()]))
    live = cli("list", "--live", *FLAGS, "--limit", "0", "--require-complete")
    assert live["data"] == [row()]
    assert browser.business_requests == [
        {
            "tntInstId": "GUAPW3SG",
            "aliasName": "ACCOUNT",
            "startDate": "20260918",
            "endDate": "20260918",
            "rowStart": 0,
            "pageSize": 500,
        }
    ]
    assert not (config / "leaf-cache.sqlite3").exists()
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS, "--require-complete")
    count = len(browser.business_requests)
    offline = cli("list", "--limit", "0")
    assert offline["data"] == live["data"]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == count


def roster(alias="ACCOUNT", entity="ALIPAYGM", **extra):
    return {
        "aliasName": alias,
        "instId": entity,
        "bankId": "BANK",
        "currency": "USD",
        **extra,
    }


def directory_page(rows):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"success": True, "bankAccountPropertyVOList": rows},
        },
    }


def composition(envelope):
    return next(
        x
        for x in envelope["meta"]["acquisition"]["attempts"]
        if x.get("composition") == "cash-balance-dayend-v1"
    )


def test_entity_enumerates_live_without_status_filters_and_freezes_aliases(installed):
    cli, browser, _ = installed

    def handler(body, _):
        if "bankAccountQueryVO" in body:
            context = parse(body["bankAccountQueryVO"])
            position, width = context["rowStart"], context["pageSize"]
            accounts = [
                roster(status="CLOSED", manualInfoStatus="DISABLED"),
                roster("UNSELECTED", "OTHER"),
            ]
            return directory_page(accounts[position : position + width])
        return page([row(entity="ALIPAYGM")])

    browser.business_handler = handler
    result = cli(
        "list",
        "--live",
        "--from-date",
        "20260918",
        "--to-date",
        "20260918",
        "--limit",
        "0",
        "--require-complete",
    )
    assert result["data"] == [row(entity="ALIPAYGM")]
    selected = composition(result)
    assert selected["directory"]["source"] == "live"
    assert selected["aliases"] == ["ACCOUNT"]
    assert selected["planned_accounts"] == selected["successful_accounts"] == 1
    assert selected["query_execution_complete"] is True


@pytest.mark.parametrize(
    "flags",
    [
        [],
        ["--from-date", "20260918"],
        ["--from-date", "20260230", "--to-date", "20260301"],
        ["--from-date", "20260919", "--to-date", "20260918"],
        ["--from-date", "2026-9-18", "--to-date", "20260918"],
        [*FLAGS, "--timezone", "GMT+08"],
        [*FLAGS, "--page-size", "500"],
    ],
)
def test_dates_required_and_old_options_removed_before_business_request(
    installed, flags
):
    cli, browser, _ = installed
    result = cli("list", "--live", *flags, code=2)
    assert result["error"] is not None
    assert not browser.business_requests


@pytest.mark.parametrize(
    "extra",
    [
        {"aliasName": "UNREQUESTED"},
        {"valueDate": "20260919"},
        {"valueDate": "2026918"},
        {"entity": ""},
        {"bankId": None},
        {"updateTime": "2026-09-19T08:00:00Z"},
        {"updateTime": "2026-09-19 8:00:00"},
        {"updateTime": "2026-02-30 08:00:00"},
        {"updateTime": None},
        {"__dogopencli_dayend_order": 0},
        {"closeBalance": 1},
    ],
)
def test_invalid_native_scope_identity_time_and_amount_fail(installed, extra):
    cli, browser, _ = installed
    browser.business_script.append(page([row(**extra)]))
    got = cli("list", "--live", *FLAGS, code=1)
    assert got["error"]["code"] == "INVALID_RESPONSE"
    assert got["data"] is None


def test_explicit_entity_validates_native_without_directory(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    got = cli("list", "--live", *FLAGS, "--entity", "ALIPAYGM", code=1)
    assert got["error"]["code"] == "INVALID_RESPONSE"
    assert len(browser.business_requests) == 1


@pytest.mark.parametrize(
    "script, expected",
    [
        ([{"status": 401, "body": {}}], "AUTH_REQUIRED"),
        ([{"status": 200, "body": {"success": False}}], "BUSINESS_QUERY_FAILED"),
        ([page([row()], rowStart=1)], "INVALID_RESPONSE"),
        ([page([row()], pageSize=10)], "INVALID_RESPONSE"),
    ],
)
def test_query_errors_and_malformed_echo_are_not_success(installed, script, expected):
    cli, browser, _ = installed
    browser.business_script.extend(script)
    got = cli("list", "--live", *FLAGS, code=1)
    assert got["error"]["code"] == expected
    assert got["data"] is None


def test_multiple_aliases_deduplicate_requests_and_keep_independent_totals(installed):
    cli, browser, _ = installed
    browser.business_script.extend([page([row()]), page([])])
    result = cli(
        "list",
        "--live",
        *FLAGS,
        "--account-alias",
        "ACCOUNT",
        "--account-alias",
        "EMPTY",
        "--limit",
        "0",
        "--require-complete",
    )
    assert result["data"] == [row()]
    selection = composition(result)
    assert selection["aliases"] == ["ACCOUNT", "EMPTY"]
    assert (
        selection["planned_accounts"]
        == selection["queried_accounts"]
        == selection["successful_accounts"]
        == 2
    )
    assert selection["successful_empty_accounts"] == 1
    assert result["meta"]["reported_total"] is None


@pytest.mark.parametrize("bad", ["overlap", "short", "drift"])
def test_paging_overlap_missing_rows_and_total_drift_rejected_strict(installed, bad):
    cli, browser, _ = installed
    records = [row(accountNo=str(i), bankId="BANK" + str(i)) for i in range(501)]
    first = records[:500] if bad != "short" else records[:499]
    second = records[499:500] if bad == "overlap" else records[500:]
    browser.business_script.extend(
        [
            page(first, total=501),
            page(second, start=500, total=502 if bad == "drift" else 501),
        ]
    )
    got = cli("list", "--live", *FLAGS, "--require-complete", code=1)
    assert got["error"]["code"] in {"INVALID_RESPONSE", "INCOMPLETE_RESULT"}


@pytest.mark.parametrize(
    "first,second",
    [
        (
            {"updateTime": "2026-09-19 08:00:00", "closeBalance": "9999"},
            {"updateTime": "2026-09-19 09:00:00", "closeBalance": "1"},
        ),
        (
            {"updateTime": "2026-09-19 09:00:00", "closeBalance": "1"},
            {"updateTime": "2026-09-19 08:00:00", "closeBalance": "9999"},
        ),
        ({"closeBalance": "9999"}, {"closeBalance": "1"}),
    ],
)
@pytest.mark.parametrize("strict", [False, True])
def test_same_key_versions_return_latest_complete_warning(
    installed, first, second, strict
):
    cli, browser, _ = installed
    browser.business_script.append(page([row(**first), row(**second)], total=1))
    got = cli("list", "--live", *FLAGS, *(["--require-complete"] if strict else []))
    expected = (
        second if row(**first)["updateTime"] <= row(**second)["updateTime"] else first
    )
    assert got["data"] == [row(**expected)]
    assert got["error"] is None
    assert got["meta"]["complete"] is True
    assert "LATEST_BY_SELECTION" in str(got["meta"])
    assert "IDENTITY_CONTENT_CONFLICT" not in str(got["meta"])


@pytest.mark.parametrize("strict", [False, True])
def test_latest_versions_refresh_offline_keep_counts_and_complete_values(
    installed, strict
):
    cli, browser, _ = installed
    flags = [*FLAGS, *(["--require-complete"] if strict else [])]
    first = row(closeBalance="9999")
    winner = row(updateTime="2026-09-19 09:00:00", unknown={"nested": ["new", False]})
    other = row(bankId="SECOND", closeBalance="2.00000000000000000001")
    browser.business_script.append(page([first, other, winner, winner], total=2))
    saved = cli("refresh", *flags)
    before = len(browser.business_requests)
    offline = cli("list", "--limit", "0", *(["--require-complete"] if strict else []))
    assert offline["data"] == [winner, other]
    assert offline["error"] is None
    assert offline["meta"]["complete"] is True
    assert "LATEST_BY_SELECTION" in str(offline["meta"])
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    account = next(
        x["acquisition"]
        for x in offline["meta"]["acquisition"]["attempts"]
        if "alias" in x
    )
    assert account["reported_total"] == 2
    assert account["arrivals"] == 4
    assert account["collected_total"] == 2
    assert account["selection"]["resolved_version_count"] == 1
    assert account["selection"]["identical_duplicate_count"] == 1
    assert len(browser.business_requests) == before


def seed_accounts(config, records, *, complete=True):
    from dogopencli.cache import Cache, SnapshotMeta
    from dogopencli.jsonutil import canonical
    from dogopencli.result_policy import AcquisitionEvidence

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
            simulated=False,
            backend_complete=complete,
            dataset_complete=complete,
            fetched_at="2026-10-19T00:00:00+00:00",
            loaded_at="2026-10-19T00:00:00+00:00",
            source_observed_from=None,
            source_observed_to=None,
            row_count=len(records),
            acquisition=evidence.record(),
        ),
        ((i, canonical(r)) for i, r in enumerate(records)),
    )


def seed_duckdog(config, rows=None, *, missing_alias=False):
    import duckdb

    database = config / "duckdog.duckdb"
    with duckdb.connect(str(database)) as connection:
        if missing_alias:
            connection.execute("CREATE TABLE accounts (instId VARCHAR, bankId VARCHAR)")
            connection.execute(
                "INSERT INTO accounts VALUES (?, ?)", ["ALIPAYGM", "BANK"]
            )
        else:
            connection.execute(
                "CREATE TABLE accounts "
                "(aliasName VARCHAR, instId VARCHAR, bankId VARCHAR)"
            )
            for item in rows or [roster()]:
                connection.execute(
                    "INSERT INTO accounts VALUES (?, ?, ?)",
                    [item.get("aliasName"), item.get("instId"), item.get("bankId")],
                )
    with (config / "config.toml").open("a") as stream:
        stream.write(
            f'\n[duckdog]\npath = "{database}"\n[duckdog.selectors]\n'
            '"liquidity/cash/accounts" = "accounts"\n'
        )


ENTITY_FLAGS = ["--from-date", "20260918", "--to-date", "20260918"]


@pytest.mark.parametrize(
    "source,complete", [("cache", True), ("cache", False), ("duckdog", None)]
)
def test_directory_selected_quality_is_retained_without_quality_fallback(
    installed, source, complete
):
    cli, browser, config = installed
    seed_accounts(config, [roster()], complete=complete is not False)
    if source == "duckdog":
        seed_duckdog(config, [roster(), roster()])
    browser.business_script.append(page([row(entity="ALIPAYGM")]))
    result = cli("list", "--live", *ENTITY_FLAGS, "--limit", "0")
    assert result["data"] == [row(entity="ALIPAYGM")]
    assert len(browser.business_requests) == 1
    directory = composition(result)["directory"]
    assert directory["source"] == source
    assert directory["quality"].get("complete") is complete
    assert result["meta"]["complete"] is (complete is True)
    if complete is not True:
        assert (
            "ACCOUNT_DIRECTORY_INCOMPLETE" if complete is False else "COVERAGE_UNPROVEN"
        ) in str(result["meta"])
        browser.business_script.append(page([row(entity="ALIPAYGM")]))
        rejected = cli("list", "--live", *ENTITY_FLAGS, "--require-complete", code=1)
        assert rejected["error"]["code"] == "INCOMPLETE_RESULT"


@pytest.mark.parametrize("kind", ["no_match", "missing_fields", "empty"])
def test_optional_directory_no_match_or_missing_fields_falls_to_cache(installed, kind):
    cli, browser, config = installed
    seed_duckdog(
        config, [roster(entity="OTHER")], missing_alias=kind == "missing_fields"
    )
    if kind == "empty":
        import duckdb

        with duckdb.connect(str(config / "duckdog.duckdb")) as connection:
            connection.execute("DELETE FROM accounts")
    seed_accounts(config, [roster()])
    browser.business_script.append(page([row(entity="ALIPAYGM")]))
    got = cli("list", "--live", *ENTITY_FLAGS, "--require-complete")
    assert composition(got)["directory"]["source"] == "cache"
    assert len(browser.business_requests) == 1


def test_ambiguous_directory_alias_is_hard_error(installed):
    cli, browser, config = installed
    seed_duckdog(config, [roster(), roster(bankId="OTHER")])
    got = cli("list", "--live", *ENTITY_FLAGS, code=1)
    assert got["error"]["code"] == "INVALID_RESPONSE"
    assert not browser.business_requests


def test_configured_broken_duckdog_never_falls_back(installed):
    cli, browser, config = installed
    seed_duckdog(config)
    (config / "duckdog.duckdb").write_bytes(b"not a database")
    seed_accounts(config, [roster()])
    got = cli("list", "--live", *ENTITY_FLAGS, code=1)
    assert got["error"]["code"] == "LEAF_LOAD_ERROR"
    assert not browser.business_requests


def test_live_directory_empty_proof_is_empty_query_scope(installed):
    cli, browser, _ = installed
    browser.business_handler = lambda body, _: directory_page([])
    got = cli("list", "--live", *ENTITY_FLAGS, "--require-complete")
    assert got["data"] == []
    assert composition(got)["planned_accounts"] == 0
    assert composition(got)["directory"]["source"] == "live"
    assert all("bankAccountQueryVO" in x for x in browser.business_requests)


def test_live_directory_auth_failure_stays_auth_failure(installed):
    cli, browser, _ = installed
    browser.business_script.append({"status": 401, "body": {}})
    got = cli("list", "--live", *ENTITY_FLAGS, code=1)
    assert got["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.parametrize("failure", ["empty", "error", "invalid_order", "strict"])
def test_rejected_and_empty_refresh_preserve_prior_snapshot(installed, failure):
    cli, browser, config = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *FLAGS)
    if failure == "empty":
        browser.business_script.append(page([]))
        cli("refresh", *FLAGS)
    elif failure == "error":
        browser.business_script.append({"status": 200, "body": {"success": False}})
        cli("refresh", *FLAGS, code=1)
    elif failure == "invalid_order":
        browser.business_script.append(page([row(), row(updateTime=None)]))
        cli("refresh", *FLAGS, code=1)
    else:
        seed_accounts(config, [roster()], complete=False)
        browser.business_script.append(page([row(entity="ALIPAYGM")]))
        cli("refresh", *ENTITY_FLAGS, "--require-complete", code=1)
    offline = cli("list", "--limit", "0")
    assert offline["data"] == [row()]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_failed_account_keeps_frozen_plan_success_failure_and_unqueried_counts(
    installed,
):
    cli, browser, _ = installed
    browser.business_script.extend(
        [page([row()]), {"status": 200, "body": {"success": False}}]
    )
    got = cli(
        "list",
        "--live",
        *FLAGS,
        "--account-alias",
        "FAILED",
        "--account-alias",
        "UNQUERIED",
        code=1,
    )
    assert got["error"]["code"] == "BUSINESS_QUERY_FAILED"
    selected = composition(got)
    assert selected["aliases"] == ["ACCOUNT", "FAILED", "UNQUERIED"]
    assert selected["planned_accounts"] == 3
    assert selected["queried_accounts"] == 2
    assert selected["successful_accounts"] == 1
    assert selected["failed_accounts"] == 1
    assert selected["successful_empty_accounts"] == 0
    assert selected["query_execution_complete"] is False
    assert len(browser.business_requests) == 2


def test_entity_any_frozen_selection_live_and_offline(installed):
    cli, browser, config = installed
    import duckdb

    database = config / "duckdog.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute("CREATE TABLE entities (instId VARCHAR)")
        connection.execute(
            "INSERT INTO entities VALUES (?), (?)", ["ALIPAYGM", "OTHER"]
        )
    with (config / "config.toml").open("a") as stream:
        stream.write(
            f'\n[duckdog]\npath = "{database}"\n[duckdog.selectors]\n'
            '"liquidity/reference/entities" = "entities"\n'
        )
    browser.business_script.append(page([row()]))
    flags = [*FLAGS, "--entity", "ANY"]
    live = cli("list", "--live", *flags, "--require-complete")
    assert live["data"] == [row()]
    assert composition(live)["entities"] == ["ALIPAYGM", "OTHER"]
    browser.business_script.append(page([row()]))
    cli("refresh", *flags, "--require-complete")
    count = len(browser.business_requests)
    offline = cli("list", "--entity", "ANY", "--limit", "0", "--require-complete")
    assert offline["data"] == [row()]
    assert len(browser.business_requests) == count


def test_complete_multi_page_native_records_survive_refresh_replay(installed):
    cli, browser, _ = installed
    records = [row(bankId="BANK" + str(i)) for i in range(501)]
    browser.business_script.extend(
        [page(records[:500], total=501), page(records[500:], start=500, total=501)]
    )
    live = cli("list", "--live", *FLAGS, "--limit", "0", "--require-complete")
    assert live["data"] == records
    assert [r["rowStart"] for r in browser.business_requests] == [0, 500]
    accounts = [x for x in live["meta"]["acquisition"]["attempts"] if "alias" in x]
    assert len(accounts) == 1
    assert accounts[0]["acquisition"]["reported_total"] == 501
    assert accounts[0]["acquisition"]["arrivals"] == 501
    browser.business_script.extend(
        [page(records[:500], total=501), page(records[500:], start=500, total=501)]
    )
    cli("refresh", *FLAGS, "--require-complete")
    before = len(browser.business_requests)
    offline = cli("list", "--limit", "0", "--require-complete")
    assert offline["data"] == records
    assert len(browser.business_requests) == before


def test_prior_source_contract_cannot_replay_as_dayend(installed):
    from dataclasses import replace

    from dogopencli.cache import Cache
    from dogopencli.jsonutil import canonical

    cli, browser, config = installed
    browser.business_script.append(page([row()]))
    cli("refresh", *FLAGS, "--require-complete")
    cache = Cache(config / "leaf-cache.sqlite3")
    snapshot, records = cache.read("leaf:liquidity.cash.balances")
    prior_scope = {**parse(snapshot.scope), "contract_id": "prior-trend-contract"}
    cache.publish(replace(snapshot, scope=canonical(prior_scope)), records)
    before = len(browser.business_requests)
    got = cli("list", code=1)
    assert got["error"]["code"] == "CACHE_CONTRACT_CHANGED"
    assert len(browser.business_requests) == before


@pytest.mark.parametrize("records", [[roster(alias=3)], [roster(instId=["ALIPAYGM"])]])
def test_malformed_configured_cached_directory_never_falls_back(installed, records):
    cli, browser, config = installed
    seed_accounts(config, records)
    got = cli("list", "--live", *ENTITY_FLAGS, code=1)
    assert got["error"]["code"] == "INVALID_RESPONSE"
    assert not browser.business_requests


def test_duckdog_directory_read_budget_is_hard_error(installed):
    cli, browser, config = installed
    seed_duckdog(config)
    import duckdb

    with duckdb.connect(str(config / "duckdog.duckdb")) as connection:
        connection.execute(
            "INSERT INTO accounts SELECT aliasName, instId, bankId "
            "FROM accounts, range(100000)"
        )
    got = cli("list", "--live", *ENTITY_FLAGS, code=1)
    assert got["error"]["code"] == "CONFIG_ERROR"
    assert not browser.business_requests


@pytest.mark.parametrize(
    "records,total,code,successful,empty,incomplete",
    [
        ([], 1, 0, 0, 0, 1),
        ([], 0, 0, 1, 1, 0),
        ([row()], 2, 0, 0, 0, 1),
        ([row()], 1, 0, 1, 0, 0),
    ],
)
def test_account_outcomes_distinguish_incomplete_from_successful_empty(
    installed, records, total, code, successful, empty, incomplete
):
    cli, browser, _ = installed
    browser.business_script.append(page(records, total=total))
    got = cli("list", "--live", *FLAGS, code=code)
    selected = composition(got)
    assert selected["planned_accounts"] == selected["queried_accounts"] == 1
    assert selected["successful_accounts"] == successful
    assert selected["successful_empty_accounts"] == empty
    assert selected["incomplete_accounts"] == incomplete
    assert selected["failed_accounts"] == 0
    assert selected["query_execution_complete"] is (incomplete == 0)
    account = next(x for x in got["meta"]["acquisition"]["attempts"] if "alias" in x)
    assert account["acquisition"]["reported_total"] == total
    assert account["acquisition"]["scope_complete"] is (incomplete == 0)
    if incomplete:
        assert "COUNT_SHORTFALL" in str(account["acquisition"])


def test_identical_duplicates_keep_qualified_unique_coverage_and_diagnostic(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row(), row()], total=1))
    got = cli("list", "--live", *FLAGS, "--require-complete")
    assert got["data"] == [row()]
    assert got["meta"]["complete"] is True
    assert got["meta"]["warnings"][0]["code"] == "DUPLICATE_ROWS"
    assert "LATEST_BY_SELECTION" not in str(got["meta"])


def test_cash_named_selection_survives_exact_workflow_import(installed, run_cli):
    _, browser, _ = installed

    def workflow(*args):
        code, output, error = run_cli(["workflow", *args])
        assert code == 0, output + error
        return parse(output)["data"]

    plan = workflow(
        "plan",
        "create",
        "--leaf",
        "liquidity.cash.balances",
        "--mode",
        "history",
        "--parameters",
        '{"account-alias":"ACCOUNT","from-date":"2026-09-18","to-date":"20260918"}',
    )
    winner = row(updateTime="2026-09-19 09:00:00", closeBalance="0.000000000000000001")
    browser.business_script.append(page([row(), winner], total=1))
    run = workflow("export", "create", "--plan", plan["id"])
    result = workflow("export", "run", "--run", run["id"])
    export_id = result["packages"][0]["export_id"]
    exported = workflow("export", "show", "--export", export_id)
    assert exported["records"] == [winner]
    assert "LATEST_BY_SELECTION" in str(exported["metadata"])
    prepared = workflow("import", "plan", "--export", export_id, "--action", "preserve")
    before = len(browser.business_requests)
    workflow("import", "apply", "--plan", prepared["id"])
    retained = workflow("observation", "show", "--export", export_id)
    assert retained["records"] == exported["records"]
    assert retained["metadata"] == exported["metadata"]
    assert len(browser.business_requests) == before


@pytest.mark.parametrize("strict", [False, True])
def test_latest_versions_cannot_repair_partial_directory(installed, strict):
    cli, browser, config = installed
    seed_accounts(config, [roster()], complete=False)
    old = row(entity="ALIPAYGM")
    winner = row(entity="ALIPAYGM", updateTime="2026-09-19 09:00:00")
    browser.business_script.append(page([old, winner], total=1))
    got = cli(
        "list",
        "--live",
        *ENTITY_FLAGS,
        *(["--require-complete"] if strict else []),
        code=int(strict),
    )
    assert got["meta"]["complete"] is False
    assert "ACCOUNT_DIRECTORY_INCOMPLETE" in str(got["meta"])
    assert "LATEST_BY_SELECTION" in str(got["meta"])
    assert got["data"] == (None if strict else [winner])
