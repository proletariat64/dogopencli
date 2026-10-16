"""Native asset roots and physical quotation group versions at public CLI seam."""

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


def asset(identity="SYN-ORDER"):
    return {
        "success": True,
        "data": {
            "orderNo": identity,
            "orderStatus": "UNKNOWN",
            "tradingDate": "20261007",
            "assetTransferAmount": "0.1234000000",
            "counterpartTransferAmount": Decimal("0.123456789012345678901"),
            "assetTransferCurrency": "USD",
            "actualValueDate": None,
            "timezone": "",
            "assetProductVo": {
                "assertProductCategory": "SYN-CATEGORY",
                "assertProductCode": "SYN-CODE",
                "assertProductName": "SYN-PRODUCT",
                "assertProductTenor": "O/N",
                "assertProductType": "SYN-TYPE",
            },
            "transFerOrderLogVoList": [
                {"orderNo": "OTHER-UNBOUND", "content": "PRIVATE-LOG"}
            ],
        },
    }


def asset_command(identity="SYN-ORDER"):
    return ["liquidity", "operations", "asset-trades", "get", "--order-no", identity]


def group_row(identity="SYN-ROW-3", version=3):
    return {
        "id": identity,
        "quotationGroupId": "SYN-BUSINESS-GROUP",
        "version": version,
        "tntInstId": "GUAPW3SG",
        "quotationGroupName": "SYN-GROUP",
        "bankId": "SYN-BANK",
        "department": "SYN-DEPARTMENT",
        "status": "UNKNOWN",
        "processStatus": "UNKNOWN-PROCESS",
        "memo": "synthetic memo",
        "contactInfoList": [
            {
                "name": "Synthetic Person",
                "emailAddress": "synthetic@example.invalid",
                "memo": "",
            }
        ],
        "operationHistoryList": [],
        "fileDownloadUrl": "PRIVATE-ATTACHMENT",
        "fileKey": "PRIVATE-KEY",
        "reviewLink": "PRIVATE-ACTION",
    }


def group(identity="SYN-ROW-3", version=3):
    data = group_row(identity, version)
    data["operationHistoryList"] = [
        group_row("SYN-ROW-3", 3),
        group_row("SYN-ROW-1", 1),
    ]
    return {"success": True, "data": data}


def group_command(identity="SYN-ROW-3"):
    return [
        "liquidity",
        "investment",
        "quote-groups",
        "get",
        "--quotation-group-row-id",
        identity,
    ]


LEAVES = ((asset_command, asset), (group_command, group))
