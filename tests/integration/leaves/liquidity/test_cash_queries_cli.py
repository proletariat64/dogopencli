"""independent packages exercised through the installed public CLI."""

import json
import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def installed(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    def install(leaf):
        source = ROOT / "leaf_packages/liquidity" / leaf
        if getattr(request, "param", "directory") == "zip":
            archive_path = tmp_path / (leaf + ".zip")
            with ZipFile(archive_path, "w") as archive:
                for item in source.iterdir():
                    if item.is_file():
                        archive.write(item, item.name)
            source = archive_path
        cli("plugins", "install", str(source))
        return cli, browser

    try:
        cli("domain", "enable", "liquidity")
        yield install
    finally:
        cdp.set_transport_factory(None)


LEAVES = {
    "cash.waterlevels": (1000, None, "aliasName"),
    "forecast.adjustments": (1000, "bankCashForecastAdjustmentQueryVO", "id"),
    "cash.statements.intraday": (1000, None, "bankTransNo"),
    "cash.statements.end_of_day": (1000, None, "end2endid"),
    "cash.credit_lines": (100, "bankCreditLineQuery", "id"),
    "cash.credit_usage": (100, "bankCreditLineQuery", "id"),
    "cash.group_balances": (100, "bankAccountManageUnitQueryVO", "id"),
    "cash.pool_balances": (100, None, "id"),
    "cash.pools": (100, None, "id"),
}
ENDPOINTS = {
    "cash.waterlevels": "/bufferReportList.json",
    "forecast.adjustments": "/bankCashForecastAdjustmentQuery.json",
    "cash.statements.intraday": "/bankAccountDetailQuery.json",
    "cash.statements.end_of_day": "/bankAccountDetailDayQuery.json",
    "cash.credit_lines": "/queryBankCreditLineByParams.json",
    "cash.credit_usage": "/queryBankCreditLineByParams.json",
    "cash.group_balances": "/bankAccountGroupQuery.json",
    "cash.pool_balances": "/cashPoolList.json",
    "cash.pools": "/cashPoolList.json",
}


def scope_flags(leaf):
    if leaf == "cash.waterlevels":
        return ["--account-alias", "synthetic"]
    if leaf.startswith("cash.statements."):
        return [
            "--account-alias",
            "synthetic",
            "--currency",
            "USD",
            "--entity" if leaf.endswith("end_of_day") else "--inst-id",
            "Z21",
            "--from-date",
            "2026-10-01",
            "--to-date",
            "2026-10-02",
        ]
    return []


def native_row(leaf, number=0):
    record = {
        LEAVES[leaf][2]: f"native-{number}",
        "amount": Decimal("0.12345678901234567890123456789"),
        "currency": "USD",
        "textAmount": "1.0000",
        "unknown": {
            "null": None,
            "empty": "",
            "zero": 0,
            "false": False,
            "list": [0, "0", None],
        },
    }
    if leaf == "cash.waterlevels":
        record["aliasName"] = "synthetic"
        record["currency"] = ["USD", "EUR", "JPY"][number % 3]
        record["curAvlBal"] = Decimal("123456789.123456789123456789")
    elif leaf.startswith("cash.statements."):
        if leaf.endswith("end_of_day"):
            record["bankTransNo"] = f"bank-{number}"
        record.update(
            instId="Z21",
            bankAccountAliasName="synthetic",
            valueDate="20261001",
            transDate="20260930",
            transTime="23:59:59",
            date=None,
            fundDirection="Cr",
            timeZone="GMT+08",
        )
    elif leaf in {"cash.pool_balances", "cash.pools"}:
        record.update(
            cashPoolCategory="BANK", cashPoolName="Synthetic", mainCurrency="EUR"
        )
    return record


def page(leaf, records, total=None):
    total = len(records) if total is None else total
    if LEAVES[leaf][1]:
        key = "dataValue" if leaf == "forecast.adjustments" else "data"
        body = {
            "resultFlag": True,
            "result": {"success": True, key: records, "count": total},
        }
        if leaf != "forecast.adjustments":
            body["count"] = total
    else:
        body = {"success": True, "data": {"data": records, "totalCount": total}}
    return {"status": 200, "body": body}


def expected_request(leaf, row_start=0):
    size, vo, _ = LEAVES[leaf]
    native = {"rowStart": row_start, "pageSize": size}
    if leaf == "cash.waterlevels":
        return {**native, "aliasNameList": ["synthetic"]}
    if leaf.startswith("cash.statements."):
        return {
            **native,
            "tntInstId": "GUAPW3SG",
            "instIds": ["Z21"],
            "bankAccountAliasName": ["synthetic"],
            "currency": "USD",
            "timeZone": "GMT+08",
            "queryDateBegin": "20261001",
            "queryDateEnd": "20261002",
        }
    if leaf in {"cash.pools", "cash.pool_balances"}:
        return {**native, "tntInstId": "GUAPW3SG", "cashPoolCategory": "BANK"}
    if leaf == "forecast.adjustments":
        native.update(tntInstId="GUAPW3SG", startValueDate=None, endValueDate=None)
    if leaf == "cash.group_balances":
        native.update(tntInstId="GUAPW3SG", equiCurrency="USD")
    return {"tntInstId": "GUAPW3SG", vo: native}


def decoded_request(leaf, request):
    vo = LEAVES[leaf][1]
    return {**request, vo: json.loads(request[vo])} if vo else request


@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_native_list_live_refresh_offline_precision_and_exact_request(installed, leaf):
    cli, browser = installed(leaf)
    flags = scope_flags(leaf)
    records = [native_row(leaf, n) for n in range(3)]
    cli("liquidity", "list", leaf, "-h")
    cli("liquidity", "describe", leaf)
    assert not browser.business_requests
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(leaf, records))
    result = cli("liquidity", "list", leaf, "--live", "--limit", "0", *flags)
    assert result["data"] == records
    assert result["meta"]["complete"] is True
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(leaf, records))
    assert (
        cli("liquidity", "refresh", leaf, "--limit", "1", *flags)["data"]["row_count"]
        == 3
    )
    count = len(browser.business_requests)
    assert cli("liquidity", "list", leaf, "--limit", "0")["data"] == records
    assert len(browser.business_requests) == count
    assert all(
        decoded_request(leaf, request) == expected_request(leaf)
        for request in browser.business_requests
    )
    expressions = [
        expression
        for transport in browser.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert all(ENDPOINTS[leaf] in expression for expression in expressions)
    method = "GET" if LEAVES[leaf][1] else "POST"
    assert all(method in expression for expression in expressions)
    if method == "POST":
        assert all("application/json" in expression for expression in expressions)
    assert all(
        url == LIQUIDITY_STARTUP_URL
        for transport in browser.transports
        for url in transport.created
    )


@pytest.mark.parametrize("leaf", LEAVES)
def test_all_native_pages_are_collected_before_display_limit(installed, leaf):
    cli, browser = installed(leaf)
    size = LEAVES[leaf][0]
    records = [native_row(leaf, n) for n in range(size + 1)]
    if leaf == "cash.waterlevels":
        records = [
            {
                **record,
                "currency": "".join(
                    chr(65 + (n // place) % 26) for place in (676, 26, 1)
                ),
            }
            for n, record in enumerate(records)
        ]
    browser.business_script.extend(
        [page(leaf, records[:size], size + 1), page(leaf, records[size:], size + 1)]
    )
    result = cli(
        "liquidity", "list", leaf, "--live", "--limit", "1", *scope_flags(leaf)
    )
    assert result["data"] == records[:1]
    assert result["meta"]["complete"] is True
    assert result["meta"]["collected_total"] == size + 1
    assert [
        decoded_request(leaf, request) for request in browser.business_requests
    ] == [expected_request(leaf), expected_request(leaf, size)]


@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize("bad", [None, "", "   ", True, {}, [], Decimal("1.5")])
def test_invalid_native_identity_is_rejected(installed, leaf, bad):
    cli, browser = installed(leaf)
    record = native_row(leaf)
    record[LEAVES[leaf][2]] = bad
    browser.business_script.append(page(leaf, [record]))
    assert (
        cli("liquidity", "list", leaf, "--live", *scope_flags(leaf), code=1)["error"][
            "code"
        ]
        == "INVALID_RESPONSE"
    )


@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "business",
        "flag-type",
        "shape",
        "missing-rows",
        "total-string",
        "total-bool",
        "total-negative",
        "changed-total",
        "early-empty",
        "overfull",
        "duplicate",
        "conflict",
        "auth",
    ],
)
def test_rejected_acquisition_preserves_previous_records_and_capture(
    installed, leaf, failure
):
    cli, browser = installed(leaf)
    records = [native_row(leaf)]
    flags = scope_flags(leaf)
    browser.business_script.append(page(leaf, records))
    cli("liquidity", "refresh", leaf, *flags)
    before = cli("liquidity", "list", leaf, "--limit", "0")
    response, expected = page(leaf, records), "INVALID_RESPONSE"
    vo = LEAVES[leaf][1]
    container = response["body"]["result" if vo else "data"]
    row_key = "dataValue" if leaf == "forecast.adjustments" else "data"
    count_key = "count" if vo else "totalCount"
    size = LEAVES[leaf][0]
    if failure == "empty":
        response, expected = page(leaf, []), None
    elif failure == "business":
        response["body"]["resultFlag" if vo else "success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "flag-type":
        response["body"]["resultFlag" if vo else "success"] = 1
    elif failure == "shape":
        container[row_key] = {}
    elif failure == "missing-rows":
        del container[row_key]
    elif failure.startswith("total-"):
        bad = {"total-string": "1", "total-bool": True, "total-negative": -1}[failure]
        container[count_key] = bad
        if "count" in response["body"]:
            response["body"]["count"] = bad
    elif failure in {"changed-total", "early-empty"}:
        first = [native_row(leaf, n) for n in range(size)]
        if leaf == "cash.waterlevels":
            first = [
                {
                    **record,
                    "currency": "".join(
                        chr(65 + (n // place) % 26) for place in (676, 26, 1)
                    ),
                }
                for n, record in enumerate(first)
            ]
        browser.business_script.append(page(leaf, first, size + 1))
        response = page(leaf, [], size + (2 if failure == "changed-total" else 1))
        if failure == "early-empty":
            expected = "INCOMPLETE_RESULT"
    elif failure == "overfull":
        response = page(leaf, [native_row(leaf, n) for n in range(size + 1)])
    elif failure == "duplicate":
        response = page(leaf, records * 2)
        expected = "INCOMPLETE_RESULT"
    elif failure == "conflict":
        response = page(leaf, [records[0], {**records[0], "unknown": "conflict"}])
        expected = "INCOMPLETE_RESULT"
    elif failure == "auth":
        response, expected = {"status": 401, "body": {}}, "AUTH_REQUIRED"
    browser.business_script.append(response)
    result = cli(
        "liquidity",
        "refresh",
        leaf,
        "--require-complete",
        *flags,
        code=1 if expected else 0,
    )
    if expected:
        assert result["error"]["code"] in (
            expected if isinstance(expected, set) else {expected}
        )
    else:
        assert result["meta"]["published"] is False
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"] == records
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "leaf", ["cash.credit_lines", "cash.credit_usage", "cash.group_balances"]
)
def test_disagreeing_native_totals_and_inner_business_failures_reject_refresh(
    installed, leaf
):
    cli, browser = installed(leaf)
    for bad in ["count", "business", "flag-type"]:
        response = page(leaf, [native_row(leaf)])
        if bad == "count":
            response["body"]["count"] = 2
        else:
            response["body"]["result"]["success"] = (
                False if bad == "business" else "true"
            )
        browser.business_script.append(response)
        result = cli("liquidity", "refresh", leaf, code=1)
        assert result["error"]["code"] == (
            "BUSINESS_QUERY_FAILED" if bad == "business" else "INVALID_RESPONSE"
        )


@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize("mutation", ["extra-key", "tenant", "page-size"])
def test_unverified_native_request_is_blocked_before_browser_fetch(
    installed, leaf, tmp_path, mutation
):
    cli, browser = installed(leaf)
    cli("plugins", "uninstall", "liquidity." + leaf)
    source = tmp_path / "mutated"
    shutil.copytree(ROOT / "leaf_packages/liquidity" / leaf, source)
    path = source / "adapter.py"
    code = path.read_text()
    # Mutate only a test-owned package's public request implementation.
    start = code.index("    def page_body")
    head, tail = code[:start], code[start:]
    if mutation == "extra-key":
        original, replacement = (
            '"rowStart": row_start',
            '"unverified": True, "rowStart": row_start',
        )
    elif mutation == "page-size":
        original, replacement = '"pageSize": PAGE_SIZE', '"pageSize": 7'
    elif leaf == "cash.waterlevels":
        original, replacement = (
            '"rowStart": row_start',
            '"tntInstId": "WRONG", "rowStart": row_start',
        )
    else:
        original, replacement = '"tntInstId": TENANT', '"tntInstId": "WRONG"'
    assert original in tail
    tail = tail.replace(original, replacement, 1)
    code = head + tail
    path.write_text(code)
    cli("plugins", "install", str(source))
    result = cli("liquidity", "list", leaf, "--live", *scope_flags(leaf), code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


MEMBERS = {
    "cash.credit_lines": ("bankAccountCreditLineList", "creditLineId"),
    "cash.credit_usage": ("bankAccountCreditLineList", "creditLineId"),
    "cash.group_balances": ("memberList", "bankAccountGroupId"),
    "cash.pool_balances": ("cashPoolMemberVOS", "cashPoolId"),
    "cash.pools": ("cashPoolMemberVOS", "cashPoolId"),
}


@pytest.mark.parametrize("leaf", MEMBERS)
def test_nested_native_precision_flags_currencies_and_typed_multiplicity(
    installed, leaf
):
    cli, browser = installed(leaf)
    key, echo = MEMBERS[leaf]
    record = native_row(leaf)
    parent = record["id"]
    record[key] = [
        {
            "id": 1,
            echo: parent,
            "aliasName": "same-account",
            "currency": "USD",
            "bankCurrency": "EUR",
            "creditCurrency": "JPY",
            "currencyCode": "GBP",
            "currentBalance": Decimal("123456789.1234567890123456789"),
            "forecastBalance": None,
            "lastDayClosingBalance": "",
            "usedAmount": 0,
            "equvAmount": "0.0000",
            "mergeFlag": "Y",
            "isShare": False,
            "masterAccount": "N",
            "currentBalanceTime": "2026-10-01 01:02:03",
            "unknownMember": {"native": [False, None, ""]},
        },
        {
            "id": "1",
            echo: parent,
            "aliasName": "same-account",
            "currency": "EUR",
            "currentBalance": "0.00",
            "forecastTime": "",
        },
    ]
    browser.business_script.append(page(leaf, [record]))
    result = cli("liquidity", "list", leaf, "--live", "--limit", "0")
    assert result["data"] == [record]
    assert result["meta"]["complete"] is True
    assert "forecastTime" not in result["data"][0][key][0]


@pytest.mark.parametrize("leaf", MEMBERS)
@pytest.mark.parametrize(
    "failure",
    ["container", "nonobject", "missing-id", "bool-id", "duplicate", "parent-echo"],
)
def test_invalid_nested_native_identity_rejects_without_cache(installed, leaf, failure):
    cli, browser = installed(leaf)
    key, echo = MEMBERS[leaf]
    record = native_row(leaf)
    member = {"id": "member-1", echo: record["id"]}
    members = [member]
    if failure == "container":
        members = {}
    elif failure == "nonobject":
        members = [None]
    elif failure == "missing-id":
        del member["id"]
    elif failure == "bool-id":
        member["id"] = True
    elif failure == "duplicate":
        members = [member, member]
    elif failure == "parent-echo":
        member[echo] = "wrong-parent"
    record[key] = members
    browser.business_script.append(page(leaf, [record]))
    result = cli("liquidity", "refresh", leaf, code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize(
    "failure", ["duplicate", "parent-echo", "bool-id", "container"]
)
def test_pool_swap_rule_identity_is_validated_at_its_native_parent(installed, failure):
    cli, browser = installed("cash.pools")
    rule = {"id": "rule-1", "cashPoolMemberId": "member-1", "sweepingAmount": "0.0000"}
    rules = [rule]
    if failure == "duplicate":
        rules = [rule, rule]
    elif failure == "parent-echo":
        rule["cashPoolMemberId"] = "wrong-member"
    elif failure == "bool-id":
        rule["id"] = True
    else:
        rules = {}
    record = {
        **native_row("cash.pools"),
        "cashPoolMemberVOS": [
            {"id": "member-1", "cashPoolId": "native-0", "cashPoolSwapRuleVOS": rules}
        ],
    }
    browser.business_script.append(page("cash.pools", [record]))
    assert (
        cli("liquidity", "list", "cash.pools", "--live", code=1)["error"]["code"]
        == "INVALID_RESPONSE"
    )


@pytest.mark.parametrize("leaf", ["cash.waterlevels", "cash.statements.intraday"])
def test_repeated_local_filters_do_not_narrow_refresh_publication(installed, leaf):
    cli, browser = installed(leaf)
    records = [native_row(leaf, n) for n in range(3)]
    if leaf == "cash.waterlevels":
        flag, values = "currency", ["USD", "EUR", "JPY"]
    else:
        flag, values = "fund-direction", ["Cr", "Dr", "cr"]
        for record, value in zip(records, values, strict=True):
            record["fundDirection"] = value
    select = ["--" + flag, values[0], "--" + flag, values[1], "--" + flag, values[0]]
    browser.business_script.append(page(leaf, records))
    assert (
        cli(
            "liquidity",
            "list",
            leaf,
            "--live",
            "--limit",
            "0",
            *scope_flags(leaf),
            *select,
        )["data"]
        == records[:2]
    )
    browser.business_script.append(page(leaf, records))
    assert (
        cli("liquidity", "refresh", leaf, *scope_flags(leaf), "--" + flag, values[0])[
            "data"
        ]["row_count"]
        == 3
    )
    count = len(browser.business_requests)
    assert (
        cli("liquidity", "list", leaf, "--limit", "0", *select)["data"] == records[:2]
    )
    assert cli("liquidity", "list", leaf, "--limit", "0")["data"] == records
    assert len(browser.business_requests) == count


def test_eod_native_identity_retains_same_transaction_and_scope(installed):
    leaf = "cash.statements.end_of_day"
    cli, browser = installed(leaf)
    first = {**native_row(leaf), "end2endid": "statement-1"}
    second = {**first, "end2endid": "statement-2", "amount": None}
    browser.business_script.append(page(leaf, [first, second]))
    result = cli(
        "liquidity", "list", leaf, "--live", "--require-complete", *scope_flags(leaf)
    )
    assert result["data"] == [first, second]
    assert result["meta"]["complete"] is True


@pytest.mark.parametrize("leaf", MEMBERS)
@pytest.mark.parametrize("value", [None, "absent"])
def test_missing_and_null_member_arrays_remain_distinct(installed, leaf, value):
    cli, browser = installed(leaf)
    record = native_row(leaf)
    if value is None:
        record[MEMBERS[leaf][0]] = None
    browser.business_script.append(page(leaf, [record]))
    assert cli("liquidity", "list", leaf, "--live")["data"] == [record]


@pytest.mark.parametrize("leaf", MEMBERS)
def test_string_and_integer_parent_identities_remain_distinct(installed, leaf):
    cli, browser = installed(leaf)
    records = [{**native_row(leaf), "id": identity} for identity in [1, "1"]]
    browser.business_script.append(page(leaf, records))
    result = cli("liquidity", "list", leaf, "--live", "--require-complete")
    assert result["data"] == records
    assert result["meta"]["complete"] is True


@pytest.mark.parametrize(
    "field,bad",
    [
        ("instId", "outside"),
        ("bankAccountAliasName", "outside"),
        ("currency", "EUR"),
        ("valueDate", "20260930"),
        ("valueDate", "20261003"),
    ],
)
def test_end_of_day_rejects_records_outside_requested_scope(installed, field, bad):
    leaf = "cash.statements.end_of_day"
    cli, browser = installed(leaf)
    record = {**native_row(leaf), field: bad}
    browser.business_script.append(page(leaf, [record]))
    assert (
        cli("liquidity", "list", leaf, "--live", *scope_flags(leaf), code=1)["error"][
            "code"
        ]
        == "INVALID_RESPONSE"
    )


def test_group_native_selection_and_cached_exact_filter(installed):
    leaf = "cash.group_balances"
    cli, browser = installed(leaf)
    records = [
        {**native_row(leaf, n), "userGroupCode": code}
        for n, code in enumerate(["G1", "G2", "g1"])
    ]
    browser.business_script.append(page(leaf, records))
    cli("liquidity", "refresh", leaf)
    requests = len(browser.business_requests)
    assert (
        cli(
            "liquidity",
            "list",
            leaf,
            "--limit",
            "0",
            "--group-code",
            "G1",
            "--group-code",
            "G2",
            "--group-code",
            "G1",
        )["data"]
        == records[:2]
    )
    assert len(browser.business_requests) == requests
    browser.business_script.append(page(leaf, records[:1]))
    assert (
        cli("liquidity", "list", leaf, "--live", "--group-code", "G1")["data"]
        == records[:1]
    )
    expected = expected_request(leaf)
    expected[LEAVES[leaf][1]]["userGroupCode"] = ["G1"]
    assert decoded_request(leaf, browser.business_requests[-1]) == expected


@pytest.mark.parametrize(
    "leaf", ["cash.pools", "cash.pool_balances", "cash.group_balances"]
)
def test_contradictory_native_tenant_is_rejected(installed, leaf):
    cli, browser = installed(leaf)
    browser.business_script.append(
        page(leaf, [{**native_row(leaf), "tntInstId": "WRONG"}])
    )
    assert (
        cli("liquidity", "list", leaf, "--live", code=1)["error"]["code"]
        == "INVALID_RESPONSE"
    )


@pytest.mark.parametrize("leaf", ["cash.pools", "cash.pool_balances"])
def test_contradictory_native_pool_category_is_rejected(installed, leaf):
    cli, browser = installed(leaf)
    browser.business_script.append(
        page(leaf, [{**native_row(leaf), "cashPoolCategory": "VIRTUAL"}])
    )
    assert (
        cli("liquidity", "list", leaf, "--live", code=1)["error"]["code"]
        == "INVALID_RESPONSE"
    )


def test_group_response_must_match_explicit_native_selection(installed):
    leaf = "cash.group_balances"
    cli, browser = installed(leaf)
    browser.business_script.append(
        page(leaf, [{**native_row(leaf), "userGroupCode": "G2"}])
    )
    result = cli("liquidity", "list", leaf, "--live", "--group-code", "G1", code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize(
    "leaf", ["cash.statements.intraday", "cash.statements.end_of_day"]
)
@pytest.mark.parametrize(
    "flag,value",
    [
        ("--from-date", "2026-02-30"),
        ("--from-date", "20261003"),
        ("--to-date", "2026-09-30"),
        ("--timezone", "UTC"),
    ],
)
def test_invalid_statement_scope_rejects_before_business_fetch(
    installed, leaf, flag, value
):
    cli, browser = installed(leaf)
    flags = scope_flags(leaf)
    if flag in flags:
        flags[flags.index(flag) + 1] = value
    else:
        flags.extend([flag, value])
    result = cli(
        "liquidity",
        "list",
        leaf,
        "--live",
        *flags,
        code=2,
    )
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


def test_waterlevel_response_must_match_requested_native_alias(installed):
    leaf = "cash.waterlevels"
    cli, browser = installed(leaf)
    browser.business_script.append(
        page(leaf, [{**native_row(leaf), "aliasName": "outside"}])
    )
    result = cli("liquidity", "refresh", leaf, *scope_flags(leaf), code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize("tenant", [None, "", "WRONG"])
def test_adjustment_tenant_echo_preserves_unknown_but_rejects_conflict(
    installed, tenant
):
    leaf = "forecast.adjustments"
    cli, browser = installed(leaf)
    record = {**native_row(leaf), "tntInstId": tenant}
    browser.business_script.append(page(leaf, [record]))
    result = cli(
        "liquidity", "list", leaf, "--live", code=1 if tenant == "WRONG" else 0
    )
    if tenant == "WRONG":
        assert result["error"]["code"] == "INVALID_RESPONSE"
    else:
        assert result["data"] == [record]


def test_intraday_missing_currency_rejects_and_preserves_cache(installed):
    leaf = "cash.statements.intraday"
    cli, browser = installed(leaf)
    records = [native_row(leaf)]
    browser.business_script.append(page(leaf, records))
    cli("liquidity", "refresh", leaf, *scope_flags(leaf))
    before = cli("liquidity", "list", leaf, "--limit", "0")
    browser.business_script.append(page(leaf, [{"bankTransNo": "tx"}]))
    result = cli("liquidity", "refresh", leaf, *scope_flags(leaf), code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"] == records
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


@pytest.mark.parametrize("nested", [False, True])
def test_group_contradictory_equivalent_currency_preserves_cache(installed, nested):
    leaf = "cash.group_balances"
    cli, browser = installed(leaf)
    record = native_row(leaf)
    browser.business_script.append(page(leaf, [record]))
    cli("liquidity", "refresh", leaf)
    before = cli("liquidity", "list", leaf, "--limit", "0")
    if nested:
        record["memberList"] = [{"id": "member-1", "equiCurrency": "EUR"}]
    else:
        record["equiCurrency"] = "EUR"
    browser.business_script.append(page(leaf, [record]))
    result = cli("liquidity", "refresh", leaf, code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


@pytest.mark.parametrize("leaf", LEAVES)
def test_short_nonfinal_page_preserves_cache(installed, leaf):
    cli, browser = installed(leaf)
    flags = scope_flags(leaf)
    record = native_row(leaf)
    browser.business_script.append(page(leaf, [record]))
    cli("liquidity", "refresh", leaf, *flags)
    before = cli("liquidity", "list", leaf, "--limit", "0")
    browser.business_script.extend(
        [page(leaf, [record], LEAVES[leaf][0] + 1), page(leaf, [], LEAVES[leaf][0] + 1)]
    )
    result = cli("liquidity", "refresh", leaf, *flags, "--require-complete", code=1)
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


@pytest.mark.parametrize("leaf", LEAVES)
def test_sdk_conflicts_reject_inconsistent_rows(installed, leaf):
    cli, browser = installed(leaf)
    first = native_row(leaf)
    changed = {**first, "unknown": {"changed": True}}
    browser.business_script.append(page(leaf, [first, changed]))
    result = cli(
        "liquidity", "list", leaf, "--live", "--limit", "0", *scope_flags(leaf), code=1
    )
    assert result["data"] is None
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["meta"]["complete"] is False
    assert result["meta"]["acquisition"]["duplicate_count"] == 1
    reasons = result["meta"]["acquisition"]["reasons"]
    assert "IDENTITY_CONTENT_CONFLICT" in reasons
    assert "LAST_ARRIVAL_WINS" in reasons


@pytest.mark.parametrize("leaf", ["cash.statements.end_of_day", "cash.credit_lines"])
def test_sdk_cross_page_overlap_preserves_prior_snapshot(installed, leaf):
    cli, browser = installed(leaf)
    size = LEAVES[leaf][0]
    records = [native_row(leaf, n) for n in range(size)]
    changed = {**records[0], "unknown": {"changed": True}}
    flags = scope_flags(leaf)
    browser.business_script.append(page(leaf, [records[0]]))
    cli("liquidity", "refresh", leaf, *flags)
    before = cli("liquidity", "list", leaf, "--limit", "0")
    browser.business_script.extend(
        [page(leaf, records, size + 1), page(leaf, [changed], size + 1)]
    )
    rejected = cli("liquidity", "refresh", leaf, *flags, code=1)
    assert rejected["error"]["code"] == "INCOMPLETE_RESULT"
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


def test_eod_missing_native_primary_key_has_no_composite_fallback(installed):
    leaf = "cash.statements.end_of_day"
    cli, browser = installed(leaf)
    record = native_row(leaf)
    del record["end2endid"]
    browser.business_script.append(page(leaf, [record]))
    result = cli("liquidity", "list", leaf, "--live", *scope_flags(leaf), code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"


def test_eod_reused_native_key_rejects_different_bank_transaction_content(installed):
    leaf = "cash.statements.end_of_day"
    cli, browser = installed(leaf)
    first = native_row(leaf)
    second = {**first, "bankTransNo": "another-transaction"}
    browser.business_script.append(page(leaf, [first, second]))
    result = cli(
        "liquidity",
        "list",
        leaf,
        "--live",
        "--require-complete",
        *scope_flags(leaf),
        code=1,
    )
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert "IDENTITY_CONTENT_CONFLICT" in result["meta"]["acquisition"]["reasons"]


@pytest.mark.parametrize("bank_number", [None, "", "absent"])
def test_eod_bank_transaction_number_is_output_only(installed, bank_number):
    leaf = "cash.statements.end_of_day"
    cli, browser = installed(leaf)
    record = {**native_row(leaf), "bankTransNo": bank_number}
    if bank_number == "absent":
        del record["bankTransNo"]
    browser.business_script.append(page(leaf, [record]))
    result = cli("liquidity", "list", leaf, "--live", *scope_flags(leaf))
    assert result["data"] == [record]
    assert result["meta"]["complete"] is True


@pytest.mark.parametrize(
    "field", ["instId", "bankAccountAliasName", "currency", "valueDate"]
)
@pytest.mark.parametrize("bad", [None, "", "absent", True, {}])
def test_eod_native_key_does_not_replace_required_scope_fields(installed, field, bad):
    leaf = "cash.statements.end_of_day"
    cli, browser = installed(leaf)
    record = {**native_row(leaf), field: bad}
    if bad == "absent":
        del record[field]
    browser.business_script.append(page(leaf, [record]))
    result = cli("liquidity", "list", leaf, "--live", *scope_flags(leaf), code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
