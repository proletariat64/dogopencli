"""Issue #111 public CLI/fake CDP/real SQLite acceptance; synthetic aliases."""

from dataclasses import replace
from functools import partial
from hashlib import sha256

import pytest

from dogopencli.browser import cdp
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.account_capacity import ACCOUNT_CAPACITY, FIELDS
from dogopencli.plugins.liquidity.leaves import list_leaf
from dogopencli.transport import QueryRequest, validate_request
from dogopencli.transport.cdp import CdpQueryTransport

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "risk", "account-capacity"]
ACCOUNTS = ["SYN-C", "SYN-A", "SYN-B"]


def scope(aliases=ACCOUNTS):
    return [part for alias in aliases for part in ("--account", alias)]


def query(*extra, aliases=ACCOUNTS):
    return [*ROOT, "list", *scope(aliases), "--all", *extra]


def refresh(*extra, aliases=ACCOUNTS):
    return ["refresh", *ROOT, *scope(aliases), *extra]


def capacity(alias):
    return {
        "aliasName": alias,
        "currency": "unknown-currency",
        "accountAvailableBalance": "123456789.123456789000",
        "availableIod": None,
        "availableResource": "-9.00000",
        "cashPoolSupportAvailableResource": "",
        "outFlowCapacity": "0",
        "totalIod": 0,
        "usedIod": "unknown-native",
        "valueTime": "2026-10-05 08:09:10",
    }


def response(row):
    return {"status": 200, "body": {"success": True, "data": row}}


def seed(setup, run_cli, aliases=ACCOUNTS):
    setup.state.business_handler = lambda payload, index: response(
        {**capacity(payload["aliasName"]), "privateOwner": "excluded"}
    )
    code, out, err = run_cli(refresh("--require-complete", aliases=aliases))
    assert code == 0, err
    return parse(out)


def test_exact_fanout_raw_fields_complete_capture_and_disconnected_offline(
    setup, run_cli
):
    assert run_cli(query())[0] == 1
    assert setup.state.transports == []
    capture = seed(setup, run_cli)
    expected = [capacity(alias) for alias in sorted(ACCOUNTS)]
    assert setup.state.business_requests == [
        {"aliasName": alias} for alias in sorted(ACCOUNTS)
    ]
    expressions = [
        expression
        for transport in setup.state.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert len(expressions) == 3
    for expression in expressions:
        assert ACCOUNT_CAPACITY.endpoint in expression
        assert "iliquidity.alipay.com" in expression and "GET" in expression
        assert "application/x-www-form-urlencoded" not in expression
    digest = sha256(setup.cache_path.read_bytes()).hexdigest()
    code, out, err = run_cli(query("--live", "--require-complete"))
    assert code == 0, err
    live = parse(out)
    assert live["data"] == expected
    assert sha256(setup.cache_path.read_bytes()).hexdigest() == digest
    assert live["meta"]["reported_total"] is None
    assert live["meta"]["requested_count"] == live["meta"]["resolved_count"] == 3
    assert live["meta"]["complete"] is True
    assert live["meta"]["acquisition"]["total_semantics"] == "requested_accounts"
    setup.state.reachable = False
    requests = len(setup.state.business_requests)
    code, out, err = run_cli(
        query("--require-complete", aliases=list(reversed(ACCOUNTS)))
    )
    assert code == 0, err
    offline = parse(out)
    assert offline["data"] == expected
    for field in (
        "scope",
        "snapshot_id",
        "fetched_at",
        "complete",
        "acquisition",
        "reported_total",
        "requested_count",
        "resolved_count",
    ):
        assert offline["meta"][field] == capture["meta"][field]
    assert offline["meta"]["source_observed_from"] is None
    assert offline["meta"]["source_observed_to"] is None
    assert len(setup.state.business_requests) == requests
    assert "account-capacity-runtimes-v1" in offline["meta"]["scope"]


@pytest.mark.parametrize(
    "aliases", [[], [""], ["   "], ["SYN-A", "SYN-A"], [f"SYN-{i}" for i in range(11)]]
)
def test_invalid_account_set_rejected_before_transport(setup, run_cli, aliases):
    for command in (query("--live", aliases=aliases), refresh(aliases=aliases)):
        code, out, _ = run_cli(command)
        assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "flag", ["--date", "--from-date", "--tenant", "--url", "--page-size", "--row-start"]
)
def test_unknown_request_parameters_rejected_before_transport(setup, run_cli, flag):
    for command in (query("--live", flag, "anything"), refresh(flag, "anything")):
        code, out, _ = run_cli(command)
        assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


