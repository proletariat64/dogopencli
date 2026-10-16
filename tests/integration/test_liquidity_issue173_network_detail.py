"""Realtime network aggregate through public CLI and synthetic CDP."""

pytest_plugins = ["test_liquidity_cli_sit"]

COMMAND = ["liquidity", "network", "realtime", "get", "--network-id", "SYN-NET"]


def bound_root():
    return {
        "id": "SYN-NET",
        "routeId": "SYN-ROUTE",
        "creditAliasName": "SYN-CREDIT",
        "debitAliasName": "SYN-DEBIT",
        "fundAction": "TRANSFER",
        "scene": "REALTIME",
        "version": 7,
    }
