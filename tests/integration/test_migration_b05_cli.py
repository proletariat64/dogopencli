"""B05 installed packages through public CLI and synthetic native CDP responses."""

from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
CASES = (
    "holdings",
    "transactions",
    "compound_ledger",
    "benchmark_values",
)
WINDOW = ("--from-date", "2026-10-01", "--to-date", "2026-10-03")
ENDPOINTS = {
    "holdings": "/portfolioQueryList.json",
    "transactions": "/queryIncrementOrderList.json",
    "compound_ledger": "/compoundOrderList.json",
    "benchmark_values": "/queryStrategyBenchmarkList.json",
}
SIZES = dict(zip(CASES, (500, 5000, 5000, 5000), strict=True))
IDENTITIES = {
    "holdings": ("investmentNo",),
    "transactions": ("orderId",),
    "compound_ledger": ("orderNo",),
    "benchmark_values": (
        "effectiveDate",
        "strategyBenchmarkType",
        "currency",
        "colorType",
    ),
}


def scope(case):
    if case == "holdings":
        return ("--date", "2026-10-03")
    if case == "benchmark_values":
        return WINDOW
    return ()


def record(case, index=0):
    row = {
        "amount": Decimal("0.123456789012345678901"),
        "textAmount": "1.0000",
        "currency": "USD",
        "productCode": "PRODUCT-A",
        "unknown": {"null": None, "false": False, "empty": "", "list": [0, "0"]},
    }
    if case == "benchmark_values":
        row.update(
            id="",
            effectiveDate="20261002",
            strategyBenchmarkType=f"S{index}",
            colorType="RED",
            value="2.0012300",
        )
    else:
        row[IDENTITIES[case][0]] = f"I{index}"
    if case == "holdings":
        row["valueDate"] = "20220815"  # Native holding date is not snapshot date.
    return row


def page(records, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "data": records,
                "totalCount": len(records) if total is None else total,
            },
        },
    }


def expected_request(case, offset=0):
    body = {"tntInstId": "GUAPW3SG", "rowStart": offset, "pageSize": SIZES[case]}
    if case == "holdings":
        body.update(date="20261003", status=["ACTIVE", "INACTIVE"])
    elif case == "benchmark_values":
        body.update(
            timeZone="GMT+08", valueDateStart="20261001", valueDateEnd="20261003"
        )
    return body


