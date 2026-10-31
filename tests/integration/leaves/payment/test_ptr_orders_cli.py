"""Installed PTR order stability and half-open windows with synthetic CDP data."""

import json
import shutil
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "leaf_packages/payment/ptr.orders"
BASELINE = "productionTrialRunFundOutAbilityVO"
START = "2026-10-01T00:00:00+08:00"
END = "2026-10-02T00:00:00+08:00"
START_MS = int(datetime.fromisoformat(START).timestamp()) * 1000
END_MS = int(datetime.fromisoformat(END).timestamp()) * 1000
BOUNDS = ("--from-time", START, "--to-time", END)


def row(identity="ORDER", modified=START_MS, **values):
    return {
        "ptrOrderId": identity,
        "gmtModified": modified,
        "caseId": "CASE",
        "orderStatus": "FUND_OUT_SUC",
        "verifyStatus": "INIT",
        "ptrFinalResult": None,
        "transactionRate": Decimal("0.123456789012345678901"),
        "debtorAmount": {
            "amount": Decimal("1.000000000000000000001"),
            "cent": 100000000000000000001,
            "centFactor": 100,
            "currency": "USD",
            "currencyCode": "USD",
            "currencyValue": "1.00",
        },
        "returnAmount": None,
        BASELINE: {
            "financialInstCode": "BANK",
            "debtorAccountAliasName": "ACCOUNT",
            "clearingSystemName": "NETWORK",
            "supportObo": "N",
            "supportFvt": None,
        },
        **values,
    }


def page(rows, total=None, **extra):
    return {
        "status": 200,
        "body": {
            "success": True,
            "resultDataList": rows,
            "pageNo": 0,
            "pageSize": 500,
            "totalCount": len(rows) if total is None else total,
            **extra,
        },
    }


def stable(browser, rows):
    browser.business_script.extend([page(rows), page(deepcopy(rows))])


