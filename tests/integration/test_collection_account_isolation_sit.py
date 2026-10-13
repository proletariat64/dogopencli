"""Account-isolation public CLI with fake CDP and a private SQLite cache."""

import pytest
from test_sla_cli_sit import sla_setup  # noqa: F401


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.collection_account_isolation]\nkind = "cdp"\n')
    return sla_setup


def row(identity="001", **changes):
    return {
        "id": identity,
        "businessCategory": "SYNTHETIC",
        "businessRegionScope": "GB",
        "customerTags": "A,B",
        "sceneCode": "SCENE",
        "creditArea": "US",
        "currency": "USD,GBP",
        "regionType": "CROSS_BORDER",
        "future": {"nested": [None, 0, ""]},
        **changes,
    }


def page(rows=None, **changes):
    rows = [row()] if rows is None else rows
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "businessDataList": rows,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": len(rows),
                "totalPageNo": 0,
                **changes,
            },
        },
    }


def test_refresh_and_offline_list_preserve_raw_rows(run_cli, envelope, setup):
    rows = [row("20"), row("001")]
    setup.state.business_script.append(page(rows))
    code, out, _ = run_cli(["refresh", "collection", "account-isolation"])
    assert code == 0, out
    assert envelope(out)["data"]["row_count"] == 2
    assert setup.state.business_requests == [{"pageNo": 0, "pageSize": 1000}]
    setup.state.running = False
    code, out, _ = run_cli(["collection", "account-isolation", "list", "--limit", "0"])
    assert code == 0, out
    assert envelope(out)["data"] == list(reversed(rows))
    assert envelope(out)["meta"]["complete"] is True


def test_offline_describe_explains_whole_string_matching(run_cli, envelope):
    code, out, _ = run_cli(["describe", "collection", "account-isolation", "list"])
    assert code == 0, out
    data = envelope(out)
    assert data["data_schema"]["items"]["required"] == ["id"]
    assert "comma" in str(data["read_guide"]).lower()
    assert "whole-string" in str(data["read_guide"])


FILTERS = {
    "--opening-rule-id": "id",
    "--business-line": "businessCategory",
    "--business-region": "businessRegionScope",
    "--customer-group": "customerTags",
    "--scene-code": "sceneCode",
    "--collection-region": "creditArea",
    "--currency": "currency",
    "--transaction-type": "regionType",
}


def listing(run_cli, *flags):
    return run_cli(["collection", "account-isolation", "list", *flags])


def refresh(run_cli, *flags):
    return run_cli(["refresh", "collection", "account-isolation", *flags])


def seed(run_cli, setup):
    setup.state.business_script.append(page())
    assert refresh(run_cli)[0] == 0
    return listing(run_cli)[1]


@pytest.mark.parametrize("flag,field", FILTERS.items())
def test_each_filter_is_local_exact_and_live_preserves_cache(
    run_cli, envelope, setup, flag, field
):
    rows = [
        row("1", **{field: "MATCH"}),
        row("2", **{field: "match"}),
        row("3", **{field: "*"}),
        row("4", **{field: " MATCH "}),
        row("5", **{field: "MATCH,OTHER"}),
    ]
    if field != "id":
        rows += [row("6", **{field: None}), row("7")]
        rows[-1].pop(field, None)
    setup.state.business_script.append(page(rows))
    assert refresh(run_cli)[0] == 0
    for value in ["MATCH", "match", "*", " MATCH ", "MATCH,OTHER"]:
        selected = envelope(listing(run_cli, flag, value)[1])
        assert [r[field] for r in selected["data"]] == [value]
    selected = envelope(listing(run_cli, flag, "MATCH", flag, "match")[1])
    assert len(selected["data"]) == 2
    assert envelope(listing(run_cli, flag, "ABSENT")[1])["data"] == []
    for value in ["", "  "]:
        assert listing(run_cli, flag, value)[0] == 2
    before = setup.cache_path.read_bytes()
    setup.state.business_script.append(page(rows))
    live = envelope(listing(run_cli, "--live", flag, "MATCH")[1])
    assert live["data"] == [rows[0]]
    assert live["meta"]["source"] == "live"
    assert setup.cache_path.read_bytes() == before
    assert setup.state.business_requests[-1] == {"pageNo": 0, "pageSize": 1000}