@pytest.fixture(params=CASES)
def installed(request, run_cli, tmp_path, monkeypatch):
    case, source_format = (
        request.param
        if isinstance(request.param, tuple)
        else (request.param, "directory")
    )
    leaf = "investment." + case
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

    def cli(action, *args, code=0, scoped=True):
        status, output, error = run_cli(
            [
                "liquidity",
                action,
                leaf,
                *(
                    scope(case)
                    if scoped
                    and (action == "refresh" or (action == "list" and "--live" in args))
                    else ()
                ),
                *args,
            ]
        )
        assert status == code, output + error
        return parse(output)

    try:
        assert run_cli(["domain", "enable", "liquidity"])[0] == 0
        package = ROOT / "leaf_packages/liquidity" / leaf
        if source_format == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(package))
            package = archive_path
        status, output, error = run_cli(["plugins", "install", str(package)])
        assert status == 0, output + error
        yield case, cli, browser, config
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize(
    "installed",
    [(case, kind) for case in CASES for kind in ("directory", "zip")],
    indirect=True,
    ids=[f"{case}-{kind}" for case in CASES for kind in ("directory", "zip")],
)
def test_native_records_request_and_refresh_offline_equality(installed):
    case, cli, browser, _ = installed
    rows = [record(case, n) for n in range(3)]
    cli("list", "-h", scoped=False)
    cli("describe")
    assert not browser.business_requests
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(rows))
    live = cli("list", "--live", "--limit", "0")
    assert live["data"] == rows
    assert live["meta"]["complete"] is True
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(rows))
    refreshed = cli("refresh", "--limit", "1")
    assert refreshed["data"]["row_count"] == 3
    count = len(browser.business_requests)
    offline = cli("list", "--limit", "0")
    assert offline["data"] == rows
    assert offline["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert len(browser.business_requests) == count
    assert browser.business_requests == [expected_request(case)] * 2
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert all(ENDPOINTS[case] in e and "application/json" in e for e in expressions)
    if case == "benchmark_values":
        assert all("primaryId" not in row for row in offline["data"])


def test_pagination_precedes_display_limit(installed):
    case, cli, browser, _ = installed
    size = SIZES[case]
    rows = [record(case, n) for n in range(size + 1)]
    browser.business_script.extend(
        [page(rows[:size], size + 1), page(rows[size:], size + 1)]
    )
    result = cli("list", "--live", "--limit", "1", "--require-complete")
    assert result["data"] == rows[:1]
    assert result["meta"]["complete"] is True
    assert result["meta"]["collected_total"] == size + 1
    assert browser.business_requests == [
        expected_request(case),
        expected_request(case, size),
    ]


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "business",
        "nested-business",
        "flag-type",
        "rows",
        "count-type",
        "count-bool",
        "count-negative",
        "changed-count",
        "early-empty",
        "overfull",
        "conflict",
        "duplicate-strict",
        "auth",
    ],
)
def test_rejected_acquisition_preserves_saved_records_and_metadata(installed, failure):
    case, cli, browser, _ = installed
    row, size = record(case), SIZES[case]
    browser.business_script.append(page([row]))
    cli("refresh")
    before = cli("list", "--limit", "0")
    response, expected, flags = page([row]), "INVALID_RESPONSE", ()
    if failure == "empty":
        response, expected = page([]), None
    elif failure == "business":
        response["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "nested-business":
        response["body"]["data"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "flag-type":
        response["body"]["success"] = 1
    elif failure == "rows":
        response["body"]["data"]["data"] = {}
    elif failure.startswith("count-"):
        response["body"]["data"]["totalCount"] = {
            "count-type": "1",
            "count-bool": True,
            "count-negative": -1,
        }[failure]
    elif failure in {"changed-count", "early-empty"}:
        if failure == "early-empty":
            expected = "INCOMPLETE_RESULT"
        browser.business_script.append(
            page([record(case, n) for n in range(size)], size + 1)
        )
        response = page([], size + (2 if failure == "changed-count" else 1))
    elif failure == "overfull":
        response = page([record(case, n) for n in range(size + 1)])
    elif failure == "conflict":
        expected = "INCOMPLETE_RESULT"
        response = page([row, {**row, "amount": "different"}])
    elif failure == "duplicate-strict":
        response = page([row, row])
        expected, flags = "INCOMPLETE_RESULT", ("--require-complete",)
    elif failure == "auth":
        response, expected = {"status": 401, "body": {}}, "AUTH_REQUIRED"
    browser.business_script.append(response)
    result = cli("refresh", *flags, code=1 if expected else 0)
    if expected:
        assert result["error"]["code"] == expected
    else:
        assert result["meta"]["published"] is False
    after = cli("list", "--limit", "0")
    assert after["data"] == before["data"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


@pytest.mark.parametrize("bad", [None, "", "   ", True, {}, [], Decimal("1.5")])
def test_invalid_native_identity_is_rejected(installed, bad):
    case, cli, browser, _ = installed
    row = record(case)
    row[IDENTITIES[case][0]] = bad
    browser.business_script.append(page([row]))
    assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


def test_identical_duplicates_are_incomplete(installed):
    case, cli, browser, _ = installed
    row = record(case)
    browser.business_script.append(page([row, row]))
    result = cli("list", "--live", "--limit", "0")
    assert result["data"] == [row]
    assert result["meta"]["complete"] is False


def test_local_repeat_filters_do_not_narrow_native_acquisition(installed):
    case, cli, browser, _ = installed
    if case not in {"holdings", "transactions"}:
        pytest.skip("No declared local filters")
    rows = [record(case, n) for n in range(4)]
    rows[1].update(currency="EUR", productCode="PRODUCT-B")
    rows[2].update(currency="usd")
    rows[3].update(productCode="OTHER")
    browser.business_script.append(page(rows))
    cli("refresh", "--currency", "USD", "--product-code", "PRODUCT-A")
    assert browser.business_requests == [expected_request(case)]
    assert cli("list", "--limit", "0")["data"] == rows
    selected = cli(
        "list",
        "--limit",
        "0",
        "--currency",
        "USD",
        "--currency",
        "EUR",
        "--product-code",
        "PRODUCT-A",
        "--product-code",
        "PRODUCT-B",
    )
    assert selected["data"] == rows[:2]


@pytest.mark.parametrize(
    "bad", ["20261003", "2026-1-03", "2026-02-30", "２０２６-１０-０３"]
)
def test_public_dates_require_iso_calendar_dates(installed, bad):
    case, cli, browser, _ = installed
    if not scope(case):
        pytest.skip("No date scope")
    options = list(scope(case))
    options[options.index("--date" if case == "holdings" else "--from-date") + 1] = bad
    for action in ("list", "refresh"):
        cli(
            action,
            *options,
            *(("--live",) if action == "list" else ()),
            scoped=False,
            code=2,
        )
    assert not browser.business_requests


def test_missing_or_unverified_scope_rejected_before_contact(installed):
    case, cli, browser, _ = installed
    if scope(case):
        cli("list", "--live", scoped=False, code=2)
        cli("refresh", scoped=False, code=2)
    cli("list", "--live", "--time-zone", "GMT+00", code=2)
    assert not browser.business_requests


def test_scope_expansion_does_not_reuse_capture(installed):
    case, cli, browser, _ = installed
    if not scope(case):
        pytest.skip("Unscoped list")
    browser.business_script.append(page([record(case)]))
    cli("refresh")
    options = list(scope(case))
    if case == "holdings":
        options[-1] = "2026-10-04"
    else:
        options[options.index("--from-date") + 1] = "2026-09-30"
    cli("list", *options, scoped=False, code=2)
    assert len(browser.business_requests) == 1


def test_composite_identity_requires_every_dimension(installed):
    case, cli, browser, _ = installed
    if len(IDENTITIES[case]) == 1:
        pytest.skip("Single identity")
    for field in IDENTITIES[case]:
        row = record(case)
        del row[field]
        browser.business_script.append(page([row]))
        assert cli("list", "--live", code=1)["error"]["code"] == "INVALID_RESPONSE"


def test_reversed_window_rejected_before_contact(installed):
    case, cli, browser, _ = installed
    if case != "benchmark_values":
        pytest.skip("No date window")
    options = list(scope(case))
    options[options.index("--from-date") + 1] = "2026-10-04"
    cli("list", "--live", *options, scoped=False, code=2)
    cli("refresh", *options, scoped=False, code=2)
    assert not browser.business_requests


@pytest.mark.parametrize("mutation", ["extra", "tenant", "size"])
def test_shared_transport_rejects_unverified_native_request(
    installed, tmp_path, mutation, run_cli
):
    import shutil

    case, cli, browser, _ = installed
    leaf = "investment." + case
    assert run_cli(["plugins", "uninstall", "liquidity." + leaf])[0] == 0
    package = tmp_path / "mutated"
    shutil.copytree(ROOT / "leaf_packages/liquidity" / leaf, package)
    path = package / "adapter.py"
    source = path.read_text()
    if mutation == "extra":
        old, new = (
            'return {**values, "rowStart":',
            'return {**values, "unverified": True, "rowStart":',
        )
    elif mutation == "tenant":
        old, new = (
            'return {**values, "rowStart":',
            'return {**values, "tntInstId": "WRONG", "rowStart":',
        )
    else:
        old, new = '"pageSize": page_size}', '"pageSize": 1}'
    assert old in source
    path.write_text(source.replace(old, new, 1))
    status, output, error = run_cli(["plugins", "install", str(package)])
    assert status == 0, output + error
    assert cli("list", "--live", code=1)["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_sdk_conflict_keeps_last_arrival_and_reports_incomplete(installed):
    case, cli, browser, _ = installed
    first = record(case)
    last = {**first, "amount": "last-arrival"}
    browser.business_script.append(page([first, last]))
    result = cli("list", "--live", "--limit", "0")
    assert result["data"] == [last]
    assert result["meta"]["complete"] is False
    assert "IDENTITY_CONTENT_CONFLICT" in result["meta"]["acquisition"]["reasons"]


def test_composite_identity_preserves_records_differing_in_each_dimension(installed):
    case, cli, browser, _ = installed
    if len(IDENTITIES[case]) == 1:
        pytest.skip("Single identity")
    first = record(case)
    rows = [first]
    for field in IDENTITIES[case]:
        value = "20261003" if field == "effectiveDate" else "OTHER"
        rows.append({**first, field: value})
    browser.business_script.append(page(rows))
    result = cli("list", "--live", "--limit", "0", "--require-complete")
    assert result["data"] == rows
    assert result["meta"]["complete"] is True
