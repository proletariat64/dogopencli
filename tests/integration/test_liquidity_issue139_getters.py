"""Qualified inquiry objects through public CLI, fake CDP and real SQLite."""

from decimal import Decimal

import pytest

pytest_plugins = ["test_liquidity_cli_sit"]


@pytest.fixture(autouse=True)
def native_details_do_not_create_cache(setup, request):
    yield
    if request.node.originalname not in {
        "test_populated_parent_list_does_not_substitute_native_get",
        "test_native_get_does_not_touch_parent_list_cache",
        "test_asset_list_cache_cannot_satisfy_or_be_changed_by_native_get",
    }:
        assert not setup.cache_path.exists()


def rfq(identity="SYN-CHILD"):
    return {
        "success": True,
        "data": {
            "inquiryTaskId": identity,
            "inquiryType": "TARGET_RFQ",
            "currency": "USD",
            "ticketSize": Decimal("0.1234567890123456789"),
            "inquiryMemo": "synthetic memo",
            "inquiryOrderListVOList": [
                {
                    "inquiryId": "SYN-INQUIRY",
                    "quotationNum": "0",
                    "inquiryStatus": "UNKNOWN",
                    "inquiryTime": None,
                }
            ],
        },
    }


def command(identity="SYN-CHILD"):
    return ["liquidity", "investment", "rfqs", "get", "--inquiry-sub-task-id", identity]


def quotas():
    return {
        "resultFlag": True,
        "result": {
            "success": True,
            "count": 0,
            "data": {
                "dynamicQuotas": [
                    {
                        "dateRange": {"begin": 1, "end": 2},
                        "individualLimit": {
                            "currency": "USD",
                            "hasLimit": True,
                            "limit": Decimal("0.1234567890123456789"),
                        },
                    }
                ],
                "staticQuotas": [
                    {"quotaId": "", "currency": "USD", "usedQuota": "0.0000"},
                    {"quotaId": "", "currency": "USD", "usedQuota": "0.0000"},
                ],
            },
        },
    }


def quota_command(alias="SYN-ALIAS", route="SYN-ROUTE"):
    return [
        "liquidity",
        "network",
        "route-quotas",
        "get",
        "--route-id",
        route,
        "--account-alias",
        alias,
    ]


LEAVES = ((command, rfq), (quota_command, quotas))
