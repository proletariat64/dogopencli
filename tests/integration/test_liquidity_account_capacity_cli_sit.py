"""Issue #111 public CLI/fake CDP/real SQLite acceptance; synthetic aliases."""

from dataclasses import replace

import pytest

from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.account_capacity import ACCOUNT_CAPACITY
from dogopencli.plugins.liquidity.leaves import list_leaf
from dogopencli.transport import QueryRequest, validate_request
from dogopencli.transport.cdp import CdpQueryTransport

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "risk", "account-capacity"]
ACCOUNTS = ["SYN-C", "SYN-A", "SYN-B"]


def scope(aliases=ACCOUNTS):
    return [part for alias in aliases for part in ("--account-alias", alias)]


def query(*extra, aliases=ACCOUNTS):
    return [*ROOT, "list", *scope(aliases), "--limit", "0", *extra]


def refresh(*extra, aliases=ACCOUNTS):
    return ["refresh", *ROOT, *scope(aliases), *extra]


def capacity(alias):
    return {
        "aliasName": alias,
        "currency": "unknown-currency",
        "accountAvailableBalance": "123456789.123456789000",
        "availableIod": None,
        "availableResource": "-9.00000",
        "cashPoolSupportAvailableResource": "",
        "outFlowCapacity": "0",
        "totalIod": 0,
        "usedIod": "unknown-native",
        "valueTime": "2026-10-05 08:09:10",
    }


def response(row):
    return {"status": 200, "body": {"success": True, "data": row}}


def seed(setup, run_cli, aliases=ACCOUNTS):
    setup.state.business_handler = lambda payload, index: response(
        {**capacity(payload["aliasName"]), "privateOwner": "excluded"}
    )
    code, out, err = run_cli(refresh("--require-complete", aliases=aliases))
    assert code == 0, err
    return parse(out)


def test_transport_rejects_extra_keys_and_endpoint_changes(setup):
    leaf = list_leaf(ACCOUNT_CAPACITY.path)
    capability = leaf.capability(ACCOUNT_CAPACITY)
    request = QueryRequest(
        capability=capability.name,
        method="GET",
        host="iliquidity.alipay.com",
        path=ACCOUNT_CAPACITY.endpoint,
        body={"aliasName": "SYN-A"},
    )
    validate_request(request, capability.contract)
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url=capability.page_url,
    )
    for changed in (
        replace(request, method="POST"),
        replace(request, host="ifundcontrol.alipay.com"),
        replace(request, path="/api/fund/capacity/update.json"),
        replace(request, body={**request.body, "tntInstId": "GUAPW3SG"}),
        replace(request, body={**request.body, "rowStart": 0}),
        replace(request, body={**request.body, "pageSize": 10}),
        replace(request, body={**request.body, "date": "20261005"}),
    ):
        with pytest.raises(CliError) as error:
            transport.execute(changed)
        assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
    assert not any(t.created for t in setup.state.transports)
    assert not any(t.expressions for t in setup.state.transports)
