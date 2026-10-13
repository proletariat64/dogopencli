"""Collection VA capacity public CLI + fake CDP + real SQLite acceptance (#38)."""

import pytest
from test_sla_cli_sit import sla_setup  # noqa: F401


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.collection_va_capacity]\nkind = "cdp"\n')
    return sla_setup


def row(rule_id="1", **changes):
    """Synthetic capacity row: the 22 verified fields, no production values."""
    base = {
        "id": "SYNTHETIC-SURROGATE-1",
        "ruleId": rule_id,
        "bankAccountVaId": "SYNTHETIC-BANKRULE-1",
        "accountNo": "SYNTHETIC-ACCOUNT",
        "bankAccountingEntityCode": "SBE",
        "serviceAccountingEntityCode": "SSE",
        "financialInst": "SYNTHETIC-INST",
        "currency": "USD",
        "sceneCode": "SC1",
        "memo": "synthetic memo",
        "totalCount": 10,
        "usedCount": 4,
        "availableCount": 6,
        "canAllocateCount": 6,
        "lastDayUseCount": 1,
        "averageApplyCount": 2,
        "totalMaxUseCount": 3,
        "warningCount": 0,
        "warningDays": 0,
        "canUseDays": 9,
        "gmtCreate": 1694000000000,
        "gmtModified": 1694100000000,
    }
    base.update(changes)
    return base


def page(rows=None, **changes):
    rows = [row()] if rows is None else rows
    return {
        "status": 200,
        "body": {
            "success": True,
            "pageNo": 1,
            "pageSize": 1000,
            "totalCount": len(rows),
            "resultDataList": rows,
            **changes,
        },
    }


def bulk_rows(count):
    return [row(f"{1000 + index}") for index in range(count)]


def listing(run_cli, *flags):
    return run_cli(["collection", "va", "capacity", "list", *flags])


def refresh(run_cli, *flags):
    return run_cli(["refresh", "collection", "va", "capacity", *flags])


def seed(run_cli, setup):
    setup.state.business_script.append(page())
    assert refresh(run_cli)[0] == 0
    return listing(run_cli)[1]


