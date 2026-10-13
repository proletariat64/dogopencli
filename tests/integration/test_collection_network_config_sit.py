"""Public network-configuration CLI, fake CDP and real temporary SQLite."""

import pytest
from test_sla_cli_sit import sla_setup  # noqa: F401


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.collection_clearing_system]\nkind = "cdp"\n')
        file.write('\n[sources.collection_card_template]\nkind = "cdp"\n')
    return sla_setup


def row(identity="001", **changes):
    return {
        "id": identity,
        "supportedCountry": "GB",
        "supportedCurrency": "GBP",
        "clearingNetworkType": "ACH",
        "clearingNetworkId": "SYNTHETIC-NETWORK",
        "status": "VALID",
        "costLevel": "01",
        "efficiencyLevel": "02",
        "future": {"nested": [None, 0, ""]},
        **changes,
    }


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


@pytest.mark.parametrize("slug", ["clearing-system", "card-template"])
def test_refresh_then_offline_list(run_cli, envelope, setup, slug):
    rows = [row("20"), row("001", cardTemplateItemList=[{"future": [None, 0]}])]
    setup.state.business_script.append(page(rows))
    code, out, _ = run_cli(["refresh", "collection", slug])
    assert code == 0, out
    assert envelope(out)["data"]["row_count"] == 2
    assert setup.state.business_requests == [{"pageNo": 1, "pageSize": 1000}]
    setup.state.running = False
    code, out, _ = run_cli(["collection", slug, "list", "--limit", "0"])
    assert code == 0, out
    assert envelope(out)["data"] == list(reversed(rows))
    assert envelope(out)["meta"]["complete"] is True


@pytest.mark.parametrize("slug", ["clearing-system", "card-template"])
def test_describe_offline_schema(run_cli, envelope, slug):
    code, out, _ = run_cli(["describe", "collection", slug, "list"])
    assert code == 0, out
    schema = envelope(out)["data_schema"]
    assert schema["items"]["required"] == ["id"]
    assert schema["items"]["additionalProperties"] is True
    if slug == "card-template":
        assert (
            "unverified"
            in schema["items"]["properties"]["cardTemplateItemList"]["description"]
        )


@pytest.fixture(params=["clearing-system", "card-template"])
def slug(request):
    return request.param


def listing(run_cli, slug, *flags):
    return run_cli(["collection", slug, "list", *flags])


def refresh(run_cli, slug, *flags):
    return run_cli(["refresh", "collection", slug, *flags])


def seed(run_cli, slug, setup):
    setup.state.business_script.append(page())
    assert refresh(run_cli, slug)[0] == 0
    return listing(run_cli, slug)[1]


def test_local_filters_all_args_and_live(run_cli, envelope, setup, slug):
    mapping = {
        "--bank-location": "supportedCountry",
        "--currency": "supportedCurrency",
        "--status": "status",
    }
    mapping.update(
        {"--system-type": "clearingNetworkType", "--system-name": "clearingNetworkId"}
        if slug == "clearing-system"
        else {
            "--bank": "supportedFinancialInst",
            "--template-name": "templateName",
            "--template-id": "id",
        }
    )
    # Each accepted filter gets positive, case, literal star, missing/null,
    # repeat/OR, nonmatch and invalid-input evidence through public CLI.
    for flag, field in mapping.items():
        rows = [
            row("1", **{field: "MATCH"}),
            row("2", **{field: "match"}),
            row("3", **{field: "*"}),
            row("4", **{field: " MATCH "}),
        ]
        if field != "id":
            rows += [row("5", **{field: None}), row("6")]
            rows[-1].pop(field, None)
        setup.state.business_script.append(page(rows))
        assert refresh(run_cli, slug)[0] == 0
        for value in ["MATCH", "match", "*", " MATCH "]:
            selected = envelope(listing(run_cli, slug, flag, value)[1])
            assert [r[field] for r in selected["data"]] == [value]
        selected = envelope(listing(run_cli, slug, flag, "MATCH", flag, "match")[1])
        assert len(selected["data"]) == 2
        assert envelope(listing(run_cli, slug, flag, "ABSENT")[1])["data"] == []
        for value in ["", "  "]:
            assert listing(run_cli, slug, flag, value)[0] == 2
        before = setup.cache_path.read_bytes()
        setup.state.business_script.append(page(rows))
        live = envelope(listing(run_cli, slug, "--live", flag, "MATCH")[1])
        assert live["data"] == [rows[0]]
        assert live["meta"]["source"] == "live"
        assert setup.cache_path.read_bytes() == before
        assert setup.state.business_requests[-1] == {"pageNo": 1, "pageSize": 1000}


