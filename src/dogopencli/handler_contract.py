"""Core execution names shared by declaration validation and CLI composition.

Domain registration can validate offline without importing the CLI while it is
initializing. The CLI checks concrete implementations after defining them.
"""

from collections.abc import Callable, Mapping
from typing import Any

CORE_HANDLER_NAMES = frozenset(
    (
        "cmd_refresh_channel",
        "cmd_channel_list",
        "cmd_refresh_cost",
        "cmd_refresh_collection_cost",
        "cmd_cost_list",
        "cmd_collection_cost_list",
        "cmd_refresh_sla",
        "cmd_sla_list",
        "cmd_sla_get",
        "cmd_refresh_collection_sla",
        "cmd_collection_sla_list",
        "cmd_collection_sla_get",
        "cmd_refresh_collection_va",
        "cmd_collection_va_rules_list",
        "cmd_collection_va_rules_get",
        "cmd_refresh_collection_va_capacity",
        "cmd_collection_va_capacity_list",
        "cmd_collection_clearing_system_list",
        "cmd_collection_account_isolation_list",
        "cmd_refresh_collection_account_isolation",
        "cmd_refresh_collection_clearing_system",
        "cmd_collection_card_template_list",
        "cmd_refresh_collection_card_template",
        "cmd_payment_ptr_orders_list",
        "cmd_refresh_payment_ptr_orders",
        "cmd_payment_ptr_cases_list",
        "cmd_refresh_payment_ptr_cases",
        "cmd_payment_rules_same_bank_transfer_list",
        "cmd_refresh_payment_rules_same_bank_transfer",
        "cmd_payment_rules_cost_reduction_list",
        "cmd_refresh_payment_rules_cost_reduction",
        "cmd_payment_rules_retry_list",
        "cmd_refresh_payment_rules_retry",
        "cmd_payment_rules_bank_switch_list",
        "cmd_refresh_payment_rules_bank_switch",
        "cmd_fx_trade",
        "cmd_refresh_fx_trade",
        "cmd_prune",
        "cmd_liquidity_list",
        "cmd_liquidity_detail",
        "cmd_refresh_liquidity_list",
        "cmd_liquidity_unsupported",
        "cmd_snapshot",
        "cmd_describe",
        "cmd_domain_management",
        "cmd_gui",
    )
)


def core_handler(name: str, implementations: Mapping[str, Any]) -> Callable[..., int]:
    """Resolve only a declared, callable core implementation."""
    handler = implementations.get(name) if name in CORE_HANDLER_NAMES else None
    if not callable(handler):
        raise ValueError(f"missing core handler implementation: {name}")
    return handler


def validate_core_handlers(implementations: Mapping[str, Any]) -> None:
    """Check the complete core contract at the CLI composition boundary."""
    for name in CORE_HANDLER_NAMES:
        core_handler(name, implementations)