def test_refresh_publishes_and_offline_reads(run_cli, envelope, setup):
    rows = [
        row("20", bankAccountVaId="SYNTHETIC-B2"),
        row("2", bankAccountVaId="SYNTHETIC-B1"),
    ]
    setup.state.business_script.append(page(rows))
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    result = envelope(out)
    assert result["data"]["namespace"] == "temporary-query:collection.va.capacity"
    assert result["data"]["row_count"] == 2
    assert result["meta"]["complete"] is True
    assert result["meta"]["stale"] is False
    assert setup.state.business_requests == [{"pageNo": 1, "pageSize": 1000}]
    expressions = [
        expression
        for transport in setup.state.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert len(expressions) == 1
    assert "warningUseCount/pageList.json" in expressions[0]
    assert 'method: "POST"' in expressions[0]
    before = len(setup.state.transports)
    setup.state.running = False
    listed = envelope(
        listing(run_cli, "--limit", "0", "--require-fresh", "--require-complete")[1]
    )
    # Stable-ID sort: "2" numerically before "20"; raw rows unchanged.
    assert listed["data"] == list(reversed(rows))
    assert listed["meta"]["complete"] is True
    assert listed["meta"]["has_more"] is False
    assert len(setup.state.transports) == before
    assert b"FAKE-CTOKEN-SECRET" not in setup.cache_path.read_bytes()


def test_live_never_writes_cache_and_filters_locally(run_cli, envelope, setup):
    old = seed(run_cli, setup)
    digest = setup.cache_path.read_bytes()
    rows = [
        row("2", bankAccountVaId="SYNTHETIC-B1"),
        row("20", bankAccountVaId="SYNTHETIC-B2"),
    ]
    setup.state.business_script.append(page(rows))
    code, out, _ = listing(run_cli, "--live", "--va-rule-id", "20")
    assert code == 0, out
    live = envelope(out)
    assert live["meta"]["source"] == "live"
    assert live["data"] == [row("20", bankAccountVaId="SYNTHETIC-B2")]
    assert setup.cache_path.read_bytes() == digest
    assert listing(run_cli)[1] == old


def test_two_page_acquisition_completes(run_cli, envelope, setup):
    first = bulk_rows(1000)
    last = [row("999999")]
    setup.state.business_script.extend(
        [
            page(first, totalCount=1001),
            page(last, pageNo=2, totalCount=1001),
        ]
    )
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    assert envelope(out)["data"]["row_count"] == 1001
    assert setup.state.business_requests == [
        {"pageNo": 1, "pageSize": 1000},
        {"pageNo": 2, "pageSize": 1000},
    ]
    listed = envelope(listing(run_cli, "--limit", "0")[1])
    assert listed["meta"]["matched_total"] == 1001


def test_empty_scope_publishes_empty_snapshot(run_cli, envelope, setup):
    setup.state.business_script.append(page([]))
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    assert envelope(out)["data"]["row_count"] == 0
    setup.state.running = False
    listed = envelope(listing(run_cli, "--require-complete")[1])
    assert listed["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"success": False}, "BUSINESS_QUERY_FAILED"),
        ({"pageNo": 0}, "INVALID_RESPONSE"),
        ({"pageNo": 2}, "INVALID_RESPONSE"),
        ({"pageSize": 10}, "INVALID_RESPONSE"),
        ({"totalCount": -1}, "INVALID_RESPONSE"),
        ({"totalCount": True}, "INVALID_RESPONSE"),
        ({"totalCount": 2}, "INCOMPLETE_RESULT"),
        ({"resultDataList": None}, "INVALID_RESPONSE"),
        ({"resultDataList": "bad"}, "INVALID_RESPONSE"),
        ({"resultDataList": ["bad"]}, "INVALID_RESPONSE"),
        ({"resultDataList": [row(), row()], "totalCount": 2}, "INCOMPLETE_RESULT"),
        ({"resultDataList": [row(rule_id=" ")]}, "INVALID_RESPONSE"),
        ({"resultDataList": [row(rule_id="")]}, "INVALID_RESPONSE"),
        ({"resultDataList": [row(rule_id=1)]}, "INVALID_RESPONSE"),
        ({"resultDataList": [row(), row()], "totalCount": 1}, "INCOMPLETE_RESULT"),
    ],
)
@pytest.mark.parametrize("live", [False, True])
def test_list_rejects_incomplete_or_bad_data(
    run_cli, envelope, setup, changes, code, live
):
    old = seed(run_cli, setup)
    setup.state.business_script.append(page(**changes))
    result = (
        listing(run_cli, "--live", "--require-complete")
        if live
        else refresh(run_cli, "--require-complete")
    )
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == code
    assert listing(run_cli)[1] == old


def test_running_estimate_total_converges_and_completes(run_cli, envelope, setup):
    """Interim totals are running estimates; only the final page validates.

    A full first page reporting an estimate equal to the page size must not
    terminate the sweep, and a converging total on the short last page is
    the completeness proof (#37 contract).
    """
    first = bulk_rows(1000)
    last = [row("999999")]
    setup.state.business_script.extend(
        [
            page(first, totalCount=1000),
            page(last, pageNo=2, totalCount=1001),
        ]
    )
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    assert envelope(out)["data"]["row_count"] == 1001
    assert envelope(out)["meta"]["complete"] is True
    assert setup.state.business_requests == [
        {"pageNo": 1, "pageSize": 1000},
        {"pageNo": 2, "pageSize": 1000},
    ]


def test_exact_full_pages_end_on_beyond_end_empty_page(run_cli, envelope, setup):
    """A scope that is an exact page-size multiple ends on a zero-row page."""
    first = bulk_rows(1000)
    second = [row(f"{2000 + index}") for index in range(1000)]
    setup.state.business_script.extend(
        [
            page(first, totalCount=1000),
            page(second, pageNo=2, totalCount=2000),
            page([], pageNo=3, totalCount=2000),
        ]
    )
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    assert envelope(out)["data"]["row_count"] == 2000
    assert setup.state.business_requests == [
        {"pageNo": 1, "pageSize": 1000},
        {"pageNo": 2, "pageSize": 1000},
        {"pageNo": 3, "pageSize": 1000},
    ]