@pytest.fixture(params=["directory", "zip"])
def installed(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for name in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(name, raising=False)
    browser = FakeBrowser(
        href="https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
        "productPTRManagement/orderInquiry"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        status, output, error = run_cli(["payment", action, "ptr.orders", *args])
        assert status == code, output + error
        return parse(output)

    try:
        source = tmp_path / "source"
        shutil.copytree(SOURCE, source)
        if request.param == "zip":
            archive = tmp_path / "orders.zip"
            with ZipFile(archive, "w") as output:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        output.write(path, path.relative_to(source))
            source = archive
        status, output, error = run_cli(["plugins", "install", str(source)])
        assert status == 0, output + error
        if request.param == "directory":
            shutil.rmtree(source)
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def test_two_padded_reads_before_trim_keep_native_totals_separate(installed):
    cli, browser, _ = installed
    rows = [
        row("PAD-BEFORE", START_MS - 1000),
        row("Z", END_MS - 1),
        row("PAD-END", END_MS),
        row("A", START_MS),
        row("PAD-AFTER", END_MS + 1000),
    ]
    browser.business_script.extend([page(rows), page(list(reversed(rows)))])
    result = cli("list", "--live", *BOUNDS, "--limit", "0", "--require-complete")
    assert result["data"] == [rows[3], rows[1]]
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    evidence = result["meta"]["acquisition"]
    assert evidence["reported_total"] is None
    assert evidence["collected_total"] == 2
    assert evidence["coverage_basis"] == "validated_sources"
    assert set(evidence["sources"]) == {"first", "second"}
    for source in evidence["sources"].values():
        assert source["acquisition"]["reported_total"] == 5
        assert source["acquisition"]["collected_total"] == 5
        assert source["acquisition"]["scope_complete"] is True
    assert (
        browser.business_requests
        == [
            {
                "pageNo": 0,
                "pageSize": 500,
                "modifiedTimeBegin": "2026-09-30 23:59:59",
                "modifiedTimeEnd": "2026-10-02 00:00:01",
            }
        ]
        * 2
    )
    expressions = [
        expression
        for transport in browser.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert all(
        "/api/ptr/manage/query.json" in expression and 'method: "GET"' in expression
        for expression in expressions
    )


def test_projection_preserves_retained_money_and_ignores_unknown_changes(installed):
    cli, browser, _ = installed
    original = row("000000000000000000000001")
    native = deepcopy(original)
    native["unknown"] = {"sensitive": "not-in-output"}
    native[BASELINE]["unapproved"] = ["not-in-output"]
    native["debtorAmount"]["unapproved"] = False
    changed_unknown = deepcopy(native)
    changed_unknown["unknown"] = 99
    changed_unknown[BASELINE]["unapproved"] = "different"
    browser.business_script.extend([page([native]), page([changed_unknown])])
    output = cli("list", "--live", *BOUNDS, "--limit", "0")
    assert output["data"] == [original]
    assert type(output["data"][0]["debtorAmount"]["cent"]) is int
    assert type(output["data"][0]["transactionRate"]) is Decimal


@pytest.mark.parametrize(
    "changed",
    ["padding_content", "padding_identity", "padding_count", "inside_content"],
)
def test_changed_padded_scope_fails_even_when_public_rows_match(installed, changed):
    cli, browser, _ = installed
    first = [row(), row("PAD", END_MS)]
    second = deepcopy(first)
    if changed == "padding_content":
        second[1]["orderStatus"] = "CHANGED"
    elif changed == "padding_identity":
        second[1]["ptrOrderId"] = "OTHER-PAD"
    elif changed == "padding_count":
        second.pop()
    else:
        second[0]["verifyStatus"] = "VERIFIED"
    browser.business_script.extend([page(first), page(second)])
    result = cli("refresh", *BOUNDS, code=1)
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["data"] is None
    assert result["meta"]["published"] is False
    assert len(browser.business_requests) == 2


def test_refresh_offline_and_failed_empty_refresh_preserve_capture(installed):
    cli, browser, config = installed
    stable(browser, [row(), row("PAD", END_MS)])
    saved = cli("refresh", *BOUNDS, "--require-complete")
    assert saved["data"]["row_count"] == 1
    before = cli("list", "--limit", "0")
    assert before["data"] == [row()]
    assert len(browser.business_requests) == 2
    database = config / "leaf-cache.sqlite3"
    assert database.exists()
    stable(browser, [])
    empty = cli("refresh", *BOUNDS)
    assert empty["meta"]["published"] is False
    after = cli("list", "--limit", "0")
    assert after["data"] == before["data"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]
    assert after["meta"]["acquisition"] == before["meta"]["acquisition"]
    browser.business_script.extend([page([row("OTHER")]), page([row("CHANGED")])])
    assert cli("refresh", *BOUNDS, code=1)["error"]["code"] == "INCOMPLETE_RESULT"
    assert cli("list")["data"] == before["data"]
    assert database.exists()


def test_second_read_failure_cannot_publish_first_success(installed):
    cli, browser, _ = installed
    stable(browser, [row()])
    cli("refresh", *BOUNDS)
    saved = cli("list")
    browser.business_script.extend(
        [page([row("CANDIDATE")]), {"status": 401, "body": {}}]
    )
    failed = cli("refresh", *BOUNDS, code=1)
    assert failed["error"]["code"] == "AUTH_REQUIRED"
    assert failed["data"] is None
    assert failed["meta"]["published"] is False
    assert len(browser.business_requests) == 4
    cached = cli("list")
    assert cached["data"] == saved["data"]
    assert cached["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_offline_cannot_replace_saved_acquisition_window(installed):
    cli, browser, _ = installed
    stable(browser, [row()])
    cli("refresh", *BOUNDS)
    assert cli("list", *BOUNDS, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert len(browser.business_requests) == 2


def test_blank_local_filter_rejects_before_auth(installed):
    cli, browser, _ = installed
    failed = cli("list", "--live", *BOUNDS, "--channel", " ", code=2)
    assert failed["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize(
    ("arguments", "identities"),
    [
        (("--id", "B", "--id", "A"), ["A", "B"]),
        (("--channel", "BANK", "--verify-status", "VERIFIED"), ["B"]),
        (("--channel", "BANK,OTHER"), []),
        (("--channel", "*"), ["C"]),
        (("--debtor-currency", "USD"), ["A", "B", "C"]),
        (("--case-id", "case"), []),
    ],
)
def test_local_nested_exact_filters_apply_after_full_scope(
    installed, arguments, identities
):
    cli, browser, _ = installed
    records = [
        row("B", verifyStatus="VERIFIED"),
        row("C", **{BASELINE: {"financialInstCode": "*"}}),
        row("A"),
    ]
    stable(browser, records)
    cli("refresh", *BOUNDS)
    result = cli("list", *arguments, "--fields", "ptrOrderId", "--limit", "0")
    assert result["data"] == [{"ptrOrderId": value} for value in identities]
    assert len(browser.business_requests) == 2


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-10-01", END),
        ("2026-10-01T00:00:00", END),
        ("2026-09-30T16:00:00Z", END),
        ("2026-10-01T00:00:00-00:00", END),
        ("2026-10-01T00:00:00.001+08:00", END),
        ("2026-09-31T00:00:00+08:00", END),
        (START, START),
        (END, START),
        ("2026-08-01T00:00:00+08:00", END),
        (START, "9999-01-01T00:00:00+08:00"),
    ],
)
def test_invalid_or_future_windows_fail_before_auth(installed, start, end):
    cli, browser, _ = installed
    failure = cli("list", "--live", "--from-time", start, "--to-time", end, code=2)
    assert failure["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests
    assert not browser.transports


def test_equivalent_offset_bounds_normalize_to_shanghai_scope(installed):
    cli, browser, _ = installed
    stable(browser, [row()])
    result = cli(
        "list",
        "--live",
        "--from-time",
        "2026-09-30T16:00:00+00:00",
        "--to-time",
        "2026-10-01T16:00:00+00:00",
    )
    assert result["data"] == [row()]
    assert browser.business_requests[0]["modifiedTimeBegin"] == "2026-09-30 23:59:59"
    assert result["meta"]["scope"]["from_time"] == START


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "invalid_json",
        "page",
        "width",
        "total_type",
        "rows",
        "id",
        "timestamp",
        "baseline",
        "money",
        "outside",
    ],
)
def test_native_failures_preserve_saved_capture(installed, failure):
    cli, browser, _ = installed
    stable(browser, [row()])
    cli("refresh", *BOUNDS)
    saved = cli("list")
    candidate = page([row("OTHER")])
    body = candidate["body"]
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        body["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "invalid_json":
        candidate["body"] = "{"
    elif failure == "page":
        body["pageNo"] = 1
    elif failure == "width":
        body["pageSize"] = 1000
    elif failure == "total_type":
        body["totalCount"] = True
    elif failure == "rows":
        body["resultDataList"] = None
    elif failure == "id":
        body["resultDataList"][0]["ptrOrderId"] = 7
    elif failure == "timestamp":
        body["resultDataList"][0]["gmtModified"] = True
    elif failure == "baseline":
        body["resultDataList"][0][BASELINE] = None
    elif failure == "money":
        body["resultDataList"][0]["debtorAmount"]["amount"] = True
    else:
        body["resultDataList"][0]["gmtModified"] = END_MS + 1001
    browser.business_script.append(candidate)
    result = cli("refresh", *BOUNDS, code=1)
    assert result["error"]["code"] == expected
    cached = cli("list")
    assert cached["data"] == saved["data"]
    assert cached["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "kind", ["same_duplicate", "conflicting_duplicate", "shortfall", "capacity"]
)
def test_unproven_padded_coverage_cannot_be_trimmed_into_success(installed, kind):
    cli, browser, _ = installed
    rows = [row(), row()]
    total = 2
    if kind == "conflicting_duplicate":
        rows[1]["verifyStatus"] = "VERIFIED"
    elif kind == "shortfall":
        rows = [row()]
    elif kind == "capacity":
        total = 501
    browser.business_script.extend([page(rows, total), page(rows, total)])
    result = cli("list", "--live", *BOUNDS, code=1)
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["data"] is None


def test_static_help_and_rejected_scope_never_query(installed, run_cli):
    cli, browser, _ = installed
    described = cli("describe")
    assert set(described["data"]["operations"]) == {"list"}
    status, output, error = run_cli(["payment", "list", "ptr.orders", "--help"])
    assert status == 0, output + error
    assert "from-time" in output
    status, _, _ = run_cli(["payment", "get", "ptr.orders", "ORDER"])
    assert status != 0
    assert not browser.transports
    assert not browser.business_requests


def test_request_allowlist_rejects_extra_selector(installed, run_cli, tmp_path):
    cli, browser, _ = installed
    status, output, error = run_cli(["plugins", "uninstall", "payment.ptr.orders"])
    assert status == 0, output + error
    source = tmp_path / "badrequest"
    shutil.copytree(SOURCE, source)
    adapter = source / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            "return dict(self.contract.fixed_body_values)",
            'return {**dict(self.contract.fixed_body_values), "execute": True}',
        )
    )
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 0, output + error
    failure = cli("list", "--live", *BOUNDS, code=1)
    assert failure["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_history_plan_round_trips_half_open_second_and_preserves_sources(
    installed, run_cli
):
    _, browser, _ = installed

    def command(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    plan = command(
        "workflow",
        "plan",
        "create",
        "--leaf",
        "payment.ptr.orders",
        "--mode",
        "history",
        "--parameters",
        json.dumps(
            {
                "from-time": START,
                "to-time": "2026-10-01T00:00:01+08:00",
                "channel": ["BANK"],
            }
        ),
    )["data"]
    assert plan["desired_range"] == {
        "from": "2026-09-30T16:00:00.000Z",
        "to": "2026-09-30T16:00:00.999Z",
    }
    assert plan["packages"][0]["parameters"]["channel"] == ["BANK"]
    assert plan["packages"][0]["parameters"]["to_time"] == "2026-10-01T00:00:01+08:00"
    stable(browser, [row(), row("EXCLUDED", START_MS + 1000)])
    run = command("workflow", "export", "create", "--plan", plan["id"])["data"]
    command("workflow", "export", "run", "--run", run["id"])
    assert (
        browser.business_requests
        == [
            {
                "pageNo": 0,
                "pageSize": 500,
                "modifiedTimeBegin": "2026-09-30 23:59:59",
                "modifiedTimeEnd": "2026-10-01 00:00:02",
            }
        ]
        * 2
    )
    history = command("workflow", "history", "show", "--plan", plan["id"])["data"]
    artifact_id = history["packages"][0]["export_id"]
    exported = command("workflow", "export", "show", "--export", artifact_id)["data"]
    acquisition = exported["metadata"]["source_acquisition"]
    assert acquisition["collected_total"] == 1
    for source in acquisition["sources"].values():
        assert source["acquisition"]["reported_total"] == 2
        assert source["acquisition"]["scope_complete"] is True
    prepared = command(
        "workflow", "import", "plan", "--export", artifact_id, "--action", "preserve"
    )["data"]
    request_count = len(browser.business_requests)
    command("workflow", "import", "apply", "--plan", prepared["id"])
    observed = command("workflow", "observation", "show", "--export", artifact_id)[
        "data"
    ]
    assert observed["records"] == [row()]
    assert observed["scope"] == exported["metadata"]["scope"]
    assert len(browser.business_requests) == request_count


@pytest.mark.parametrize(
    "lower,upper",
    [
        ("2026-09-30T16:00:00.001Z", "2026-09-30T16:00:00.999Z"),
        ("2026-09-30T16:00:00.000Z", "2026-09-30T16:00:00.998Z"),
        ("2026-09-30T16:00:00Z", "2026-09-30T16:00:00.999Z"),
        ("2026-10-01T00:00:00.000+08:00", "2026-09-30T16:00:00.999Z"),
    ],
)
def test_history_windows_reject_lossy_or_noncanonical_endpoints(
    installed, run_cli, lower, upper
):
    _, browser, _ = installed
    status, output, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "payment.ptr.orders",
            "--mode",
            "history",
            "--parameters",
            json.dumps({"from-time": START, "to-time": END}),
            "--windows",
            json.dumps([{"from": lower, "to": upper}]),
        ]
    )
    assert status == 2, output + error
    assert parse(output)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


