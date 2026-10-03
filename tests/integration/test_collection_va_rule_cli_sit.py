"""Collection VA rule public CLI + fake CDP + real SQLite acceptance (#32)."""

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
        file.write('\n[sources.collection_va]\nkind = "cdp"\n')
    return sla_setup


def row(identity="1", **changes):
    return {
        "vaRuleId": identity,
        "bankRuleId": 7001,
        "aliasName": "SYNTHETIC-ALIAS",
        "bankAccountNo": "SYNTHETIC-ACCOUNT",
        "financialInst": "SYNTHETIC-INST",
        "reconInst": "SYNTHETIC-RECON",
        "entity": "SYNTHETIC-ENTITY",
        "currency": "USD",
        "memo": "synthetic memo",
        "operator": "synthetic-operator",
        "assembleStrategy": "SYNTHETIC-STRATEGY",
        "regionType": "SYNTHETIC-REGION",
        "ruleStatus": "ENABLED",
        "countries": ["US", "SG"],
        "sceneCodes": ["SYNTHETIC-SCENE"],
        "supportMultiCurrency": False,
        "gmtCreate": 1694000000000,
        "gmtModified": 1694100000000,
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


def detail(identity="1", **changes):
    base = row(identity)
    result = {
        "vaRuleId": identity,
        "bankRuleId": base["bankRuleId"],
        "assembleStrategy": base["assembleStrategy"],
        "entity": base["entity"],
        "memo": base["memo"],
        "regionType": base["regionType"],
        "ruleStatus": base["ruleStatus"],
        "sceneCodes": base["sceneCodes"],
        "clientEntity": "SYNTHETIC-CLIENT",
        "creditAreas": ["US", "SG"],
        "assignInfo": {
            "assignCount": 0,
            "assignFlows": [],
            "ruleVaTotal": 3,
            "vaAssignAble": 3,
            "vaAssigned": 0,
            "vaImported": 0,
            "vaRuleId": identity,
            "vaUnused": 3,
            "vaUsed": 0,
        },
        "vaWarningInfo": {"warningCount": 0},
    }
    result.update(changes)
    return {"status": 200, "body": {"success": True, "resultObj": result}}


def refusal():
    """The observed platform refusal: HTTP 200 declaring success=false."""
    return {"status": 200, "body": {"success": False, "errorCode": "SYNTHETIC-REFUSAL"}}


def listing(run_cli, *flags):
    return run_cli(["collection", "va", "rules", "list", *flags])


def getting(run_cli, *flags):
    return run_cli(["collection", "va", "rules", "get", *flags])


def refresh(run_cli, *flags):
    return run_cli(["refresh", "collection", "va", *flags])


def seed(run_cli, setup):
    setup.state.business_script.extend([page(), detail()])
    assert refresh(run_cli)[0] == 0
    return listing(run_cli)[1], getting(run_cli, "--id", "1")[1]


def test_refresh_publishes_pairs_and_offline_reads(run_cli, envelope, setup):
    rows = [row("20"), row("2")]
    setup.state.business_script.extend([page(rows), detail("2"), detail("20")])
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    result = envelope(out)
    assert result["data"]["namespace"] == "collection.va.rules.list:rules:cdp"
    assert result["data"]["row_count"] == 2
    assert setup.state.business_requests == [
        {"pageNo": 1, "pageSize": 1000},
        {"vaRuleId": "2"},
        {"vaRuleId": "20"},
    ]
    expressions = [
        expression
        for transport in setup.state.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert len(expressions) == 3
    assert "virtualAccountRule/list.json" in expressions[0]
    assert 'method: "POST"' in expressions[0]
    for expression in expressions[1:]:
        assert "virtualAccountRule/detail.json" in expression
        assert 'method: "GET"' in expression
        # vaRuleId rides the URL query, never a JSON body.
        assert "URLSearchParams" in expression
    before = len(setup.state.transports)
    setup.state.running = False
    listed = envelope(
        listing(run_cli, "--all", "--require-fresh", "--require-complete")[1]
    )
    assert listed["data"] == list(reversed(rows))
    assert listed["meta"]["complete"] and not listed["meta"]["has_more"]
    for identity in ["2", "20"]:
        code, out, _ = getting(
            run_cli, "--id", identity, "--require-fresh", "--require-complete"
        )
        assert code == 0
        detail_data = envelope(out)["data"]
        assert detail_data == detail(identity)["body"]["resultObj"]
        # List-only fields never leak into the true detail.
        assert "countries" not in detail_data
        assert "bankAccountNo" not in detail_data
    assert len(setup.state.transports) == before
    assert b"FAKE-CTOKEN-SECRET" not in setup.cache_path.read_bytes()


def test_cache_miss_directs_refresh_and_live_never_writes_cache(
    run_cli, envelope, setup
):
    code, out, _ = listing(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_MISS"
    assert "refresh collection va" in envelope(out)["error"]["message"]
    assert envelope(getting(run_cli, "--id", "1")[1])["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []

    old = seed(run_cli, setup)
    digest = setup.cache_path.read_bytes()
    setup.state.business_script.append(page([row("3")]))
    code, out, _ = listing(run_cli, "--live")
    assert code == 0
    live_list = envelope(out)
    assert live_list["meta"]["source"] == "live"
    assert live_list["data"] == [row("3")]
    setup.state.business_script.append(detail("3"))
    code, out, _ = getting(run_cli, "--id", "3", "--live")
    assert code == 0
    live_get = envelope(out)
    assert live_get["data"]["clientEntity"] == "SYNTHETIC-CLIENT"
    assert live_get["meta"]["query"] == {
        "capability": "collection.va.rules.get",
        "id": "3",
    }
    # A live null detail is an explicit failure, never a cached substitute.
    setup.state.business_script.append(
        {"status": 200, "body": {"success": True, "resultObj": None}}
    )
    assert (
        envelope(getting(run_cli, "--id", "3", "--live")[1])["error"]["code"]
        == "INVALID_RESPONSE"
    )
    assert setup.cache_path.read_bytes() == digest
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old
    assert envelope(getting(run_cli, "--id", "absent")[1])["error"]["code"] == (
        "NOT_FOUND"
    )


def test_overflow_and_detail_mismatch_preserve_snapshot(run_cli, envelope, setup):
    old = seed(run_cli, setup)
    setup.state.business_script.append(page([row()], totalCount=1001))
    result = refresh(run_cli, "--require-complete")
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INCOMPLETE_RESULT"
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old

    mismatched = detail()
    mismatched["body"]["resultObj"]["ruleStatus"] = "DRIFTED"
    setup.state.business_script.extend([page(), mismatched])
    result = refresh(run_cli, "--require-complete")
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INVALID_RESPONSE"
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


def test_offline_help_describe_and_bare_navigation(run_cli, envelope, monkeypatch):
    monkeypatch.setattr(
        cli.config_mod, "load", lambda *args: pytest.fail("loaded config")
    )
    groups = [("collection", "va"), ("collection", "va", "rules")]
    leaves = [
        ("collection", "va", "rules", "list"),
        ("collection", "va", "rules", "get"),
        ("refresh", "collection", "va"),
    ]
    for path in groups:
        assert run_cli(list(path))[0] == 0
    for path in groups + leaves:
        assert run_cli(["help", *path])[0] == 0
        assert run_cli([*path, "--help"])[0] == 0
    list_help = run_cli(["help", "collection", "va", "rules", "list"])[1]
    assert "ASCII" in list_help and "original string" in list_help
    assert "bankRuleId" in list_help
    get_help = run_cli(["help", "collection", "va", "rules", "get"])[1]
    assert "bankAccountVaRule" in get_help
    for action, data in [("list", [row()]), ("get", detail()["body"]["resultObj"])]:
        code, out, _ = run_cli(["describe", "collection", "va", "rules", action])
        assert code == 0
        document = envelope(out)
        assert document["read_guide"]["evidence"].endswith(
            "2026-09-26-collection-va-rule-contract-recheck.md"
        )
        schema = document["data_schema"]
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(data)
    detail_schema = envelope(
        run_cli(["describe", "collection", "va", "rules", "get"])[1]
    )["data_schema"]
    assert set(detail_schema["properties"]["assignInfo"]["properties"]) == {
        "assignCount",
        "assignFlows",
        "ruleVaTotal",
        "vaAssignAble",
        "vaAssigned",
        "vaImported",
        "vaRuleId",
        "vaUnused",
        "vaUsed",
    }
    assert "vaWarningInfo" in detail_schema["properties"]
    assert "vaWarningInfo" not in detail_schema["required"]


def test_describe_guidance_matches_refusal_semantics(run_cli, envelope):
    """Review finding: describe must not promise atomicity ADR 0010 removed."""
    guides = [
        envelope(run_cli(["describe", "collection", "va", "rules", action])[1])[
            "read_guide"
        ]
        for action in ("list", "get")
    ]
    for guide in guides:
        refresh = guide["access_modes"]["refresh"]
        assert "Any failure preserves" not in refresh
        assert "null detail" in refresh
        assert "INCOMPLETE_RESULT" in refresh
    detail_schema = envelope(
        run_cli(["describe", "collection", "va", "rules", "get"])[1]
    )["data_schema"]
    assert (
        "does not prove assignment history is empty"
        in detail_schema["properties"]["assignInfo"]["description"]
    )


def test_unsupported_domain_filters_rejected_before_browser(run_cli, envelope, setup):
    for argv in [
        ["collection", "va", "rules", "list", "--entity", "SYNTHETIC"],
        ["collection", "va", "rules", "list", "--live", "--alias-name", "X"],
        ["collection", "va", "rules", "get", "--id", "1", "--currency", "USD"],
        ["refresh", "collection", "va", "--rule-status", "ENABLED"],
    ]:
        code, out, _ = run_cli(argv)
        assert code == 2, argv
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert setup.state.business_requests == []


def test_transport_restrictions_before_browser(setup):
    from dogopencli.plugins.collection.va_rule import (
        COLLECTION_VA_RULES,
        COLLECTION_VA_RULES_DETAIL,
    )

    for capability, body in [
        (COLLECTION_VA_RULES, {"pageNo": 1, "pageSize": 1000}),
        (COLLECTION_VA_RULES_DETAIL, {"vaRuleId": "1"}),
    ]:
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
            body,
        )
        for change in [
            {"path": "/ivostro/api/virtualAccountRule/save.json"},
            {"host": "evil.example"},
            {"method": "DELETE"},
            {"body": {**body, "action": "save"}},
            {"body": {"pageNo": 1, "pageSize": 10}},
            {"capability": "collection.sla.configs.list"},
        ]:
            with pytest.raises(CliError) as caught:
                transport.execute(replace(request, **change))
            assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert not setup.state.business_requests
    assert not any(t.created for t in setup.state.transports)


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"success": False}, "BUSINESS_QUERY_FAILED"),
        ({"pageNo": 0}, "INVALID_RESPONSE"),
        ({"pageNo": 2}, "INVALID_RESPONSE"),
        ({"pageSize": 10}, "INVALID_RESPONSE"),
        ({"totalCount": -1}, "INVALID_RESPONSE"),
        ({"totalCount": True}, "INVALID_RESPONSE"),
        ({"totalCount": 1001}, "INCOMPLETE_RESULT"),
        ({"totalCount": 2}, "INCOMPLETE_RESULT"),
        ({"resultDataList": None}, "INVALID_RESPONSE"),
        ({"resultDataList": [row(), row()], "totalCount": 2}, "INCOMPLETE_RESULT"),
        ({"resultDataList": [row()], "totalCount": 0}, "INVALID_RESPONSE"),
        ({"resultDataList": [row(vaRuleId=" ")]}, "INVALID_RESPONSE"),
        ({"resultDataList": [row(vaRuleId="")]}, "INVALID_RESPONSE"),
        ({"resultDataList": [row(vaRuleId=1)]}, "INVALID_RESPONSE"),
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
    "body,expected",
    [
        ({"errorCode": "SYNTHETIC-REFUSAL"}, "BUSINESS_QUERY_FAILED"),
        ({"success": None}, "BUSINESS_QUERY_FAILED"),
        ({"success": True, "resultObj": None}, "INVALID_RESPONSE"),
        (
            {"success": True, "resultObj": detail("wrong")["body"]["resultObj"]},
            "INVALID_RESPONSE",
        ),
    ],
)
def test_detail_failure_preserves_snapshot(run_cli, envelope, setup, body, expected):
    old = seed(run_cli, setup)
    setup.state.business_script.extend([page(), {"status": 200, "body": body}])
    result = refresh(run_cli)
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == expected
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


