"""QUOTED-only source reads; all identifiers and financial values are invented."""

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "investment", "quotes"]
BOUNDS = ["--from-date", "2026-01-01", "--to-date", "2026-01-02"]


def query(*extra, bounds=None):
    if bounds is None:
        bounds = BOUNDS if "--live" in extra else []
    return [*ROOT, "list", *bounds, "--limit", "0", *extra]


def refresh(*extra, bounds=BOUNDS):
    return ["refresh", *ROOT, *bounds, *extra]


def quote(identity="SYN-QUOTE"):
    return {
        "quotationOrderId": identity,
        "inquiryId": "SYN-INQUIRY",
        "bankId": "SYN-BANK",
        "quotationGroupName": "SYN-GROUP",
        "accountType": "SYN-ACCOUNT-TYPE",
        "department": "SYN-DEPARTMENT",
        "currency": "USD",
        "tenor": "O/N",
        "quote": "-0.1234500",
        "ticketSize": "1,234.567800",
        "curMaxLimitAvailable": "unconfirmed-native-value",
        "maxCurMaxLimitAvailable": False,
        "maxQuote": True,
        "inquiryTime": "2026-01-01 11:22:33",
        "quotationTime": "2026-01-01 11:33:44",
        "inquiryType": "SYN-INQUIRY-TYPE",
        "productType": "SYN-PRODUCT",
        "valueDate": "20260101",
        "expectMaturityDate": "not-a-date",
        "quoteEffectiveEndDate": "unknown",
        "winAmount": "",
        "redemptionFeature": "SYN-REDEMPTION",
        "negotiationStatus": "UNKNOWN-STATUS",
        "otherRemark": "SYNTHETIC NOTE",
    }


def response(rows):
    return {"status": 200, "body": {"success": True, "data": rows}}


def seed(setup, run_cli, rows=None, bounds=BOUNDS):
    setup.state.business_handler = lambda payload, index: response(
        [quote()] if rows is None else rows
    )
    code, out, err = run_cli(refresh("--require-complete", bounds=bounds))
    assert code == 0, err
    return parse(out)