def test_history_explicit_window_keeps_fixed_filters_and_exact_padding(
    installed, run_cli
):
    _, browser, _ = installed
    status, output, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "payment.ptr.orders",
            "--mode",
            "history",
            "--parameters",
            json.dumps(
                {"from-time": START, "to-time": END, "order-status": ["FUND_OUT_SUC"]}
            ),
            "--windows",
            json.dumps(
                [
                    {
                        "from": "2026-09-30T16:00:01.000Z",
                        "to": "2026-09-30T16:00:01.999Z",
                    }
                ]
            ),
        ]
    )
    assert status == 0, output + error
    package = parse(output)["data"]["packages"][0]
    assert package["parameters"] == {
        "from_time": "2026-10-01T00:00:01+08:00",
        "to_time": "2026-10-01T00:00:02+08:00",
        "order_status": ["FUND_OUT_SUC"],
    }
    assert package["native_scope"] == {
        "from_time": "2026-10-01T00:00:01+08:00",
        "to_time": "2026-10-01T00:00:02+08:00",
    }
    assert not browser.transports


def test_two_sources_keep_six_physical_request_limit(installed, monkeypatch):
    from dogopencli import collect

    cli, browser, _ = installed
    monkeypatch.setattr(collect, "_sleep", lambda seconds: None)
    retry = {"status": 502, "body": {}}
    browser.business_script.extend(
        [retry, retry, page([row()]), retry, retry, page([row()])]
    )
    assert cli("list", "--live", *BOUNDS)["data"] == [row()]
    assert len(browser.business_requests) == 6