def test_filter_sort_window_project_and_identity_precision(run_cli, envelope, setup):
    rows = [
        row("9999999999999999999", creditArea="GB"),
        row("9007199254740993"),
        row("9007199254740992"),
        row("001"),
    ]
    setup.state.business_script.append(page(rows))
    assert refresh(run_cli)[0] == 0
    for live in [False, True]:
        if live:
            setup.state.business_script.append(page(rows))
        data = envelope(
            listing(
                run_cli,
                *(["--live"] if live else []),
                "--collection-region",
                "US",
                "--business-region",
                "GB",
                "--offset",
                "1",
                "--limit",
                "1",
                "--fields",
                "id,future",
            )[1]
        )
        assert data["data"] == [
            {"id": "9007199254740992", "future": {"nested": [None, 0, ""]}}
        ]
        assert data["meta"]["matched_total"] == 3
        assert data["meta"]["complete"] is True
    assert envelope(listing(run_cli, "--opening-rule-id", "1")[1])["data"] == []
    assert envelope(listing(run_cli, "--opening-rule-id", "001")[1])["data"] == [
        rows[3]
    ]


@pytest.mark.parametrize("size", [0, 1, 1000])
def test_scope_boundaries_and_no_next_page(run_cli, envelope, setup, size):
    rows = [row(str(i)) for i in range(size)]
    setup.state.business_script.append(page(rows))
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    assert envelope(out)["data"]["row_count"] == size
    assert len(setup.state.business_requests) == 1
    result = envelope(listing(run_cli, "--limit", "0")[1])
    if size:
        assert result["data"] == sorted(rows, key=lambda r: r["id"])
    else:
        assert result["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("populated", [False, True])
def test_unverified_null_zero_empty_never_publishes(
    run_cli, envelope, setup, live, populated
):
    old = seed(run_cli, setup) if populated else None
    setup.state.business_script.append(page([], businessDataList=None, pageSize=0))
    result = listing(run_cli, "--live") if live else refresh(run_cli)
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INVALID_RESPONSE"
    if populated:
        assert listing(run_cli)[1] == old
    else:
        assert envelope(listing(run_cli)[1])["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize("corruption", ["row_count", "duplicate"])
def test_corrupt_cached_scope_identifies_capability(
    run_cli, envelope, setup, corruption
):
    import sqlite3

    seed(run_cli, setup)
    with sqlite3.connect(setup.cache_path) as db:
        db.execute("UPDATE snapshots SET row_count = 2")
        if corruption == "duplicate":
            db.execute(
                "INSERT INTO records SELECT namespace, seqid + 1, body FROM records"
            )
    code, out, _ = listing(run_cli)
    assert code == 1
    error = envelope(out)["error"]
    assert error["code"] == "INVALID_RESPONSE"
    assert envelope(out)["data"] is None
    assert "collection.account_isolation.list" in error["message"]


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"pageNo": 1}, "INVALID_RESPONSE"),
        ({"pageNo": True}, "INVALID_RESPONSE"),
        ({"pageSize": 0}, "INVALID_RESPONSE"),
        ({"totalCount": -1}, "INVALID_RESPONSE"),
        ({"totalCount": "1"}, "INVALID_RESPONSE"),
        ({"totalPageNo": None}, "INVALID_RESPONSE"),
        ({"totalCount": 2}, "INCOMPLETE_RESULT"),
        ({"totalCount": 1001}, "INCOMPLETE_RESULT"),
        ({"businessDataList": None}, "INVALID_RESPONSE"),
        ({"businessDataList": [None]}, "INVALID_RESPONSE"),
        ({"businessDataList": [{"id": 1}]}, "INVALID_RESPONSE"),
        ({"businessDataList": [{"id": " "}]}, "INVALID_RESPONSE"),
        ({"businessDataList": [row(), row()], "totalCount": 2}, "INCOMPLETE_RESULT"),
        (
            {"businessDataList": [row(), row(sceneCode="changed")], "totalCount": 2},
            "INVALID_RESPONSE",
        ),
        ({"businessDataList": [], "totalCount": 0, "pageNo": 99}, "INVALID_RESPONSE"),
        (
            {
                "businessDataList": None,
                "totalCount": 0,
                "pageSize": 0,
                "totalPageNo": 1,
            },
            "INVALID_RESPONSE",
        ),
    ],
)
@pytest.mark.parametrize("live", [False, True])
def test_bad_acquisition_preserves_old_cache(
    run_cli, envelope, setup, changes, error, live
):
    old = seed(run_cli, setup)
    setup.state.business_script.append(page(**changes))
    result = (
        listing(run_cli, "--live", "--require-complete")
        if live
        else refresh(run_cli, "--require-complete")
    )
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == error
    assert listing(run_cli)[1] == old