@pytest.mark.parametrize(
    "defect",
    [
        "wrong-alias",
        "missing-alias",
        "empty-alias",
        "int-alias",
        "missing-data",
        "empty-object",
        "list-data",
        "null-data",
        "false",
        "missing-success",
        "auth",
        "permission",
        "transport",
    ],
)
def test_one_failed_account_aborts_live_and_refresh_preserving_old_capture(
    setup, run_cli, defect
):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()

    def answer(payload, index):
        row = capacity(payload["aliasName"])
        if payload["aliasName"] != "SYN-B":
            return response(row)
        result = response(row)
        if defect == "wrong-alias":
            row["aliasName"] = "SYN-OTHER"
        elif defect == "missing-alias":
            del row["aliasName"]
        elif defect == "empty-alias":
            row["aliasName"] = ""
        elif defect == "int-alias":
            row["aliasName"] = 7
        elif defect == "missing-data":
            del result["body"]["data"]
        elif defect in ("empty-object", "list-data", "null-data"):
            result["body"]["data"] = {
                "empty-object": {},
                "list-data": [row],
                "null-data": None,
            }[defect]
        elif defect == "false":
            result["body"]["success"] = False
        elif defect == "missing-success":
            del result["body"]["success"]
        elif defect in ("auth", "permission"):
            result["status"] = {"auth": 401, "permission": 403}[defect]
        elif defect == "transport":
            return cdp.CdpError("synthetic transport failure")
        return result

    setup.state.business_handler = answer
    for command in (query("--live"), refresh(), refresh("--require-complete")):
        requests = len(setup.state.business_requests)
        code, out, _ = run_cli(command)
        result = parse(out)
        assert code == 1 and result["data"] is None
        assert result["error"]["code"] in (
            "INVALID_RESPONSE",
            "BUSINESS_QUERY_FAILED",
            "AUTH_REQUIRED",
            "TIMEOUT",
        )
        assert setup.cache_path.read_bytes() == before
        # Sorted fan-out stops at the failed second alias; no request for SYN-C.
        assert all(
            request["aliasName"] != "SYN-C"
            for request in setup.state.business_requests[requests:]
        )
    setup.state.reachable = False
    code, out, err = run_cli(query())
    assert code == 0, err
    assert parse(out)["data"] == [capacity(alias) for alias in sorted(ACCOUNTS)]
    assert run_cli(query("--live"))[0] == 1  # no live fallback


def test_single_multi_exact_scope_history_and_display_isolation(setup, run_cli):
    single = seed(setup, run_cli, aliases=["SYN-A"])
    multi = seed(setup, run_cli)
    setup.state.business_handler = lambda payload, index: response(
        {**capacity(payload["aliasName"]), "valueTime": "2026-10-05 09:09:10"}
    )
    code, out, err = run_cli(refresh("--require-complete"))
    assert code == 0, err
    another = parse(out)
    assert single["meta"]["scope"] != multi["meta"]["scope"]
    assert multi["meta"]["snapshot_id"] != another["meta"]["snapshot_id"]
    setup.state.reachable = False
    for aliases, count in ((["SYN-A"], 1), (ACCOUNTS, 3)):
        code, out, err = run_cli(query(aliases=aliases))
        assert code == 0, err
        result = parse(out)
        assert len(result["data"]) == count
        assert result["meta"]["requested_count"] == count
        assert result["meta"]["reported_total"] is None
    code, out, _ = run_cli(query(aliases=["SYN-B"]))
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    code, out, err = run_cli([*ROOT, "list", *scope(), "--offset", "1", "--limit", "1"])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == [{**capacity("SYN-B"), "valueTime": "2026-10-05 09:09:10"}]
    assert result["meta"]["requested_count"] == result["meta"]["resolved_count"] == 3
    assert result["meta"]["returned_count"] == 1
    code, out, err = run_cli(["snapshot", *ROOT])
    assert code == 0, err
    assert "account-capacity" in out and "7 rows" in out
    assert not setup.state.reachable


def test_special_query_characters_are_native_aliases_with_exact_scope(setup, run_cli):
    aliases = ["SYN-a;b=c&d+e", 'SYN-quote"-中文']
    seed(setup, run_cli, aliases=aliases)
    assert setup.state.business_requests == [
        {"aliasName": alias} for alias in sorted(aliases)
    ]
    setup.state.reachable = False
    code, out, err = run_cli(query(aliases=list(reversed(aliases))))
    assert code == 0, err
    assert parse(out)["data"] == [capacity(alias) for alias in sorted(aliases)]


def test_help_describe_snapshot_are_offline_with_truthful_field_meanings(
    setup, run_cli
):
    for command in (["help", *ROOT, "list"], ["snapshot", *ROOT]):
        assert run_cli(command)[0] == 0
    code, out, err = run_cli(["describe", *ROOT, "list"])
    assert code == 0, err
    description = parse(out)
    guide = description["read_guide"]
    assert guide["kind"] == "runtimes" and guide["offline_profile"] == "history"
    assert guide["identity"] == ["aliasName"]
    assert guide["live_verified"] == "2026-10-05"
    assert guide["request"]["encoding"] == "query"
    assert guide["request"]["reported_total"] is None
    properties = description["data_schema"]["properties"]
    assert set(properties) == set(FIELDS)
    assert "Outflow Capacity" in properties["availableResource"]["description"]
    assert "unknown business definition" in properties["outFlowCapacity"]["description"]
    assert properties["valueTime"]["x-timezone"] == "unknown"
    assert setup.state.transports == []


