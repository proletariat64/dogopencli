"""Installed cash balances preserve latest and daily native contract variants."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
LEAF = "cash.balances"
SOURCE = ROOT / "leaf_packages/liquidity" / LEAF
TENANT = "GUAPW3SG"


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


def snapshot(identity="B1", **values):
    return {
        "balId": identity,
        "entity": "ALIPAYGM",
        "aliasName": "ACCOUNT",
        "currency": "USD",
        "curBalance": Decimal("12.1234567890123456789"),
        "leastDayendBalVo": {"closeBalance": "12,345.67", "unknown": [None, False, 0]},
        "unknown": {"kept": True},
        "avlBalanceSwitch": True,
        **values,
    }


def response(data):
    return {"status": 200, "body": {"success": True, "data": data}}


def roster(alias="ACCOUNT", entity="ALIPAYGM", currency="USD"):
    return {
        "aliasName": alias,
        "instId": entity,
        "currency": currency,
        "bankId": "BANK",
    }


def daily(alias="ACCOUNT", day="2026-10-01", **values):
    return {
        "id": "chart-native-id",
        "data": alias,
        "statisticalDate": day,
        "balance": Decimal("123.4567890123456789"),
        "unknown": [None, False, "", 0],
        **values,
    }


def script(browser, accounts, make_daily=None, latest=None):
    def handler(body, _):
        if "bankAccountQueryVO" in body:
            vo = parse(body["bankAccountQueryVO"])
            rows = accounts[vo["rowStart"] : vo["rowStart"] + vo["pageSize"]]
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": 99999,
                    "result": {"success": True, "bankAccountPropertyVOList": rows},
                },
            }
        if "balanceType" in body:
            assert set(body) == {
                "tntInstId",
                "balanceType",
                "aliasNames",
                "queryStartDate",
                "queryDate",
            }
            assert body["balanceType"] == "day"
            assert 1 <= len(body["aliasNames"]) <= 30
            return response(
                make_daily(body)
                if make_daily
                else [daily(a) for a in body["aliasNames"]]
            )
        rows = latest if latest is not None else [snapshot()]
        return response(
            {
                "data": rows[body["rowStart"] : body["rowStart"] + body["pageSize"]],
                "totalCount": len(rows),
            }
        )

    browser.business_handler = handler


def frozen(envelope):
    return next(
        a
        for a in envelope["meta"]["acquisition"]["attempts"]
        if a.get("composition") == "cash-balance-selection-v1"
    )


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_latest_native_pages_refresh_offline_and_no_side_effect_help(installed):
    cli, browser, config = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.transports
    records = [snapshot(str(i)) for i in range(3)]
    script(browser, [], latest=records)
    live = cli(
        "list", "--live", "--page-size", "2", "--limit", "0", "--require-complete"
    )
    assert live["data"] == records
    assert live["meta"]["reported_total"] == 3
    assert not (config / "leaf-cache.sqlite3").exists()
    assert [b["rowStart"] for b in browser.business_requests] == [0, 2]
    saved = cli("refresh", "--page-size", "2", "--require-complete")
    n = len(browser.business_requests)
    offline = cli("list", "--limit", "0")
    assert offline["data"] == records
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == n
    assert frozen(offline)["entities"] == ["ALIPAYGM"]


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_daily_current_roster_labels_and_full_native_fields(installed):
    cli, browser, _ = installed
    script(browser, [roster(), roster("OTHER", "OTHER")])
    flags = [
        "--entity",
        "ALIPAYGM",
        "--account-alias",
        "ACCOUNT",
        "--from-date",
        "2026-10-01",
        "--to-date",
        "20261001",
    ]
    live = cli("list", "--live", *flags, "--require-complete")
    expected = {
        **daily(),
        "aliasName": "ACCOUNT",
        "entity": "ALIPAYGM",
        "currency": "USD",
    }
    assert live["data"] == [expected]
    assert live["meta"]["reported_total"] is None
    state = frozen(live)
    assert state["binding_semantics"] == "current-roster-not-historical-ownership"
    assert state["planned_chunks"] == state["succeeded_chunks"] == 1
    assert state["dependencies"][0]["acquisition"]["scope_complete"] is True
    cli("refresh", *flags, "--require-complete")
    n = len(browser.business_requests)
    assert cli("list", *flags)["data"] == [expected]
    assert len(browser.business_requests) == n


def test_daily_31_accounts_eight_days_are_four_disjoint_chunks(installed):
    cli, browser, _ = installed
    accounts = [roster(f"A{i:02}") for i in range(31)]

    def make(body):
        from datetime import datetime, timedelta

        first = datetime.strptime(body["queryStartDate"], "%Y%m%d")
        last = datetime.strptime(body["queryDate"], "%Y%m%d")
        return [
            daily(a, (first + timedelta(days=d)).strftime("%Y-%m-%d"))
            for a in body["aliasNames"]
            for d in range((last - first).days + 1)
        ]

    script(browser, accounts, make)
    result = cli(
        "list",
        "--live",
        "--from-date",
        "2026-10-01",
        "--to-date",
        "2026-10-08",
        "--limit",
        "0",
        "--require-complete",
    )
    assert len(result["data"]) == 31 * 8
    chunks = [b for b in browser.business_requests if "balanceType" in b]
    assert [
        (len(b["aliasNames"]), b["queryStartDate"], b["queryDate"]) for b in chunks
    ] == [
        (30, "20261001", "20261007"),
        (30, "20261008", "20261008"),
        (1, "20261001", "20261007"),
        (1, "20261008", "20261008"),
    ]
    assert frozen(result)["planned_chunks"] == 4


@pytest.mark.parametrize(
    "flags",
    [
        ["--from-date", "2026-10-01"],
        ["--to-date", "2026-10-01"],
        ["--from-date", "2026-10-03", "--to-date", "2026-10-01"],
        [
            "--from-date",
            "2026-10-01",
            "--to-date",
            "2026-10-02",
            "--timezone",
            "GMT+08",
        ],
        ["--from-date", "2026-10-01", "--to-date", "2026-10-02", "--page-size", "10"],
        ["--entity", " "],
        ["--account-alias", "ANY"],
        ["--page-size", "101"],
        ["--entity", "ANY", "--entity", "OTHER"],
    ],
)
def test_invalid_scope_rejected_before_browser(installed, flags):
    cli, browser, _ = installed
    assert cli("list", "--live", *flags, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize(
    "failure",
    [
        "unknown_alias",
        "ambiguous_binding",
        "returned_alias",
        "returned_date",
        "amount",
        "missing_balance",
        "native_label_conflict",
    ],
)
def test_daily_binding_or_chunk_failure_preserves_prior_capture(installed, failure):
    cli, browser, _ = installed
    flags = ["--from-date", "2026-10-01", "--to-date", "2026-10-01"]
    script(browser, [roster()])
    saved = cli("refresh", *flags, "--require-complete")
    accounts = [roster()]

    def make(body):
        return [daily()]

    if failure == "unknown_alias":
        flags += ["--account-alias", "MISSING"]
    elif failure == "ambiguous_binding":
        accounts += [roster(entity="OTHER", currency="CNY")]
    elif failure == "returned_alias":

        def make(body):
            return [daily("OTHER")]
    elif failure == "returned_date":

        def make(body):
            return [daily(day="2026-10-02")]
    elif failure == "amount":

        def make(body):
            return [daily(balance=True)]
    elif failure == "missing_balance":

        def make(body):
            r = daily()
            r.pop("balance")
            return [r]
    else:

        def make(body):
            return [daily(entity="OTHER")]

    script(browser, accounts, make)
    assert (
        cli("refresh", *flags, "--require-complete", code=1)["error"]["code"]
        == "INVALID_RESPONSE"
    )
    offline = cli("list", "--from-date", "2026-10-01", "--to-date", "2026-10-01")
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_required_chunk_business_failure_is_fatal(installed):
    cli, browser, _ = installed
    script(browser, [roster()])
    original = browser.business_handler

    def handler(body, ctx):
        if "balanceType" in body:
            return {"status": 200, "body": {"success": False, "data": None}}
        return original(body, ctx)

    browser.business_handler = handler
    result = cli(
        "refresh",
        "--from-date",
        "2026-10-01",
        "--to-date",
        "2026-10-01",
        "--require-complete",
        code=1,
    )
    assert result["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert result["meta"]["published"] is False


def test_any_freezes_local_selector_in_scope_and_never_sends_any(
    installed, monkeypatch
):
    from dogopencli import duckdog

    cli, browser, _ = installed
    current = ["ALIPAYGM"]
    calls = []

    def selector(path, field, *, config_file):
        calls.append((path, field))
        return list(current)

    monkeypatch.setattr(duckdog, "resolve_selector", selector)
    script(browser, [], latest=[snapshot()])
    result = cli("refresh", "--entity", "ANY", "--require-complete")
    assert frozen(result)["mode"] == "ANY"
    assert frozen(result)["entities"] == ["ALIPAYGM"]
    assert all(
        "ANY" not in body.get("entitys", []) for body in browser.business_requests
    )
    n = len(browser.business_requests)
    assert cli("list", "--entity", "ANY")["data"] == [snapshot()]
    assert len(browser.business_requests) == n
    assert calls
    current[:] = ["OTHER"]
    assert cli("list", "--entity", "ANY", code=1)["error"]["code"] in (
        "CACHE_MISS",
        "INVALID_ARGUMENT",
    )


def test_empty_any_selector_never_submits_unscoped_balance_query(
    installed, monkeypatch
):
    from dogopencli import duckdog

    cli, browser, _ = installed
    monkeypatch.setattr(duckdog, "resolve_selector", lambda *args, **kwargs: [])
    result = cli("list", "--live", "--entity", "ANY", "--require-complete")
    assert result["data"] == []
    assert not browser.business_requests


@pytest.mark.parametrize(
    "failure", ["changed_total", "duplicate", "conflict", "scope", "amount", "auth"]
)
def test_latest_page_failures_preserve_saved_capture(installed, failure):
    cli, browser, _ = installed
    script(browser, [], latest=[snapshot()])
    saved = cli("refresh", "--require-complete")
    browser.business_handler = None
    first = response({"data": [snapshot("A")], "totalCount": 2})
    second = response({"data": [snapshot("B")], "totalCount": 2})
    expected = "INVALID_RESPONSE"
    if failure == "changed_total":
        second["body"]["data"]["totalCount"] = 3
    elif failure == "duplicate":
        second["body"]["data"]["data"] = [snapshot("A")]
        expected = "INCOMPLETE_RESULT"
    elif failure == "conflict":
        second["body"]["data"]["data"] = [snapshot("A", curBalance=1)]
    elif failure == "scope":
        second["body"]["data"]["data"] = [snapshot("B", entity="OTHER")]
    elif failure == "amount":
        second["body"]["data"]["data"] = [snapshot("B", curBalance=True)]
    else:
        second = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    browser.business_script.extend([first, second])
    failed = cli("refresh", "--page-size", "1", "--require-complete", code=1)
    assert failed["error"]["code"] == expected
    assert failed["meta"]["published"] is False
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_daily_disallows_more_than_1000_chunks_before_balance_requests(installed):
    cli, browser, _ = installed
    script(browser, [roster()])
    result = cli(
        "list", "--live", "--from-date", "2000-01-01", "--to-date", "2026-10-01", code=2
    )
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not [body for body in browser.business_requests if "balanceType" in body]


@pytest.mark.parametrize("daily_mode", [False, True])
def test_boolean_zero_unknown_field_conflict_fails_in_both_modes(installed, daily_mode):
    cli, browser, _ = installed
    if daily_mode:
        script(
            browser,
            [roster()],
            lambda body: [daily(unknown={"flag": False}), daily(unknown={"flag": 0})],
        )
        flags = ["--from-date", "2026-10-01", "--to-date", "2026-10-01"]
    else:
        script(
            browser,
            [],
            latest=[snapshot(unknown={"flag": False}), snapshot(unknown={"flag": 0})],
        )
        flags = []
    failed = cli("refresh", *flags, "--require-complete", code=1)
    assert failed["error"]["code"] == "INVALID_RESPONSE"
    assert failed["meta"]["published"] is False
