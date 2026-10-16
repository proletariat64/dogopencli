"""Collection SLA public CLI + fake CDP + real SQLite acceptance (#28)."""

from dataclasses import replace

import pytest
from test_sla_cli_sit import sla_setup  # noqa: F401

from dogopencli.errors import CliError
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.collection_sla]\nkind = "cdp"\n')
    return sla_setup


def row(identity="1", **changes):
    return {
        "slaConfigId": identity,
        "businessCategory": "SYNTHETIC",
        "legalEntityCode": "ENTITY",
        "creditorCurrency": "USD",
        "creditorRegion": "US",
        "endToEndSla": 86400,
        "ipayInnerSla": 3600,
        "holidayLimit": {"currencyCodes": ["USD", "EUR"], "regionCodes": ["US", "SG"]},
        "gmtModified": 1694100000000,
        "unknownExtension": {"keep": [1, 2]},
        **changes,
    }


def page(rows=None, **changes):
    rows = [row()] if rows is None else rows
    return {
        "status": 200,
        "body": {
            "success": True,
            "pageNo": 0,
            "pageSize": 1000,
            "totalCount": len(rows),
            "resultDataList": rows,
            **changes,
        },
    }


def detail(identity="1", **changes):
    return {
        "status": 200,
        "body": {
            "success": True,
            "resultData": row(identity, detailOnly=True, **changes),
        },
    }


def listing(run_cli, *flags):
    return run_cli(["collection", "sla", "configs", "list", *flags])


def getting(run_cli, *flags):
    return run_cli(["collection", "sla", "configs", "get", *flags])


def refresh(run_cli, *flags):
    return run_cli(["refresh", "collection", "sla", *flags])


def seed(run_cli, setup):
    setup.state.business_script.append(page())
    assert refresh(run_cli)[0] == 0
    return listing(run_cli)[1], None


def test_transport_restrictions_before_browser(setup):
    from dogopencli.plugins.collection.sla import COLLECTION_SLA, COLLECTION_SLA_DETAIL

    for cap, body in [
        (COLLECTION_SLA, {"pageNo": 0, "pageSize": 1000}),
        (COLLECTION_SLA_DETAIL, {"slaConfigId": "1"}),
    ]:
        transport = CdpQueryTransport(
            setup.state.transport("http://127.0.0.1:9222"),
            cap,
            page_url="https://ifundcontrol.alipay.com",
        )
        request = QueryRequest(
            cap.name, cap.contract.method, cap.contract.host, cap.contract.path, body
        )
        for change in [
            {"path": "/api/fundInSlaConfig/save.json"},
            {"host": "evil.example"},
            {"method": "DELETE"},
            {"body": {**body, "action": "save"}},
            {"capability": "payment.sla.baselines.list"},
        ]:
            with pytest.raises(CliError) as caught:
                transport.execute(replace(request, **change))
            assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert not setup.state.business_requests
    assert not any(t.created for t in setup.state.transports)


FILTERS = [
    ("--business-line", "businessCategory"),
    ("--entity", "legalEntityCode"),
    ("--currency", "creditorCurrency"),
    ("--region", "creditorRegion"),
]
