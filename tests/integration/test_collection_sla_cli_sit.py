"""Collection SLA public CLI + fake CDP + real SQLite acceptance (#28)."""

from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
from test_sla_cli_sit import sla_setup  # noqa: F401

from dogopencli import cli
from dogopencli.errors import CliError
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.collection_sla]\nkind = "cdp"\n')
    return sla_setup


def row(identity="1", **changes):
    return {
        "slaConfigId": identity,
        "businessCategory": "SYNTHETIC",
        "legalEntityCode": "ENTITY",
        "creditorCurrency": "USD",
        "creditorRegion": "US",
        "endToEndSla": 86400,
        "ipayInnerSla": 3600,
        "holidayLimit": {"currencyCodes": ["USD", "EUR"], "regionCodes": ["US", "SG"]},
        "gmtModified": 1694100000000,
        "unknownExtension": {"keep": [1, 2]},
        **changes,
    }


def page(rows=None, **changes):
    rows = [row()] if rows is None else rows
    return {
        "status": 200,
        "body": {
            "success": True,
            "pageNo": 0,
            "pageSize": 1000,
            "totalCount": len(rows),
            "resultDataList": rows,
            **changes,
        },
    }


def detail(identity="1", **changes):
    return {
        "status": 200,
        "body": {
            "success": True,
            "resultData": row(identity, detailOnly=True, **changes),
        },
    }


def listing(run_cli, *flags):
    return run_cli(["collection", "sla", "configs", "list", *flags])


def getting(run_cli, *flags):
    return run_cli(["collection", "sla", "configs", "get", *flags])


def refresh(run_cli, *flags):
    return run_cli(["refresh", "collection", "sla", *flags])


def seed(run_cli, setup):
    setup.state.business_script.extend([page(), detail()])
    assert refresh(run_cli)[0] == 0
    return listing(run_cli)[1], getting(run_cli, "--id", "1")[1]


def test_core_refresh_true_details_offline_and_display(run_cli, envelope, setup):
    rows = [row("20"), row("2")]
    setup.state.business_script.extend([page(rows), detail("2"), detail("20")])
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    assert (
        envelope(out)["data"]["namespace"] == "collection.sla.configs.list:configs:cdp"
    )
    assert setup.state.business_requests == [
        {"pageNo": 0, "pageSize": 1000},
        {"slaConfigId": "2"},
        {"slaConfigId": "20"},
    ]
    before = len(setup.state.transports)
    setup.state.running = False
    result = envelope(
        listing(run_cli, "--all", "--require-fresh", "--require-complete")[1]
    )
    assert result["data"] == list(reversed(rows))
    assert result["meta"]["complete"] and not result["meta"]["has_more"]
    for identity in ["2", "20"]:
        code, out, _ = getting(
            run_cli, "--id", identity, "--require-fresh", "--require-complete"
        )
        assert code == 0
        assert envelope(out)["data"] == detail(identity)["body"]["resultData"]
    projected = envelope(
        listing(run_cli, "--limit", "1", "--fields", "slaConfigId,holidayLimit")[1]
    )
    assert projected["data"] == [
        {key: rows[1][key] for key in ["slaConfigId", "holidayLimit"]}
    ]
    assert projected["meta"]["complete"] and projected["meta"]["has_more"]
    assert envelope(listing(run_cli, "--offset", "1")[1])["data"] == [rows[0]]
    assert "slaConfigId" in listing(run_cli, "--format", "table")[1]
    assert (
        "detailOnly"
        in getting(run_cli, "--id", "2", "--format", "table", "--fields", "detailOnly")[
            1
        ]
    )
    assert len(setup.state.transports) == before
    assert b"FAKE-CTOKEN-SECRET" not in setup.cache_path.read_bytes()