@pytest.mark.parametrize("status", [401, 403])
def test_detail_refusal_boundary_preserves_snapshot(run_cli, envelope, setup, status):
    """Only an explicit success=false refusal is tolerated (ADR 0010)."""
    old = seed(run_cli, setup)
    setup.state.business_script.extend(
        [page([row("1"), row("2")]), detail("1"), {"status": status, "body": {}}]
    )
    result = refresh(run_cli)
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == (
        "AUTH_REQUIRED" if status == 401 else "BUSINESS_QUERY_FAILED"
    )
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


def test_refused_detail_publishes_partial_snapshot(run_cli, envelope, setup):
    rows = [row("2"), row("20")]
    setup.state.business_script.extend([page(rows), detail("2"), refusal()])
    code, out, err = refresh(run_cli)
    assert code == 0
    result = envelope(out)
    assert result["error"] is None
    assert result["data"]["published"] is True
    assert result["meta"]["published"] is True
    assert result["meta"]["acquisition"]["reasons"] == ["DETAIL_REFUSED"]
    assert "INCOMPLETE_RESULT" in err
    assert "SYNTHETIC-REFUSAL" not in out
    listed = envelope(listing(run_cli, "--all")[1])
    assert [record["vaRuleId"] for record in listed["data"]] == ["2", "20"]
    # The list scope is still complete; only the detail dataset is not.
    assert listed["meta"]["complete"] is True
    assert listed["meta"]["dataset_complete"] is False


