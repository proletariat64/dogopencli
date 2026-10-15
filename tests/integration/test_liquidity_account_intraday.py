"""Public D03 CLI through fake CDP and temporary SQLite."""

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "forecast", "account_demands_intraday"]
SCOPE = [
    "--alias",
    "SYN-A",
    "--entity",
    "SYN-E",
    "--bank",
    "SYN-B",
    "--from-date",
    "20261014",
    "--to-date",
    "20261014",
]


def slots():
    return [
        {
            "statisticalDate": f"{hour:02}:{minute:02}",
            "inflowAmount": "123456789.123456789123456789",
            "outflowAmount": "123456789.123456789123456790",
            "totalAmount": "-0.000000000000000001",
        }
        for hour in range(24)
        for minute in (0, 15, 30, 45)
    ]


def response(rows):
    return lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": rows},
    }


def test_intraday_one_native_request_live_and_refresh_offline(setup, run_cli):
    rows = slots()
    setup.state.business_handler = response(rows)
    code, out, err = run_cli([*ROOT, "list", "--live", *SCOPE, "--limit", "0"])
    assert code == 0, err
    assert parse(out)["data"] == rows
    assert parse(out)["meta"]["complete"] is True
    assert setup.state.business_requests == [
        {
            "aliasName": "SYN-A",
            "entity": "SYN-E",
            "bankId": "SYN-B",
            "startDate": "20261014",
            "endDate": "20261014",
        }
    ]
    assert not setup.cache_path.exists()
    assert run_cli(["refresh", *ROOT, *SCOPE, "--require-complete"])[0] == 0
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list", "--limit", "0"])
    assert code == 0, err
    assert parse(out)["data"] == rows