def test_cache_miss_live_nonwriting_and_null_not_missing(run_cli, envelope, setup):
    assert envelope(listing(run_cli)[1])["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    old = seed(run_cli, setup)
    setup.state.business_script.extend([page([row("3")]), detail("3")])
    assert envelope(listing(run_cli, "--live")[1])["data"] == [row("3")]
    result = envelope(getting(run_cli, "--live", "--id", "3")[1])
    assert result["meta"]["complete"] and result["data"]["detailOnly"]
    setup.state.business_script.append(
        {"status": 200, "body": {"success": True, "resultData": None}}
    )
    assert (
        envelope(getting(run_cli, "--id", "3", "--live")[1])["error"]["code"]
        == "INVALID_RESPONSE"
    )
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old
    assert (
        envelope(getting(run_cli, "--id", "absent")[1])["error"]["code"] == "NOT_FOUND"
    )


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"success": False}, "BUSINESS_QUERY_FAILED"),
        ({"pageNo": 1}, "INVALID_RESPONSE"),
        ({"pageSize": 10}, "INVALID_RESPONSE"),
        ({"totalCount": -1}, "INVALID_RESPONSE"),
        ({"totalCount": True}, "INVALID_RESPONSE"),
        ({"totalCount": 1001}, "INCOMPLETE_RESULT"),
        ({"totalCount": 2}, "INCOMPLETE_RESULT"),
        ({"resultDataList": None}, "INVALID_RESPONSE"),
        ({"resultDataList": [row(), row()], "totalCount": 2}, "INCOMPLETE_RESULT"),
        (
            {"resultDataList": [row(), row(endToEndSla=7)], "totalCount": 2},
            "INVALID_RESPONSE",
        ),
        ({"resultDataList": [row(slaConfigId=" ")]}, "INVALID_RESPONSE"),
        ({"resultDataList": [row(slaConfigId=1)]}, "INVALID_RESPONSE"),
        ({"resultDataList": ["bad"]}, "INVALID_RESPONSE"),
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
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


@pytest.mark.parametrize(
    "bad,expected",
    [
        ({"success": False}, "BUSINESS_QUERY_FAILED"),
        ({"success": True, "resultData": None}, "INVALID_RESPONSE"),
        ({"success": True, "resultData": row("wrong")}, "INVALID_RESPONSE"),
        ({"success": True, "resultData": row(endToEndSla=9)}, "INVALID_RESPONSE"),
    ],
)
def test_detail_failure_preserves_atomic_pair(run_cli, envelope, setup, bad, expected):
    old = seed(run_cli, setup)
    setup.state.business_script.extend([page(), {"status": 200, "body": bad}])
    result = refresh(run_cli)
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == expected
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


def test_interrupted_detail_preserves_snapshot(run_cli, setup):
    old = seed(run_cli, setup)

    def interrupted(payload, index):
        if "slaConfigId" in payload:
            raise KeyboardInterrupt
        return page([row("99")])

    setup.state.business_handler = interrupted
    assert refresh(run_cli)[0] == 130
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


def test_empty_scope(run_cli, envelope, setup):
    seed(run_cli, setup)
    setup.state.business_script.append(page([]))
    assert refresh(run_cli)[0] == 0
    assert envelope(listing(run_cli)[1])["data"] == []
    assert envelope(getting(run_cli, "--id", "1")[1])["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "status,expected", [(401, "AUTH_REQUIRED"), (403, "BUSINESS_QUERY_FAILED")]
)
def test_http_error_is_not_empty(run_cli, envelope, setup, status, expected):
    old = seed(run_cli, setup)
    setup.state.business_script.append({"status": status, "body": {}})
    assert envelope(listing(run_cli, "--live")[1])["error"]["code"] == expected
    assert listing(run_cli)[1] == old[0]


def test_offline_navigation_schema_and_arguments(run_cli, envelope, monkeypatch):
    monkeypatch.setattr(
        cli.config_mod, "load", lambda *args: pytest.fail("loaded config")
    )
    paths = [
        ("collection", "sla"),
        ("collection", "sla", "configs"),
        ("collection", "sla", "configs", "list"),
        ("collection", "sla", "configs", "get"),
        ("refresh", "collection", "sla"),
    ]
    for path in paths:
        assert run_cli(["help", *path])[0] == 0
        assert run_cli([*path, "--help"])[0] == 0
    for action, data in [("list", [row()]), ("get", detail()["body"]["resultData"])]:
        code, out, _ = run_cli(["describe", "collection", "sla", "configs", action])
        assert code == 0
        schema = envelope(out)["data_schema"]
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(data)
    for flags in [
        ("--all", "--limit", "1"),
        ("--limit", "0"),
        ("--offset", "-1"),
        ("--fields", " , "),
        ("--business-line", " "),
    ]:
        assert listing(run_cli, *flags)[0] == 2
    for flags in [(), ("--id", ""), ("--id", " "), ("--id", "1", "--limit", "1")]:
        assert getting(run_cli, *flags)[0] == 2


