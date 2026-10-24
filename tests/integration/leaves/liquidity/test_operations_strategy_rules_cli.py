"""Native strategy rule categories through independently installed packages."""

from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAF = "operations.strategy_rules"


@pytest.fixture(params=["directory", "zip"])
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
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    try:
        cli("domain", "enable", "liquidity")
        package = ROOT / "leaf_packages/liquidity" / LEAF
        if request.param == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        archive.write(path, path.relative_to(package))
            package = archive_path
        cli("plugins", "install", str(package))
        yield cli, browser
    finally:
        cdp.set_transport_factory(None)


def native(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "data": rows,
                "totalCount": len(rows) if total is None else total,
            },
        },
    }


def test_main_category_retains_distinct_versions_and_native_content(installed):
    cli, browser = installed
    rows = [
        {
            "id": "physical-1",
            "strategyRuleId": "rule-a",
            "version": "1",
            "strategyCategory": "MAIN_DECISION_STRATEGY",
            "strategyRuleContent": '{"subIds":["a","a"]}',
            "gmtCreate": 1780000000000,
            "gmtModified": 1780000000001,
            "unknown": [None, False, {"amount": "0.0000000000000000001"}],
        },
        {
            "id": "physical-2",
            "strategyRuleId": "rule-a",
            "version": "2",
            "strategyCategory": "MAIN_DECISION_STRATEGY",
            "strategyRuleContent": '{"subIds":[]}',
        },
    ]
    cli("liquidity", "list", LEAF, "--help")
    assert not browser.business_requests
    browser.business_script.append(native(rows))
    result = cli(
        "liquidity",
        "list",
        LEAF,
        "--category",
        "MAIN_DECISION_STRATEGY",
        "--live",
        "--limit",
        "0",
        "--require-complete",
    )
    assert result["data"] == rows
    assert browser.business_requests == [
        {"rowStart": 0, "pageSize": 50, "strategyCategory": "MAIN_DECISION_STRATEGY"}
    ]
    expressions = [
        x for t in browser.transports for x in t.expressions if "fetch(" in x
    ]
    assert any(
        "queryStrategyRulePage.json" in x and "application/json" in x
        for x in expressions
    )


@pytest.mark.parametrize(
    "types",
    [[], ["PRINCIPAL_PLANNING"], ["INVESTMENT_PORTFOLIO"], ["INVESTMENT_PREFERENCE"]],
)
def test_sub_type_scope_is_native_explicit_and_retained(installed, types):
    cli, browser = installed
    expected = types or [
        "PRINCIPAL_PLANNING",
        "INVESTMENT_PORTFOLIO",
        "INVESTMENT_PREFERENCE",
    ]
    rows = [
        {
            "id": "sub-1",
            "strategyCategory": "SUB_STRATEGY",
            "strategyType": expected[0],
            "strategyRuleContent": '{"weights":[1,1]}',
            "version": "3",
        }
    ]
    browser.business_script.append(native(rows))
    flags = ["--category", "SUB_STRATEGY"]
    for value in types:
        flags.extend(["--strategy-type", value])
    result = cli("liquidity", "refresh", LEAF, *flags, "--require-complete")
    assert result["meta"]["published"] is True
    assert browser.business_requests == [
        {
            "rowStart": 0,
            "pageSize": 50,
            "strategyCategory": "SUB_STRATEGY",
            "strategyTypes": expected,
        }
    ]
    assert cli("liquidity", "list", LEAF, "--limit", "0")["data"] == rows


def test_native_offset_fallback_collects_every_physical_record(installed):
    cli, browser = installed
    rows = [
        {
            "id": f"row-{i}",
            "strategyCategory": "MAIN_DECISION_STRATEGY",
            "strategyRuleId": "same-logical-rule",
            "version": str(i),
        }
        for i in range(11)
    ]
    browser.business_script.extend(
        [native(rows[:10], 11), native(rows[:10], 11), native(rows[10:], 11)]
    )
    result = cli(
        "liquidity",
        "list",
        LEAF,
        "--category",
        "MAIN_DECISION_STRATEGY",
        "--live",
        "--require-complete",
        "--limit",
        "0",
    )
    assert result["data"] == rows
    assert [(r["rowStart"], r["pageSize"]) for r in browser.business_requests] == [
        (0, 50),
        (0, 10),
        (10, 10),
    ]