def test_converged_total_mismatch_is_incomplete(run_cli, envelope, setup):
    """Interim totals may move; a final total below coverage is incomplete."""
    old = seed(run_cli, setup)
    setup.state.business_script.extend(
        [
            page(bulk_rows(1000), totalCount=1500),
            page(bulk_rows(500), pageNo=2, totalCount=1400),
        ]
    )
    result = refresh(run_cli, "--require-complete")
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INCOMPLETE_RESULT"
    assert listing(run_cli)[1] == old


def test_empty_first_page_with_wrong_page_echo_preserves_snapshot(
    run_cli, envelope, setup
):
    """An empty page does not waive the echo check; garbage must not clear
    the previous snapshot."""
    old = seed(run_cli, setup)
    setup.state.business_script.append(page([], pageNo=99, totalCount=0))
    result = refresh(run_cli)
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INVALID_RESPONSE"
    assert listing(run_cli)[1] == old


def test_drifted_row_between_pages_fails(run_cli, envelope, setup):
    """A ruleId recurring on a later page with changed counters is drift."""
    old = seed(run_cli, setup)
    first = bulk_rows(1000)
    drifted = dict(first[0], usedCount=first[0]["usedCount"] + 1)
    setup.state.business_script.extend(
        [
            page(first, totalCount=1001),
            page([drifted], pageNo=2, totalCount=1001),
        ]
    )
    result = refresh(run_cli)
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INVALID_RESPONSE"
    assert listing(run_cli)[1] == old


def test_offline_help_describe_and_bare_navigation(run_cli, envelope, monkeypatch):
    from dogopencli import cli

    monkeypatch.setattr(
        cli.config_mod, "load", lambda *args: pytest.fail("loaded config")
    )
    groups = [("collection", "va"), ("collection", "va", "capacity")]
    leaves = [
        ("collection", "va", "capacity", "list"),
        ("refresh", "collection", "va", "capacity"),
    ]
    for path in groups:
        assert run_cli(list(path))[0] == 0
    for path in groups + leaves:
        assert run_cli(["help", *path])[0] == 0
        assert run_cli([*path, "--help"])[0] == 0
        assert run_cli([*path, "-h"])[0] == 0
    list_help = run_cli(["help", "collection", "va", "capacity", "list"])[1]
    document = envelope(list_help)
    flags = {flag for option in document["options"] for flag in option["flags"]}
    assert {
        "--bank-va-rule-id",
        "--va-rule-id",
        "--limit",
        "--offset",
        "--live",
        "--require-fresh",
        "--require-complete",
        "--format",
        "--fields",
    } <= flags
    # The deferred warning-state candidate is never exposed.
    assert "--warning-state" not in flags
    assert "--waring-state" not in flags
    refresh_help = envelope(
        run_cli(["help", "refresh", "collection", "va", "capacity"])[1]
    )
    assert {flag for option in refresh_help["options"] for flag in option["flags"]} == {
        "--require-complete",
        "--limit",
        "--offset",
        "--fields",
        "--format",
    }
    # Bare refresh collection va keeps its executable rule refresh contract.
    va_help = envelope(run_cli(["help", "refresh", "collection", "va"])[1])
    assert any(child["name"] == "capacity" for child in va_help["children"])
    described = envelope(
        run_cli(["describe", "collection", "va", "capacity", "list"])[1]
    )
    assert described["capability"] == "collection.va.capacity.list"
    assert described["data_schema"]["type"] == "array"
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(described["data_schema"])
    Draft202012Validator(described["data_schema"]).validate([row()])


def test_cache_miss_directs_capacity_refresh(run_cli, envelope, setup):
    code, out, _ = listing(run_cli)
    assert code == 1
    error = envelope(out)["error"]
    assert error["code"] == "CACHE_MISS"
    assert "refresh collection va capacity" in error["message"]
    assert setup.state.transports == []