def test_partial_snapshot_reads_report_the_missing_detail(run_cli, envelope, setup):
    rows = [row("2"), row("20")]
    setup.state.business_script.extend([page(rows), detail("2"), refusal()])
    assert refresh(run_cli)[0] == 0
    missing = getting(run_cli, "--id", "20")
    assert missing[0] == 1
    assert envelope(missing[1])["error"]["code"] == "INCOMPLETE_RESULT"
    # A refusal never answers with the list row.
    assert envelope(missing[1])["data"] is None
    healthy = envelope(getting(run_cli, "--id", "2")[1])
    assert healthy["data"] == detail("2")["body"]["resultObj"]
    assert envelope(getting(run_cli, "--id", "999")[1])["error"]["code"] == "NOT_FOUND"
    for result in [
        listing(run_cli, "--require-complete"),
        getting(run_cli, "--id", "2", "--require-complete"),
    ]:
        assert result[0] == 1
        assert envelope(result[1])["error"]["code"] == "INCOMPLETE_RESULT"


def test_strict_detail_refusal_never_publishes(run_cli, envelope, setup):
    old = seed(run_cli, setup)
    cache_bytes = setup.cache_path.read_bytes()
    setup.state.business_script.extend([page(), refusal()])
    code, out, _ = refresh(run_cli, "--require-complete")
    assert code == 1
    result = envelope(out)
    assert result["data"] is None
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["meta"]["published"] is False
    assert result["meta"]["acquisition"]["reasons"] == ["DETAIL_REFUSED"]
    assert setup.cache_path.read_bytes() == cache_bytes
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