def test_replaced_updated_options_are_rejected(installed):
    cli, browser, _ = installed
    failure = cli(
        "list", "--live", "--updated-from", START, "--updated-to", END, code=2
    )
    assert failure["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("strict", [False, True])
def test_stable_versions_select_latest_with_source_proof(installed, reverse, strict):
    cli, browser, _ = installed
    older = row(modified=START_MS, verifyStatus="INIT")
    newer = row(modified=START_MS + 1000, verifyStatus="VERIFIED")
    rows = [newer, older] if reverse else [older, newer]
    browser.business_script.extend([page(rows, 1), page(deepcopy(rows), 1)])
    flags = ["--require-complete"] if strict else []
    result = cli("list", "--live", *BOUNDS, "--limit", "0", *flags)
    assert result["data"][0]["verifyStatus"] == "VERIFIED"
    assert result["error"] is None
    assert result["meta"]["complete"] is True
    assert any(w["code"] == "LATEST_BY_SELECTION" for w in result["meta"]["warnings"])
    for source in result["meta"]["acquisition"]["sources"].values():
        evidence = source["acquisition"]
        assert evidence["arrivals"] == 2
        assert evidence["reported_total"] == 1
        assert evidence["collected_total"] == 1
        assert evidence["selection"]["latest_by"] == "gmtModified"
        assert evidence["selection"]["resolved_version_count"] == 1


@pytest.mark.parametrize(
    "mutation", ["older_content", "missing_version", "padding", "version_order"]
)
def test_selected_winners_cannot_hide_unstable_full_sources(installed, mutation):
    cli, browser, _ = installed
    modified = START_MS - 500 if mutation == "padding" else START_MS
    first = [
        row(modified=modified),
        row(modified=START_MS + 1000, verifyStatus="VERIFIED"),
    ]
    second = deepcopy(first)
    if mutation in {"older_content", "padding"}:
        second[0]["verifyStatus"] = "CHANGED"
    elif mutation == "missing_version":
        second.pop(0)
    else:
        second.reverse()
    browser.business_script.extend([page(first, 1), page(second, 1)])
    result = cli("list", "--live", *BOUNDS, "--require-complete", code=1)
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert "padded scope changed" in result["error"]["message"]
    assert result["data"] is None
    assert len(browser.business_requests) == 2
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"


def test_stable_equal_order_ties_keep_last_complete_row(installed):
    cli, browser, _ = installed
    first = row(verifyStatus="INIT")
    last = row(verifyStatus="VERIFIED", unknownNested={"items": [None, False, "1.000"]})
    rows = [first, last]
    browser.business_script.extend([page(rows, 1), page(deepcopy(rows), 1)])
    result = cli("list", "--live", *BOUNDS, "--require-complete", "--limit", "0")
    assert result["data"][0]["verifyStatus"] == "VERIFIED"
    assert result["data"][0]["gmtModified"] == START_MS
    # PTR preserves its existing projection, not arbitrary unqualified fields.
    assert result["meta"]["complete"] is True
    for source in result["meta"]["acquisition"]["sources"].values():
        assert source["acquisition"]["selection"]["equal_order_count"] == 1


def test_selected_source_proof_survives_refresh_and_offline(installed):
    cli, browser, _ = installed
    rows = [row(), row(modified=START_MS + 1000, verifyStatus="VERIFIED")]
    browser.business_script.extend([page(rows, 1), page(deepcopy(rows), 1)])
    refreshed = cli("refresh", *BOUNDS, "--require-complete")
    assert refreshed["meta"]["published"] is True
    request_count = len(browser.business_requests)
    offline = cli("list", "--require-complete", "--limit", "0")
    assert len(offline["data"]) == 1
    assert offline["data"][0]["verifyStatus"] == "VERIFIED"
    assert offline["meta"]["acquisition"] == refreshed["meta"]["acquisition"]
    assert offline["meta"]["warnings"]
    assert len(browser.business_requests) == request_count
    assert set(offline["meta"]["acquisition"]["sources"]["first"]) == {
        "scope",
        "acquisition",
    }


def test_cached_source_selection_requires_its_witness(installed):
    import sqlite3

    from dogopencli.jsonutil import canonical

    cli, browser, config = installed
    rows = [row(), row(modified=START_MS + 1000, verifyStatus="VERIFIED")]
    browser.business_script.extend([page(rows, 1), page(deepcopy(rows), 1)])
    cli("refresh", *BOUNDS, "--require-complete")
    with sqlite3.connect(config / "leaf-cache.sqlite3") as database:
        saved = database.execute("SELECT acquisition FROM snapshots").fetchone()[0]
        evidence = parse(saved)
        evidence["sources"]["first"]["acquisition"].pop("selection")
        database.execute("UPDATE snapshots SET acquisition=?", [canonical(evidence)])
    result = cli("list", "--require-complete", code=1)
    assert result["data"] is None
    assert result["error"]["code"] == "INVALID_RESPONSE"


def test_selected_source_proof_survives_exact_workflow_import(installed, run_cli):
    _, browser, _ = installed

    def command(*args):
        status, output, error = run_cli(list(args))
        assert status == 0, output + error
        return parse(output)["data"]

    plan = command(
        "workflow",
        "plan",
        "create",
        "--leaf",
        "payment.ptr.orders",
        "--parameters",
        json.dumps({"from-time": START, "to-time": END}),
    )
    rows = [row(), row(modified=START_MS + 1000, verifyStatus="VERIFIED")]
    browser.business_script.extend([page(rows, 1), page(deepcopy(rows), 1)])
    run = command("workflow", "export", "create", "--plan", plan["id"])
    exported = command("workflow", "export", "run", "--run", run["id"], "--limit", "0")
    artifact = command("workflow", "export", "show", "--export", exported["id"])
    acquisition = artifact["metadata"]["acquisition"]
    assert (
        acquisition["sources"]["first"]["acquisition"]["selection"][
            "resolved_version_count"
        ]
        == 1
    )
    assert len(artifact["records"]) == 1
    assert artifact["records"][0]["verifyStatus"] == "VERIFIED"
    prepared = command(
        "workflow", "import", "plan", "--export", artifact["id"], "--action", "preserve"
    )
    request_count = len(browser.business_requests)
    command("workflow", "import", "apply", "--plan", prepared["id"])
    observed = command("workflow", "observation", "show", "--export", artifact["id"])
    assert observed["records"] == artifact["records"]
    assert observed["metadata"]["acquisition"] == acquisition
    assert len(browser.business_requests) == request_count


@pytest.mark.parametrize(
    "fault",
    ["aggregate_order", "blank_order", "paged_validation", "unnamed_validation"],
)
def test_source_selection_policy_rejects_invalid_declarations(run_cli, tmp_path, fault):
    source = tmp_path / "source"
    shutil.copytree(SOURCE, source)
    manifest_path = source / "leaf.json"
    manifest = parse(manifest_path.read_text())
    policy = manifest["collection"]
    if fault == "aggregate_order":
        policy["latest_by"] = "gmtModified"
    elif fault == "blank_order":
        policy["sources"]["first"]["latest_by"] = " "
    elif fault == "paged_validation":
        policy["sources"]["first"]["paging"]["mode"] = "offset"
    else:
        policy.pop("sources")
        policy["paging"] = {"mode": "single", "page_sizes": [500]}
    manifest_path.write_text(json.dumps(manifest))
    status, output, error = run_cli(["plugins", "install", str(source)])
    assert status == 1, output + error
    assert parse(output)["error"]["code"] == "INVALID_LEAF"


def test_winner_in_padding_does_not_fall_back_to_older_public_version(installed):
    cli, browser, _ = installed
    rows = [row(), row(modified=END_MS, verifyStatus="VERIFIED")]
    browser.business_script.extend([page(rows, 1), page(deepcopy(rows), 1)])
    result = cli("list", "--live", *BOUNDS, "--require-complete", "--limit", "0")
    assert result["data"] == []
    assert result["error"] is None
    assert result["meta"]["complete"] is True
    assert (
        result["meta"]["acquisition"]["sources"]["first"]["acquisition"][
            "collected_total"
        ]
        == 1
    )
