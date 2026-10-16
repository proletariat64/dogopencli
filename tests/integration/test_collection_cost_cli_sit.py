"""Issue #21 public CLI proof using synthetic responses and the real cache."""

from dataclasses import replace

import pytest
from test_cost_cli_sit import cost_page, cost_row, cost_setup, no_sleep  # noqa: F401

from dogopencli.errors import CliError
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


def refresh(run_cli, *flags):
    return run_cli(["refresh", "collection", "cost", *flags])


def seed(run_cli, setup):
    setup.state.business_script.append(page())
    assert refresh(run_cli)[0] == 0
    return listing(run_cli)[1]


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
