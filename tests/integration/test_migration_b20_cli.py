"""Installed account strategies: typed versions, native scopes and SDK coverage."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
LEAF = "operations.account_strategies"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
LABELS = {
    "BANK_SWEEPING": "Bank Sweeping Agreement",
    "SELF_BUILD_CASH_POOL": "Self-Built Cash Pool",
    "PROGRAMMABLE_PAYMENT": "Programmable Payment",
    "AI_GLOBAL_DECISION": "AI Global Decision",
    "EOD_BAL_ESTIMATION": "EOD Bal Estimation Decision",
    "T0_DECISION": "T0 Decision",
    "RT_DECISION": "RT Decision",
    "NO_NEED": "No Need",
}


def row(alias="ACCOUNT", version=1, **values):
    return {
        "aliasName": alias,
        "currency": "USD",
        "version": version,
        "entity": "ENTITY",
        "bankId": "BANK",
        "accountType": "TYPE",
        "operationStrategy": (
            "Bank Sweeping Agreement, Self-Built Cash Pool, Bank Sweeping Agreement"
        ),
        "coverAlgorithm": "Y",
        "status": "Invalid",
        "processStatus": "SUBMITTED",
        "optional": None,
        "unknown": {
            "amount": Decimal("0.123456789012345678901"),
            "values": [None, False, "", 0],
        },
        **values,
    }


def page(rows, total=None, **echo):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "data": rows,
                "totalCount": len(rows) if total is None else total,
                **echo,
            },
        },
    }


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


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_full_native_versions_invalid_rows_arrival_order_and_offline(installed):
    cli, browser, config = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.transports
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    rows = [row("Z", 2), row("A", -1), row("Z", 1), row("Z", 1, currency="EUR")]
    browser.business_script.append(page(rows, pageSize=5000, rowStart=0))
    live = cli("list", "--live", "--limit", "0", "--require-complete")
    assert live["data"] == rows
    assert all(
        set(item) == set(source)
        for item, source in zip(live["data"], rows, strict=True)
    )
    assert live["meta"]["unique_count"] == 4
    assert not (config / "leaf-cache.sqlite3").exists()
    browser.business_script.append(page(rows))
    saved = cli("refresh", "--require-complete")
    assert cli("list", "--limit", "0")["data"] == rows
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert browser.business_requests == [{"rowStart": 0, "pageSize": 5000}] * 2
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions and all(
        "/strategyManage/queryList.json" in e
        and 'method: "POST"' in e
        and "application/json" in e
        for e in expressions
    )


@pytest.mark.parametrize(
    ("flags", "native"),
    [
        (["--entity", "ENTITY"], {"fundEntityList": ["ENTITY"]}),
        (["--bank", "BANK"], {"fundBankIdList": ["BANK"]}),
        (["--alias", "ACCOUNT"], {"aliasNameList": ["ACCOUNT"]}),
        (["--currency", "USD"], {"currencyList": ["USD"]}),
        (["--account-type", "TYPE"], {"accountTypeList": ["TYPE"]}),
        (
            ["--operation-strategy", "SELF_BUILD_CASH_POOL"],
            {"operationStrategyList": ["SELF_BUILD_CASH_POOL"]},
        ),
        (["--cover-algorithm", "Y"], {"coverAlgorithm": "Y"}),
    ],
)
def test_all_native_filters_and_supported_offline_scope(installed, flags, native):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", *flags, "--require-complete")
    assert browser.business_requests == [{**native, "rowStart": 0, "pageSize": 5000}]
    assert cli("list", *flags, "--require-complete")["data"] == [row()]
    assert cli("list", "--require-complete")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == 1


def test_repeat_or_and_canonical_sets_and_changed_scope_quality(installed):
    cli, browser, _ = installed
    rows = [row("B", currency="EUR"), row("A", currency="USD")]
    flags = [
        "--currency",
        "USD",
        "--currency",
        "EUR",
        "--currency",
        "USD",
        "--entity",
        "ENTITY",
    ]
    browser.business_script.append(page(rows))
    saved = cli("refresh", *flags, "--require-complete")
    assert browser.business_requests == [
        {
            "currencyList": ["EUR", "USD"],
            "fundEntityList": ["ENTITY"],
            "rowStart": 0,
            "pageSize": 5000,
        }
    ]
    assert (
        cli(
            "list",
            "--currency",
            "EUR",
            "--currency",
            "USD",
            "--entity",
            "ENTITY",
            "--require-complete",
        )["data"]
        == rows
    )
    changed = cli("list", "--currency", "JPY", "--require-complete", code=1)
    assert changed["error"]["code"] == "INCOMPLETE_RESULT"
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert cli("list", "--limit", "0")["data"] == rows


@pytest.mark.parametrize(
    ("code", "label"),
    list(LABELS.items()) + [("SELF_BUILD_CASH_POOL", "Self-Build Cash Pool")],
)
def test_known_strategy_codes_match_complete_display_members_unchanged(
    installed, code, label
):
    cli, browser, _ = installed
    display = " " + label + ", " + label + ", unrelated"
    native = row(operationStrategy=display)
    browser.business_script.append(page([native]))
    result = cli("list", "--live", "--operation-strategy", code, "--require-complete")
    assert result["data"] == [native]
    assert browser.business_requests == [
        {"operationStrategyList": [code], "rowStart": 0, "pageSize": 5000}
    ]


@pytest.mark.parametrize(
    "flags",
    [
        ["--entity", " "],
        ["--bank", " "],
        ["--alias", " "],
        ["--currency", " "],
        ["--account-type", " "],
        ["--operation-strategy", "UNKNOWN"],
        ["--cover-algorithm", "X"],
        ["--status", "VALID"],
    ],
)
def test_invalid_scope_refuses_before_browser(installed, flags):
    cli, browser, _ = installed
    assert cli("list", "--live", *flags, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "marker",
        "root",
        "rows",
        "alias",
        "currency",
        "version_string",
        "version_bool",
        "version_null",
        "total",
        "echo_size",
        "echo_offset",
        "scope",
    ],
)
def test_failure_preserves_saved_complete_capture(installed, failure):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", "--require-complete")
    candidate = page([row("OTHER")])
    body = candidate["body"]
    data = body["data"]
    expected = "INVALID_RESPONSE"
    flags = []
    if failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        body["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        body["success"] = 1
    elif failure == "root":
        body["data"] = []
    elif failure == "rows":
        data["data"] = None
    elif failure == "alias":
        data["data"][0]["aliasName"] = " "
    elif failure == "currency":
        data["data"][0]["currency"] = None
    elif failure == "version_string":
        data["data"][0]["version"] = "1"
    elif failure == "version_bool":
        data["data"][0]["version"] = True
    elif failure == "version_null":
        data["data"][0].pop("version")
    elif failure == "total":
        data["totalCount"] = True
    elif failure == "echo_size":
        data["pageSize"] = 10
    elif failure == "echo_offset":
        data["rowStart"] = 1
    else:
        flags = ["--currency", "EUR"]
    browser.business_script.append(candidate)
    failed = cli("refresh", *flags, "--require-complete", code=1)
    assert failed["error"]["code"] == expected
    assert failed["meta"]["published"] is False
    assert len(browser.business_requests) == 2
    cached = cli("list")
    assert cached["data"] == [row()]
    assert cached["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("conflict", [False, True])
def test_duplicate_identity_or_conflict_never_publishes(installed, conflict):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", "--require-complete")
    rows = [
        row("DUPLICATE"),
        row("DUPLICATE", status="Valid") if conflict else row("DUPLICATE"),
    ]
    browser.business_script.append(page(rows))
    assert (
        cli("refresh", "--require-complete", code=1)["error"]["code"]
        == "INCOMPLETE_RESULT"
    )
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_offset_stride_no_terminal_query_and_display_window(installed):
    cli, browser, _ = installed
    rows = [{"aliasName": str(i), "currency": "USD", "version": 1} for i in range(5001)]
    browser.business_script.extend(
        [page(rows[:5000], total=5001), page(rows[5000:], total=5001)]
    )
    result = cli("list", "--live", "--limit", "1", "--require-complete")
    assert result["data"] == rows[:1]
    assert result["meta"]["collected_total"] == 5001
    assert browser.business_requests == [
        {"rowStart": 0, "pageSize": 5000},
        {"rowStart": 5000, "pageSize": 5000},
    ]


def test_closed_transport_rejects_injected_tenant(installed, run_cli, tmp_path):
    cli, browser, _ = installed
    status, output, error = run_cli(["plugins", "uninstall", "liquidity." + LEAF])
    assert status == 0, output + error
    source = tmp_path / "badrequest"
    shutil.copytree(SOURCE, source)
    adapter = source / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            'return {**values, "rowStart": row_start, "pageSize": PAGE_SIZE}',
            'return {**values, "rowStart": row_start, '
            '"pageSize": PAGE_SIZE, "tntInstId": "GUAPW3SG"}',
        )
    )
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 0, output + error
    assert cli("list", "--live", code=1)["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_native_empty_array_remains_empty(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([]))
    assert cli("list", "--live", "--require-complete")["data"] == []


def test_short_native_scope_cannot_replace_saved_complete_capture(installed):
    cli, browser, _ = installed
    browser.business_script.append(page([row()]))
    saved = cli("refresh", "--require-complete")
    browser.business_script.append(page([row("PARTIAL")], total=2))
    rejected = cli("refresh", "--require-complete", code=1)
    assert rejected["error"]["code"] == "INCOMPLETE_RESULT"
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert cli("list")["data"] == [row()]


def test_changed_native_total_is_hard_failure_without_extra_probe(installed):
    cli, browser, _ = installed
    rows = [{"aliasName": str(i), "currency": "USD", "version": 1} for i in range(5001)]
    browser.business_script.extend(
        [page(rows[:5000], total=5001), page(rows[5000:], total=5002)]
    )
    result = cli("list", "--live", "--require-complete", code=1)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert browser.business_requests == [
        {"rowStart": 0, "pageSize": 5000},
        {"rowStart": 5000, "pageSize": 5000},
    ]