def test_partial_list_detail_absence_is_unknown_and_found_detail_is_real(
    run_cli,
    envelope,
    setup,
):
    setup.state.business_script.extend([page(totalCount=2), detail()])
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    assert envelope(out)["meta"]["complete"] is False
    found = envelope(getting(run_cli, "--id", "1")[1])
    assert found["data"] == detail()["body"]["resultObj"]
    missing = envelope(getting(run_cli, "--id", "absent")[1])
    assert missing["data"] is None
    assert missing["error"]["code"] == "INCOMPLETE_RESULT"


DETAIL_REQUIRED_FIELDS = [
    "assembleStrategy",
    "assignInfo",
    "bankRuleId",
    "clientEntity",
    "creditAreas",
    "entity",
    "memo",
    "regionType",
    "ruleStatus",
    "sceneCodes",
    "vaRuleId",
]


@pytest.mark.parametrize("field", DETAIL_REQUIRED_FIELDS)
@pytest.mark.parametrize("live", [False, True])
def test_incomplete_detail_rejected_without_replacing_cache(
    run_cli, envelope, setup, field, live
):
    old = seed(run_cli, setup)
    response = detail()
    del response["body"]["resultObj"][field]
    if not live:
        setup.state.business_script.append(page())
    setup.state.business_script.append(response)
    result = getting(run_cli, "--id", "1", "--live") if live else refresh(run_cli)
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INVALID_RESPONSE"
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


