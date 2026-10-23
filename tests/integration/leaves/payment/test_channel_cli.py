"""Channel short-page traversal, classified holes and conservative coverage."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.leaves.registry import Registry
from dogopencli.transport import QueryRequest, validate_request

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "leaf_packages/payment/channel"
STARTUP = "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"


def row(identity=1, scope="EXTERNAL", **extra):
    return {
        "abilityId": identity,
        "payoutType": scope,
        "financialInstCode": "BANK",
        "debitInstCountryCode": "GB",
        "status": "ENABLE",
        "debitAccountName": "ACCOUNT",
        "debitAccountNo": "123",
        "clearingSystemName": "SWIFT",
        "debitCurrency": "USD",
        "creditCurrency": "USD",
        "configVersion": "",
        "unknown": {"values": [Decimal("1.00000000000000001"), None, "", False]},
        **extra,
    }


def page(records, number=1, total=None, size=100, **paging):
    count = len(records) if total is None else total
    return {
        "status": 200,
        "body": {
            "success": True,
            "status": True,
            "resultObj": {
                "success": True,
                "payoutAbilityVOList": records,
                "pageNum": number,
                "pageSize": size,
                "totalCount": count,
                "totalPages": -(-count // 100),
                **paging,
            },
        },
    }


def scripted(browser, records):
    def handler(body, _):
        assert set(body) == {"payoutType", "pageNum", "pageSize"}
        width = body["pageSize"]
        assert 1 <= width <= 100
        start = (body["pageNum"] - 1) * width
        return page(
            records[start : start + width], body["pageNum"], len(records), size=width
        )

    browser.business_handler = handler


@pytest.fixture
def installed(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for key in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(key, raising=False)
    browser = FakeBrowser(href=STARTUP)
    cdp.set_transport_factory(browser.transport)
    source = SOURCE
    if getattr(request, "param", "directory") == "zip":
        target = tmp_path / "candidate.zip"
        with ZipFile(target, "w") as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(source))
        source = target
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 0, output + error

    def cli(action, *flags, code=0):
        status, output, error = run_cli(["payment", action, "channel", *flags])
        assert status == code, output + error
        return parse(output)

    try:
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_native_records_multipage_local_filters_and_refresh_replay(installed):
    cli, browser, _ = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.transports
    native = [row(i) for i in range(101)] + [
        row(101, clearingSystemName="BOOK", creditCurrency="GBP")
    ]
    scripted(browser, native)
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    live = cli(
        "list",
        "--live",
        "--clearing-system-name",
        "BOOK",
        "--require-complete",
        "--limit",
        "0",
    )
    assert live["data"] == native[-1:]
    assert live["meta"]["reported_total"] is None
    assert live["meta"]["collected_total"] == 102
    assert live["meta"]["matched_total"] == 1
    assert [body["pageNum"] for body in browser.business_requests[:2]] == [1, 2]
    assert browser.business_requests[-2:] == [
        {"payoutType": "EXTERNAL", "pageNum": n, "pageSize": 100} for n in (3, 4)
    ]
    assert all(
        set(body) == {"pageNum", "pageSize", "payoutType"}
        for body in browser.business_requests
    )
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    saved = cli("refresh", "--require-complete")
    count = len(browser.business_requests)
    offline = cli(
        "list", "--clearing-system-name", "BOOK", "--require-complete", "--limit", "0"
    )
    assert offline["data"] == live["data"]
    assert offline["meta"]["matched_total"] == 1
    assert offline["meta"]["reported_total"] is None
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == count
    assert cli("list", "--clearing-system-name", "book")["data"] == []
    assert cli("list", "--debit-currency", "U*")["data"] == []
    assert cli("list", "--debit-currency", "USD,GBP")["data"] == []


@pytest.mark.parametrize("scope", ["EXTERNAL", "LIQUIDITY", "MANUAL", "SETTLEMENT"])
def test_four_native_payout_scopes(installed, scope):
    cli, browser, _ = installed
    scripted(browser, [row(scope=scope)])
    got = cli("list", "--live", "--payout-type", scope, "--require-complete")
    assert got["data"][0]["payoutType"] == scope
    assert browser.business_requests[0] == {
        "payoutType": scope,
        "pageNum": 1,
        "pageSize": 100,
    }
    assert browser.business_requests[-2:] == [
        {"payoutType": scope, "pageNum": n, "pageSize": 100} for n in (2, 3)
    ]


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
@pytest.mark.parametrize("conflict", [False, True])
def test_duplicate_primary_keys_deduplicate_or_hard_fail(installed, conflict):
    cli, browser, _ = installed
    scripted(browser, [row(999)])
    saved = cli("refresh", "--require-complete")
    original = [row(i) for i in range(100)]
    repeated = {**original[0], **({"status": "DISABLE"} if conflict else {})}
    scripted(browser, [*original, repeated])
    if conflict:
        rejected = cli("list", "--live", "--limit", "0", code=1)
        assert rejected["error"]["code"] == "INVALID_RESPONSE"
        assert rejected.get("data") in (None, [])
        failed = cli("refresh", "--require-complete", code=1)
        assert failed["meta"]["published"] is False
        assert failed["error"]["code"] == "INVALID_RESPONSE"
        offline = cli("list")
        assert offline["data"] == [row(999)]
        assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    else:
        got = cli("list", "--live", "--require-complete", "--limit", "0")
        assert got["data"] == original
        assert got["meta"]["complete"] is True
        assert got["meta"]["reported_total"] is None
        evidence = got["meta"]["acquisition"]
        assert evidence["coverage_basis"] == "accepted_short_page"
        assert evidence["arrivals"] == 101 and evidence["duplicate_count"] == 1
        assert "UNEXPECTED_DUPLICATE_ROWS" not in evidence["reasons"]
        refreshed = cli("refresh", "--require-complete")
        assert refreshed["meta"]["published"] is True
        count = len(browser.business_requests)
        offline = cli("list", "--require-complete", "--limit", "0")
        assert offline["data"] == original
        assert offline["meta"]["acquisition"]["coverage_basis"] == "accepted_short_page"
        assert len(browser.business_requests) == count


@pytest.mark.parametrize(
    "failure",
    [
        "business",
        "inner_business",
        "auth",
        "marker",
        "inner_marker",
        "status",
        "root",
        "rows",
        "id",
        "bool_id",
        "scope",
        "page",
        "clamp",
    ],
)
def test_failures_and_page_echoes_preserve_previous_capture(installed, failure):
    cli, browser, _ = installed
    scripted(browser, [row()])
    saved = cli("refresh", "--require-complete")
    browser.business_handler = None
    reply = page([row(2)])
    result = reply["body"]["resultObj"]
    expected = "INVALID_RESPONSE"
    if failure == "business":
        reply["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "inner_business":
        result["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "auth":
        reply = {"status": 403, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "marker":
        reply["body"]["success"] = "true"
    elif failure == "inner_marker":
        result["success"] = "true"
    elif failure == "status":
        reply["body"]["status"] = 1
    elif failure == "root":
        reply["body"]["resultObj"] = []
    elif failure == "rows":
        result["payoutAbilityVOList"] = None
    elif failure == "id":
        del result["payoutAbilityVOList"][0]["abilityId"]
    elif failure == "bool_id":
        result["payoutAbilityVOList"][0]["abilityId"] = True
    elif failure == "scope":
        result["payoutAbilityVOList"][0]["payoutType"] = "MANUAL"
    elif failure == "page":
        result["pageNum"] = 2
    elif failure == "clamp":
        result["pageSize"] = 10
    browser.business_script.append(reply)
    failed = cli("refresh", "--require-complete", code=1)
    assert failed["error"]["code"] == expected
    assert failed["meta"]["published"] is False
    assert cli("list")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "flag,field",
    [
        ("financial-inst-id", "financialInstCode"),
        ("debit-inst-country-code", "debitInstCountryCode"),
        ("status", "status"),
        ("debit-account-name", "debitAccountName"),
        ("debit-account-no", "debitAccountNo"),
        ("clearing-system-name", "clearingSystemName"),
        ("debit-currency", "debitCurrency"),
        ("credit-currency", "creditCurrency"),
    ],
)
def test_each_exact_local_filter_and_repeated_value_or(installed, flag, field):
    cli, browser, _ = installed
    alternative = "DISABLE" if flag == "status" else "OTHER"
    records = [row(1), row(2, **{field: alternative}), row(3, **{field: None})]
    scripted(browser, records)
    got = cli(
        "list",
        "--live",
        "--" + flag,
        records[0][field],
        "--" + flag,
        alternative,
        "--limit",
        "0",
        "--require-complete",
    )
    assert got["data"] == records[:2]
    assert got["meta"]["reported_total"] is None
    assert got["meta"]["matched_total"] == 2
    assert set(browser.business_requests[0]) == {"payoutType", "pageNum", "pageSize"}


@pytest.mark.parametrize("change", ["endpoint", "method", "extra", "width", "scope"])
def test_native_request_default_deny(installed, change):
    _, _, config = installed
    adapter = Registry(config / "config.toml").scan().get("payment", "channel").adapter
    capability = adapter.query_capability("list", "channels", {})
    body = capability.page_body("EXTERNAL", 1, 100)
    contract = capability.contract
    request = QueryRequest(
        capability.name, contract.method, contract.host, contract.path, deepcopy(body)
    )
    validate_request(request, contract)
    if change == "endpoint":
        request = replace(request, path="/mutation.json")
    elif change == "method":
        request = replace(request, method="GET")
    elif change == "extra":
        request.body["action"] = "save"
    elif change == "width":
        request.body["pageSize"] = 101
    else:
        with pytest.raises(CliError) as failure:
            capability.page_body("ANY", 1, 100)
        assert failure.value.code == "REQUEST_NOT_ALLOWED"
        return
    with pytest.raises(CliError) as failure:
        validate_request(request, contract)
    assert failure.value.code == "REQUEST_NOT_ALLOWED"


def record_hole(
    message="debit account not exists: test-account USD", code="IPAY_RS_510090020"
):
    return {
        "status": 200,
        "body": {"success": False, "status": False, "msgCode": code, "msg": message},
    }


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
@pytest.mark.parametrize("clamped", [False, True])
def test_known_holes_cold_hot_refresh_and_offline(installed, clamped):
    cli, browser, config = installed
    native = [row(i) for i in range(230)]
    holes = {103, 147, 148} if clamped else {147, 148, 203}

    def handler(body, _):
        width = body["pageSize"]
        number = body["pageNum"]
        start = (number - 1) * width
        if clamped and start >= len(native):
            number = -(-len(native) // width)
            start = (number - 1) * width
        if any(start <= position < start + width for position in holes):
            return record_hole()
        return page(native[start : start + width], number, total=9999, size=width)

    browser.business_handler = handler
    cold = cli("list", "--live", "--require-complete", "--limit", "0")
    assert cold["data"] == [r for i, r in enumerate(native) if i not in holes]
    assert cold["meta"]["complete"] is True
    assert cold["meta"]["reported_total"] is None
    assert "PAGINATION_HOLES_BYPASSED" in {w["code"] for w in cold["meta"]["warnings"]}
    attempt = cold["meta"]["acquisition"]["attempts"][0]
    assert attempt["hole_count"] == 3
    assert [(h["start"], h["end"]) for h in attempt["holes"]] == (
        [(103, 104), (147, 149)] if clamped else [(147, 149), (203, 204)]
    )
    assert attempt["termination_reason"] == (
        "two_clamped_batches" if clamped else "two_empty_batches"
    )
    if clamped:
        from dogopencli.result_policy import AcquisitionEvidence

        assert [
            b["native_terminal"]["native_page"] for b in attempt["terminal_batches"]
        ] == [3, 3]
        for field in ("requested_page", "native_page", "native_rows"):
            evidence = deepcopy(cold["meta"]["acquisition"])
            evidence["attempts"][0]["terminal_batches"][0]["native_terminal"][
                field
            ] = -1
            with pytest.raises(CliError, match="clamped terminal"):
                AcquisitionEvidence.from_record(evidence)
    saved = cli("refresh", "--require-complete")
    count = len(browser.business_requests)
    offline = cli("list", "--require-complete", "--limit", "0")
    assert offline["data"] == cold["data"]
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == count
    hot = offline["meta"]["acquisition"]["attempts"][0]
    assert hot["history_checked"] == hot["history_matched"] == 2
    history = (config / "collection-state.holes.json").read_text()
    assert "test-account" not in history and "debit account not exists" not in history


@pytest.mark.parametrize(
    "failure", [record_hole(code="OTHER"), record_hole(message="permission denied")]
)
def test_similar_business_errors_are_never_holes(installed, failure):
    cli, browser, _ = installed
    scripted(browser, [row()])
    saved = cli("refresh", "--require-complete")
    browser.business_handler = None
    browser.business_script.append(failure)
    got = cli("refresh", code=1)
    assert got["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert got["meta"]["published"] is False
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_native_totals_are_diagnostic_and_do_not_end_traversal(installed):
    cli, browser, _ = installed
    native = [row(i) for i in range(101)]

    def handler(body, _):
        width = body["pageSize"]
        start = (body["pageNum"] - 1) * width
        return page(
            native[start : start + width],
            body["pageNum"],
            total=0,
            size=width,
            totalPages=999,
        )

    browser.business_handler = handler
    got = cli("list", "--live", "--require-complete", "--limit", "0")
    assert got["data"] == native
    assert got["meta"]["reported_total"] is None


@pytest.mark.parametrize("invalid_terminal", ["full", "changed", "stale", "size"])
def test_unqualified_last_page_repetition_preserves_previous_capture(
    installed, invalid_terminal
):
    cli, browser, _ = installed
    scripted(browser, [row(999)])
    saved = cli("refresh", "--require-complete")
    native = [
        row(i)
        for i in range(
            200
            if invalid_terminal == "stale"
            else 100
            if invalid_terminal == "full"
            else 3
        )
    ]

    def handler(body, _):
        width = body["pageSize"]
        number = body["pageNum"]
        start = (number - 1) * width
        if start >= len(native):
            records = [
                r
                for r in native[:100]
                if invalid_terminal != "stale" or r["abilityId"] != 5
            ]
            if invalid_terminal == "changed":
                records[0] = {**records[0], "status": "DISABLE"}
            return page(records, 1, size=50 if invalid_terminal == "size" else width)
        records = [
            r
            for r in native[start : start + width]
            if invalid_terminal != "stale" or r["abilityId"] != 5
        ]
        return page(records, number, total=len(native), size=width)

    browser.business_handler = handler
    got = cli("refresh", code=1)
    assert got["error"]["code"] == "INVALID_RESPONSE"
    assert got["meta"]["published"] is False
    assert cli("list")["data"] == [row(999)]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
