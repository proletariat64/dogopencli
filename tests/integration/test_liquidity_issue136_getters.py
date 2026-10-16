"""Three independently requested native objects through CLI, fake CDP and SQLite."""

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


def demand(identity="SYN-TASK"):
    return {
        "resultFlag": True,
        "result": {
            "success": True,
            "riskActionVO": {
                "taskId": identity,
                "tntInstId": "",
                "source": "FUND_REQUIRE",
                "amount": "1.230000",
                "decisionAmount": None,
                "operationAmount": 0,
                "instructionStatus": "unknown",
                "createTime": "2026-10-07 01:02:03",
                "updateTime": "2026-10-07 04:05:06",
                "accountNo": "PRIVATE",
                "decisionReports": [{"tntInstId": "GUAPW3SG", "operator": "PRIVATE"}],
            },
        },
    }


def command(identity="SYN-TASK"):
    return ["liquidity", "operations", "demands", "get", "--task-id", identity]


def quotation(identity="SYN-QUOTE"):
    return {
        "baseResult": {
            "success": True,
            "data": {
                "quotationDetail": {
                    "quotationId": identity,
                    "bankId": "SYN-BANK",
                    "quote": "-0.1234500",
                    "quotationTime": "2026-10-07 08:00:00",
                    "quotationStatus": "UNRECOGNIZED",
                    "attachmentUrl": "PRIVATE",
                },
                "productDetail": {
                    "currency": "USD",
                    "quote": "1.00000000",
                    "tenor": "O/N",
                    "actualMaturityDate": None,
                    "curMaxLimitAvailable": 0,
                    "operator": "PRIVATE",
                },
                "operationLog": "PRIVATE",
            },
        }
    }


LEAVES = (
    (("operations", "demands"), "task-id", "SYN-TASK", demand),
    (
        ("network", "realtime"),
        "network-id",
        "SYN-NET",
        lambda identity="SYN-NET": {
            "success": True,
            "data": {"id": identity, "version": 7},
        },
    ),
    (("investment", "quotes"), "quotation-order-id", "SYN-QUOTE", quotation),
)


def invocation(leaf, *, identity=None):
    path, flag, default, _ = leaf
    return [
        "liquidity",
        *path,
        "get",
        "--" + flag,
        default if identity is None else identity,
    ]
