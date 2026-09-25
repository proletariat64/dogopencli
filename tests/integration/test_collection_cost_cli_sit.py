"""Issue #21 public CLI proof using synthetic responses and the real cache."""

from dataclasses import replace
from decimal import Decimal

import pytest
from jsonschema import Draft202012Validator
from test_cost_cli_sit import cost_page, cost_row, cost_setup, no_sleep  # noqa: F401

from dogopencli import cli
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.plugins.collection.cost import COLLECTION_COST_CAPABILITY, COST_TYPE
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport


@pytest.fixture
def setup(cost_setup):  # noqa: F811
    config = cost_setup.tmp_path / "config.toml"
    with config.open("a") as file:
        file.write('\n[sources.collection_cost]\nkind = "cdp"\n')
    return cost_setup


def row(identity="1", **kwargs):
    return cost_row(identity, itemType=COST_TYPE, **kwargs)


def page(rows=None, **kwargs):
    return cost_page([row()] if rows is None else rows, page_size=1000, **kwargs)


def listing(run_cli, *flags):
    return run_cli(["collection", "cost", "list", *flags])


def refresh(run_cli):
    return run_cli(["refresh", "collection", "cost"])


def seed(run_cli, setup):
    setup.state.business_script.append(page())
    assert refresh(run_cli)[0] == 0
    return listing(run_cli)[1]


def test_refresh_offline_isolation_precision_and_display(run_cli, envelope, setup):
    setup.state.business_script.append(cost_page([cost_row("900")]))
    assert run_cli(["refresh", "payment", "cost"])[0] == 0
    rows = [row("10"), row("2")]
    setup.state.business_script.append(page(rows))
    code, out, _ = refresh(run_cli)
    assert code == 0
    assert envelope(out)["data"]["namespace"].startswith("collection.cost.list")
    before = len(setup.state.transports)
    setup.state.running = False
    code, out, err = listing(run_cli, "--all", "--require-fresh", "--require-complete")
    assert (code, err) == (0, "")
    result = parse(out)
    assert result["data"] == [rows[1], rows[0]]
    amount = result["data"][0]["costRateConfigList"][0]["costRateVO"][
        "feeRateRatioValue"
    ]["amount"]
    assert amount == Decimal("0.1234567890123456789")
    assert result["meta"]["complete"] and not result["meta"]["stale"]
    assert len(setup.state.transports) == before
    assert (
        envelope(run_cli(["payment", "cost", "list"])[1])["data"][0]["itemId"] == "900"
    )
    projected = envelope(listing(run_cli, "--limit", "1", "--fields", "itemId")[1])
    assert projected["data"] == [{"itemId": "2"}]
    assert projected["meta"]["complete"] and projected["meta"]["has_more"]
    assert envelope(listing(run_cli, "--offset", "1")[1])["data"][0]["itemId"] == "10"
    assert "itemId" in listing(run_cli, "--format", "table")[1]
    assert setup.state.business_requests[-1] == {
        "costTypeCode": COST_TYPE,
        "pageNo": 0,
        "pageSize": 1000,
    }
    assert b"FAKE-CTOKEN-SECRET" not in setup.cache_path.read_bytes()


def test_cache_miss_live_no_write_and_no_fallback(run_cli, envelope, setup):
    code, out, _ = listing(run_cli)
    assert code == 1 and envelope(out)["error"]["code"] == "CACHE_MISS"
    assert "refresh collection cost" in envelope(out)["error"]["message"]
    assert setup.state.transports == []
    old = seed(run_cli, setup)
    setup.state.business_script.append(page([row("7")]))
    code, out, _ = listing(run_cli, "--live")
    assert code == 0
    assert envelope(out)["meta"]["source"] == "live"
    assert envelope(out)["data"][0]["itemId"] == "7"
    assert listing(run_cli)[1] == old
    setup.state.business_script.append(page([], success=False))
    code, out, _ = listing(run_cli, "--live")
    assert code == 1 and envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert listing(run_cli)[1] == old