@pytest.mark.parametrize(
    "flags",
    [
        [],
        ["--category", "OTHER"],
        [
            "--category",
            "MAIN_DECISION_STRATEGY",
            "--strategy-type",
            "PRINCIPAL_PLANNING",
        ],
        ["--category", "SUB_STRATEGY", "--strategy-type", "OTHER"],
        ["--category", "MAIN_DECISION_STRATEGY", "--execute"],
        ["--category", "MAIN_DECISION_STRATEGY", "--tnt-inst-id", "OTHER"],
    ],
)
def test_invalid_or_operating_arguments_do_not_query(installed, flags):
    cli, browser = installed
    result = cli("liquidity", "list", LEAF, *flags, "--live", code=2)
    assert result["data"] is None
    assert not browser.business_requests


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "business",
        "auth",
        "success",
        "rows",
        "total",
        "id",
        "category",
        "type",
        "duplicate",
        "conflict",
        "gap",
        "changing_total",
    ],
)
def test_unsuccessful_refresh_preserves_own_previous_capture(installed, failure):
    cli, browser = installed
    rows = [
        {
            "id": "sub-row",
            "strategyCategory": "SUB_STRATEGY",
            "strategyType": "PRINCIPAL_PLANNING",
            "strategyRuleContent": "{}",
        }
    ]
    flags = ["--category", "SUB_STRATEGY", "--strategy-type", "PRINCIPAL_PLANNING"]
    browser.business_script.append(native(rows))
    cli("liquidity", "refresh", LEAF, *flags, "--require-complete")
    before = cli("liquidity", "list", LEAF, "--limit", "0")
    bad = {**rows[0]}
    response = native([bad])
    if failure == "empty":
        response = native([])
    elif failure == "business":
        response["body"]["success"] = False
    elif failure == "auth":
        response["status"] = 401
    elif failure == "success":
        response["body"]["success"] = "true"
    elif failure == "rows":
        response["body"]["data"]["data"] = None
    elif failure == "total":
        response["body"]["data"]["totalCount"] = True
    elif failure == "id":
        bad["id"] = True
    elif failure == "category":
        bad["strategyCategory"] = "MAIN_DECISION_STRATEGY"
    elif failure == "type":
        bad["strategyType"] = "INVESTMENT_PREFERENCE"
    elif failure == "duplicate":
        response = native([bad, bad], 2)
    elif failure == "conflict":
        response = native([bad, {**bad, "strategyRuleContent": "changed"}], 2)
    elif failure == "gap":
        response = native([bad], 2)
    if failure == "changing_total":
        first = [{**bad, "id": f"first-{i}"} for i in range(50)]
        small = [{**bad, "id": f"small-{i}"} for i in range(10)]
        browser.business_script.extend(
            [native(first, 51), native([bad], 52), native(small, 11), native([bad], 12)]
        )
    else:
        browser.business_script.extend([response, response])
    result = cli(
        "liquidity",
        "refresh",
        LEAF,
        *flags,
        "--require-complete",
        code=0 if failure == "empty" else 1,
    )
    assert result["meta"]["published"] is False
    after = cli("liquidity", "list", LEAF, "--limit", "0")
    assert after["data"] == before["data"] == rows
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


def test_live_category_change_does_not_replace_saved_sub_scope(installed):
    cli, browser = installed
    sub = [
        {
            "id": "saved",
            "strategyCategory": "SUB_STRATEGY",
            "strategyType": "PRINCIPAL_PLANNING",
        }
    ]
    main = [{"id": "live", "strategyCategory": "MAIN_DECISION_STRATEGY"}]
    browser.business_script.append(native(sub))
    cli(
        "liquidity", "refresh", LEAF, "--category", "SUB_STRATEGY", "--require-complete"
    )
    before = cli("liquidity", "list", LEAF, "--limit", "0")
    browser.business_script.append(native(main))
    assert (
        cli(
            "liquidity",
            "list",
            LEAF,
            "--category",
            "MAIN_DECISION_STRATEGY",
            "--live",
            "--limit",
            "0",
        )["data"]
        == main
    )
    after = cli("liquidity", "list", LEAF, "--limit", "0")
    assert after["data"] == before["data"] == sub
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]