def test_transport_restrictions_before_browser(setup):
    from dogopencli.plugins.collection.sla import COLLECTION_SLA, COLLECTION_SLA_DETAIL

    for cap, body in [
        (COLLECTION_SLA, {"pageNo": 0, "pageSize": 1000}),
        (COLLECTION_SLA_DETAIL, {"slaConfigId": "1"}),
    ]:
        transport = CdpQueryTransport(
            setup.state.transport("http://127.0.0.1:9222"),
            cap,
            page_url="https://ifundcontrol.alipay.com",
        )
        request = QueryRequest(
            cap.name, cap.contract.method, cap.contract.host, cap.contract.path, body
        )
        for change in [
            {"path": "/api/fundInSlaConfig/save.json"},
            {"host": "evil.example"},
            {"method": "DELETE"},
            {"body": {**body, "action": "save"}},
            {"capability": "payment.sla.baselines.list"},
        ]:
            with pytest.raises(CliError) as caught:
                transport.execute(replace(request, **change))
            assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert not setup.state.business_requests
    assert not any(t.created for t in setup.state.transports)


def test_payment_and_collection_cache_isolation(run_cli, envelope, setup):
    from test_sla_cli_sit import detail_outcome, list_page, sla_row

    setup.state.business_script.extend(
        [list_page([sla_row("900")]), detail_outcome("900")]
    )
    assert run_cli(["refresh", "payment", "sla"])[0] == 0
    payment_before = run_cli(["payment", "sla", "baselines", "list"])[1]
    seed(run_cli, setup)
    assert run_cli(["payment", "sla", "baselines", "list"])[1] == payment_before
    assert envelope(listing(run_cli)[1])["data"][0]["slaConfigId"] == "1"


def test_freshness_and_incomplete_cache_requirements(run_cli, envelope, setup):
    import sqlite3

    seed(run_cli, setup)
    config = setup.tmp_path / "config.toml"
    config.write_text(config.read_text().replace("ttl_hours = 72", "ttl_hours = 0"))
    for query in [
        lambda *flags: listing(run_cli, *flags),
        lambda *flags: getting(run_cli, "--id", "1", *flags),
    ]:
        assert envelope(query()[1])["meta"]["stale"]
        assert envelope(query("--require-fresh")[1])["error"]["code"] == "CACHE_STALE"
        assert query("--require-complete")[0] == 0
    with sqlite3.connect(setup.cache_path) as connection:
        # Synthetic incomplete metadata; production snapshots remain untouched.
        connection.execute(
            "UPDATE snapshots SET backend_complete = 0, acquisition = NULL"
        )
    for query in [
        lambda *flags: listing(run_cli, *flags),
        lambda *flags: getting(run_cli, "--id", "1", *flags),
    ]:
        assert (
            envelope(query("--require-complete")[1])["error"]["code"]
            == "INCOMPLETE_RESULT"
        )


def test_last_detail_failure_and_deadline_preserve_all_rows(
    run_cli, envelope, setup, monkeypatch
):
    import dogopencli.collect as collect_mod

    old = seed(run_cli, setup)
    setup.state.business_script.extend(
        [page([row("2"), row("3")]), detail("2"), detail("3", creditorCurrency="EUR")]
    )
    assert envelope(refresh(run_cli)[1])["error"]["code"] == "INVALID_RESPONSE"
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old
    clock = [0.0]
    monkeypatch.setattr(collect_mod, "_monotonic", lambda: clock[0])
    monkeypatch.setattr(collect_mod, "REFRESH_BUDGET_SECONDS", 1.0)

    def delayed(payload, index):
        if "slaConfigId" in payload:
            clock[0] += 2
            return detail()
        return page()

    setup.state.business_handler = delayed
    assert envelope(refresh(run_cli)[1])["error"]["code"] == "TIMEOUT"
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


def test_detail_retries_authentication_and_business_failures(
    run_cli, envelope, setup, monkeypatch
):
    import dogopencli.collect as collect_mod

    waits = []
    monkeypatch.setattr(collect_mod, "_sleep", waits.append)
    setup.state.business_script.extend([{"status": 503, "body": {}}] * 2 + [detail()])
    assert getting(run_cli, "--id", "1", "--live")[0] == 0
    assert waits == [1.0, 2.0]
    for response, code in [
        ({"status": 401, "body": {}}, "AUTH_REQUIRED"),
        ({"status": 403, "body": {}}, "BUSINESS_QUERY_FAILED"),
        ({"status": 200, "body": {"success": False}}, "BUSINESS_QUERY_FAILED"),
    ]:
        setup.state.business_script.append(response)
        assert (
            envelope(getting(run_cli, "--id", "1", "--live")[1])["error"]["code"]
            == code
        )
    assert not setup.cache_path.exists()