@pytest.mark.parametrize(
    "body",
    [
        {"success": False},
        {"success": True, "data": None},
        {
            "success": True,
            "data": {"pageNo": 0, "pageSize": 0, "totalCount": 0, "totalPageNo": 0},
        },
        "SENSITIVE-RESPONSE",
    ],
)
def test_invalid_envelope_never_publishes_or_leaks(run_cli, setup, body):
    old = seed(run_cli, setup)
    setup.state.business_script.append({"status": 200, "body": body})
    code, out, err = refresh(run_cli)
    assert code == 1
    assert "SENSITIVE-RESPONSE" not in out + err
    assert "FAKE-CTOKEN-SECRET" not in out + err
    assert listing(run_cli)[1] == old


def test_common_options_and_help_inventory(run_cli, envelope, setup):
    rows = [row(f"{1000 + i}") for i in range(150)]
    setup.state.business_script.append(page(rows))
    assert refresh(run_cli)[0] == 0
    default = envelope(listing(run_cli)[1])
    assert len(default["data"]) == 100
    assert default["meta"]["has_more"] is True
    assert (
        len(envelope(listing(run_cli, "--offset", "145", "--limit", "10")[1])["data"])
        == 5
    )
    assert envelope(listing(run_cli, "--offset", "200")[1])["data"] == []
    assert len(envelope(listing(run_cli, "--limit", "0")[1])["data"]) == 150
    assert envelope(listing(run_cli, "--fields", "id,unknown", "--limit", "1")[1])[
        "data"
    ] == [{"id": "1000"}]
    assert "source: cache" in listing(run_cli, "--format", "table")[1]
    for flags in [
        ("--all", "--limit", "1"),
        ("--all", "--offset", "1"),
        ("--limit", "-1"),
        ("--offset", "-1"),
        ("--fields", ""),
        ("--format", "xml"),
        ("--unknown",),
    ]:
        assert listing(run_cli, *flags)[0] == 2
    paths = [
        ["collection", "account-isolation"],
        ["collection", "account-isolation", "list"],
        ["refresh", "collection", "account-isolation"],
        ["describe", "collection", "account-isolation", "list"],
    ]
    setup.state.running = False
    for path in paths:
        for args in [
            ["help", *path],
            [*path, "--help"],
            [*path, "-h"],
            ["help", *path, "--format", "text"],
        ]:
            assert run_cli(args)[0] == 0, args
    doc = envelope(run_cli(["help", "collection", "account-isolation", "list"])[1])
    assert {f for o in doc["options"] for f in o["flags"]} == set(FILTERS) | {
        "--limit",
        "--offset",
        "--live",
        "--require-fresh",
        "--require-complete",
        "--format",
        "--fields",
    }
    assert (
        run_cli(
            ["describe", "collection", "account-isolation", "list", "--format", "text"]
        )[0]
        == 0
    )
    for extra in [["--currency", "GBP"], ["--limit", "0"], ["extra"]]:
        assert run_cli(["refresh", "collection", "account-isolation", *extra])[0] == 2
    assert run_cli(["collection", "account-isolation", "get", "--id", "001"])[0] == 2
    assert run_cli(["collection", "bank-va", "rules", "list"])[0] == 2