def test_bare_refresh_collection_va_still_executes_rule_refresh(
    run_cli, envelope, setup
):
    """The new capacity child must not capture the existing rule refresh."""
    config = setup.tmp_path / "config.toml"
    with config.open("a") as file:
        file.write('\n[sources.collection_va]\nkind = "cdp"\n')
    from test_collection_va_rule_cli_sit import page as rule_page

    setup.state.business_script.extend([rule_page()])
    code, out, _ = run_cli(["refresh", "collection", "va"])
    assert code == 0, out
    assert envelope(out)["data"]["namespace"] == "temporary-query:collection.va.rules"
    # A refresh selector remains rejected before any browser or business call.
    count = len(setup.state.business_requests)
    code, out, _ = run_cli(["refresh", "collection", "va", "rules"])
    assert code == 2
    assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert len(setup.state.business_requests) == count


def filter_rows():
    return [
        row("1", bankAccountVaId="B-ONE", currency="USD"),
        row("2", bankAccountVaId="B-TWO", currency="EUR"),
        row("3", bankAccountVaId="B-one", currency="USD"),
        row("4", bankAccountVaId=None, currency="USD"),
    ]


def filter_seed(run_cli, setup):
    setup.state.business_script.append(page(filter_rows()))
    assert refresh(run_cli)[0] == 0


def test_filter_matching_semantics(run_cli, envelope, setup):
    filter_seed(run_cli, setup)

    def ids(*flags):
        result = envelope(listing(run_cli, "--limit", "0", *flags)[1])
        return [record["ruleId"] for record in result["data"]]

    # Positive exact matches on both accepted fields.
    assert ids("--va-rule-id", "2") == ["2"]
    assert ids("--bank-va-rule-id", "B-ONE") == ["1"]
    # Nonmatch is an empty local result, not an error.
    assert envelope(listing(run_cli, "--va-rule-id", "absent")[1])["data"] == []
    # Same-field repetition ORs; different fields AND.
    assert ids("--va-rule-id", "1", "--va-rule-id", "3") == ["1", "3"]
    assert ids("--bank-va-rule-id", "B-ONE", "--va-rule-id", "1") == ["1"]
    assert ids("--bank-va-rule-id", "B-ONE", "--va-rule-id", "2") == []
    # Case is significant; values are never normalized.
    assert ids("--bank-va-rule-id", "B-one") == ["3"]
    assert ids("--bank-va-rule-id", "b-one") == []
    # A literal star is not a wildcard.
    assert ids("--va-rule-id", "*") == []
    assert ids("--va-rule-id", "1*") == []
    # Missing/null fields never match.
    assert ids("--bank-va-rule-id", "B-ONE", "--va-rule-id", "4") == []
    assert "4" not in ids("--bank-va-rule-id", "B-ONE", "--bank-va-rule-id", "B-TWO")


def test_filter_rejects_empty_and_whitespace_values(run_cli, envelope, setup):
    filter_seed(run_cli, setup)
    for flag in ("--va-rule-id", "--bank-va-rule-id"):
        for value in ("", " "):
            code, out, _ = listing(run_cli, flag, value)
            assert code == 2, (flag, value)
            assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
        code, out, _ = listing(run_cli, "--live", flag, " ")
        assert code == 2
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_filters_apply_before_windowing(run_cli, envelope, setup):
    filter_seed(run_cli, setup)
    setup.state.business_script.append(page(filter_rows()))
    live = envelope(
        listing(
            run_cli,
            "--live",
            "--bank-va-rule-id",
            "B-ONE",
            "--bank-va-rule-id",
            "B-TWO",
            "--bank-va-rule-id",
            "B-one",
            "--limit",
            "1",
            "--offset",
            "1",
        )[1]
    )
    assert [record["ruleId"] for record in live["data"]] == ["2"]
    assert live["meta"]["matched_total"] == 3
    assert live["meta"]["has_more"] is True
    assert live["meta"]["complete"] is True
    # Live acquisition stays unfiltered: filters never enter the request.
    assert setup.state.business_requests[-1] == {"pageNo": 1, "pageSize": 1000}