def test_interrupted_detail_preserves_snapshot(run_cli, setup):
    old = seed(run_cli, setup)

    def interrupted(payload, index):
        if "vaRuleId" in payload:
            raise KeyboardInterrupt
        return page([row("99")])

    setup.state.business_handler = interrupted
    assert refresh(run_cli)[0] == 130
    setup.state.business_handler = None
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


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
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old
    setup.state.business_script.extend([page(), detail()])
    assert refresh(run_cli)[0] == 0


@pytest.mark.parametrize("omit", [False, True])
def test_empty_scope_publishes_empty_snapshot(run_cli, envelope, setup, omit):
    response = page([])
    if omit:
        del response["body"]["resultDataList"]
    setup.state.business_script.append(response)
    code, out, _ = refresh(run_cli)
    assert code == 0
    assert envelope(out)["data"]["row_count"] == 0
    setup.state.running = False
    listed = envelope(listing(run_cli, "--require-complete")[1])
    assert listed["data"] == []
    assert listed["meta"]["complete"] is True
    for identity in ["1", "absent"]:
        code, out, _ = getting(run_cli, "--id", identity)
        assert code == 1
        assert envelope(out)["error"]["code"] == "NOT_FOUND"


def test_freshness_and_completeness_requirements(run_cli, envelope, setup):
    import sqlite3

    seed(run_cli, setup)
    config = setup.tmp_path / "config.toml"
    config.write_text(config.read_text().replace("ttl_hours = 72", "ttl_hours = 0"))
    assert envelope(listing(run_cli)[1])["meta"]["stale"] is True
    assert envelope(getting(run_cli, "--id", "1")[1])["meta"]["stale"] is True
    for query in [
        lambda *flags: listing(run_cli, *flags),
        lambda *flags: getting(run_cli, "--id", "1", *flags),
    ]:
        assert envelope(query("--require-fresh")[1])["error"]["code"] == "CACHE_STALE"
        assert query("--require-complete")[0] == 0
    with sqlite3.connect(setup.cache_path) as connection:
        # Synthetic incomplete metadata; production snapshots remain untouched.
        connection.execute(
            "UPDATE snapshots SET backend_complete = 0, acquisition = NULL"
        )
    assert (
        envelope(listing(run_cli, "--require-complete")[1])["error"]["code"]
        == "INCOMPLETE_RESULT"
    )
    # Absence cannot be confirmed against an incomplete snapshot.
    assert (
        envelope(getting(run_cli, "--id", "absent")[1])["error"]["code"]
        == "INCOMPLETE_RESULT"
    )
    # A present ID still resolves from the incomplete snapshot.
    assert getting(run_cli, "--id", "1")[0] == 0


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("drift", "INVALID_RESPONSE"),
        ("duplicate", "INCOMPLETE_RESULT"),
        ("missing", "INCOMPLETE_RESULT"),
    ],
)
def test_cached_pair_revalidation_surfaces_distinctly(
    run_cli, envelope, setup, mode, expected
):
    import json
    import sqlite3

    setup.state.business_script.extend(
        [page([row("1"), row("2")]), detail("1"), detail("2")]
    )
    assert refresh(run_cli)[0] == 0
    ns = "collection.va.rules.list:rules:cdp"
    with sqlite3.connect(setup.cache_path) as connection:
        # Synthetic cache corruption exercises read-time re-validation only.
        bodies = dict(
            connection.execute(
                "SELECT seqid, body FROM records WHERE namespace = ?", (ns,)
            )
        )
        if mode == "drift":
            pair = json.loads(bodies[1])
            pair["detail"]["ruleStatus"] = "DRIFTED"
            connection.execute(
                "UPDATE records SET body = ? WHERE namespace = ? AND seqid = 1",
                (json.dumps(pair), ns),
            )
        elif mode == "duplicate":
            pair = json.loads(bodies[2])
            pair["rule"]["vaRuleId"] = "1"
            pair["detail"]["vaRuleId"] = "1"
            connection.execute(
                "UPDATE records SET body = ? WHERE namespace = ? AND seqid = 2",
                (json.dumps(pair), ns),
            )
        else:
            connection.execute(
                "DELETE FROM records WHERE namespace = ? AND seqid = 2", (ns,)
            )
    for out in [listing(run_cli)[1], getting(run_cli, "--id", "1")[1]]:
        assert envelope(out)["error"]["code"] == expected


