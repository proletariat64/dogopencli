"""Cash balance date/selection contracts at the public CLI seam."""

import json

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]

QUERY = ["liquidity", "cash", "balances", "list"]
REFRESH = ["refresh", "liquidity", "cash", "balances"]
DATES = ["--from-date", "2026-10-01", "--to-date", "2026-10-02"]


@pytest.mark.parametrize(
    "options",
    [
        ["--from-date", "2026-10-01"],
        ["--to-date", "2026-10-02"],
        ["--from-date", "2026-02-30", "--to-date", "2026-10-02"],
        ["--from-date", "2026-10-03", "--to-date", "2026-10-02"],
        ["--from-date", "9999-12-32", "--to-date", "9999-12-31"],
        ["--from-date", "9999-12-31", "--to-date", "9999-12-30"],
        ["--from-date", "0000-01-01", "--to-date", "0001-01-01"],
        ["--from-date", "00000101", "--to-date", "00010101"],
        ["--from-date", "001-01-01", "--to-date", "0001-01-01"],
        ["--from-date", "0001-1-01", "--to-date", "0001-01-01"],
        [*DATES, "--timezone", "GMT+08"],
        [*DATES, "--page-size", "100"],
    ],
)
def test_invalid_daily_options_fail_before_browser(setup, run_cli, options):
    code, out, err = run_cli([*QUERY, *options, "--live"])
    assert code == 2, err
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


def roster(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": len(rows) if total is None else total,
            "result": {"bankAccountPropertyVOList": rows},
        },
    }


def daily(rows):
    return {"status": 200, "body": {"success": True, "data": rows}}


def test_daily_live_is_native_source_days_not_latest(setup, run_cli):
    requests = []

    def answer(payload, index):
        requests.append(payload)
        if "wallet" in payload:
            return roster([{"aliasName": "A1", "instId": "E1", "currency": "USD"}])
        return daily(
            [
                {
                    "id": "native",
                    "data": "A1",
                    "statisticalDate": "2026-10-01",
                    "balance": "123.4500",
                },
                {
                    "id": "native",
                    "data": "A1",
                    "statisticalDate": "2026-10-02",
                    "balance": "0",
                },
            ]
        )

    setup.state.business_handler = answer
    code, out, err = run_cli([*QUERY, *DATES, "--entity", "E1", "--live"])
    assert code == 0, err
    assert "collected chunk 1/1" in err
    envelope = parse(out)
    assert envelope["data"] == [
        {
            "source_id": "native",
            "account_alias": "A1",
            "statistical_date": "2026-10-01",
            "balance": "123.4500",
            "account_holder_entity_id": "E1",
            "currency": "USD",
        },
        {
            "source_id": "native",
            "account_alias": "A1",
            "statistical_date": "2026-10-02",
            "balance": "0",
            "account_holder_entity_id": "E1",
            "currency": "USD",
        },
    ]
    assert requests[-1] == {
        "tntInstId": "GUAPW3SG",
        "balanceType": "day",
        "aliasNames": ["A1"],
        "queryStartDate": "20261001",
        "queryDate": "20261002",
    }
    assert not setup.cache_path.exists()


def entities(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": len(rows) if total is None else total,
            "result": {"entityMaintVOList": rows},
        },
    }


def directory():
    return [{"id": "row1", "instId": "E1", "instCode": "NOT-AN-ID"}]


def account(alias="A1", entity="E1", currency="USD"):
    return {"aliasName": alias, "instId": entity, "currency": currency}


def observation(alias="A1", day="2026-10-01", balance="12.00"):
    return {
        "id": "repeated-native-id",
        "data": alias,
        "statisticalDate": day,
        "balance": balance,
    }


def install_daily(setup, *, accounts=None, directory_rows=None, total=None, rows=None):
    accounts = [account()] if accounts is None else accounts
    directory_rows = directory() if directory_rows is None else directory_rows
    rows = [observation()] if rows is None else rows

    def answer(payload, index):
        if "entityMaintQueryVO" in payload:
            return entities(directory_rows)
        if "wallet" in payload:
            return roster(accounts, total)
        return daily(rows)

    setup.state.business_handler = answer


