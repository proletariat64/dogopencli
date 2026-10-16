"""Four-source interest inquiries through public CLI and synthetic CDP."""

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "investment", "interest-rates"]
BOUNDS = ["--from-date", "2026-01-01", "--to-date", "2026-01-02"]


def market():
    return {
        "currency": "USD",
        "rateName": "SYN-RATE",
        "ratePeriod": "O/N",
        "effectiveDate": "2026-01-01",
        "rateValue": "-0.1234500",
    }


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


def bank(identity="SYN-BANK", product="SYN-PRODUCT"):
    return {
        "bankId": identity,
        "currency": "USD",
        "productTerm": "O/N",
        "productType": product,
        "quoteDate": "20260101",
        "rateValue": "-0.0002500",
        "gmtModified": None,
        "maxPurchaseAmount": "",
        "inquiryAmount": "0",
    }


def rule(category, identity="SYN-RULE"):
    return {
        "ruleId": identity,
        "ruleStatus": "INVALID",
        "ruleValue": "-0.0025000",
        "rateCategory": category,
        "currency": "USD",
        "effectiveDate": "20260101",
        "expireDate": "21260101",
        "version": "1",
    }


def external_detail():
    return {
        **rule("FINANCIAL_INST_TYPE"),
        "approveState": "SYN-APPROVED",
        "customizedMarketRateName": "SYN-NAME",
        "effectDateList": {"20260101": "-0.0025000"},
        "expectedRateProvider": "SYN-PROVIDER",
        "financialInstFiles": [],
        "financialInstFilesMap": {"SYN-FILE": {"name": "synthetic"}},
        "gmtCreate": "20260101",
        "gmtModify": None,
        "lastOperator": "SYN-OPERATOR",
        "oldIncrementFinancialRateRuleDetail": {
            "ruleValue": "",
            "effectDateList": None,
        },
        "operationLogDetailList": [{"operation": "SYN-LOG", "value": "0"}],
        "operator": "SYN-OPERATOR",
        "processId": None,
        "rateBasicType": "SYN-TYPE",
        "ratePeriod": "O/N",
        "rateProvideCode": "SYN-CODE",
        "rateType": "SYN-TYPE",
        "reason": "SYNTHETIC TEST",
        "ruleType": "SYN-FIXED",
    }
