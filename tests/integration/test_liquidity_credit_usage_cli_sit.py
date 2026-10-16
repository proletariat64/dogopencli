"""Credit usage reads source states; all account and amount examples are invented."""

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
QUERY = ["liquidity", "cash", "credit-usage", "list", "--limit", "0"]
REFRESH = ["refresh", "liquidity", "cash", "credit-usage"]


def line():
    return {
        "id": "SYN-LINE",
        "creditLineType": "SUB_LIMIT",
        "currency": "USD",
        "amount": "1,234.567800",
        "usedAmount": "2,999.999900",
        "availableAmount": "-31.00",
        "bankId": "SYN-BANK",
        "masterBankId": "SYN-MASTER",
        "instId": "SYN-INST",
        "shareTag": "N",
        "status": "ACTIVE",
        "manageStatus": "SYN",
        "tntInstId": "GUAPW3SG",
        "gmtModified": "not-a-usage-time",
        "startTimestamp": "unknown-validity",
        "expiryTimestamp": "not-a-date",
        "bankAccountCreditLineList": [
            {
                "id": "SYN-MEMBER",
                "creditLineId": "SYN-LINE",
                "accountNo": "SYN-ACCOUNT",
                "aliasName": "SYN-ALIAS",
                "bankId": "SYN-BANK",
                "instId": "SYN-INST",
                "creditAmount": "9,876.543210",
                "usedCreditAmount": "10,000.000001",
                "availableCreditAmount": "3,200.00",
                "creditCurrency": "USD",
                "currency": "HKD",
                "equvAmount": "7,000.012300",
                "usedAmount": "9,999.00",
                "availableAmount": "-10.00",
                "isMasterAccount": "N",
                "mergeFlag": "SYN-GROUP",
                "status": "ACTIVE",
                "gmtModified": "not-a-time",
                "startTimestamp": "",
                "expiryTimestamp": None,
            }
        ],
    }


def response(rows, total=None):
    total = len(rows) if total is None else total
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": total,
            "result": {"success": True, "data": rows, "count": total},
        },
    }


def seed(setup, run_cli, rows=None):
    setup.state.business_handler = lambda payload, index: response(
        [line()] if rows is None else rows
    )
    code, out, err = run_cli(REFRESH)
    assert code == 0, err
    return parse(out)