def test_freshness_completeness_and_cache_miss(run_cli, envelope, setup):
    import sqlite3

    assert envelope(listing(run_cli)[1])["error"]["code"] == "CACHE_MISS"
    seed(run_cli, setup)
    config = setup.tmp_path / "config.toml"
    config.write_text(config.read_text().replace("ttl_hours = 72", "ttl_hours = 0"))
    assert envelope(listing(run_cli)[1])["meta"]["stale"] is True
    assert (
        envelope(listing(run_cli, "--require-fresh")[1])["error"]["code"]
        == "CACHE_STALE"
    )
    assert listing(run_cli, "--require-complete")[0] == 0
    with sqlite3.connect(setup.cache_path) as db:
        db.execute("UPDATE snapshots SET backend_complete = 0, acquisition = NULL")
    assert (
        envelope(listing(run_cli, "--require-complete")[1])["error"]["code"]
        == "INCOMPLETE_RESULT"
    )
    assert listing(run_cli)[0] == 0


def test_failures_lock_auth_browser_timeout_interrupt(
    run_cli, envelope, setup, monkeypatch
):
    import dogopencli.collect as collect
    from dogopencli.cache import Cache

    old = seed(run_cli, setup)
    with Cache(setup.cache_path).refresh_lock():
        assert envelope(refresh(run_cli)[1])["error"]["code"] == "LOCKED"
    for status, error in [(401, "AUTH_REQUIRED"), (403, "BUSINESS_QUERY_FAILED")]:
        setup.state.business_script.append({"status": status, "body": {}})
        assert envelope(refresh(run_cli)[1])["error"]["code"] == error
        assert listing(run_cli)[1] == old
    setup.state.running = False
    assert (
        envelope(listing(run_cli, "--live")[1])["error"]["code"]
        == "BROWSER_UNAVAILABLE"
    )
    setup.state.running = True

    def interrupt(payload, index):
        raise KeyboardInterrupt

    setup.state.business_handler = interrupt
    assert refresh(run_cli)[0] == 130
    setup.state.business_handler = None
    ticks = iter([0, 901])
    monkeypatch.setattr(collect, "_monotonic", lambda: next(ticks))
    assert envelope(refresh(run_cli)[1])["error"]["code"] == "TIMEOUT"
    assert listing(run_cli)[1] == old


def test_request_allowlist_rejects_selectors_mutations_and_pagination(setup):
    from dogopencli.errors import CliError
    from dogopencli.plugins import get_capability
    from dogopencli.transport import QueryRequest, validate_request

    cap = get_capability("collection.account_isolation.list")
    base = dict(
        capability=cap.name,
        method="POST",
        host="ifundcontrolprodops.alipay.com",
        path="/api/virtualAccountRuleConfig/search",
        body={"pageNo": 0, "pageSize": 1000},
    )
    for changes in [
        dict(method="GET"),
        dict(host="other.example"),
        dict(path="/api/virtualAccountRuleConfig/createBizRule"),
        dict(body={"pageNo": 1, "pageSize": 1000}),
        dict(body={"pageNo": 0, "pageSize": 10}),
        dict(body={"pageNo": 0, "pageSize": 1000, "id": "001"}),
        dict(body={"pageNo": 0, "pageSize": 1000, "ctoken": "SECRET"}),
    ]:
        with pytest.raises(CliError) as exc:
            validate_request(QueryRequest(**(base | changes)), cap.contract)
        assert exc.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
