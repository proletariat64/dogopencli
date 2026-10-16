"""Issue #104 public CLI/fake CDP/real SQLite acceptance; invented records only."""

import pytest

from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.realtime_network import FIELDS

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "network", "realtime"]


def query(*extra):
    return [*ROOT, "list", "--limit", "0", *extra]


def refresh(*extra):
    return ["refresh", *ROOT, *extra]


def network(identity="SYN-NETWORK"):
    row = dict.fromkeys(FIELDS, "SYN-UNKNOWN")
    row.update(
        id=identity,
        routeId="SYN-ROUTE",
        version=0,
        debitAliasName="SYN-DEBIT",
        creditAliasName="SYN-CREDIT",
        debitCurrency="USD",
        creditCurrency="unknown-currency",
        operationCalendar=None,
        operationTime="",
        singlePaymentLimit="0.000000",
        gmtCreate="unknown-time",
        gmtModified=None,
        timeZone=None,
    )
    return row


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


def seed(setup, run_cli, rows=None):
    setup.state.business_handler = lambda payload, index: response(
        [network()] if rows is None else rows
    )
    code, out, err = run_cli(refresh("--require-complete"))
    assert code == 0, err
    return parse(out)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"rowStart": 0},
        {"pageSize": 5000},
        {"rowStart": 5000, "pageSize": 5000},
        {"rowStart": 0, "pageSize": 1},
        {"rowStart": 5000, "pageSize": 1},
        {"rowStart": 0, "pageSize": 5000, "tntInstId": "SYN-TENANT"},
    ],
)
def test_changed_or_missing_fixed_pagination_rejected_before_browser(setup, body):
    from dogopencli.errors import CliError
    from dogopencli.plugins.liquidity.capability import LiquidityListCapability
    from dogopencli.plugins.liquidity.realtime_network import REALTIME_NETWORK
    from dogopencli.transport import QueryRequest
    from dogopencli.transport.cdp import CdpQueryTransport

    capability = LiquidityListCapability(REALTIME_NETWORK)
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url=capability.page_url,
    )
    request = QueryRequest(
        capability.name,
        capability.contract.method,
        capability.contract.host,
        capability.contract.path,
        body,
    )
    with pytest.raises(CliError) as caught:
        transport.execute(request)
    assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
    assert not any(t.created for t in setup.state.transports)
    assert not any(t.expressions for t in setup.state.transports)
