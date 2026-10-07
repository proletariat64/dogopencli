"""QUOTED-only source reads; all identifiers and financial values are invented."""

import copy

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "investment", "quotes"]
BOUNDS = ["--from-date", "2026-01-01", "--to-date", "2026-01-02"]


def query(*extra, bounds=BOUNDS):
    return [*ROOT, "list", *bounds, "--all", *extra]


def refresh(*extra, bounds=BOUNDS):
    return ["refresh", *ROOT, *bounds, *extra]


def quote(identity="SYN-QUOTE"):
    return {
        "quotationOrderId": identity,
        "inquiryId": "SYN-INQUIRY",
        "bankId": "SYN-BANK",
        "quotationGroupName": "SYN-GROUP",
        "accountType": "SYN-ACCOUNT-TYPE",
        "department": "SYN-DEPARTMENT",
        "currency": "USD",
        "tenor": "O/N",
        "quote": "-0.1234500",
        "ticketSize": "1,234.567800",
        "curMaxLimitAvailable": "unconfirmed-native-value",
        "maxCurMaxLimitAvailable": False,
        "maxQuote": True,
        "inquiryTime": "2026-01-01 11:22:33",
        "quotationTime": "2026-01-01 11:33:44",
        "inquiryType": "SYN-INQUIRY-TYPE",
        "productType": "SYN-PRODUCT",
        "valueDate": "20260101",
        "expectMaturityDate": "not-a-date",
        "quoteEffectiveEndDate": "unknown",
        "winAmount": "",
        "redemptionFeature": "SYN-REDEMPTION",
        "negotiationStatus": "UNKNOWN-STATUS",
        "otherRemark": "SYNTHETIC NOTE",
    }


def response(rows):
    return {"status": 200, "body": {"success": True, "data": rows}}


def seed(setup, run_cli, rows=None, bounds=BOUNDS):
    setup.state.business_handler = lambda payload, index: response(
        [quote()] if rows is None else rows
    )
    code, out, err = run_cli(refresh("--require-complete", bounds=bounds))
    assert code == 0, err
    return parse(out)


def test_single_response_contract_raw_fidelity_and_disconnected_lifecycle(
    setup, run_cli
):
    code, out, _ = run_cli(query())
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    # Two distinct quotations may belong to the same inquiry.
    rows = [quote("SYN-QUOTE-A"), quote("SYN-QUOTE-B")]
    rows[1].update(
        currency="unknown-currency",
        quote=None,
        ticketSize="",
        valueDate=None,
        maxQuote="unknown-flag",
    )
    raw = [
        {**row, "quoteNum": "excluded-frontend-derivation", "unknownExtra": "excluded"}
        for row in rows
    ]
    seeded = seed(setup, run_cli, raw)
    assert setup.state.business_requests == [
        {
            "dataType": "QUOTED",
            "timeZone": None,
            "startValueDate": "20260101",
            "endValueDate": "20260102",
            "rowStart": 0,
            "pageSize": 5000,
        }
    ]
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any(
        "quotationAnalysis.json" in e and "application/json" in e and "POST" in e
        for e in expressions
    )
    assert seeded["meta"]["complete"] is True
    assert seeded["meta"]["reported_total"] is None
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(query("--live", "--require-complete"))
    assert code == 0, err
    live = parse(out)
    assert live["data"] == rows
    assert live["meta"]["reported_total"] is None
    assert live["meta"]["collected_total"] == 2
    assert live["meta"]["complete"] is True
    assert len(setup.state.business_requests) == 2  # One native request per invocation.
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    code, out, err = run_cli(query("--require-complete"))
    assert code == 0, err
    cached = parse(out)
    assert cached["data"] == rows
    assert cached["meta"]["scope"] == seeded["meta"]["scope"]
    assert cached["meta"]["fetched_at"] == seeded["meta"]["fetched_at"]
    assert cached["meta"]["source_observed_from"] is None
    assert cached["meta"]["source_observed_to"] is None
    assert "quotes-v1" in cached["meta"]["scope"]
    assert len(setup.state.business_requests) == 2
    setup.state.reachable = True
    setup.state.business_handler = lambda payload, index: {
        "status": 401,
        "body": {"success": False},
    }
    code, out, _ = run_cli(query("--live"))
    assert code == 1 and parse(out)["data"] is None  # No cached fallback for live.
    assert setup.cache_path.read_bytes() == before