@pytest.mark.parametrize("empty", [True, False])
@pytest.mark.parametrize(
    "start, expected_chunks",
    [
        ("9999-12-31", [("99991231", "99991231")]),
        ("9999-12-24", [("99991224", "99991230"), ("99991231", "99991231")]),
    ],
)
def test_last_calendar_day_live_refresh_and_offline(
    setup, run_cli, empty, start, expected_chunks
):
    chunks = []

    def answer(payload, index):
        if "wallet" in payload:
            return roster([account()])
        chunks.append((payload["queryStartDate"], payload["queryDate"]))
        return daily(
            []
            if empty
            else [
                observation(day="9999-12-31")
                if payload["queryDate"] == "99991231"
                else observation(day="9999-12-24")
            ]
        )

    setup.state.business_handler = answer
    options = ["--entity", "E1", "--from-date", start, "--to-date", "9999-12-31"]
    code, out, err = run_cli([*QUERY, *options, "--live", "--require-complete"])
    assert code == 0, err
    acquired = parse(out)
    assert acquired["meta"]["complete"] is True
    assert [row["statistical_date"] for row in acquired["data"]] == (
        []
        if empty
        else ["9999-12-31"]
        if start == "9999-12-31"
        else ["9999-12-24", "9999-12-31"]
    )
    assert chunks == expected_chunks
    assert not setup.cache_path.exists()
    chunks.clear()
    code, out, err = run_cli([*REFRESH, *options, "--require-complete"])
    assert code == 0, err
    assert parse(out)["meta"]["published"] is True
    assert parse(out)["meta"]["complete"] is True
    assert chunks == expected_chunks
    before = setup.cache_path.read_bytes()
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *options, "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"] == acquired["data"]
    assert parse(out)["meta"]["complete"] is True
    assert len(setup.state.business_requests) == count
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("old_start", ["9999-12-30", "9999-12-31"])
def test_last_calendar_day_retention_preserves_only_covered_days(
    setup, run_cli, monkeypatch, old_start
):
    from datetime import datetime, timezone

    from dogopencli.plugins.liquidity import refresh, store

    monkeypatch.setitem(store.plan_capture_publish.__kwdefaults__, "cap", 1)
    install_daily(setup, rows=[observation(day="9999-12-31", balance="1")])
    options = ["--entity", "E1", "--from-date", old_start, "--to-date", "9999-12-31"]
    monkeypatch.setattr(
        refresh, "now", lambda: datetime(2026, 10, 1, tzinfo=timezone.utc)
    )
    code, out, err = run_cli([*REFRESH, *options])
    assert code == 0, err
    install_daily(setup, rows=[observation(day="9999-12-31", balance="2")])
    monkeypatch.setattr(
        refresh, "now", lambda: datetime(2026, 10, 2, tzinfo=timezone.utc)
    )
    # A distinct alias-filter scope shares the same per-leaf retention budget.
    retained = [
        "--entity",
        "E1",
        "--account-alias",
        "A1",
        "--from-date",
        "9999-12-31",
        "--to-date",
        "9999-12-31",
    ]
    code, out, err = run_cli([*REFRESH, *retained, "--require-complete"])
    assert code == 0, err
    assert parse(out)["meta"]["retention"]["dropped"] == 1
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *retained, "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"][0]["balance"] == "2"
    code, out, err = run_cli([*QUERY, *options])
    if old_start == "9999-12-31":
        assert code == 1, err
        assert parse(out)["error"]["code"] == "CACHE_MISS"
    else:
        assert code == 0, err
        assert parse(out)["data"] == []
        assert parse(out)["meta"]["complete"] is False
        code, out, err = run_cli([*QUERY, *options, "--require-complete"])
        assert code == 1, err
        code, out, err = run_cli(
            [
                *QUERY,
                "--entity",
                "E1",
                "--from-date",
                old_start,
                "--to-date",
                old_start,
                "--require-complete",
            ]
        )
        assert code == 0, err
        assert parse(out)["data"] == []
        assert parse(out)["meta"]["complete"] is True


