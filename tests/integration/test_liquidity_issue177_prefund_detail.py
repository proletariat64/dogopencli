"""Prefund aggregate inquiries through public CLI and synthetic CDP."""

import json

from dogopencli.plugins.liquidity.spec import TENANT

pytest_plugins = ["test_liquidity_cli_sit"]
COMMAND = ["liquidity", "operations", "prefunds", "get", "--id", "SYN-CURRENT"]


def application(identity="SYN-CURRENT", version=2, status="APPROVED"):
    return {
        "id": identity,
        "version": version,
        "instId": "SYN-ENTITY",
        "status": status,
        "prefundingBizNo": "SYN-BUSINESS",
        "tntInstId": TENANT,
        "amount": "100.000000000000000001",
        "allowUseAmount": "98.00",
        "usedAmount": "2.00",
        "memo": None,
        "fileUrlList": [],
    }


def transaction(identity="SYN-USE", application_id="SYN-OLD"):
    return {
        "preFundingUseDetailId": identity,
        "preFundingOrderId": application_id,
        "prefundingBizNo": "",
        "tntInstId": TENANT,
        "useDirection": "USE",
        "status": "FAIL",
        "applyCurrency": "USD",
        "exchangeAmount": "2.000000000000000001",
        "useRevertRelationVOList": [
            {"currency": "EUR", "amount": "1.234567890123456789"}
        ],
    }


def page(rows, count):
    return {
        "status": 200,
        "body": {"resultFlag": True, "result": {"dataValue": rows, "count": count}},
    }


def configure(setup, *, root=None, history=None, transactions=None, count=0):
    root = application() if root is None else root
    history = (
        [application("SYN-OLD", 1, "APPROVED_FINAL")] if history is None else history
    )
    transactions = [transaction()] if transactions is None else transactions

    def answer(payload, index):
        if "preFundingId" in payload:
            return {
                "status": 200,
                "body": {"resultFlag": True, "result": {"data": root, "count": 0}},
            }
        if "preFundingOrderQueryVO" in payload:
            query = json.loads(payload["preFundingOrderQueryVO"])
            assert query["prefundingBizNo"] == "SYN-BUSINESS"
            if query["statusList"] == ["APPROVED", "CLOSED"]:
                return page([application()], 1)
            return page(history, len(history))
        assert payload == {"tntInstId": TENANT, "prefundingBizNo": "SYN-BUSINESS"}
        return page(transactions, count)

    setup.state.business_handler = answer
    return root, history, transactions
