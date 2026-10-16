"""Public D03 CLI through fake CDP and temporary SQLite."""

import pytest

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "forecast", "account_demands_intraday"]
SCOPE = [
    "--alias",
    "SYN-A",
    "--entity",
    "SYN-E",
    "--bank",
    "SYN-B",
    "--from-date",
    "20261014",
    "--to-date",
    "20261014",
]


def slots():
    return [
        {
            "statisticalDate": f"{hour:02}:{minute:02}",
            "inflowAmount": "123456789.123456789123456789",
            "outflowAmount": "123456789.123456789123456790",
            "totalAmount": "-0.000000000000000001",
        }
        for hour in range(24)
        for minute in (0, 15, 30, 45)
    ]


def response(rows):
    return lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": rows},
    }


def test_intraday_transport_rejects_pagination_extra_fields_and_mutation(setup):
    from dataclasses import replace

    from dogopencli.errors import CliError
    from dogopencli.plugins.liquidity.account_intraday import INTRADAY
    from dogopencli.plugins.liquidity.leaves import list_leaf
    from dogopencli.transport import QueryRequest
    from dogopencli.transport.cdp import CdpQueryTransport

    capability = list_leaf(INTRADAY.path).capability(INTRADAY)
    body = {
        "aliasName": "SYN-A",
        "entity": "SYN-E",
        "bankId": "SYN-B",
        "startDate": "20261014",
        "endDate": "20261014",
    }
    request = QueryRequest(
        capability=capability.name,
        method="POST",
        host="iliquidity.alipay.com",
        path=INTRADAY.endpoint,
        body=body,
    )
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url=capability.page_url,
    )
    for changed in (
        replace(request, body={**body, "rowStart": 0}),
        replace(request, body={**body, "pageSize": 96}),
        replace(request, body={**body, "fundActionTypes": ["WITHDRAW"]}),
        replace(request, path="/strategyManage/update.json"),
        replace(request, method="GET"),
        replace(request, host="ifundcontrol.alipay.com"),
    ):
        with pytest.raises(CliError) as error:
            transport.execute(changed)
        assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
