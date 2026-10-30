"""Native task variants through independently installed directory and ZIP leaves."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAF = "investment.strategy_results"
TYPES = ("FUND_DECISION_TASK", "PRODUCT_DECISION_TASK")
STAMP = int(
    datetime(2026, 10, 19, 12, tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000
)


@pytest.fixture(
    params=[(kind, source) for kind in TYPES for source in ("directory", "zip")]
)
def installed(request, run_cli, tmp_path, monkeypatch):
    kind, source = request.param
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
        if source == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        archive.write(path, path.relative_to(package))
            package = archive_path
        cli("plugins", "install", str(package))
        yield kind, cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def flags(kind):
    return ("--task-type", kind, "--from-date", "2026-10-19", "--to-date", "20261019")


def records(kind, count=3):
    return [
        {
            "id": str(index),
            "taskType": kind,
            "triggerDate": STAMP,
            "amount": Decimal("0.12345678901234567890123456789"),
            "unknown": {"children": [None, False, 0, "", {"native": "1.0000"}]},
        }
        for index in range(count)
    ]


def native_detail(kind, identity="1"):
    return {
        "taskId": identity,
        "taskType": kind,
        "success": "native",
        "investableFundResultVo": None
        if kind == TYPES[1]
        else {"USD": [Decimal("1.0000000000000000001")]},
        "operationLogVOList": [{"nested": [0, None, False, ""]}],
        "unknown": {"preserved": True},
    }


def reply(data, status=200):
    return {"status": status, "body": {"success": True, "data": data}}


def list_reply(rows, total=None):
    return reply(
        {
            "data": rows,
            "totalCount": len(rows) if total is None else total,
            "pageSize": 0,
            "rowStart": 0,
        }
    )


def test_native_list_refresh_offline_and_windowed_binding(installed):
    kind, cli, browser, _ = installed
    rows = records(kind)
    cli("liquidity", "list", LEAF, "--help")
    assert not browser.business_requests
    browser.business_script.append(list_reply(rows))
    assert (
        cli(
            "liquidity",
            "list",
            LEAF,
            *flags(kind),
            "--live",
            "--require-complete",
            "--limit",
            "0",
        )["data"]
        == rows
    )
    assert browser.business_requests == [
        {
            "tntInstId": "GUAPW3SG",
            "taskType": kind,
            "triggerStartDate": "2026-10-19 00:00:00",
            "triggerEndDate": "2026-10-19 23:59:59",
            "rowStart": 0,
            "pageSize": 5000,
        }
    ]
    browser.business_script.append(list_reply(rows))
    cli("liquidity", "refresh", LEAF, *flags(kind), "--require-complete")
    before = cli("liquidity", "list", LEAF, "--limit", "0")
    detail = native_detail(kind)
    browser.business_script.extend([list_reply(rows), reply(detail)])
    combined = cli(
        "liquidity",
        "list",
        LEAF,
        *flags(kind),
        "--live",
        "--with-detail",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        "id",
    )
    assert combined["data"] == [{"record": {"id": "1"}, "detail": detail}]
    assert browser.business_requests[-1] == {"taskId": "1"}
    after = cli("liquidity", "list", LEAF, "--limit", "0")
    assert before["data"] == after["data"] == rows
    assert before["meta"]["fetched_at"] == after["meta"]["fetched_at"]
    browser.business_script.append(list_reply(rows))
    count = len(browser.business_requests)
    assert (
        cli(
            "liquidity",
            "list",
            LEAF,
            *flags(kind),
            "--live",
            "--with-detail",
            "--offset",
            "3",
        )["data"]
        == []
    )
    assert len(browser.business_requests) == count + 1


def test_independent_native_get_preserves_root_and_publishes_nothing(installed):
    kind, cli, browser, config = installed
    before = sorted(
        str(p.relative_to(config)) for p in config.rglob("*") if p.is_file()
    )
    detail = native_detail(kind)
    browser.business_script.append(reply(detail))
    result = cli("liquidity", "get", LEAF, "1", "--task-type", kind)
    assert result["data"] == detail
    assert result["meta"]["detail_scope"] == "native_root"
    assert browser.business_requests == [{"taskId": "1"}]
    expressions = [
        x
        for transport in browser.transports
        for x in transport.expressions
        if "fetch(" in x
    ]
    assert any(
        "task/taskDetail.json" in x and "application/x-www-form-urlencoded" in x
        for x in expressions
    )
    assert before == sorted(
        str(p.relative_to(config)) for p in config.rglob("*") if p.is_file()
    )


@pytest.mark.parametrize(
    "args",
    [
        (
            "list",
            "--task-type",
            TYPES[0],
            "--from-date",
            "2026-02-30",
            "--to-date",
            "20261019",
            "--live",
        ),
        (
            "list",
            "--task-type",
            TYPES[0],
            "--from-date",
            "20261020",
            "--to-date",
            "20261019",
            "--live",
        ),
        (
            "list",
            "--task-type",
            "AMOUNT",
            "--from-date",
            "20261019",
            "--to-date",
            "20261019",
            "--live",
        ),
        ("get", "1"),
        ("get", " ", "--task-type", TYPES[0]),
    ],
)
def test_invalid_context_rejected_before_business_queries(installed, args):
    _, cli, browser, _ = installed
    operation, *rest = args
    result = cli("liquidity", operation, LEAF, *rest, code=2)
    assert result["data"] is None
    assert not browser.business_requests


@pytest.mark.parametrize(
    "failure",
    [
        "type",
        "identity",
        "tenant",
        "timestamp",
        "bounds",
        "rows",
        "total",
        "business",
        "auth",
    ],
)
def test_list_failures_preserve_saved_capture(installed, failure):
    kind, cli, browser, _ = installed
    rows = records(kind)
    browser.business_script.append(list_reply(rows))
    cli("liquidity", "refresh", LEAF, *flags(kind), "--require-complete")
    saved = cli("liquidity", "list", LEAF, "--limit", "0")
    bad = deepcopy(rows)
    if failure == "type":
        bad[0]["taskType"] = TYPES[1] if kind == TYPES[0] else TYPES[0]
    if failure == "identity":
        bad[0]["id"] = True
    if failure == "tenant":
        bad[0]["tntInstId"] = "OTHER"
    if failure == "timestamp":
        bad[0]["triggerDate"] = True
    if failure == "bounds":
        bad[0]["triggerDate"] = 0
    response = list_reply(bad)
    if failure == "rows":
        response["body"]["data"]["data"] = None
    if failure == "total":
        response["body"]["data"]["totalCount"] = True
    if failure == "business":
        response["body"]["success"] = False
    if failure == "auth":
        response["status"] = 401
    browser.business_script.append(response)
    result = cli(
        "liquidity", "refresh", LEAF, *flags(kind), "--require-complete", code=1
    )
    assert result["data"] is None
    after = cli("liquidity", "list", LEAF, "--limit", "0")
    assert after["data"] == saved["data"] == rows
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("taskId", "wrong"),
        ("taskId", None),
        ("taskType", "wrong"),
        ("tntInstId", "OTHER"),
    ],
)
def test_get_identity_scope_failure_and_atomic_composition(installed, field, value):
    kind, cli, browser, _ = installed
    bad = native_detail(kind)
    bad[field] = value
    browser.business_script.append(reply(bad))
    assert (
        cli("liquidity", "get", LEAF, "1", "--task-type", kind, code=1)["data"] is None
    )
    browser.business_script.extend(
        [list_reply(records(kind)), reply(native_detail(kind, "0")), reply(bad)]
    )
    assert (
        cli(
            "liquidity",
            "list",
            LEAF,
            *flags(kind),
            "--live",
            "--with-detail",
            "--limit",
            "2",
            code=1,
        )["data"]
        is None
    )


@pytest.mark.parametrize("failure", ["empty", "duplicate", "gap"])
def test_empty_or_incomplete_refresh_retains_saved_data(installed, failure):
    kind, cli, browser, _ = installed
    rows = records(kind)
    browser.business_script.append(list_reply(rows))
    cli("liquidity", "refresh", LEAF, *flags(kind), "--require-complete")
    if failure == "empty":
        responses = [list_reply([])]
    elif failure == "duplicate":
        responses = [list_reply([rows[0], rows[0]], 2)] * 2
    else:
        responses = [list_reply(rows, 4)] * 2
    browser.business_script.extend(responses)
    cli(
        "liquidity",
        "refresh",
        LEAF,
        *flags(kind),
        "--require-complete",
        code=0 if failure == "empty" else 1,
    )
    assert cli("liquidity", "list", LEAF, "--limit", "0")["data"] == rows


def test_qualified_smaller_width_restarts_and_paginates(installed):
    kind, cli, browser, _ = installed
    rows = records(kind, 11)
    browser.business_script.extend(
        [
            list_reply(rows[:10], 11),
            list_reply(rows[:10], 11),
            list_reply(rows[10:], 11),
        ]
    )
    result = cli(
        "liquidity",
        "list",
        LEAF,
        *flags(kind),
        "--live",
        "--require-complete",
        "--limit",
        "0",
    )
    assert result["data"] == rows
    assert [(r["rowStart"], r["pageSize"]) for r in browser.business_requests] == [
        (0, 5000),
        (0, 10),
        (10, 10),
    ]


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {},
        {"success": "true", "data": {}},
        {"success": False},
        {"success": True, "data": []},
    ],
)
def test_get_business_and_schema_errors(installed, bad):
    kind, cli, browser, _ = installed
    browser.business_script.append({"status": 200, "body": bad})
    result = cli("liquidity", "get", LEAF, "1", "--task-type", kind, code=1)
    assert result["data"] is None
    assert result["error"]["code"] in {"INVALID_RESPONSE", "BUSINESS_QUERY_FAILED"}


def test_get_auth_failure_is_not_an_empty_success(installed):
    kind, cli, browser, _ = installed
    browser.business_script.append(reply({}, status=401))
    result = cli("liquidity", "get", LEAF, "1", "--task-type", kind, code=1)
    assert result["data"] is None
    assert result["error"]["code"] == "AUTH_REQUIRED"


def test_request_allowlist_rejects_unregistered_fields_width_and_context(monkeypatch):
    import importlib.util
    import sys

    from dogopencli.errors import CliError
    from dogopencli.jsonutil import canonical
    from dogopencli.transport import QueryRequest, validate_request

    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    spec = importlib.util.spec_from_file_location(
        "b12_results_contract", ROOT / "leaf_packages/liquidity" / LEAF / "adapter.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    params = {"task_type": TYPES[0], "from_date": "20261019", "to_date": "20261019"}
    inquiry = module.adapter.capability(params)
    scope = module.adapter.scope(params)
    valid = inquiry.page_body(scope, 0, 5000)
    for body in [
        {**valid, "execute": True},
        {**valid, "pageSize": 100},
        {**valid, "taskType": TYPES[1]},
    ]:
        with pytest.raises(CliError) as error:
            validate_request(
                QueryRequest(
                    inquiry.name,
                    "POST",
                    "iliquidity.alipay.com",
                    inquiry.contract.path,
                    body,
                ),
                inquiry.contract,
            )
        assert error.value.code == "REQUEST_NOT_ALLOWED"
    for changed_scope, offset, width in [
        (canonical({}), 0, 5000),
        (scope, 1, 5000),
        (scope, 0, 0),
        (scope, 0, True),
    ]:
        with pytest.raises(CliError):
            inquiry.page_body(changed_scope, offset, width)


def test_workflow_detail_plan_freezes_sources_without_row_bound_values(installed):
    from dogopencli.jsonutil import canonical

    kind, cli, browser, _ = installed
    plan = cli(
        "workflow",
        "plan",
        "create",
        "--leaf",
        "liquidity." + LEAF,
        "--with-detail",
        "--parameters",
        canonical(
            {
                "task-type": kind,
                "from-date": "20261019",
                "to-date": "20261019",
            }
        ),
    )["data"]
    assert not browser.business_requests
    assert plan["detail_contract"]["declaration"]["list_binding"] == {
        "identity_field": "id",
        "parameters": {"task-type": "taskType"},
    }
    rows = records(kind, count=1)
    detail = native_detail(kind, identity="0")
    browser.business_script.extend([list_reply(rows), reply(detail)])
    run = cli("workflow", "export", "create", "--plan", plan["id"])["data"]
    exported = cli("workflow", "export", "run", "--run", run["id"])["data"]
    assert exported["state"] == "complete_nonempty"
    assert exported["records"] == [{"record": rows[0], "detail": detail}]
    assert browser.business_requests[-1] == {"taskId": "0"}
    browser.business_script.append(list_reply([]))
    fresh_run = cli("workflow", "export", "create", "--plan", plan["id"])["data"]
    empty = cli("workflow", "export", "run", "--run", fresh_run["id"])["data"]
    assert empty["state"] == "complete_empty"
    assert empty["records"] == []
