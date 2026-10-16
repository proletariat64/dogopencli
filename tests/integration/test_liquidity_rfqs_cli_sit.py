"""TARGET_RFQ public CLI, fake CDP and real SQLite; every row is synthetic."""

import hashlib
from dataclasses import replace

import pytest

from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.capability import (
    LiquidityListCapability,
    encode_scope,
)
from dogopencli.plugins.liquidity.rfqs import RFQS
from dogopencli.transport import QueryRequest, validate_request

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "investment", "rfqs"]
BOUNDS = ["--from-date", "2026-01-01", "--to-date", "2026-10-05"]


def query(*extra, bounds=None):
    if bounds is None:
        bounds = BOUNDS if "--live" in extra else []
    return [*ROOT, "list", *bounds, "--limit", "0", *extra]


def refresh(*extra, bounds=BOUNDS):
    return ["refresh", *ROOT, *bounds, *extra]


def subtask(identity="SYN-SUBTASK"):
    return {
        "inquirySubTaskId": identity,
        "inquiryTaskId": "SYN-PARENT",
        "inquiryType": "TARGET_RFQ",
        "productType": "SYN-PRODUCT",
        "currency": "USD",
        "tenor": "O/N",
        "redemptionFeature": "",
        "inquiryStatus": "UNKNOWN-INQUIRY",
        "quotationStatus": None,
        "winStatus": "UNKNOWN-WIN",
        "quotedNum": 0,
        "inquiryNum": -2,
        "winNum": 7,
        "inquiryStartTime": "2026-01-01 11:22:33",
        "inquiryEndTime": "",
        "modifyTime": "unknown-time",
        "processStatus": "UNKNOWN-PROCESS",
    }


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


def digest(setup):
    return hashlib.sha256(setup.cache_path.read_bytes()).hexdigest()


def seed(setup, run_cli, rows=None, bounds=BOUNDS):
    setup.state.business_handler = lambda payload, index: response(
        [subtask()] if rows is None else rows
    )
    code, out, err = run_cli(refresh("--require-complete", bounds=bounds))
    assert code == 0, err
    return parse(out)


@pytest.mark.parametrize(
    "mutation",
    ["type", "offset", "width", "filter", "method", "host", "path"],
)
def test_shared_transport_rejects_contract_mutations(mutation):
    capability = LiquidityListCapability(RFQS)
    body = capability.page_body(
        encode_scope(
            {"inquiryStartDate": "2026-01-01", "inquiryEndDate": "2026-10-05"}
        ),
        0,
    )
    request = QueryRequest(
        capability.name, "POST", "iliquidity.alipay.com", RFQS.endpoint, body
    )
    validate_request(request, capability.contract)
    if mutation == "type":
        body["inquiryType"] = "FULL_RANGE_RFQ"
    elif mutation == "offset":
        body["rowStart"] = 5000
    elif mutation == "width":
        body["pageSize"] = 10
    elif mutation == "filter":
        body["inquiryTaskId"] = "SYN-PARENT"
    else:
        changes = {
            "method": {"method": "GET"},
            "host": {"host": "ifundcontrol.alipay.com"},
            "path": {"path": "/rfq/subInquiryTask/update.json"},
        }[mutation]
        request = replace(request, **changes)
    with pytest.raises(CliError) as caught:
        validate_request(request, capability.contract)
    assert caught.value.code == "REQUEST_NOT_ALLOWED"
