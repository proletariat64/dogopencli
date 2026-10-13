"""Credit usage reads source states; all account and amount examples are invented."""

import copy
import json

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
QUERY = ["liquidity", "cash", "credit-usage", "list", "--limit", "0"]
REFRESH = ["refresh", "liquidity", "cash", "credit-usage"]


def line():
    return {
        "id": "SYN-LINE",
        "creditLineType": "SUB_LIMIT",
        "currency": "USD",
        "amount": "1,234.567800",
        "usedAmount": "2,999.999900",
        "availableAmount": "-31.00",
        "bankId": "SYN-BANK",
        "masterBankId": "SYN-MASTER",
        "instId": "SYN-INST",
        "shareTag": "N",
        "status": "ACTIVE",
        "manageStatus": "SYN",
        "tntInstId": "GUAPW3SG",
        "gmtModified": "not-a-usage-time",
        "startTimestamp": "unknown-validity",
        "expiryTimestamp": "not-a-date",
        "bankAccountCreditLineList": [
            {
                "id": "SYN-MEMBER",
                "creditLineId": "SYN-LINE",
                "accountNo": "SYN-ACCOUNT",
                "aliasName": "SYN-ALIAS",
                "bankId": "SYN-BANK",
                "instId": "SYN-INST",
                "creditAmount": "9,876.543210",
                "usedCreditAmount": "10,000.000001",
                "availableCreditAmount": "3,200.00",
                "creditCurrency": "USD",
                "currency": "HKD",
                "equvAmount": "7,000.012300",
                "usedAmount": "9,999.00",
                "availableAmount": "-10.00",
                "isMasterAccount": "N",
                "mergeFlag": "SYN-GROUP",
                "status": "ACTIVE",
                "gmtModified": "not-a-time",
                "startTimestamp": "",
                "expiryTimestamp": None,
            }
        ],
    }


def response(rows, total=None):
    total = len(rows) if total is None else total
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": total,
            "result": {"success": True, "data": rows, "count": total},
        },
    }


def seed(setup, run_cli, rows=None):
    setup.state.business_handler = lambda payload, index: response(
        [line()] if rows is None else rows
    )
    code, out, err = run_cli(REFRESH)
    assert code == 0, err
    return parse(out)


def test_public_lifecycle_raw_source_business_states_and_settings_isolation(
    setup, run_cli
):
    code, out, _ = run_cli(QUERY)
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    setup.state.business_handler = lambda payload, index: response([line()])
    settings = ["liquidity", "cash", "credit-lines", "list", "--limit", "0"]
    assert run_cli(["refresh", "liquidity", "cash", "credit-lines"])[0] == 0
    settings_before = parse(run_cli(settings)[1])
    seed(setup, run_cli)
    request = setup.state.business_requests[-1]
    assert request == {
        "tntInstId": "GUAPW3SG",
        "bankCreditLineQuery": json.dumps({"rowStart": 0, "pageSize": 100}),
    }
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any(
        "queryBankCreditLineByParams.json" in e and "GET" in e for e in expressions
    )
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli([*QUERY, "--live", "--require-complete"])
    assert code == 0, err
    live = parse(out)
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    count = len(setup.state.business_requests)
    code, out, err = run_cli([*QUERY, "--require-complete"])
    assert code == 0, err
    offline = parse(out)
    assert offline["data"] == live["data"]
    assert len(setup.state.business_requests) == count
    assert offline["meta"]["kind"] == "runtimes"
    assert offline["meta"]["complete"] is True
    assert offline["meta"]["source_observed_from"] is None
    assert offline["meta"]["capability"] == "liquidity.cash.credit-usage.list"
    row = offline["data"][0]
    assert (
        row["usedAmount"] == "2,999.999900"
    )  # Exceeds parent amount; still source data.
    assert row["availableAmount"] == "-31.00"
    assert row["bankAccountCreditLineList"][0]["creditAmount"] == "9,876.543210"
    assert "gmtModified" not in row and "expiryTimestamp" not in row
    assert "gmtModified" not in row["bankAccountCreditLineList"][0]
    settings_after = parse(run_cli(settings)[1])
    assert settings_after["data"] == settings_before["data"]
    assert settings_after["meta"]["fetched_at"] == settings_before["meta"]["fetched_at"]
    assert settings_after["meta"]["capability"] != offline["meta"]["capability"]
    assert "usedAmount" not in settings_after["data"][0]