FILTERS = [
    ("--business-line", "businessCategory"),
    ("--entity", "legalEntityCode"),
    ("--currency", "creditorCurrency"),
    ("--region", "creditorRegion"),
]


@pytest.mark.parametrize("flag,field", FILTERS)
def test_local_filters_identical_cached_live(run_cli, envelope, setup, flag, field):
    rows = [
        row("20", **{field: "A"}),
        row("2", **{field: "B"}),
        row("3", **{field: "*"}),
        row("4", **{field: None}),
        row("5"),
        row("6", **{field: " A "}),
    ]
    del rows[4][field]
    setup.state.business_script.append(page(rows))
    setup.state.business_script.extend(
        {
            "status": 200,
            "body": {"success": True, "resultData": {field: None, **record}},
        }
        for record in sorted(rows, key=lambda record: int(record["slaConfigId"]))
    )
    assert refresh(run_cli)[0] == 0
    before = setup.cache_path.read_bytes()
    cases = [
        ([flag, "A"], ["20"]),
        ([flag, "A", flag, "B"], ["2", "20"]),
        ([flag, "A", flag, "B", "--limit", "1", "--offset", "1"], ["20"]),
        ([flag, "*"], ["3"]),
        ([flag, "a"], []),
        ([flag, " A "], ["6"]),
        ([flag, "no-match"], []),
    ]
    for flags, ids in cases:
        for live in [False, True]:
            requests = len(setup.state.business_requests)
            if live:
                setup.state.business_script.append(page(rows))
            code, out, _ = listing(run_cli, *flags, *(["--live"] if live else []))
            assert code == 0, out
            result = envelope(out)
            assert [record["slaConfigId"] for record in result["data"]] == ids
            assert result["meta"]["complete"] and not result["meta"]["stale"]
            assert len(setup.state.business_requests) == requests + int(live)
            if live:
                assert setup.state.business_requests[-1] == {
                    "pageNo": 0,
                    "pageSize": 1000,
                }
    assert setup.cache_path.read_bytes() == before


def test_local_filter_cross_field_and_before_window(run_cli, envelope, setup):
    rows = [
        row("10"),
        row("2"),
        row("3", creditorRegion="SG"),
        row("4", creditorCurrency="EUR"),
        row("5", legalEntityCode="OTHER"),
        row("6", businessCategory="OTHER"),
    ]
    setup.state.business_script.append(page(rows))
    setup.state.business_script.extend(
        {"status": 200, "body": {"success": True, "resultData": record}}
        for record in sorted(rows, key=lambda record: int(record["slaConfigId"]))
    )
    assert refresh(run_cli)[0] == 0
    flags = [
        "--business-line",
        "SYNTHETIC",
        "--entity",
        "ENTITY",
        "--currency",
        "USD",
        "--region",
        "US",
        "--limit",
        "1",
    ]
    for live in [False, True]:
        if live:
            setup.state.business_script.append(page(rows))
        result = envelope(listing(run_cli, *flags, *(["--live"] if live else []))[1])
        assert [record["slaConfigId"] for record in result["data"]] == ["2"]
        assert result["meta"]["matched_total"] == 2
        assert result["meta"]["complete"] and result["meta"]["has_more"]


@pytest.mark.parametrize("flag,field", FILTERS)
def test_filter_validation_and_scope_before_network(run_cli, setup, flag, field):
    for flags in [[flag], [flag, ""], [flag, " \t"], [flag, "A", flag, ""]]:
        assert listing(run_cli, "--live", *flags)[0] == 2
    assert getting(run_cli, "--id", "1", flag, "A")[0] == 2
    assert run_cli(["refresh", "collection", "sla", flag, "A"])[0] == 2
    assert setup.state.transports == []


def test_filtered_live_permission_failure_is_not_no_match(run_cli, envelope, setup):
    setup.state.business_script.append({"status": 403, "body": {}})
    code, out, _ = listing(run_cli, "--live", "--currency", "no-match")
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"


@pytest.mark.parametrize(
    "field",
    [
        "businessCategory",
        "legalEntityCode",
        "creditorCurrency",
        "creditorRegion",
        "endToEndSla",
        "ipayInnerSla",
        "holidayLimit",
    ],
)
@pytest.mark.parametrize("live", [False, True])
def test_incomplete_detail_rejected_without_replacing_cache(
    run_cli, envelope, setup, field, live
):
    old = seed(run_cli, setup)
    response = detail()
    del response["body"]["resultData"][field]
    if not live:
        setup.state.business_script.append(page())
    setup.state.business_script.append(response)
    result = getting(run_cli, "--live", "--id", "1") if live else refresh(run_cli)
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INVALID_RESPONSE"
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


