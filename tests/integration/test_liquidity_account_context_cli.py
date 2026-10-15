"""Account ownership through public CLI, fake CDP and temporary datasets."""

import os
from pathlib import Path

import pytest
from test_liquidity_cli_sit import account_row, accounts_handler

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "forecast", "account_demands"]
DATES = ["--from-date", "20261009", "--to-date", "20261015"]
EXPLICIT = ["--alias", "SYN-A", "--entity", "SYN-E", "--bank", "SYN-B"]


def demand(entity="SYN-E", bank="SYN-B"):
    return {
        "id": "D1",
        "aliasName": "SYN-A",
        "entity": entity,
        "bankID": bank,
        "amount": "123.000001",
        "expectValueDate": "20261012",
    }


def demands_handler(row=None):
    row = demand() if row is None else row

    def answer(payload, index):
        assert payload["entity"] == row["entity"]
        assert payload["bankId"] == row["bankID"]
        assert payload["aliasName"] == "SYN-A"
        return {
            "status": 200,
            "body": {
                "success": True,
                "data": {
                    "data": [row] if payload["rowStart"] == 0 else [],
                    "totalCount": 1,
                },
            },
        }

    return answer


def configure_accounts(setup, rows=None, *, missing=False):
    config = Path(os.environ["DOGOPENCLI_CONFIG"])
    database = setup.tmp_path / "accounts.duckdb"
    if not missing:
        duckdb = pytest.importorskip("duckdb")
        with duckdb.connect(str(database)) as connection:
            connection.execute(
                'CREATE TABLE accounts ("aliasName" VARCHAR, "instId" VARCHAR, '
                '"bankId" VARCHAR)'
            )
            for row in rows or []:
                connection.execute("INSERT INTO accounts VALUES (?, ?, ?)", list(row))
    with config.open("a") as stream:
        stream.write(
            f'\n[duckdog]\npath="{database}"\n[duckdog.selectors]\n"liquidity/cash/accounts"="accounts"\n'
        )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--alias", "ANY", *DATES],
        ["--alias", "SYN-A", "--from-date", "20261015"],
        ["--alias", "SYN-A", "--from-date", "20261015", "--to-date", "20261009"],
    ],
)
def test_invalid_online_scope_precedes_account_directories(setup, run_cli, arguments):
    configure_accounts(setup, missing=True)
    code, out, _ = run_cli([*ROOT, "list", "--live", *arguments])
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert not setup.state.transports
    assert not setup.cache_path.exists()


def test_explicit_context_never_reads_configured_missing_directory(setup, run_cli):
    configure_accounts(setup, missing=True)
    setup.state.business_handler = demands_handler()
    code, out, err = run_cli([*ROOT, "list", "--live", *EXPLICIT, *DATES])
    assert code == 0, err
    assert parse(out)["data"] == [demand()]
    assert parse(out)["meta"]["account_context"]["source"] == "explicit"
    assert len(setup.state.business_requests) == 2
    assert not setup.cache_path.exists()


def test_duckdog_first_match_warning_survives_projection_and_offline(setup, run_cli):
    configure_accounts(
        setup, [("SYN-A", "SYN-E", "SYN-B"), ("SYN-A", "OTHER", "OTHER")]
    )
    setup.state.business_handler = demands_handler()
    code, out, err = run_cli(
        ["refresh", *ROOT, "--alias", "SYN-A", *DATES, "--fields", "id"]
    )
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["account_context"]["source"] == "duckdog"
    assert "ACCOUNT_CONTEXT_MULTIPLE_MATCHES" in err
    warning = next(
        w
        for w in result["meta"]["warnings"]
        if w["code"] == "ACCOUNT_CONTEXT_MULTIPLE_MATCHES"
    )
    assert warning["match_count"] == 2
    assert warning["selected"] == {
        "aliasName": "SYN-A",
        "instId": "SYN-E",
        "bankId": "SYN-B",
    }
    assert len(setup.state.business_requests) == 2
    requests = len(setup.state.business_requests)
    Path(setup.tmp_path / "accounts.duckdb").unlink()
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list", "--fields", "id"])
    assert code == 0, err
    assert parse(out)["data"] == [{"id": "D1"}]
    assert "ACCOUNT_CONTEXT_MULTIPLE_MATCHES" in err
    assert parse(out)["meta"]["account_context"]["source"] == "duckdog"
    assert len(setup.state.business_requests) == requests