def test_windowing_defaults_boundaries_and_conflicts(run_cli, envelope, setup):
    rows = [row(f"{1000 + index}") for index in range(150)]
    setup.state.business_script.append(page(rows))
    assert refresh(run_cli)[0] == 0
    default = envelope(listing(run_cli)[1])
    assert default["meta"]["matched_total"] == 150
    assert default["meta"]["returned_count"] == 100
    assert default["meta"]["has_more"] is True
    assert len(default["data"]) == 100
    tail = envelope(listing(run_cli, "--limit", "10", "--offset", "145")[1])
    assert tail["meta"]["returned_count"] == 5
    assert tail["meta"]["has_more"] is False
    beyond = envelope(listing(run_cli, "--offset", "200")[1])
    assert beyond["data"] == []
    assert beyond["meta"]["matched_total"] == 150
    all_rows = envelope(listing(run_cli, "--limit", "0")[1])
    assert all_rows["meta"]["returned_count"] == 150
    for flags in [
        ("--all", "--limit", "1"),
        ("--all", "--offset", "1"),
        ("--all",),
        ("--limit", "-1"),
        ("--offset", "-1"),
    ]:
        code, out, _ = listing(run_cli, *flags)
        assert code == 2, flags
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_fields_projection_and_formats(run_cli, envelope, setup):
    seed(run_cli, setup)
    single = envelope(listing(run_cli, "--fields", "ruleId")[1])
    assert single["data"] == [{"ruleId": "1"}]
    multiple = envelope(listing(run_cli, "--fields", "ruleId,warningCount")[1])
    assert multiple["data"] == [{"ruleId": "1", "warningCount": 0}]
    # Unknown fields are dropped, never fabricated; metadata stays intact.
    unknown = envelope(listing(run_cli, "--fields", "ruleId,unknownField")[1])
    assert unknown["data"] == [{"ruleId": "1"}]
    assert unknown["meta"]["matched_total"] == 1
    for flags in [("--fields", " , "), ("--fields", "")]:
        assert listing(run_cli, *flags)[0] == 2
    table = listing(run_cli, "--format", "table")[1]
    assert "source: cache" in table
    assert "ruleId" in table
    assert "SYNTHETIC-ACCOUNT" in table
    assert envelope(listing(run_cli, "--format", "json")[1])["data"][0]["ruleId"] == "1"


def test_freshness_and_completeness_requirements(run_cli, envelope, setup):
    import sqlite3

    seed(run_cli, setup)
    config = setup.tmp_path / "config.toml"
    config.write_text(config.read_text().replace("ttl_hours = 72", "ttl_hours = 0"))
    stale = envelope(listing(run_cli)[1])
    assert stale["meta"]["stale"] is True
    assert stale["data"], "stale reads remain available by default"
    assert envelope(listing(run_cli, "--require-fresh")[1])["error"]["code"] == (
        "CACHE_STALE"
    )
    assert listing(run_cli, "--require-complete")[0] == 0
    with sqlite3.connect(setup.cache_path) as connection:
        # Synthetic incomplete metadata; production snapshots remain untouched.
        connection.execute(
            "UPDATE snapshots SET backend_complete = 0, acquisition = NULL"
        )
    assert envelope(listing(run_cli, "--require-complete")[1])["error"]["code"] == (
        "INCOMPLETE_RESULT"
    )
    # An ordinary stale read of an incomplete snapshot still works.
    assert listing(run_cli)[0] == 0


def test_cached_corruption_revalidation(run_cli, envelope, setup):
    import json
    import sqlite3

    rows = [row("1"), row("2")]
    setup.state.business_script.append(page(rows))
    assert refresh(run_cli)[0] == 0
    ns = "temporary-query:collection.va.capacity"
    with sqlite3.connect(setup.cache_path) as connection:
        # Synthetic cache corruption exercises read-time re-validation only.
        bodies = dict(
            connection.execute(
                "SELECT seqid, body FROM records WHERE namespace = ?", (ns,)
            )
        )
        drifted = json.loads(bodies[2])
        drifted["ruleId"] = "1"
        connection.execute(
            "UPDATE records SET body = ? WHERE namespace = ? AND seqid = 2",
            (json.dumps(drifted), ns),
        )
    assert envelope(listing(run_cli)[1])["error"]["code"] == "INCOMPLETE_RESULT"
    with sqlite3.connect(setup.cache_path) as connection:
        connection.execute(
            "DELETE FROM records WHERE namespace = ? AND seqid = 2", (ns,)
        )
    assert envelope(listing(run_cli)[1])["error"]["code"] == "INCOMPLETE_RESULT"
    with sqlite3.connect(setup.cache_path) as connection:
        connection.execute(
            "UPDATE records SET body = ? WHERE namespace = ? AND seqid = 1",
            (json.dumps(["bad"]), ns),
        )
    assert envelope(listing(run_cli)[1])["error"]["code"] == "INVALID_RESPONSE"