def test_offline_get_never_substitutes_list_row(run_cli, envelope, setup):
    setup.state.business_script.extend(
        [page(), detail("1", clientEntity="SYNTHETIC-DETAIL-ONLY")]
    )
    assert refresh(run_cli)[0] == 0
    setup.state.running = False
    data = envelope(getting(run_cli, "--id", "1")[1])["data"]
    # The cached detail object, not the list row, answers an offline get.
    assert data["clientEntity"] == "SYNTHETIC-DETAIL-ONLY"
    for list_only in ["aliasName", "bankAccountNo", "countries"]:
        assert list_only not in data


def test_live_detail_failures_are_explicit_never_not_found(run_cli, envelope, setup):
    old = seed(run_cli, setup)
    digest = setup.cache_path.read_bytes()
    missing = detail()
    del missing["body"]["resultObj"]["assignInfo"]
    codes = []
    for body in [
        missing["body"],
        {
            "success": False,
            "errorContext": {"message": "denied SENSITIVE-CONTEXT"},
        },
    ]:
        setup.state.business_script.append({"status": 200, "body": body})
        code, out, _ = getting(run_cli, "--id", "1", "--live")
        assert code == 1
        assert "SENSITIVE-CONTEXT" not in out
        codes.append(envelope(out)["error"]["code"])
    assert codes == ["INVALID_RESPONSE", "BUSINESS_QUERY_FAILED"]
    assert setup.cache_path.read_bytes() == digest
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


@pytest.mark.parametrize("action", ["list", "get", "refresh"])
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
        if action == "list":
            result = listing(run_cli, "--live")
        elif action == "get":
            result = getting(run_cli, "--id", "1", "--live")
        else:
            result = refresh(run_cli)
        assert result[0] == 1
        assert envelope(result[1])["error"]["code"] == "AUTH_REQUIRED"
        assert "PRIVATE" not in result[1]
        assert "PRIVATE" not in result[2]
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


@pytest.mark.parametrize("status", [400, 403])
@pytest.mark.parametrize("action", ["list", "get", "refresh"])
def test_non_retryable_status_preserves_evidence_without_retry_or_cache_change(
    run_cli, envelope, setup, status, action
):
    old = seed(run_cli, setup)
    count = len(setup.state.business_requests)
    setup.state.business_script.append(
        {"status": status, "body": {"error": "SENSITIVE-DENIAL"}}
    )
    if action == "list":
        result = listing(run_cli, "--live")
    elif action == "get":
        result = getting(run_cli, "--id", "1", "--live")
    else:
        result = refresh(run_cli)
    assert result[0] == 1
    error = envelope(result[1])["error"]
    assert error["code"] == "BUSINESS_QUERY_FAILED"
    assert str(status) in error["message"]
    assert error["retryable"] is False
    assert "SENSITIVE-DENIAL" not in result[1]
    assert len(setup.state.business_requests) == count + 1
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


