"""S01 public CLI, fake CDP and temporary SQLite acceptance."""

import pytest

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "operations", "account_strategies"]


def strategy(alias="SYN-A", version=1, **changes):
    return {
        "aliasName": alias,
        "version": version,
        "entity": "SYN-ENTITY",
        "bankId": "SYN-BANK",
        "currency": "USD",
        "accountType": "CASH",
        "operationStrategy": "Self-Built Cash Pool,No Need,Self-Built Cash Pool",
        "coverAlgorithm": "N",
        "status": "Invalid",
        "processStatus": "APPROVED",
        "lastModifiedTime": "2026-10-15 12:30:00",
        **changes,
    }


def install(setup, rows):
    def answer(payload, index):
        start = payload["rowStart"]
        page = rows[start : start + payload["pageSize"]]
        return {
            "status": 200,
            "body": {"success": True, "data": {"data": page, "totalCount": len(rows)}},
        }

    setup.state.business_handler = answer


def test_readonly_allowlist_rejects_status_and_mutation_before_cdp(setup):
    from dataclasses import replace

    from dogopencli.errors import CliError
    from dogopencli.plugins.liquidity.account_strategies import ACCOUNT_STRATEGIES
    from dogopencli.plugins.liquidity.leaves import list_leaf
    from dogopencli.transport import QueryRequest
    from dogopencli.transport.cdp import CdpQueryTransport

    capability = list_leaf(ACCOUNT_STRATEGIES.path).capability(ACCOUNT_STRATEGIES)
    request = QueryRequest(
        capability=capability.name,
        method="POST",
        host="iliquidity.alipay.com",
        path=ACCOUNT_STRATEGIES.endpoint,
        body={"rowStart": 0, "pageSize": 5000},
    )
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url=capability.page_url,
    )
    for changed in (
        replace(request, body={**request.body, "status": "INVALID"}),
        replace(request, path="/strategyManage/update.json"),
        replace(request, method="GET"),
        replace(request, host="ifundcontrol.alipay.com"),
    ):
        with pytest.raises(CliError) as error:
            transport.execute(changed)
        assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