def test_filters_before_window_and_projection(run_cli, envelope, setup, slug):
    rows = [
        row("3", supportedCountry="US"),
        row("2"),
        row("1"),
        row("4", status="INVALID"),
    ]
    setup.state.business_script.append(page(rows))
    assert refresh(run_cli, slug)[0] == 0
    for live in [False, True]:
        if live:
            setup.state.business_script.append(page(rows))
        flags = ["--live"] if live else []
        data = envelope(
            listing(
                run_cli,
                slug,
                *flags,
                "--bank-location",
                "GB",
                "--status",
                "VALID",
                "--offset",
                "1",
                "--limit",
                "1",
                "--fields",
                "id",
            )[1]
        )
        assert data["data"] == [{"id": "2"}]
        assert data["meta"]["matched_total"] == 2
        assert data["meta"]["complete"] is True


def test_formats_and_fields(run_cli, envelope, setup, slug):
    seed(run_cli, slug, setup)
    for fields, expected in [
        ("id", {"id": "001"}),
        ("id,costLevel", {"id": "001", "costLevel": "01"}),
        ("id,unknown", {"id": "001"}),
        ("future", {"future": {"nested": [None, 0, ""]}}),
    ]:
        data = envelope(
            listing(run_cli, slug, "--fields", fields, "--format", "json")[1]
        )
        assert data["data"] == [expected]
        assert data["meta"]["matched_total"] == 1
    for fields in ["", " , "]:
        assert listing(run_cli, slug, "--fields", fields)[0] == 2
    table = listing(run_cli, slug, "--format", "table")[1]
    assert "source: cache" in table
    assert "001" in table
    assert listing(run_cli, slug, "--format", "xml")[0] == 2


@pytest.mark.parametrize("size", [0, 1, 1000])
def test_full_scope_boundaries(run_cli, envelope, setup, slug, size):
    rows = [row(str(i)) for i in range(size)]
    setup.state.business_script.append(page(rows))
    code, out, _ = refresh(run_cli, slug)
    assert code == 0, out
    assert envelope(out)["data"]["row_count"] == size
    assert len(setup.state.business_requests) == 1
    result = envelope(listing(run_cli, slug, "--limit", "0")[1])
    if size:
        assert result["data"] == sorted(rows, key=lambda r: r["id"])
    else:
        assert result["error"]["code"] == "CACHE_MISS"


def test_zeroed_empty_echo_is_supported(run_cli, envelope, setup, slug):
    old = seed(run_cli, slug, setup)
    setup.state.business_script.append(page([], pageNo=0))
    assert refresh(run_cli, slug)[0] == 0
    assert listing(run_cli, slug)[1] == old


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"success": False}, "BUSINESS_QUERY_FAILED"),
        ({"pageNo": 0}, "INVALID_RESPONSE"),
        ({"pageNo": 2}, "INVALID_RESPONSE"),
        ({"pageSize": 20}, "INVALID_RESPONSE"),
        ({"pageSize": 0}, "INVALID_RESPONSE"),
        ({"pageNo": True}, "INVALID_RESPONSE"),
        ({"totalCount": -1}, "INVALID_RESPONSE"),
        ({"totalCount": "1"}, "INVALID_RESPONSE"),
        ({"totalCount": 2}, "INCOMPLETE_RESULT"),
        ({"totalCount": 1001}, "INCOMPLETE_RESULT"),
        ({"resultDataList": None}, "INVALID_RESPONSE"),
        ({"resultDataList": [None]}, "INVALID_RESPONSE"),
        ({"resultDataList": [{"id": 1}]}, "INVALID_RESPONSE"),
        ({"resultDataList": [{"id": " "}]}, "INVALID_RESPONSE"),
        ({"resultDataList": [row(), row()], "totalCount": 2}, "INCOMPLETE_RESULT"),
        (
            {"resultDataList": [row(), row(costLevel="changed")], "totalCount": 2},
            "INVALID_RESPONSE",
        ),
        ({"resultDataList": [], "totalCount": 0, "pageNo": 99}, "INVALID_RESPONSE"),
    ],
)
@pytest.mark.parametrize("live", [False, True])
def test_bad_acquisition_preserves_snapshot(
    run_cli, envelope, setup, slug, changes, error, live
):
    old = seed(run_cli, slug, setup)
    setup.state.business_script.append(page(**changes))
    result = (
        listing(run_cli, slug, "--live", "--require-complete")
        if live
        else refresh(run_cli, slug, "--require-complete")
    )
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == error
    assert listing(run_cli, slug)[1] == old