def test_cash_cache_precedes_online_directory_and_does_not_publish_live(setup, run_cli):
    row = {**account_row("SYN-A"), "instId": "SYN-E", "bankId": "SYN-B"}
    setup.state.business_handler = accounts_handler([row])
    code, _, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    requests = len(setup.state.business_requests)
    setup.state.business_handler = demands_handler()
    code, out, err = run_cli([*ROOT, "list", "--live", "--alias", "SYN-A", *DATES])
    assert code == 0, err
    assert parse(out)["meta"]["account_context"]["source"] == "cache"
    assert len(setup.state.business_requests) == requests + 2
    assert setup.cache_path.read_bytes() == before


def test_context_storage_failure_preserves_existing_demand_slot(setup, run_cli):
    setup.state.business_handler = demands_handler()
    assert run_cli(["refresh", *ROOT, *EXPLICIT, *DATES])[0] == 0
    before = setup.cache_path.read_bytes()
    requests = len(setup.state.business_requests)
    configure_accounts(setup, missing=True)
    code, out, _ = run_cli(["refresh", *ROOT, "--alias", "SYN-A", *DATES])
    assert code != 0
    assert parse(out)["error"]["code"] == "CONFIG_ERROR"
    assert len(setup.state.business_requests) == requests
    assert setup.cache_path.read_bytes() == before


def test_account_cache_quality_remains_visible_in_business_query(setup, run_cli):
    row = {**account_row("SYN-A"), "instId": "SYN-E", "bankId": "SYN-B"}
    setup.state.business_handler = accounts_handler([row], cash_total=3)
    code, _, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 0, err
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = demands_handler()
    code, out, err = run_cli(
        [*ROOT, "list", "--live", "--alias", "SYN-A", *DATES, "--fields", "id"]
    )
    assert code == 0, err
    meta = parse(out)["meta"]
    assert meta["account_context"]["directory_quality"]["complete"] is False
    assert "INCOMPLETE_RESULT" in err
    assert any(warning["code"] == "INCOMPLETE_RESULT" for warning in meta["warnings"])
    assert setup.cache_path.read_bytes() == before


def test_legacy_cash_cache_cannot_supply_context_when_public_accounts_rejects_it(
    setup, run_cli
):
    from dogopencli.cache import Cache
    from dogopencli.plugins.liquidity.leaves import list_leaf
    from dogopencli.result_policy import AcquisitionEvidence
    from dogopencli.temporary_query import publish_slot

    accounts = list_leaf(("cash", "accounts"))
    resolved = accounts.resolve({})
    cache = Cache(setup.cache_path)
    row = {**account_row("SYN-A"), "instId": "SYN-E", "bankId": "SYN-B"}
    with cache.refresh_lock():
        publish_slot(
            cache,
            "liquidity.cash.accounts",
            [row],
            capability=resolved.spec.name,
            scope=resolved.request_values,
            variant=resolved.spec.endpoint,
            fetched_at="2026-10-15T00:00:00+00:00",
            evidence=AcquisitionEvidence.for_collection(
                complete=True, reported_total=1, collected_total=1
            ),
        )
    code, out, _ = run_cli(["liquidity", "cash", "accounts", "list"])
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = demands_handler()
    code, out, _ = run_cli([*ROOT, "list", "--live", "--alias", "SYN-A", *DATES])
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.state.business_requests
    assert setup.cache_path.read_bytes() == before


def test_live_account_directory_quality_retained_without_publishing_accounts(
    setup, run_cli
):
    row = {**account_row("SYN-A"), "instId": "SYN-E", "bankId": "SYN-B"}
    directory = accounts_handler([row], cash_total=3)
    business = demands_handler()

    def answer(payload, index):
        if "aliasName" in payload and "rowStart" in payload:
            return business(payload, index)
        return directory(payload, index)

    setup.state.business_handler = answer
    code, out, err = run_cli([*ROOT, "list", "--live", "--alias", "SYN-A", *DATES])
    assert code == 0, err
    context = parse(out)["meta"]["account_context"]
    assert context["source"] == "live"
    assert context["directory_quality"]["complete"] is False
    assert "INCOMPLETE_RESULT" in err
    requests = len(setup.state.business_requests)
    code, out, _ = run_cli(["liquidity", "cash", "accounts", "list"])
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert len(setup.state.business_requests) == requests