@pytest.mark.parametrize(
    "holiday",
    [
        {},
        {"currencyCodes": []},
        {"currencyCodes": "USD", "regionCodes": []},
        {"currencyCodes": [], "regionCodes": [1]},
    ],
)
def test_malformed_holiday_detail_rejected(run_cli, envelope, setup, holiday):
    setup.state.business_script.append(detail(holidayLimit=holiday))
    result = getting(run_cli, "--live", "--id", "1")
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


def test_detail_must_preserve_list_extension_but_not_list_only_field(
    run_cli, envelope, setup
):
    old = seed(run_cli, setup)
    response = detail()
    del response["body"]["resultData"]["unknownExtension"]
    setup.state.business_script.extend([page(), response])
    result = refresh(run_cli)
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INVALID_RESPONSE"
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old
    setup.state.business_script.extend(
        [page([row(viewProcessInstanceRequired=True)]), detail()]
    )
    assert refresh(run_cli)[0] == 0
    assert (
        "viewProcessInstanceRequired"
        not in envelope(getting(run_cli, "--id", "1")[1])["data"]
    )


def test_explicit_nullable_detail_values_preserved(run_cli, envelope, setup):
    changes = dict(businessCategory=None, endToEndSla=None, holidayLimit=None)
    setup.state.business_script.extend([page([row(**changes)]), detail(**changes)])
    assert refresh(run_cli)[0] == 0
    result = envelope(getting(run_cli, "--id", "1")[1])["data"]
    assert all(result[key] is None for key in changes)


@pytest.mark.parametrize("total,omit", [(0, True), (1, True), (0, False)])
def test_omitted_empty_rows_and_invalid_absence(run_cli, envelope, setup, total, omit):
    old = seed(run_cli, setup)
    response = page([], totalCount=total)
    if omit:
        del response["body"]["resultDataList"]
    else:
        response["body"]["resultDataList"] = None
    setup.state.business_script.append(response)
    result = refresh(run_cli)
    if total == 0 and omit:
        assert result[0] == 0
        setup.state.running = False
        cached = envelope(listing(run_cli, "--require-complete")[1])
        assert cached["data"] == [] and cached["meta"]["complete"]
        assert (
            envelope(getting(run_cli, "--id", "1")[1])["error"]["code"] == "NOT_FOUND"
        )
    else:
        assert result[0] == 1
        assert envelope(result[1])["error"]["code"] == "INVALID_RESPONSE"
        assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


def test_stable_id_order_preserves_original_strings(run_cli, envelope, setup):
    identities = ["20", "2", "02", "a", "١", "²", "A"]
    setup.state.business_script.append(page([row(identity) for identity in identities]))
    result = envelope(listing(run_cli, "--live", "--all")[1])
    assert [record["slaConfigId"] for record in result["data"]] == [
        "02",
        "2",
        "20",
        "A",
        "a",
        "²",
        "١",
    ]
    help_text = run_cli(["help", "collection", "sla", "configs", "list"])[1]
    assert "ASCII" in help_text and "original string" in help_text


@pytest.mark.parametrize("action", ["list", "get", "refresh"])
def test_permission_http_evidence_preserved_without_retry_or_cache_change(
    run_cli, envelope, setup, action
):
    old = seed(run_cli, setup)
    count = len(setup.state.business_requests)
    if action == "refresh":
        setup.state.business_script.append(page())
    setup.state.business_script.append({"status": 403, "body": {}})
    if action == "list":
        result = listing(run_cli, "--live")
    elif action == "get":
        result = getting(run_cli, "--live", "--id", "1")
    else:
        result = refresh(run_cli)
    assert result[0] == 1
    error = envelope(result[1])["error"]
    assert error["code"] == "BUSINESS_QUERY_FAILED"
    assert "403" in error["message"]
    assert error["retryable"] is False
    assert len(setup.state.business_requests) == count + 1 + int(action == "refresh")
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


def test_unverified_backend_denial_text_not_classified_or_leaked(
    run_cli, envelope, setup
):
    setup.state.business_script.append(
        {
            "status": 200,
            "body": {
                "success": False,
                "errorContext": {"message": "permission denied SENSITIVE-CONTEXT"},
            },
        }
    )
    code, out, _ = getting(run_cli, "--live", "--id", "1")
    assert code == 1
    assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert "SENSITIVE-CONTEXT" not in out
    assert len(setup.state.business_requests) == 1