def test_shared_tree_flags_unknown_business_values_and_nulls_are_preserved(
    setup, run_cli
):
    row = line()
    row.update(
        shareTag="Y",
        amount="unknown-native-value",
        usedAmount=None,
        availableAmount=0,
        currency="not-an-ISO-code",
    )
    member = row["bankAccountCreditLineList"][0]
    member.update(
        creditAmount="",
        creditCurrency="",
        currency=None,
        usedCreditAmount="unavailable",
        availableCreditAmount="-0.0000",
        equvAmount="",
    )
    del member["availableAmount"]
    other = copy.deepcopy(member)
    other.update(id="SYN-MEMBER-2", aliasName="SYN-ALIAS-2")
    row["bankAccountCreditLineList"].append(other)
    seed(setup, run_cli, [row])
    code, out, err = run_cli([*QUERY, "--require-complete"])
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["complete"] is True
    got = result["data"][0]
    for key in ("shareTag", "amount", "usedAmount", "availableAmount", "currency"):
        assert got[key] == row[key]
    assert (
        len(got["bankAccountCreditLineList"]) == 2
    )  # Same mergeFlag never collapses members.
    for expected, actual in zip(
        row["bankAccountCreditLineList"], got["bankAccountCreditLineList"], strict=True
    ):
        for key in (
            "id",
            "mergeFlag",
            "creditAmount",
            "creditCurrency",
            "currency",
            "usedCreditAmount",
            "availableCreditAmount",
            "equvAmount",
        ):
            assert actual[key] == expected[key]
        assert "availableAmount" not in actual


@pytest.mark.parametrize(
    "case",
    [
        "parent_id",
        "member_id",
        "parent_link",
        "parent_tenant",
        "member_tenant",
        "members_shape",
        "member_duplicate",
        "line_conflict",
        "failure",
        "inner_failure",
        "total_conflict",
    ],
)
def test_reading_protocol_failure_preserves_previous_capture(setup, run_cli, case):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    row = line()
    member = row["bankAccountCreditLineList"][0]
    if case == "parent_id":
        row["id"] = True
    elif case == "member_id":
        member["id"] = []
    elif case == "parent_link":
        member["creditLineId"] = "WRONG"
    elif case == "parent_tenant":
        row["tntInstId"] = "OTHER"
    elif case == "member_tenant":
        member["tntInstId"] = "OTHER"
    elif case == "members_shape":
        row["bankAccountCreditLineList"] = {}
    elif case == "member_duplicate":
        row["bankAccountCreditLineList"].append(copy.deepcopy(member))
    rows = [row]
    if case == "line_conflict":
        rows.append({**row, "amount": "different-source-value"})
    answer = response(rows)
    if case == "failure":
        answer["body"]["resultFlag"] = False
    elif case == "inner_failure":
        answer["body"]["result"]["success"] = False
    elif case == "total_conflict":
        answer["body"]["result"]["count"] = 3
    setup.state.business_handler = lambda payload, index: answer
    for command in ([*QUERY, "--live"], REFRESH):
        code, out, _ = run_cli(command)
        assert code == 1
        assert parse(out)["error"] is not None
        assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    assert run_cli(QUERY)[0] == 0


def test_partial_strict_and_explicit_success_empty(setup, run_cli):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    rows = []
    for i in range(100):
        row = line()
        row["id"] = f"SYN-LINE-{i}"
        row["bankAccountCreditLineList"][0]["creditLineId"] = row["id"]
        rows.append(row)
    setup.state.business_handler = lambda payload, index: response(
        rows
        if json.loads(payload["bankCreditLineQuery"])["rowStart"] == 0
        else rows[:1],
        101,
    )
    code, out, _ = run_cli([*REFRESH, "--require-complete"])
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    assert run_cli(REFRESH)[0] == 0
    setup.state.reachable = False
    code, out, err = run_cli(QUERY)
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["complete"] is False
    assert len(parse(out)["data"]) == 100
    assert run_cli([*QUERY, "--require-complete"])[0] == 1
    setup.state.reachable = True
    partial_before = setup.cache_path.read_bytes()
    empty = seed(setup, run_cli, [])
    assert empty["data"]["row_count"] == 0 and empty["meta"]["complete"] is True
    assert empty["meta"]["published"] is False
    assert setup.cache_path.read_bytes() == partial_before
    setup.state.reachable = False
    code, out, _ = run_cli([*QUERY, "--require-complete"])
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    code, out, _ = run_cli(QUERY)
    assert code == 0 and len(parse(out)["data"]) == 100


def test_offline_describe_and_help_explain_source_values_and_time(setup, run_cli):
    code, out, err = run_cli(["describe", "liquidity", "cash", "credit-usage", "list"])
    assert code == 0, err
    description = parse(out)
    assert description["read_guide"]["kind"] == "runtimes"
    assert description["data_schema"]["x-usage-observation-time"] == "unknown"
    assert (
        description["data_schema"]["x-business-validation"]
        == "none; source values preserved"
    )
    assert (
        "bankAccountCreditLineList[].mergeFlag"
        in description["data_schema"]["properties"]
    )
    assert run_cli(["help", "liquidity", "cash", "credit-usage"])[0] == 0
    assert setup.state.transports == []