def test_empty_native_statistics_preserve_previous_slot(setup, run_cli):
    setup.state.business_handler = response(slots())
    assert run_cli(["refresh", *ROOT, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = response([])
    code, out, err = run_cli(["refresh", *ROOT, *SCOPE, "--require-complete"])
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["complete"] is True
    assert result["meta"]["published"] is False
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli([*ROOT, "list", "--live", *SCOPE])
    assert code == 0, err
    assert parse(out)["data"] == []
    assert setup.cache_path.read_bytes() == before


def test_missing_slots_partial_persists_quality_and_strict_preserves(setup, run_cli):
    setup.state.business_handler = response(slots())
    assert run_cli(["refresh", *ROOT, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()
    partial = [slots()[3], slots()[0]]
    setup.state.business_handler = response(partial)
    code, out, err = run_cli(["refresh", *ROOT, *SCOPE, "--require-complete"])
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(["refresh", *ROOT, *SCOPE, "--fields", "statisticalDate"])
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is False
    assert "INTRADAY_SLOT_GAP" in err
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list", "--fields", "totalAmount"])
    assert code == 0, err
    assert parse(out)["data"] == [{"totalAmount": "-0.000000000000000001"}] * 2
    assert parse(out)["meta"]["complete"] is False
    assert "INTRADAY_SLOT_GAP" in err
    code, out, err = run_cli([*ROOT, "list", "--require-complete"])
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"


@pytest.mark.parametrize(
    "changes",
    [
        ["--alias", "ANY"],
        ["--alias", "A,B"],
        ["--alias", " "],
        ["--from-date", "20261014", "--to-date", "20261015"],
        ["--from-date", "20260230", "--to-date", "20260230"],
        ["--from-date", "20261014"],
    ],
)
def test_intraday_invalid_scope_precedes_directory_browser(setup, run_cli, changes):
    args = ["--alias", "SYN-A", "--from-date", "20261014", "--to-date", "20261014"]
    if changes[0] == "--alias":
        args[:2] = changes
    else:
        args[2:] = changes
    code, out, err = run_cli([*ROOT, "list", "--live", *args])
    assert code == 2, err
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


@pytest.mark.parametrize(
    "bad",
    [
        {"statisticalDate": "24:00"},
        {"statisticalDate": "00:01"},
        {"statisticalDate": 0},
        {"statisticalDate": []},
        {"inflowAmount": 1.25},
        {"totalAmount": "NaN"},
    ],
)
def test_intraday_malformed_source_preserves_cache(setup, run_cli, bad):
    setup.state.business_handler = response(slots())
    assert run_cli(["refresh", *ROOT, *SCOPE])[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = response([{**slots()[0], **bad}])
    code, out, err = run_cli(["refresh", *ROOT, *SCOPE])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("conflicting", [False, True])
def test_intraday_duplicate_native_slot_hard_failure(setup, run_cli, conflicting):
    row = slots()[0]
    setup.state.business_handler = response(
        [row, {**row, **({"totalAmount": "9"} if conflicting else {})}]
    )
    code, out, err = run_cli([*ROOT, "list", "--live", *SCOPE])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


def test_intraday_offline_scope_matches_saved_account_day_without_network(
    setup, run_cli
):
    setup.state.business_handler = response(slots())
    assert run_cli(["refresh", *ROOT, *SCOPE])[0] == 0
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list", *SCOPE, "--limit", "0"])
    assert code == 0, err
    assert len(parse(out)["data"]) == 96
    assert parse(out)["meta"]["requested_scope_covered"] is True
    code, out, err = run_cli([*ROOT, "list", "--alias", "SYN-OTHER"])
    assert code == 0, err
    assert parse(out)["data"] == []
    assert parse(out)["meta"]["requested_scope_covered"] is False
    code, out, err = run_cli(
        [*ROOT, "list", "--from-date", "20261015", "--to-date", "20261015"]
    )
    assert code == 0, err
    assert parse(out)["data"] == []
    assert parse(out)["meta"]["requested_scope_covered"] is False


def test_intraday_help_describe_prune_and_no_paging_input(setup, run_cli):
    code, out, err = run_cli(["help", *ROOT, "list"])
    assert code == 0, err
    assert "--alias" in out and "--from-date" in out
    code, out, err = run_cli(["describe", *ROOT, "list"])
    assert code == 0, err
    assert "statisticalDate" in out and "inflowAmount" in out
    assert "timezone" in out and "independent" in out
    assert run_cli(["prune", *ROOT])[0] == 0
    assert not setup.cache_path.exists()
    setup.state.business_handler = response(slots())
    assert run_cli(["refresh", *ROOT, *SCOPE])[0] == 0
    assert run_cli(["prune", *ROOT])[0] == 0
    assert run_cli([*ROOT, "list"])[0] == 1


def test_intraday_alias_resolution_warning_survives_partial_projection_and_cache(
    setup, run_cli
):
    from test_liquidity_account_context_cli import configure_accounts

    configure_accounts(
        setup, [("SYN-A", "SYN-E", "SYN-B"), ("SYN-A", "OTHER", "OTHER")]
    )
    setup.state.business_handler = response([slots()[0]])
    args = ["--alias", "SYN-A", *SCOPE[-4:]]
    code, out, err = run_cli(["refresh", *ROOT, *args, "--fields", "inflowAmount"])
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["account_context"]["source"] == "duckdog"
    assert result["meta"]["complete"] is False
    assert "ACCOUNT_CONTEXT_MULTIPLE_MATCHES" in err
    assert "INTRADAY_SLOT_GAP" in err
    assert setup.state.business_requests == [
        {
            "aliasName": "SYN-A",
            "entity": "SYN-E",
            "bankId": "SYN-B",
            "startDate": "20261014",
            "endDate": "20261014",
        }
    ]
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list", "--fields", "outflowAmount"])
    assert code == 0, err
    assert "ACCOUNT_CONTEXT_MULTIPLE_MATCHES" in err
    assert "INTRADAY_SLOT_GAP" in err
    assert parse(out)["data"] == [{"outflowAmount": "123456789.123456789123456790"}]


def test_intraday_preserves_native_amounts_independent_of_demand_sums(setup, run_cli):
    row = {
        **slots()[0],
        "inflowAmount": "+0001.2300",
        "outflowAmount": "0.00",
        "totalAmount": "9000.000",
    }
    setup.state.business_handler = response([row])
    code, out, err = run_cli([*ROOT, "list", "--live", *SCOPE])
    assert code == 0, err
    assert parse(out)["data"] == [row]


def test_intraday_null_empty_zero_and_absent_amounts_stay_distinct(setup, run_cli):
    rows = [
        {
            "statisticalDate": "00:00",
            "inflowAmount": None,
            "outflowAmount": "",
            "totalAmount": "0",
        },
        {"statisticalDate": "00:15", "inflowAmount": "0.00", "outflowAmount": "0.000"},
    ]
    setup.state.business_handler = response(rows)
    code, out, err = run_cli(["refresh", *ROOT, *SCOPE])
    assert code == 0, err
    assert parse(out)["meta"]["published"] is True
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list"])
    assert code == 0, err
    assert parse(out)["data"] == rows


def test_intraday_transport_rejects_pagination_extra_fields_and_mutation(setup):
    from dataclasses import replace

    from dogopencli.errors import CliError
    from dogopencli.plugins.liquidity.account_intraday import INTRADAY
    from dogopencli.plugins.liquidity.leaves import list_leaf
    from dogopencli.transport import QueryRequest
    from dogopencli.transport.cdp import CdpQueryTransport

    capability = list_leaf(INTRADAY.path).capability(INTRADAY)
    body = {
        "aliasName": "SYN-A",
        "entity": "SYN-E",
        "bankId": "SYN-B",
        "startDate": "20261014",
        "endDate": "20261014",
    }
    request = QueryRequest(
        capability=capability.name,
        method="POST",
        host="iliquidity.alipay.com",
        path=INTRADAY.endpoint,
        body=body,
    )
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url=capability.page_url,
    )
    for changed in (
        replace(request, body={**body, "rowStart": 0}),
        replace(request, body={**body, "pageSize": 96}),
        replace(request, body={**body, "fundActionTypes": ["WITHDRAW"]}),
        replace(request, path="/strategyManage/update.json"),
        replace(request, method="GET"),
        replace(request, host="ifundcontrol.alipay.com"),
    ):
        with pytest.raises(CliError) as error:
            transport.execute(changed)
        assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