def test_exact_date_scope_isolation_and_complete_empty_without_total(setup, run_cli):
    populated = seed(setup, run_cli)
    adjacent = ["--from-date", "2026-01-03", "--to-date", "2026-01-03"]
    setup.state.reachable = False
    for bounds in (adjacent, ["--from-date", "2026-01-01", "--to-date", "2026-01-01"]):
        code, out, _ = run_cli(query(bounds=bounds))
        assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    setup.state.reachable = True
    setup.state.business_handler = lambda payload, index: response([])
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(query("--live", "--require-complete", bounds=adjacent))
    assert code == 0, err
    empty_live = parse(out)
    assert empty_live["data"] == []
    assert empty_live["meta"]["complete"] is True
    assert empty_live["meta"]["reported_total"] is None
    assert setup.cache_path.read_bytes() == before
    empty = seed(setup, run_cli, [], bounds=adjacent)
    assert empty["meta"]["scope"] != populated["meta"]["scope"]
    setup.state.reachable = False
    code, out, err = run_cli(query("--require-complete", bounds=adjacent))
    assert code == 0, err
    assert parse(out)["data"] == [] and parse(out)["meta"]["complete"] is True
    code, out, err = run_cli(query())
    assert code == 0, err
    assert parse(out)["data"] == [quote()]
    assert parse(out)["meta"]["fetched_at"] == populated["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "bounds",
    [
        [],
        ["--from-date", "2026-01-01"],
        ["--from-date", "2026-02-30", "--to-date", "2026-03-01"],
        ["--from-date", "20260101", "--to-date", "2026-01-02"],
        ["--from-date", "2026-1-1", "--to-date", "2026-01-02"],
        ["--from-date", "2026-01-03", "--to-date", "2026-01-02"],
        [*BOUNDS, "--data-type", "WIN"],
    ],
)
def test_invalid_or_unbounded_requests_and_win_never_reach_transport(
    setup, run_cli, bounds
):
    for command in (query("--live", bounds=bounds), refresh(bounds=bounds)):
        code, out, _ = run_cli(command)
        assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "defect",
    [
        "false",
        "missing-success",
        "container",
        "row-shape",
        "identity-empty",
        "identity-int",
        "identity-conflict",
        "auth",
    ],
)
def test_protocol_identity_and_auth_failures_preserve_previous_cache(
    setup, run_cli, defect
):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    row = quote()
    answer = response([row])
    if defect == "false":
        answer["body"]["success"] = False
    elif defect == "missing-success":
        del answer["body"]["success"]
    elif defect == "container":
        answer["body"]["data"] = {"data": [row]}
    elif defect == "row-shape":
        answer["body"]["data"] = [None]
    elif defect == "identity-empty":
        row["quotationOrderId"] = ""
    elif defect == "identity-int":
        row["quotationOrderId"] = 123
    elif defect == "identity-conflict":
        answer["body"]["data"].append({**row, "quote": "different"})
    elif defect == "auth":
        answer = {"status": 401, "body": {"success": False}}
    setup.state.business_handler = lambda payload, index: answer
    for command in (query("--live"), refresh()):
        code, out, _ = run_cli(command)
        assert code == 1 and parse(out)["data"] is None
        assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    code, out, err = run_cli(query())
    assert code == 0, err
    assert parse(out)["data"] == [quote()]


def test_identical_duplicates_keep_partial_strict_policy_without_offset_loop(
    setup, run_cli
):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    row = quote()
    setup.state.business_handler = lambda payload, index: response(
        [row, copy.deepcopy(row)]
    )
    count = len(setup.state.business_requests)
    code, out, _ = run_cli(refresh("--require-complete"))
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    assert len(setup.state.business_requests) == count + 1
    code, out, err = run_cli(refresh())
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["complete"] is False
    assert len(setup.state.business_requests) == count + 2
    setup.state.reachable = False
    code, out, err = run_cli(query())
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert parse(out)["data"] == [row]
    assert parse(out)["meta"]["reported_total"] is None
    assert run_cli(query("--require-complete"))[0] == 1


def test_offline_description_states_units_timezone_scope_and_get_requires_identity(
    setup, run_cli
):
    code, out, err = run_cli(["describe", *ROOT, "list"])
    assert code == 0, err
    description = parse(out)
    guide = description["read_guide"]
    assert guide["offline_profile"] == "history"
    assert guide["request"]["pagination"] == "single"
    assert guide["request"]["reported_total"] is None
    assert guide["request"]["page_size"] == 5000
    assert guide["identity"] == ["quotationOrderId"]
    schema = description["data_schema"]
    assert schema["x-source-timezone"] == "UTC+08:00"
    assert schema["properties"]["quote"]["x-unit"] == "percent"
    assert "Minimum deposit" in schema["properties"]["ticketSize"]["description"]
    assert "unconfirmed" in schema["properties"]["curMaxLimitAvailable"]["description"]
    assert "quoteNum" not in schema["properties"]
    assert "revision" not in schema["properties"]
    code, _, err = run_cli(["help", *ROOT, "list"])
    assert code == 0, err
    code, out, _ = run_cli([*ROOT, "get"])
    assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