def test_help_inventory_and_navigation(run_cli, envelope, slug, monkeypatch):
    from dogopencli import cli

    monkeypatch.setattr(cli.config_mod, "load", lambda *a: pytest.fail("config used"))
    group = ["collection", slug]
    assert run_cli(group)[0] == 0
    paths = [
        group,
        [*group, "list"],
        ["refresh", "collection", slug],
        ["describe", *group, "list"],
    ]
    for path in paths:
        for args in [
            ["help", *path],
            [*path, "--help"],
            [*path, "-h"],
            ["help", *path, "--format", "text"],
        ]:
            assert run_cli(args)[0] == 0, args
    assert run_cli(["describe", *group, "list", "--format", "text"])[0] == 0
    doc = envelope(run_cli(["help", *group, "list"])[1])
    flags = {f for option in doc["options"] for f in option["flags"]}
    expected = {
        "--limit",
        "--offset",
        "--live",
        "--require-fresh",
        "--require-complete",
        "--format",
        "--fields",
        "--bank-location",
        "--currency",
        "--status",
    }
    expected |= (
        {"--system-type", "--system-name"}
        if slug == "clearing-system"
        else {"--bank", "--template-name", "--template-id"}
    )
    assert flags == expected
    refresh_options = envelope(run_cli(["help", "refresh", "collection", slug])[1])[
        "options"
    ]
    assert {flag for option in refresh_options for flag in option["flags"]} == {
        "--require-complete",
        "--limit",
        "--offset",
        "--fields",
        "--format",
    }
    for extra in [["--unknown"], ["--warning-state", "Y"], ["--profile", "x"]]:
        assert listing(run_cli, slug, *extra)[0] == 2
    for extra in [["--currency", "GBP"], ["--limit", "-1"], ["extra"]]:
        assert run_cli(["refresh", "collection", slug, *extra])[0] == 2


def test_namespaces_are_isolated(run_cli, envelope, setup):
    setup.state.business_script.extend([page([row("1")]), page([row("2")])])
    assert refresh(run_cli, "clearing-system")[0] == 0
    assert refresh(run_cli, "card-template")[0] == 0
    assert envelope(listing(run_cli, "clearing-system")[1])["data"][0]["id"] == "1"
    assert envelope(listing(run_cli, "card-template")[1])["data"][0]["id"] == "2"


def test_windowing_defaults_boundaries_and_conflicts(run_cli, slug, envelope, setup):
    rows = [row(f"{1000 + index}") for index in range(150)]
    setup.state.business_script.append(page(rows))
    assert refresh(run_cli, slug)[0] == 0
    default = envelope(listing(run_cli, slug)[1])
    assert default["meta"]["matched_total"] == 150
    assert default["meta"]["returned_count"] == 100
    assert default["meta"]["has_more"] is True
    assert len(default["data"]) == 100
    tail = envelope(listing(run_cli, slug, "--limit", "10", "--offset", "145")[1])
    assert tail["meta"]["returned_count"] == 5
    assert tail["meta"]["has_more"] is False
    beyond = envelope(listing(run_cli, slug, "--offset", "200")[1])
    assert beyond["data"] == []
    assert beyond["meta"]["matched_total"] == 150
    all_rows = envelope(listing(run_cli, slug, "--limit", "0")[1])
    assert all_rows["meta"]["returned_count"] == 150
    for flags in [
        ("--all", "--limit", "1"),
        ("--all", "--offset", "1"),
        ("--limit", "-1"),
        ("--limit", "-1"),
        ("--offset", "-1"),
    ]:
        code, out, _ = listing(run_cli, slug, *flags)
        assert code == 2, flags
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_freshness_and_completeness_requirements(run_cli, slug, envelope, setup):
    import sqlite3

    seed(run_cli, slug, setup)
    config = setup.tmp_path / "config.toml"
    config.write_text(config.read_text().replace("ttl_hours = 72", "ttl_hours = 0"))
    stale = envelope(listing(run_cli, slug)[1])
    assert stale["meta"]["stale"] is True
    assert stale["data"], "stale reads remain available by default"
    assert envelope(listing(run_cli, slug, "--require-fresh")[1])["error"]["code"] == (
        "CACHE_STALE"
    )
    assert listing(run_cli, slug, "--require-complete")[0] == 0
    with sqlite3.connect(setup.cache_path) as connection:
        # Synthetic incomplete metadata; production snapshots remain untouched.
        connection.execute(
            "UPDATE snapshots SET backend_complete = 0, acquisition = NULL"
        )
    assert envelope(listing(run_cli, slug, "--require-complete")[1])["error"][
        "code"
    ] == ("INCOMPLETE_RESULT")
    # An ordinary stale read of an incomplete snapshot still works.
    assert listing(run_cli, slug)[0] == 0


def test_refresh_lock_contention_maps_to_locked(run_cli, slug, envelope, setup):
    from dogopencli.cache import Cache

    old = seed(run_cli, slug, setup)
    count = len(setup.state.business_requests)
    with Cache(setup.cache_path).refresh_lock():
        code, out, _ = refresh(run_cli, slug)
        assert code == 1
        error = envelope(out)["error"]
        assert error["code"] == "LOCKED"
        assert error["retryable"] is True
        # The lock is taken before any browser session or business request.
        assert len(setup.state.business_requests) == count
    assert listing(run_cli, slug)[1] == old
    setup.state.business_script.append(page())
    assert refresh(run_cli, slug)[0] == 0


