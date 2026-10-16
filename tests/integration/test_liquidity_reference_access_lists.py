"""Independent access lists through public CLI and isolated external seams."""

import json

import pytest

from dogopencli.errors import CliError
from dogopencli.plugins.liquidity.access_lists import ACCOUNT_BLACKLIST
from dogopencli.plugins.liquidity.capability import LiquidityListCapability
from dogopencli.transport import QueryRequest, validate_request

pytest_plugins = ["test_liquidity_cli_sit"]


@pytest.mark.parametrize(
    "change",
    [
        {"Edit": True},
        {"status": "VALID"},
        {"tntInstId": "OTHER"},
        {"currentArea": "2"},
        {"timezone": "UTC"},
        {"rowStart": -1},
        {"rowStart": True},
        {"rowStart": 1.0},
        {"rowStart": "1"},
        {"rowStart": {}},
        {"rowStart": None},
        {"pageSize": 0},
        {"pageSize": 10},
        {"pageSize": 1001},
        {"pageSize": True},
        {"pageSize": 1000.0},
        {"pageSize": "1000"},
        {"pageSize": {}},
        {"pageSize": None},
    ],
)
def test_access_transport_rejects_unverified_nested_requests(change):
    capability = LiquidityListCapability(ACCOUNT_BLACKLIST)
    body = capability.page_body("", 0)
    vo = json.loads(body["accountFilterConfigQuery"])
    vo.update(change)
    body["accountFilterConfigQuery"] = json.dumps(vo)
    request = QueryRequest(
        capability.name,
        "GET",
        "iliquidity.alipay.com",
        "/accountFilterConfigQuery.json",
        body,
    )
    with pytest.raises(CliError) as caught:
        validate_request(request, capability.contract)
    assert caught.value.code == "REQUEST_NOT_ALLOWED"


def access_page(rows, total):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": total,
            "result": {"success": True, "data": rows, "count": total},
        },
    }


def source_rows(setup, rows_by_field):
    def answer(payload, index):
        field = next(k for k in rows_by_field if k in payload)
        rows = rows_by_field[field]
        vo = json.loads(payload[field])
        start = vo["rowStart"]
        return access_page(rows[start : start + vo["pageSize"]], len(rows))

    setup.state.business_handler = answer