def test_refresh_lock_contention_maps_to_locked(run_cli, envelope, setup):
    from dogopencli.cache import Cache

    old = seed(run_cli, setup)
    count = len(setup.state.business_requests)
    with Cache(setup.cache_path).refresh_lock():
        code, out, _ = refresh(run_cli)
        assert code == 1
        error = envelope(out)["error"]
        assert error["code"] == "LOCKED"
        assert error["retryable"] is True
        # The lock is taken before any browser session or business request.
        assert len(setup.state.business_requests) == count
    assert listing(run_cli)[1] == old
    setup.state.business_script.append(page())
    assert refresh(run_cli)[0] == 0


@pytest.mark.parametrize("action", ["list", "refresh"])
def test_live_auth_failures_map_to_auth_required(run_cli, envelope, setup, action):
    old = seed(run_cli, setup)
    outcomes = [
        {"status": 401, "body": {}},
        {
            "status": 200,
            "body": "<html>login</html>",
            "redirected": True,
            "final_url": "https://ipaybuservice.alipay.com/login.htm?secret=PRIVATE",
        },
    ]
    for outcome in outcomes:
        setup.state.business_script.append(outcome)
        result = listing(run_cli, "--live") if action == "list" else refresh(run_cli)
        assert result[0] == 1
        assert envelope(result[1])["error"]["code"] == "AUTH_REQUIRED"
        assert "PRIVATE" not in result[1]
        assert "PRIVATE" not in result[2]
    assert listing(run_cli)[1] == old


@pytest.mark.parametrize("status", [400, 403])
@pytest.mark.parametrize("action", ["list", "refresh"])
def test_business_refusal_preserves_snapshot(run_cli, envelope, setup, status, action):
    old = seed(run_cli, setup)
    count = len(setup.state.business_requests)
    setup.state.business_script.append(
        {"status": status, "body": {"error": "SENSITIVE-DENIAL"}}
    )
    result = listing(run_cli, "--live") if action == "list" else refresh(run_cli)
    assert result[0] == 1
    error = envelope(result[1])["error"]
    assert error["code"] == "BUSINESS_QUERY_FAILED"
    assert str(status) in error["message"]
    assert "SENSITIVE-DENIAL" not in result[1]
    # 400/403 are not retried.
    assert len(setup.state.business_requests) == count + 1
    assert listing(run_cli)[1] == old


def test_interrupted_acquisition_preserves_snapshot(run_cli, setup):
    old = seed(run_cli, setup)

    def interrupted(payload, index):
        raise KeyboardInterrupt

    setup.state.business_handler = interrupted
    assert refresh(run_cli)[0] == 130
    setup.state.business_handler = None
    assert listing(run_cli)[1] == old


def test_unsupported_flags_rejected_before_browser(run_cli, envelope, setup):
    for argv in [
        ["collection", "va", "capacity", "list", "--warning-state", "Y"],
        ["collection", "va", "capacity", "list", "--waring-state", "Y"],
        ["collection", "va", "capacity", "list", "--entity", "SYNTHETIC"],
        ["collection", "va", "capacity", "list", "--currency", "USD"],
        ["collection", "va", "capacity", "list", "--account-no", "X"],
        ["collection", "va", "capacity", "list", "--live", "--memo", "X"],
        ["collection", "va", "capacity", "get", "--id", "1"],
        ["refresh", "collection", "va", "capacity", "--va-rule-id", "1"],
        ["refresh", "collection", "va", "capacity", "--limit", "-1"],
    ]:
        code, out, _ = run_cli(argv)
        assert code == 2, argv
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert setup.state.business_requests == []


