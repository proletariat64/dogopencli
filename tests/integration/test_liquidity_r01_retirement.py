"""R01 public refusal preserves storage and never opens transport."""

import pytest

pytest_plugins = ["test_liquidity_cli_sit"]
RESOURCES = (
    ("cash", "groups"),
    ("investment", "strategies"),
    ("rules", "notification"),
    ("ledger", "customers"),
    ("ledger", "accounts"),
    ("reference", "business-lines"),
    ("reference", "calendars"),
)


@pytest.mark.parametrize("path", RESOURCES)
def test_historical_bindings_cannot_acquire_and_have_no_cache_routes(path):
    from dogopencli.errors import CliError
    from dogopencli.plugins import cache_bindings
    from dogopencli.plugins.liquidity.capability import LiquidityListCapability
    from dogopencli.plugins.liquidity.leaves import RETIRED_LEAVES

    for spec in RETIRED_LEAVES[path].variants:
        capability = LiquidityListCapability(spec)
        for acquire in (
            lambda capability=capability: capability.contract,
            lambda capability=capability: capability.page_body("", 0),
        ):
            with pytest.raises(CliError) as error:
                acquire()
            assert error.value.code == "UNSUPPORTED_CAPABILITY"
            assert "#167" in error.value.message
    assert ("liquidity", *path, "list") not in cache_bindings()
    assert ("refresh", "liquidity", *path) not in cache_bindings()


def test_active_registry_excludes_retired_sources_and_preserves_scope():
    from dogopencli.plugins import get_capability
    from dogopencli.plugins.liquidity.leaves import DETAIL_LEAVES, LIST_LEAVES

    for path in RESOURCES:
        assert path not in LIST_LEAVES
        with pytest.raises(KeyError):
            get_capability("liquidity." + ".".join(path) + ".list")
    assert ("cash", "group-balances") in LIST_LEAVES
    assert ("forecast", "adjustments") in LIST_LEAVES
    assert ("pricing", "strategies") not in LIST_LEAVES
    for path in (
        ("investment", "strategies", "get"),
        ("rules", "notification", "get"),
        ("ledger", "customers", "get"),
    ):
        assert path in DETAIL_LEAVES
        assert DETAIL_LEAVES[path].capability.contract.path