@pytest.mark.parametrize("year", ["0001", "0999"])
@pytest.mark.parametrize("empty", [True, False])
@pytest.mark.parametrize("end_day", ["01", "08"])
def test_early_calendar_year_live_refresh_and_offline(
    setup, run_cli, year, empty, end_day
):
    chunks = []

    def answer(payload, index):
        if "wallet" in payload:
            return roster([account()])
        chunks.append((payload["queryStartDate"], payload["queryDate"]))
        return daily(
            []
            if empty
            else [observation(day=f"{year}-01-{payload['queryStartDate'][-2:]}")]
        )

    setup.state.business_handler = answer
    options = [
        "--entity",
        "E1",
        "--from-date",
        f"{year}-01-01",
        "--to-date",
        f"{year}01{end_day}",
    ]
    code, out, err = run_cli([*QUERY, *options, "--live", "--require-complete"])
    assert code == 0, err
    acquired = parse(out)
    expected_days = [f"{year}-01-01"]
    expected_chunks = [(f"{year}0101", f"{year}0101")]
    if end_day == "08":
        expected_days.append(f"{year}-01-08")
        expected_chunks = [
            (f"{year}0101", f"{year}0107"),
            (f"{year}0108", f"{year}0108"),
        ]
    assert acquired["data"] == (
        []
        if empty
        else [
            {
                "source_id": "repeated-native-id",
                "account_alias": "A1",
                "statistical_date": day,
                "balance": "12.00",
                "account_holder_entity_id": "E1",
                "currency": "USD",
            }
            for day in expected_days
        ]
    )
    assert acquired["meta"]["complete"] is True
    assert chunks == expected_chunks
    assert not setup.cache_path.exists()
    chunks.clear()
    code, out, err = run_cli([*REFRESH, *options, "--require-complete"])
    assert code == 0, err
    assert parse(out)["meta"]["published"] is True
    assert chunks == expected_chunks
    before = setup.cache_path.read_bytes()
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *options, "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"] == acquired["data"]
    assert parse(out)["meta"]["complete"] is True
    assert len(setup.state.business_requests) == count
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("first_day", ["00010101", "00010102"])
def test_early_calendar_retention_preserves_empty_prefix_and_later_days(
    setup, run_cli, monkeypatch, first_day
):
    from dogopencli.plugins.liquidity import store

    monkeypatch.setitem(store.plan_capture_publish.__kwdefaults__, "cap", 1)
    install_daily(
        setup,
        rows=[observation(day="0001-01-02"), observation(day="0001-01-03")],
    )
    options = ["--entity", "E1", "--from-date", first_day, "--to-date", "0001-01-03"]
    code, out, err = run_cli([*REFRESH, *options])
    assert code == 0, err
    assert parse(out)["meta"]["retention"]["dropped"] == 1
    before = setup.cache_path.read_bytes()
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *options])
    assert code == 0, err
    assert [row["statistical_date"] for row in parse(out)["data"]] == ["0001-01-03"]
    assert parse(out)["meta"]["complete"] is False
    expected_record = {
        "source_id": "repeated-native-id",
        "account_alias": "A1",
        "statistical_date": "0001-01-03",
        "balance": "12.00",
        "account_holder_entity_id": "E1",
        "currency": "USD",
    }
    covered_days = [("00010103", [expected_record])]
    if first_day == "00010101":
        covered_days.append(("00010101", []))
    for day, expected in covered_days:
        code, out, err = run_cli(
            [
                *QUERY,
                "--entity",
                "E1",
                "--from-date",
                day,
                "--to-date",
                day,
                "--require-complete",
            ]
        )
        assert code == 0, err
        assert parse(out)["data"] == expected
        assert parse(out)["meta"]["complete"] is True
    code, out, err = run_cli(
        [
            *QUERY,
            "--entity",
            "E1",
            "--from-date",
            "00010102",
            "--to-date",
            "00010102",
            "--require-complete",
        ]
    )
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert len(setup.state.business_requests) == count
    assert setup.cache_path.read_bytes() == before