def test_transport_rejects_extra_keys_and_endpoint_changes(setup):
    leaf = list_leaf(ACCOUNT_CAPACITY.path)
    capability = leaf.capability(ACCOUNT_CAPACITY)
    request = QueryRequest(
        capability=capability.name,
        method="GET",
        host="iliquidity.alipay.com",
        path=ACCOUNT_CAPACITY.endpoint,
        body={"aliasName": "SYN-A"},
    )
    validate_request(request, capability.contract)
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url=capability.page_url,
    )
    for changed in (
        replace(request, method="POST"),
        replace(request, host="ifundcontrol.alipay.com"),
        replace(request, path="/api/fund/capacity/update.json"),
        replace(request, body={**request.body, "tntInstId": "GUAPW3SG"}),
        replace(request, body={**request.body, "rowStart": 0}),
        replace(request, body={**request.body, "pageSize": 10}),
        replace(request, body={**request.body, "date": "20261005"}),
    ):
        with pytest.raises(CliError) as error:
            transport.execute(changed)
        assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
    assert not any(t.created for t in setup.state.transports)
    assert not any(t.expressions for t in setup.state.transports)


def test_budget_expiry_after_valid_first_account_never_publishes(
    setup, run_cli, monkeypatch
):
    from dogopencli import collect as collect_mod

    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    original = collect_mod.execute_bounded
    calls = 0

    def execute(capability, transport, body, deadline):
        nonlocal calls
        calls += 1
        if calls == 2:
            from dogopencli.errors import TIMEOUT, CliError

            raise CliError(TIMEOUT, "synthetic deadline exhaustion")
        return original(capability, transport, body, deadline)

    monkeypatch.setattr(collect_mod, "execute_bounded", execute)
    code, out, _ = run_cli(refresh())
    assert code == 1 and parse(out)["error"]["code"] == "TIMEOUT"
    assert setup.cache_path.read_bytes() == before


def test_retention_partial_keeps_scope_counts_and_strict_preserves_old_capture(
    setup, run_cli, monkeypatch
):
    from dogopencli.plugins.liquidity import store

    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    monkeypatch.setattr(
        store, "plan_capture_publish", partial(store.plan_capture_publish, cap=2)
    )
    code, out, _ = run_cli(refresh("--require-complete"))
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(refresh())
    assert code == 0 and "INCOMPLETE_RESULT" in err
    capture = parse(out)
    assert capture["meta"]["complete"] is False
    assert capture["meta"]["requested_count"] == 3
    assert capture["meta"]["resolved_count"] == 2
    assert capture["meta"]["reported_total"] is None
    setup.state.reachable = False
    code, out, err = run_cli(query())
    assert code == 0 and "INCOMPLETE_RESULT" in err
    result = parse(out)
    assert len(result["data"]) == result["meta"]["resolved_count"] == 2
    assert result["meta"]["requested_count"] == 3
    assert result["meta"]["reported_total"] is None
    assert "RETENTION_GAP" in result["meta"]["acquisition"]["reasons"]
    assert run_cli(query("--require-complete"))[0] == 1


def test_other_list_and_native_detail_captures_remain_isolated(setup, run_cli):
    other = ["liquidity", "rules", "realtime"]
    rule = {"id": "SYN-RULE", "ruleName": "SYN-NAME", "runStatus": "UNKNOWN"}
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": {"data": [rule], "totalCount": 1}},
    }
    assert run_cli(["refresh", *other])[0] == 0
    detail = ["liquidity", "operations", "decisions", "get", "--id", "7"]
    setup.state.business_handler = lambda payload, index: response(
        {"id": 7, "decisionNo": "SYN-NO"}
    )
    command = [
        "refresh",
        "liquidity",
        "operations",
        "decisions",
        "detail",
        "get",
        "--id",
        "7",
    ]
    assert run_cli(command)[0] == 0
    seed(setup, run_cli)
    setup.state.reachable = False
    code, out, err = run_cli([*other, "list", "--all"])
    assert code == 0, err
    assert parse(out)["data"] == [rule]
    assert "requested_count" not in parse(out)["meta"]
    code, out, err = run_cli(detail)
    assert code == 0, err
    assert parse(out)["data"] == {"id": 7, "decisionNo": "SYN-NO"}
    assert run_cli(query())[0] == 0


def test_client_budget_accepts_ten_explicit_accounts(setup, run_cli):
    aliases = [f"SYN-{index:02d}" for index in range(10)]
    capture = seed(setup, run_cli, aliases=aliases)
    assert capture["meta"]["requested_count"] == 10
    assert capture["meta"]["resolved_count"] == 10
    assert len(setup.state.business_requests) == 10
    setup.state.reachable = False
    code, out, err = run_cli(query(aliases=aliases))
    assert code == 0, err
    assert parse(out)["data"] == [capacity(alias) for alias in aliases]