def test_detail_retries_retryable_statuses_with_bounded_waits(
    run_cli, envelope, setup, monkeypatch
):
    import dogopencli.collect as collect_mod

    waits = []
    monkeypatch.setattr(collect_mod, "_sleep", waits.append)
    setup.state.business_script.extend([{"status": 503, "body": {}}] * 2 + [detail()])
    code, out, _ = getting(run_cli, "--id", "1", "--live")
    assert code == 0
    assert envelope(out)["data"]["clientEntity"] == "SYNTHETIC-CLIENT"
    assert waits == [1.0, 2.0]

    waits.clear()
    setup.state.business_script.extend([{"status": 503, "body": {}}] * 3)
    code, out, _ = getting(run_cli, "--id", "1", "--live")
    assert code == 1
    error = envelope(out)["error"]
    assert error["code"] == "BUSINESS_QUERY_FAILED"
    assert error["retryable"] is True
    assert "503" in error["message"]
    assert waits == [1.0, 2.0]
    assert not setup.cache_path.exists()


def test_windowing_flag_boundaries_conflicts_and_id_validation(
    run_cli, envelope, setup
):
    for flags in [
        ("--all", "--limit", "1"),
        ("--all", "--offset", "1"),
        ("--limit", "0"),
        ("--limit", "-1"),
        ("--offset", "-1"),
    ]:
        code, out, _ = listing(run_cli, *flags)
        assert code == 2, flags
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    # get accepts ID selection only; list-windowing flags are rejected.
    for flags in [
        (),
        ("--id", ""),
        ("--id", " "),
        ("--id", "1", "--limit", "1"),
        ("--id", "1", "--offset", "1"),
        ("--id", "1", "--all"),
    ]:
        code, out, _ = getting(run_cli, *flags)
        assert code == 2, flags
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert setup.state.business_requests == []


def test_fields_projection_contract_and_formats(run_cli, envelope, setup):
    seed(run_cli, setup)
    single = envelope(listing(run_cli, "--fields", "vaRuleId")[1])
    assert single["data"] == [{"vaRuleId": "1"}]
    multiple = envelope(listing(run_cli, "--fields", "vaRuleId,ruleStatus")[1])
    assert multiple["data"] == [{"vaRuleId": "1", "ruleStatus": "ENABLED"}]
    # Unknown fields are dropped, never fabricated.
    unknown = envelope(listing(run_cli, "--fields", "vaRuleId,unknownField")[1])
    assert unknown["data"] == [{"vaRuleId": "1"}]
    got = envelope(getting(run_cli, "--id", "1", "--fields", "clientEntity")[1])
    assert got["data"] == {"clientEntity": "SYNTHETIC-CLIENT"}
    for flags in [("--fields", " , "), ("--fields", "")]:
        assert listing(run_cli, *flags)[0] == 2
        assert getting(run_cli, "--id", "1", *flags)[0] == 2
    table = listing(run_cli, "--format", "table")[1]
    assert "source: cache" in table
    assert "vaRuleId" in table
    assert "SYNTHETIC-ALIAS" in table
    assert (
        envelope(listing(run_cli, "--format", "json")[1])["data"][0]["vaRuleId"] == "1"
    )
    assert "source: cache" in getting(run_cli, "--id", "1", "--format", "table")[1]


def test_stable_id_sort_preserves_strings_before_windowing(run_cli, envelope, setup):
    identities = ["20", "2", "02", "a", "١", "²", "A"]
    rows = [row(identity) for identity in identities]
    setup.state.business_script.append(page(rows))
    result = envelope(listing(run_cli, "--live", "--all")[1])
    assert [record["vaRuleId"] for record in result["data"]] == [
        "02",
        "2",
        "20",
        "A",
        "a",
        "²",
        "١",
    ]
    setup.state.business_script.append(page(rows))
    windowed = envelope(listing(run_cli, "--live", "--limit", "2", "--offset", "2")[1])
    assert [record["vaRuleId"] for record in windowed["data"]] == ["20", "A"]
    assert windowed["meta"]["matched_total"] == 7
    assert windowed["meta"]["has_more"] is True
    assert not setup.cache_path.exists()