def test_daily_all_refresh_freezes_selection_and_offline_never_discovers(
    setup, run_cli
):
    install_daily(setup, accounts=[account(), account("OUT", "OUTSIDE")])
    code, out, err = run_cli([*REFRESH, *DATES, "--all"])
    assert code == 0, err
    acquired = parse(out)
    frozen = acquired["meta"]["selection"]
    assert frozen["mode"] == "all-directory"
    assert frozen["entities"] == ["E1"]
    assert frozen["accounts"] == [
        {"aliasName": "A1", "entity": "E1", "currency": "USD"}
    ]
    assert frozen["excluded_account_count"] == 1
    assert frozen["timezone"] == "unknown"
    before = setup.cache_path.read_bytes()
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *DATES, "--all", "--require-complete"])
    assert code == 0, err
    assert parse(out)["meta"]["selection"] == frozen
    assert parse(out)["data"][0]["balance"] == "12.00"
    assert len(setup.state.business_requests) == count
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("change_binding", [True, False])
def test_daily_coverage_only_stitches_identical_frozen_universes(
    setup, run_cli, change_binding
):
    install_daily(setup)
    first = ["--from-date", "2026-10-01", "--to-date", "2026-10-01", "--all"]
    assert run_cli([*REFRESH, *first])[0] == 0
    install_daily(
        setup,
        accounts=[account(currency="EUR" if change_binding else "USD")],
        rows=[observation(day="2026-10-02")],
    )
    second = ["--from-date", "2026-10-02", "--to-date", "2026-10-02", "--all"]
    code, out, err = run_cli([*REFRESH, *second])
    assert code == 0, err
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *DATES, "--all"])
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["complete"] is (not change_binding)
    assert len(result["data"]) == (1 if change_binding else 2)
    assert result["meta"]["selection"]["accounts"][0]["currency"] == (
        "EUR" if change_binding else "USD"
    )
    code, out, err = run_cli([*QUERY, *DATES, "--all", "--require-complete"])
    assert code == (1 if change_binding else 0), err


def test_daily_help_and_describe_expose_distinct_contracts(run_cli):
    code, out, err = run_cli(["describe", *QUERY])
    assert code == 0, err
    description = parse(out)
    variants = description["read_guide"]["variants"]
    history = next(
        item
        for item in variants
        if item["request"]["path"] == "/balStatisticalQuery.json"
    )
    assert history["selectors"] == {"date_bounds": "paired"}
    assert history["request"]["record_container"] == "$.data"
    assert history["request"]["page_size"] is None
    assert history["data_schema"]["x-source-timezone"] == "unknown"
    assert set(history["data_schema"]["properties"]) == {
        "source_id",
        "statistical_date",
        "balance",
        "account_alias",
        "account_holder_entity_id",
        "currency",
    }
    for command in (["help", *QUERY], ["help", *REFRESH]):
        code, out, err = run_cli(command)
        assert code == 0, err
        help_doc = parse(out)
        assert "daily" in " ".join(help_doc["constraints"]).lower()
        all_option = next(item for item in help_doc["options"] if item["name"] == "all")
        assert all_option["argument_contract"]["modes"]["refresh"]["available"] is True
        date_options = [
            item
            for item in help_doc["options"]
            if item["name"] in ("from_date", "to_date")
        ]
        assert len(date_options) == 2
        assert [item["flags"] for item in date_options] == [
            ["--from-date"],
            ["--to-date"],
        ]


def synthetic_balance_id(row):
    account = [row.get(field) for field in ("entity", "aliasName", "currency")]
    return f"synthetic:{json.dumps(account, separators=(',', ':'), ensure_ascii=True)}"


def latest(rows):
    native_rows = [
        row if "balId" in row else {**row, "balId": synthetic_balance_id(row)}
        for row in rows
    ]
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": native_rows, "totalCount": len(native_rows)},
        },
    }


@pytest.mark.parametrize("explicit", [False, True])
def test_latest_all_uses_inst_ids_combined_and_explicit_all_stays_scoped(
    setup, run_cli, explicit
):
    def answer(payload, index):
        if "entityMaintQueryVO" in payload:
            return entities(
                [
                    *directory(),
                    {"id": "row2", "instId": "E2", "instCode": "CODE"},
                    {"id": "row3", "instId": "E1"},
                ]
            )
        return latest(
            [{"entity": "E1", "aliasName": "A1", "currency": "USD", "curBalance": "1"}]
        )

    setup.state.business_handler = answer
    options = ["--entity", "E1"] if explicit else []
    code, out, err = run_cli([*REFRESH, *options, "--all"])
    assert code == 0, err
    expected = ["E1"] if explicit else ["E1", "E2"]
    assert setup.state.business_requests[-1]["entitys"] == expected
    assert parse(out)["meta"]["selection"]["entities"] == expected
    assert parse(out)["meta"]["selection"]["shared_budget_seconds"] == (
        900 if explicit else 1800
    )
    requests = len(setup.state.business_requests)
    assert requests == (1 if explicit else 2)
    # Refreshing an unrelated reference capture cannot reinterpret frozen ALL.
    setup.state.business_handler = lambda payload, index: entities(
        [{"id": "new", "instId": "NEW-ENTITY", "instCode": "E1"}]
    )
    assert run_cli(["refresh", "liquidity", "reference", "entities"])[0] == 0
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *options, "--all", "--require-complete"])
    assert code == 0, err
    assert parse(out)["meta"]["selection"]["entities"] == expected
    assert parse(out)["data"][0]["current_balance"] == "1"
    assert len(setup.state.business_requests) == requests + 1