def test_transport_restrictions_before_browser(setup):
    from dataclasses import replace

    from dogopencli.errors import CliError
    from dogopencli.plugins.collection.va_capacity import COLLECTION_VA_CAPACITY
    from dogopencli.transport import QueryRequest
    from dogopencli.transport.cdp import CdpQueryTransport

    capability = COLLECTION_VA_CAPACITY
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url="https://ifundcontrol.alipay.com",
    )
    request = QueryRequest(
        capability.name,
        capability.contract.method,
        capability.contract.host,
        capability.contract.path,
        {"pageNo": 1, "pageSize": 1000},
    )
    for change in [
        {"path": "/ivostro/api/warningUseCount/save.json"},
        {"host": "evil.example"},
        {"method": "DELETE"},
        {"body": {"pageNo": 1, "pageSize": 1000, "ruleId": "1"}},
        {"body": {"pageNo": 1, "pageSize": 10}},
        {"body": {"pageNo": 1}},
        {"capability": "collection.va.rules.list"},
    ]:
        with pytest.raises(CliError) as caught:
            transport.execute(replace(request, **change))
        assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert not setup.state.business_requests
    assert not any(t.created for t in setup.state.transports)


def test_ctoken_never_reaches_output_cache_or_payloads(run_cli, setup):
    seed(run_cli, setup)
    setup.state.business_script.append(page())
    runs = [refresh(run_cli), listing(run_cli)]
    for code, out, err in runs:
        assert code == 0
        for text in (out, err):
            assert "FAKE-CTOKEN-SECRET" not in text
            assert "ctoken" not in text
    cache_bytes = setup.cache_path.read_bytes()
    assert b"FAKE-CTOKEN-SECRET" not in cache_bytes
    assert b"ctoken" not in cache_bytes
    for payload in setup.state.business_requests:
        assert set(payload) <= {"pageNo", "pageSize"}


def test_namespace_isolation_vs_other_caches(run_cli, envelope, setup):
    from test_collection_cost_cli_sit import page as cost_page
    from test_collection_cost_cli_sit import row as cost_row
    from test_collection_va_rule_cli_sit import page as rule_page

    config = setup.tmp_path / "config.toml"
    with config.open("a") as file:
        file.write(
            '\n[sources.collection_va]\nkind = "cdp"'
            '\n[sources.collection_cost]\nkind = "cdp"\n'
        )
    setup.state.business_script.extend([rule_page()])
    assert run_cli(["refresh", "collection", "va"])[0] == 0
    setup.state.business_script.append(cost_page([cost_row("700")]))
    assert run_cli(["refresh", "collection", "cost"])[0] == 0
    others = (
        run_cli(["collection", "va", "rules", "list"])[1],
        run_cli(["collection", "cost", "list"])[1],
    )
    old = seed(run_cli, setup)
    assert envelope(listing(run_cli)[1])["data"][0]["ruleId"] == "1"
    # Capacity refresh left the other namespaces untouched.
    assert (
        run_cli(["collection", "va", "rules", "list"])[1],
        run_cli(["collection", "cost", "list"])[1],
    ) == others
    # A later rule refresh leaves the capacity snapshot untouched.
    setup.state.business_script.extend([rule_page()])
    assert run_cli(["refresh", "collection", "va"])[0] == 0
    assert listing(run_cli)[1] == old


def test_snapshot_source_kind_rejected(run_cli, envelope, setup):
    config = setup.tmp_path / "config.toml"
    config.write_text(
        config.read_text().replace(
            '[sources.collection_va_capacity]\nkind = "cdp"',
            "[sources.collection_va_capacity]\n"
            'kind = "snapshot"\n'
            'path = "/tmp/synthetic-capacity-dataset"',
        )
    )
    for result in [
        refresh(run_cli),
        listing(run_cli),
        listing(run_cli, "--live"),
    ]:
        code, out, _ = result
        assert code == 2
        assert envelope(out)["error"]["code"] == "CONFIG_ERROR"
    assert setup.state.transports == []
    assert setup.state.business_requests == []