def test_ctoken_never_reaches_output_cache_or_payloads(run_cli, setup):
    seed(run_cli, setup)
    setup.state.business_script.extend([page(), detail()])
    runs = [refresh(run_cli), listing(run_cli), getting(run_cli, "--id", "1")]
    for code, out, err in runs:
        assert code == 0
        for text in (out, err):
            assert "FAKE-CTOKEN-SECRET" not in text
            assert "ctoken" not in text
    cache_bytes = setup.cache_path.read_bytes()
    assert b"FAKE-CTOKEN-SECRET" not in cache_bytes
    assert b"ctoken" not in cache_bytes
    for payload in setup.state.business_requests:
        assert set(payload) <= {"pageNo", "pageSize"} or set(payload) == {"vaRuleId"}
    expressions = [
        expression
        for transport in setup.state.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert expressions
    for expression in expressions:
        assert "FAKE-CTOKEN-SECRET" not in expression


def test_namespace_isolation_vs_payment_cost_and_sla_caches(run_cli, envelope, setup):
    from test_collection_cost_cli_sit import page as cost_page
    from test_collection_cost_cli_sit import row as cost_row
    from test_collection_sla_cli_sit import detail as sla_config_detail
    from test_collection_sla_cli_sit import page as sla_config_page
    from test_collection_sla_cli_sit import row as sla_config_row
    from test_sla_cli_sit import detail_outcome, list_page, sla_row

    config = setup.tmp_path / "config.toml"
    with config.open("a") as file:
        file.write(
            '\n[sources.collection_sla]\nkind = "cdp"'
            '\n[sources.collection_cost]\nkind = "cdp"\n'
        )
    setup.state.business_script.extend(
        [list_page([sla_row("900")]), detail_outcome("900")]
    )
    assert run_cli(["refresh", "payment", "sla"])[0] == 0
    setup.state.business_script.extend(
        [sla_config_page([sla_config_row("800")]), sla_config_detail("800")]
    )
    assert run_cli(["refresh", "collection", "sla"])[0] == 0
    setup.state.business_script.append(cost_page([cost_row("700")]))
    assert run_cli(["refresh", "collection", "cost"])[0] == 0
    others = (
        run_cli(["payment", "sla", "baselines", "list"])[1],
        run_cli(["collection", "sla", "configs", "list"])[1],
        run_cli(["collection", "cost", "list"])[1],
    )
    seed(run_cli, setup)
    va_before = listing(run_cli)[1]
    assert envelope(va_before)["data"][0]["vaRuleId"] == "1"
    assert (
        run_cli(["payment", "sla", "baselines", "list"])[1],
        run_cli(["collection", "sla", "configs", "list"])[1],
        run_cli(["collection", "cost", "list"])[1],
    ) == others
    setup.state.business_script.extend(
        [list_page([sla_row("901")]), detail_outcome("901")]
    )
    assert run_cli(["refresh", "payment", "sla"])[0] == 0
    assert listing(run_cli)[1] == va_before


def test_snapshot_source_kind_rejected(run_cli, envelope, setup):
    config = setup.tmp_path / "config.toml"
    config.write_text(
        config.read_text().replace(
            '[sources.collection_va]\nkind = "cdp"',
            "[sources.collection_va]\n"
            'kind = "snapshot"\n'
            'path = "/tmp/synthetic-va-dataset"',
        )
    )
    for result in [
        refresh(run_cli),
        listing(run_cli),
        listing(run_cli, "--live"),
        getting(run_cli, "--id", "1"),
    ]:
        code, out, _ = result
        assert code == 2
        assert envelope(out)["error"]["code"] == "CONFIG_ERROR"
    assert setup.state.transports == []
    assert setup.state.business_requests == []