@pytest.mark.parametrize(
    "patch, omitted, expected",
    [
        ({"totalCount": 0}, True, None),
        ({"totalCount": 1}, True, "INVALID_RESPONSE"),
        ({"totalCount": 0, "resultDataList": None}, False, "INVALID_RESPONSE"),
        ({"totalCount": -1}, False, "INVALID_RESPONSE"),
        ({"totalCount": True}, False, "INVALID_RESPONSE"),
        ({"pageNo": -1}, False, "INVALID_RESPONSE"),
        ({"pageNo": 1}, False, "INVALID_RESPONSE"),
        ({"pageSize": 10}, False, "INVALID_RESPONSE"),
        ({"totalCount": 1001}, False, "INCOMPLETE_RESULT"),
        ({"totalCount": 2}, False, "INCOMPLETE_RESULT"),
        ({"totalCount": 0}, False, "INVALID_RESPONSE"),
        (
            {"resultDataList": [row(), row()], "totalCount": 2},
            False,
            "INCOMPLETE_RESULT",
        ),
        (
            {"resultDataList": [row(), row(status="OTHER")], "totalCount": 2},
            False,
            "INCOMPLETE_RESULT",
        ),
        ({"resultDataList": [cost_row("1")]}, False, "INVALID_RESPONSE"),
        (
            {"resultDataList": [{"itemId": "", "itemType": COST_TYPE}]},
            False,
            "INVALID_RESPONSE",
        ),
        ({"resultDataList": ["bad"]}, False, "INVALID_RESPONSE"),
    ],
)
@pytest.mark.parametrize("live", [False, True])
def test_invalid_or_empty_response(
    run_cli, envelope, setup, patch, omitted, expected, live
):
    old = seed(run_cli, setup)
    response = page()
    response["body"].update(patch)
    if omitted:
        response["body"].pop("resultDataList")
    setup.state.business_script.append(response)
    before = len(setup.state.business_requests)
    code, out, _ = listing(run_cli, "--live") if live else refresh(run_cli)
    assert len(setup.state.business_requests) == before + 1
    assert code == (1 if expected else 0)
    if expected:
        assert envelope(out)["error"]["code"] == expected
    if live or expected:
        assert listing(run_cli)[1] == old
    else:
        assert envelope(listing(run_cli)[1])["data"] == []


@pytest.mark.parametrize(
    "status, expected", [(401, "AUTH_REQUIRED"), (403, "BUSINESS_QUERY_FAILED")]
)
def test_http_failure_preserves_cache(run_cli, envelope, setup, status, expected):
    old = seed(run_cli, setup)
    setup.state.business_script.append({"status": status, "body": {}})
    code, out, _ = refresh(run_cli)
    assert code == 1 and envelope(out)["error"]["code"] == expected
    assert listing(run_cli)[1] == old


def test_interruption_preserves_cache(run_cli, setup):
    old = seed(run_cli, setup)

    def interrupted(payload, index):
        raise KeyboardInterrupt

    setup.state.business_handler = interrupted
    assert refresh(run_cli)[0] == 130
    assert listing(run_cli)[1] == old
    assert all(len(t.closed) == len(t.created) for t in setup.state.transports)


def test_bounded_retry_no_page_fallback(run_cli, envelope, setup, no_sleep):  # noqa: F811
    setup.state.business_script.extend([{"status": 503, "body": {}}] * 3)
    code, out, _ = listing(run_cli, "--live")
    assert code == 1 and envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    assert no_sleep == [1.0, 2.0]
    assert len(setup.state.business_requests) == 3
    assert all(
        p["pageNo"] == 0 and p["pageSize"] == 1000
        for p in setup.state.business_requests
    )


def test_fixed_allowlist_before_browser(setup):
    cap = COLLECTION_COST_CAPABILITY
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        cap,
        page_url="https://ifundcontrol.alipay.com",
    )
    request = QueryRequest(
        cap.name,
        "POST",
        cap.contract.host,
        cap.contract.path,
        cap.page_body(COST_TYPE, 0, 1000),
    )
    changes = [
        {"method": "GET"},
        {"host": "evil.example"},
        {"path": "/api/fundCost/save.json"},
        {"capability": "payment.cost.list"},
    ]
    bodies = [
        {},
        {**request.body, "action": "save"},
        {**request.body, "legalEntityCode": "X"},
    ]
    for key, value in [
        ("costTypeCode", "FUND_OUT_CHANNEL_TRANS_FEE"),
        ("costTypeCode", "FUND_IN_VA_FEE"),
        ("pageNo", 1),
        ("pageNo", False),
        ("pageSize", 10),
    ]:
        bodies.append({**request.body, key: value})
    changes += [{"body": body} for body in bodies]
    for change in changes:
        with pytest.raises(CliError) as caught:
            transport.execute(replace(request, **change))
        assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert not setup.state.business_requests
    assert not any(t.created for t in setup.state.transports)


def test_help_describe_offline_and_unknown_commands(run_cli, envelope, monkeypatch):
    monkeypatch.setattr(
        cli.config_mod,
        "load",
        lambda *args: pytest.fail("offline command loaded config"),
    )
    for path in [
        ("collection",),
        ("collection", "cost"),
        ("collection", "cost", "list"),
        ("refresh", "collection", "cost"),
    ]:
        assert run_cli(["help", *path])[0] == 0
    code, out, _ = run_cli(["describe", "collection", "cost", "list"])
    assert code == 0
    doc = envelope(out)
    Draft202012Validator.check_schema(doc["data_schema"])
    Draft202012Validator(doc["data_schema"]).validate([row()])
    assert "FUND_OUT" not in out
    for flags in [
        ("--cost-type", "FX_FEE"),
        ("--bank-account", "X"),
        ("--all", "--limit", "1"),
    ]:
        assert listing(run_cli, *flags)[0] == 2
    assert run_cli(["collection", "va-pool", "list"])[0] == 2