@pytest.mark.parametrize("action", ["list", "refresh"])
def test_live_auth_failures_map_to_auth_required(
    run_cli, slug, envelope, setup, action
):
    old = seed(run_cli, slug, setup)
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
        result = (
            listing(run_cli, slug, "--live")
            if action == "list"
            else refresh(run_cli, slug)
        )
        assert result[0] == 1
        assert envelope(result[1])["error"]["code"] == "AUTH_REQUIRED"
        assert "PRIVATE" not in result[1]
        assert "PRIVATE" not in result[2]
    assert listing(run_cli, slug)[1] == old


@pytest.mark.parametrize("status", [400, 403])
@pytest.mark.parametrize("action", ["list", "refresh"])
def test_business_refusal_preserves_snapshot(
    run_cli, slug, envelope, setup, status, action
):
    old = seed(run_cli, slug, setup)
    count = len(setup.state.business_requests)
    setup.state.business_script.append(
        {"status": status, "body": {"error": "SENSITIVE-DENIAL"}}
    )
    result = (
        listing(run_cli, slug, "--live") if action == "list" else refresh(run_cli, slug)
    )
    assert result[0] == 1
    error = envelope(result[1])["error"]
    assert error["code"] == "BUSINESS_QUERY_FAILED"
    assert str(status) in error["message"]
    assert "SENSITIVE-DENIAL" not in result[1]
    # 400/403 are not retried.
    assert len(setup.state.business_requests) == count + 1
    assert listing(run_cli, slug)[1] == old


def test_interrupted_acquisition_preserves_snapshot(run_cli, slug, setup):
    old = seed(run_cli, slug, setup)

    def interrupted(payload, index):
        raise KeyboardInterrupt

    setup.state.business_handler = interrupted
    assert refresh(run_cli, slug)[0] == 130
    setup.state.business_handler = None
    assert listing(run_cli, slug)[1] == old


def test_transport_restrictions(setup, slug):
    from dogopencli.errors import CliError
    from dogopencli.plugins import get_capability
    from dogopencli.transport import QueryRequest, validate_request

    cap = get_capability(f"collection.{slug.replace('-', '_')}.list")
    base = dict(
        capability=cap.name,
        method="POST",
        host="ifundboss-api.alipay.com",
        path=cap.contract.path,
        body={"pageNo": 1, "pageSize": 1000},
    )
    for changes in [
        dict(method="GET"),
        dict(host="other.example"),
        dict(path=cap.contract.path.replace("pageList", "delete")),
        dict(body={"pageNo": 2, "pageSize": 1000}),
        dict(body={"pageNo": 1, "pageSize": 20}),
        dict(body={"pageNo": 1, "pageSize": 1000, "status": "VALID"}),
        dict(body={"pageNo": 1, "pageSize": 1000, "ctoken": "SECRET"}),
    ]:
        with pytest.raises(CliError) as exc:
            validate_request(QueryRequest(**(base | changes)), cap.contract)
        assert exc.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []


def test_timeout_preserves_previous_snapshot(
    run_cli, envelope, setup, slug, monkeypatch
):
    import dogopencli.collect as collect

    old = seed(run_cli, slug, setup)
    ticks = iter([0, 901])
    monkeypatch.setattr(collect, "_monotonic", lambda: next(ticks))
    code, out, _ = refresh(run_cli, slug)
    assert code == 1
    assert envelope(out)["error"]["code"] == "TIMEOUT"
    assert listing(run_cli, slug)[1] == old


def test_browser_unavailable_and_cache_miss(run_cli, envelope, setup, slug):
    code, out, _ = listing(run_cli, slug)
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_MISS"
    assert f"refresh collection {slug}" in envelope(out)["error"]["message"]
    old = seed(run_cli, slug, setup)
    setup.state.running = False
    code, out, _ = listing(run_cli, slug, "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "BROWSER_UNAVAILABLE"
    assert listing(run_cli, slug)[1] == old


def test_non_json_response_and_token_hygiene(run_cli, envelope, setup, slug):
    old = seed(run_cli, slug, setup)
    setup.state.business_script.append({"status": 200, "body": "SENSITIVE-MALFORMED"})
    code, out, err = refresh(run_cli, slug)
    assert code == 1
    assert envelope(out)["error"]["code"] == "INVALID_RESPONSE"
    assert "SENSITIVE-MALFORMED" not in out + err
    assert "FAKE-CTOKEN-SECRET" not in out + err
    assert b"FAKE-CTOKEN-SECRET" not in setup.cache_path.read_bytes()
    assert listing(run_cli, slug)[1] == old