@pytest.mark.parametrize("command", [QUERY, REFRESH])
def test_complete_empty_all_directory_never_sends_balance_request(
    setup, run_cli, command
):
    setup.state.business_handler = lambda payload, index: entities([])
    code, out, err = run_cli(
        [*command, "--all", *(["--live"] if command == QUERY else [])]
    )
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is True
    assert len(setup.state.business_requests) == 1
    assert parse(out)["meta"]["selection"]["entities"] == []


@pytest.mark.parametrize("bad", [None, "", 123])
def test_malformed_directory_does_not_fall_back_to_default(setup, run_cli, bad):
    setup.state.business_handler = lambda payload, index: entities(
        [{"id": "row", "instId": bad}]
    )
    code, out, err = run_cli([*QUERY, "--all", "--live"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert len(setup.state.business_requests) == 1
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("strict", [False, True])
def test_daily_catalogue_gap_stays_incomplete_even_with_empty_chunks(
    setup, run_cli, strict
):
    install_daily(setup)
    assert run_cli([*REFRESH, *DATES, "--all"])[0] == 0
    before = setup.cache_path.read_bytes()
    install_daily(setup, total=2, rows=[])
    options = ["--require-complete"] if strict else []
    code, out, err = run_cli([*QUERY, *DATES, "--all", "--live", *options])
    assert code == (1 if strict else 0), err
    assert parse(out)["meta"]["complete"] is False
    assert "DEPENDENCY_INCOMPLETE" in parse(out)["meta"]["acquisition"]["reasons"]
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli([*REFRESH, *DATES, "--all", *options])
    assert code == (1 if strict else 0), err
    if strict:
        assert parse(out)["meta"]["published"] is False
        assert setup.cache_path.read_bytes() == before
    else:
        assert parse(out)["meta"]["published"] is True
        setup.state.reachable = False
        code, out, err = run_cli([*QUERY, *DATES, "--all"])
        assert code == 0, err
        assert parse(out)["meta"]["complete"] is False
        assert parse(out)["data"] == []


@pytest.mark.parametrize(
    "fault", ["alias", "day", "bad_day", "amount", "conflict", "refusal", "binding"]
)
def test_daily_hard_failures_preserve_previous_capture(setup, run_cli, fault):
    install_daily(setup)
    assert run_cli([*REFRESH, *DATES, "--all"])[0] == 0
    before = setup.cache_path.read_bytes()
    bad = [observation()]
    accounts = [account()]
    if fault == "alias":
        bad = [observation(alias="UNREQUESTED")]
    elif fault == "day":
        bad = [observation(day="2026-10-03")]
    elif fault == "bad_day":
        bad = [observation(day="2026-02-30")]
    elif fault == "amount":
        bad = [observation(balance="NaN")]
    elif fault == "conflict":
        bad.append(observation(balance="99"))
    elif fault == "binding":
        accounts.append(account(currency="EUR"))
    install_daily(setup, accounts=accounts, rows=bad)
    if fault == "refusal":
        original = setup.state.business_handler
        setup.state.business_handler = lambda payload, index: (
            original(payload, index)
            if "balanceType" not in payload
            else {"status": 200, "body": {"success": False, "errorMessage": "denied"}}
        )
    code, out, err = run_cli([*REFRESH, *DATES, "--all"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == (
        "BUSINESS_QUERY_FAILED" if fault == "refusal" else "INVALID_RESPONSE"
    )
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *DATES, "--all"])
    assert code == 0, err
    assert parse(out)["data"][0]["balance"] == "12.00"


@pytest.mark.parametrize("balance", [None, "", "0", "0.0000", "123.4500"])
def test_daily_money_states_and_same_day_compact_iso_are_preserved(
    setup, run_cli, balance
):
    install_daily(setup, rows=[observation(balance=balance)])
    options = ["--entity", "E1", "--from-date", "20261001", "--to-date", "2026-10-01"]
    code, out, err = run_cli([*REFRESH, *options])
    assert code == 0, err
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, *options])
    assert code == 0, err
    assert parse(out)["data"][0]["balance"] == balance
    assert parse(out)["meta"]["requested_window"] == ["20261001", "20261001"]
    code, out, err = run_cli([*QUERY, "--entity", "E1"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "CACHE_MISS"


def test_daily_alias_intersection_and_disjoint_thirty_by_seven_chunks(setup, run_cli):
    accounts = [account(f"A{i:02d}") for i in range(31)] + [account("OUT", "OUTSIDE")]
    chunks = []

    def answer(payload, index):
        if "wallet" in payload:
            return roster(accounts)
        chunks.append(payload)
        # Each sparse response can be empty; no rows are fabricated for absent days.
        return daily([])

    setup.state.business_handler = answer
    code, out, err = run_cli(
        [*REFRESH, "--entity", "E1", "--from-date", "20261001", "--to-date", "20261008"]
    )
    assert code == 0, err
    assert [
        (len(p["aliasNames"]), p["queryStartDate"], p["queryDate"]) for p in chunks
    ] == [
        (30, "20261001", "20261007"),
        (30, "20261008", "20261008"),
        (1, "20261001", "20261007"),
        (1, "20261008", "20261008"),
    ]
    assert set(chunks[0]["aliasNames"]).isdisjoint(chunks[2]["aliasNames"])
    assert parse(out)["meta"]["selection"]["planned_chunks"] == 4
    chunks.clear()
    code, out, err = run_cli(
        [*QUERY, *DATES, "--entity", "E1", "--account-alias", "A02", "--live"]
    )
    assert code == 0, err
    assert chunks[0]["aliasNames"] == ["A02"]
    assert parse(out)["data"] == []
    code, out, err = run_cli(
        [*QUERY, *DATES, "--entity", "E1", "--account-alias", "OUT", "--live"]
    )
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"


def test_daily_over_budget_plan_rejects_before_history_and_preserves_cache(
    setup, run_cli
):
    install_daily(setup)
    assert run_cli([*REFRESH, *DATES, "--all"])[0] == 0
    before = setup.cache_path.read_bytes()
    count = len(setup.state.business_requests)
    code, out, err = run_cli(
        [*REFRESH, "--all", "--from-date", "2000-01-01", "--to-date", "2026-10-01"]
    )
    assert code == 2, err
    assert "reduce the date window/account selection" in parse(out)["error"]["message"]
    assert len(setup.state.business_requests) == count + 2
    assert setup.cache_path.read_bytes() == before


def test_daily_missing_source_balance_is_not_fabricated(setup, run_cli):
    row = observation()
    row.pop("balance")
    install_daily(setup, rows=[row])
    code, out, err = run_cli([*QUERY, *DATES, "--entity", "E1", "--live"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("dated", [False, True])
def test_acquisition_budget_includes_discovery_without_deadline_reset(
    setup, run_cli, monkeypatch, dated
):
    import time

    install_daily(setup)
    assert run_cli([*REFRESH, *DATES, "--all"])[0] == 0
    before = setup.cache_path.read_bytes()
    monotonic = time.monotonic
    elapsed = {"seconds": 0}
    monkeypatch.setattr(time, "monotonic", lambda: monotonic() + elapsed["seconds"])

    def answer(payload, index):
        if "entityMaintQueryVO" in payload:
            elapsed["seconds"] = 901
            return entities(directory())
        if "wallet" in payload:
            return roster([account()])
        return latest([])

    setup.state.business_handler = answer
    count = len(setup.state.business_requests)
    command = [*REFRESH, "--all", *(DATES if dated else [])]
    code, out, err = run_cli(command)
    if dated:
        assert code == 1, err
        assert parse(out)["error"]["code"] == "TIMEOUT"
        assert len(setup.state.business_requests) == count + 1
        assert setup.cache_path.read_bytes() == before
    else:
        # ALL latest alone has an explicitly longer shared budget, not a reset.
        assert code == 0, err
        assert len(setup.state.business_requests) == count + 2
        assert parse(out)["meta"]["selection"]["shared_budget_seconds"] == 1800


def test_daily_deadline_is_shared_across_chunks_and_failure_never_publishes(
    setup, run_cli, monkeypatch
):
    import time

    install_daily(setup)
    assert run_cli([*REFRESH, *DATES, "--all"])[0] == 0
    before = setup.cache_path.read_bytes()
    monotonic = time.monotonic
    elapsed = {"seconds": 0}
    monkeypatch.setattr(time, "monotonic", lambda: monotonic() + elapsed["seconds"])
    requests = []

    def answer(payload, index):
        if "wallet" in payload:
            return roster([account()])
        requests.append(payload)
        elapsed["seconds"] += 500
        return daily([])

    setup.state.business_handler = answer
    code, out, err = run_cli(
        [*REFRESH, "--entity", "E1", "--from-date", "20261001", "--to-date", "20261015"]
    )
    assert code == 1, err
    assert parse(out)["error"]["code"] == "TIMEOUT"
    assert len(requests) == 2  # third planned chunk is never issued
    assert setup.cache_path.read_bytes() == before


def test_daily_allowlist_rejects_export_mutation_and_latest_fields(setup):
    from dataclasses import replace

    from dogopencli.errors import CliError
    from dogopencli.plugins.liquidity.cash_forecast import CASH_DAILY_BALANCES
    from dogopencli.plugins.liquidity.leaves import list_leaf
    from dogopencli.transport import QueryRequest, validate_request
    from dogopencli.transport.cdp import CdpQueryTransport

    leaf = list_leaf(("cash", "balances"))
    capability = leaf.capability(CASH_DAILY_BALANCES)
    request = QueryRequest(
        capability=capability.name,
        method="POST",
        host="iliquidity.alipay.com",
        path="/balStatisticalQuery.json",
        body={
            "tntInstId": "GUAPW3SG",
            "balanceType": "day",
            "aliasNames": ["A1"],
            "queryStartDate": "20261001",
            "queryDate": "20261002",
        },
    )
    validate_request(request, capability.contract)
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url=capability.page_url,
    )
    invalid = [
        replace(request, path="/dayEndBalanceExport.json"),
        replace(request, path="/updateBalance.json"),
        replace(request, method="GET"),
        replace(request, host="ifundcontrol.alipay.com"),
    ]
    invalid.extend(
        replace(request, body={**request.body, field: value})
        for field, value in [
            ("entitys", ["E1"]),
            ("timeZone", "GMT+08"),
            ("rowStart", 0),
            ("pageSize", 100),
            ("arbitrary", "code"),
            ("balanceType", "month"),
            ("tntInstId", "OTHER"),
        ]
    )
    for changed in invalid:
        with pytest.raises(CliError) as error:
            transport.execute(changed)
        assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
    assert not any(t.created for t in setup.state.transports)


def test_mixed_daily_latest_retention_uses_each_axis_and_preserves_newest(
    setup, run_cli, monkeypatch
):
    from datetime import datetime, timezone

    from dogopencli.plugins.liquidity import refresh, store

    # Bound the real retention policy to a synthetic one-record budget, not
    # a substitute storage/collector implementation.
    monkeypatch.setitem(store.plan_capture_publish.__kwdefaults__, "cap", 1)
    install_daily(setup, rows=[observation(day="2026-10-02")])
    dates = ["--from-date", "20261002", "--to-date", "20261002", "--entity", "E1"]
    assert run_cli([*REFRESH, *dates])[0] == 0
    setup.state.business_handler = lambda payload, index: latest(
        [{"entity": "E1", "aliasName": "A1", "currency": "USD", "curBalance": "10"}]
    )
    monkeypatch.setattr(
        refresh, "now", lambda: datetime(2026, 10, 3, tzinfo=timezone.utc)
    )
    code, out, err = run_cli([*REFRESH, "--entity", "E1"])
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is True
    assert parse(out)["meta"]["retention"]["dropped"] == 1
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, "--entity", "E1"])
    assert code == 0, err
    assert parse(out)["data"][0]["current_balance"] == "10"
    assert parse(out)["meta"]["complete"] is True
    code, out, err = run_cli([*QUERY, *dates])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "CACHE_MISS"
