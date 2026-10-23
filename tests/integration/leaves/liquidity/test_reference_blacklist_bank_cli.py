"""Installed bank blacklist SDK acquisition, raw records and local filters."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAF = "reference.blacklist.bank"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
TENANT = "GUAPW3SG"


def row(bank="BANK", swift="SWIFT", modified=20, created=10, **values):
    return {
        "bankId": bank,
        "bankSwiftCode": swift,
        "gmtModified": modified,
        "gmtCreate": created,
        "status": "VALID",
        "tntInstId": "",
        "unknown": {
            "amount": Decimal("0.123456789012345678901"),
            "values": [None, False, "", 0],
        },
        **values,
    }


def page(rows, total=None, **extra):
    count = len(rows) if total is None else total
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": count,
            "result": {"success": True, "count": count, "data": rows},
            **extra,
        },
    }


def decoded_requests(browser):
    result = []
    for request in browser.business_requests:
        assert set(request) == {"tntInstId", "bankFilterConfigQuery"}
        assert request["tntInstId"] == TENANT
        assert isinstance(request["bankFilterConfigQuery"], str)
        result.append(parse(request["bankFilterConfigQuery"]))
    return result


@pytest.fixture(params=["directory"])
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
    browser = FakeBrowser(
        href="https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        result, output, error = run_cli(["liquidity", action, LEAF, *args])
        assert result == code, output + error
        return parse(output)

    try:
        source = tmp_path / "source"
        shutil.copytree(SOURCE, source)
        if request.param == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(source))
            source = archive_path
        result, output, error = run_cli(["plugins", "install", str(source)])
        assert result == 0, output + error
        if request.param == "directory":
            shutil.rmtree(source)
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def acquisition(browser, rows):
    """One acquisition, independent shifted overlap and exact-total terminal."""
    browser.business_script.extend(
        [
            page(rows),
            page(rows[1:] if len(rows) > 1 else rows),
            page([], total=len(rows)),
        ]
        if rows
        else [page([]), page([])]
    )
    # Overlap witnesses retain the source's total, not the response length.
    if rows:
        browser.business_script[-2] = page(
            rows[1:] if len(rows) > 1 else rows, total=len(rows)
        )


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_native_selection_occurrence_coverage_and_offline(installed):
    cli, browser, config = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.transports
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    rows = [
        row("B", "S", 20, 10),
        row("B", "S", 20, 30, status="INVALID"),
        row("B", "OTHER", 10, 90),
        row("C", "", 20, 10),
        row("B", "S", 19, 99),
    ]
    expected = [rows[1], rows[2], rows[3]]
    acquisition(browser, rows)
    live = cli("list", "--live", "--limit", "0", "--require-complete")
    assert live["data"] == expected
    assert live["meta"]["reported_total"] == 5
    assert live["meta"]["collected_total"] == 3
    assert live["meta"]["complete"] is True
    assert live["meta"]["coverage_ratio"] == 1
    assert live["meta"]["missing_count"] == 0
    assert live["meta"]["acquisition"]["arrivals"] == 5
    assert live["meta"]["warnings"][0]["code"] == "SOURCE_ROWS_SELECTED"
    assert not (config / "leaf-cache.sqlite3").exists()
    acquisition(browser, rows)
    saved = cli("refresh", "--require-complete")
    calls = len(browser.business_requests)
    offline = cli("list", "--limit", "0")
    assert offline["data"] == expected
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert offline["meta"]["acquisition"] == live["meta"]["acquisition"]
    assert len(browser.business_requests) == calls
    assert [(r["rowStart"], r["pageSize"]) for r in decoded_requests(browser)] == [
        (0, 5000),
        (1, 1000),
        (5, 1000),
    ] * 2
    assert all(r["currentArea"] == "2" for r in decoded_requests(browser))


def test_selection_precedes_exact_local_filters(installed):
    cli, browser, _ = installed
    old = row("B", "S", status="VALID")
    new = row("B", "S", modified=30, status="INVALID")
    rows = [old, new, row("B", "OTHER"), row("*", "S")]
    acquisition(browser, rows)
    cli("refresh", "--require-complete")
    assert cli("list", "--bank-id", "B", "--status", "VALID")["data"] == [rows[2]]
    assert cli("list", "--bank-id", "B", "--status", "INVALID")["data"] == [new]
    assert cli("list", "--bank-id", "*")["data"] == [rows[3]]
    assert cli("list", "--bank-id", "B,*")["data"] == []
    assert len(browser.business_requests) == 3


@pytest.mark.parametrize("flag", ["bank-id", "status"])
def test_blank_filter_rejected_before_auth(installed, flag):
    cli, browser, _ = installed
    assert (
        cli("list", "--live", "--" + flag, " ", code=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert not browser.transports


@pytest.mark.parametrize(
    "failure",
    ["auth", "outer", "inner", "count", "identity", "swift", "timestamp", "tenant"],
)
def test_invalid_source_preserves_prior_capture(installed, failure):
    cli, browser, _ = installed
    acquisition(browser, [row()])
    saved = cli("refresh", "--require-complete")
    candidate = page([row("OTHER")])
    body = candidate["body"]
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "outer":
        body["resultFlag"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "inner":
        body["result"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "count":
        body["count"] = 9
    elif failure == "identity":
        body["result"]["data"][0]["bankId"] = ""
    elif failure == "swift":
        body["result"]["data"][0]["bankSwiftCode"] = None
    elif failure == "timestamp":
        body["result"]["data"][0]["gmtModified"] = True
    else:
        body["result"]["data"][0]["tntInstId"] = "OTHER"
    browser.business_script.append(candidate)
    failed = cli("refresh", "--require-complete", code=1)
    assert failed["error"]["code"] == expected
    assert failed["meta"]["published"] is False
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "failure", ["changed_overlap", "short_overlap", "changed_total", "bounds"]
)
def test_coverage_witness_failures_never_publish(installed, failure):
    cli, browser, _ = installed
    acquisition(browser, [row()])
    saved = cli("refresh", "--require-complete")
    rows = [row("A"), row("B")]
    browser.business_script.append(page(rows))
    expected = "INVALID_RESPONSE"
    if failure == "changed_overlap":
        browser.business_script.append(page([row("C")], total=2))
    elif failure == "short_overlap":
        browser.business_script.append(page([], total=2))
        expected = "INCOMPLETE_RESULT"
    elif failure == "changed_total":
        browser.business_script.append(page([row("B")], total=3))
    else:
        browser.business_script.append(page(rows, total=2))
    assert cli("refresh", "--require-complete", code=1)["error"]["code"] == expected
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_capped_source_restarts_then_checks_all_page_joins(installed):
    cli, browser, _ = installed
    rows = [row(str(i)) for i in range(1001)]
    browser.business_script.extend(
        [
            page([row("GHOST")], total=1001),
            page(rows[:1000], total=1001),
            page(rows[1000:], total=1001),
            page(rows[1:], total=1001),
            page(rows[999:], total=1001),
            page([], total=1001),
        ]
    )
    result = cli("list", "--live", "--limit", "0", "--require-complete")
    assert result["data"] == rows
    assert [(r["rowStart"], r["pageSize"]) for r in decoded_requests(browser)] == [
        (0, 5000),
        (0, 1000),
        (1000, 1000),
        (1, 1000),
        (999, 1000),
        (1001, 1000),
    ]


def test_empty_scope_has_independent_empty_witness(installed):
    cli, browser, _ = installed
    acquisition(browser, [])
    result = cli("list", "--live", "--require-complete")
    assert result["data"] == []
    assert result["meta"]["complete"] is True
    assert len(browser.business_requests) == 2


def test_identical_duplicate_occurrences_are_legitimate(installed):
    cli, browser, _ = installed
    acquisition(browser, [row(), row()])
    result = cli("list", "--live", "--require-complete")
    assert result["data"] == [row()]
    assert result["meta"]["reported_total"] == 2
    assert result["meta"]["complete"] is True


def test_closed_native_query_rejects_extra_selector_before_network(
    installed, run_cli, tmp_path
):
    cli, browser, _ = installed
    status, output, error = run_cli(["plugins", "uninstall", "liquidity." + LEAF])
    assert status == 0, output + error
    source = tmp_path / "unverified-query"
    shutil.copytree(SOURCE, source)
    adapter = source / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            '"rowStart": row_start,', '"unknownSelector": True, "rowStart": row_start,'
        )
    )
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 0, output + error
    assert cli("list", "--live", code=1)["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_distinct_payloads_tied_on_both_timestamps_fail_without_publication(installed):
    cli, browser, _ = installed
    acquisition(browser, [row(), row(status="INVALID")])
    failed = cli("refresh", "--require-complete", code=1)
    assert failed["error"]["code"] == "INVALID_RESPONSE"
    assert failed["meta"]["published"] is False


def test_same_rank_boolean_zero_payload_conflict_is_not_collapsed(installed):
    cli, browser, _ = installed
    acquisition(browser, [row(unknown={"flag": False}), row(unknown={"flag": 0})])
    failed = cli("refresh", "--require-complete", code=1)
    assert failed["error"]["code"] == "INVALID_RESPONSE"
    assert failed["meta"]["published"] is False


def test_overlap_boolean_zero_payload_change_is_not_accepted(installed):
    cli, browser, _ = installed
    rows = [row("A"), row("B", unknown={"flag": False})]
    browser.business_script.extend(
        [page(rows), page([row("B", unknown={"flag": 0})], total=2)]
    )
    failed = cli("refresh", "--require-complete", code=1)
    assert failed["error"]["code"] == "INVALID_RESPONSE"
    assert failed["meta"]["published"] is False


def test_same_modified_later_created_selects_despite_boolean_zero_difference(installed):
    cli, browser, _ = installed
    old = row(created=10, unknown={"flag": False})
    new = row(created=11, unknown={"flag": 0})
    acquisition(browser, [old, new])
    result = cli("list", "--live", "--require-complete")
    assert result["data"] == [new]
    assert type(result["data"][0]["unknown"]["flag"]) is int
