"""B01 policy refusal through public CLI, fake CDP, and real SQLite."""

import pytest

pytest_plugins = ["test_liquidity_cli_sit"]
RESOURCES = (
    "factors",
    "factor-values",
    "cost-prices",
    "strategies",
    "client-prices",
    "fee-orders",
)


@pytest.mark.parametrize("resource", RESOURCES)
def test_direct_historical_source_bindings_are_not_executable(resource):
    from dogopencli.errors import CliError
    from dogopencli.plugins import cache_bindings
    from dogopencli.plugins.liquidity.capability import LiquidityListCapability
    from dogopencli.plugins.liquidity.leaves import RETIRED_LEAVES

    leaf = RETIRED_LEAVES[("pricing", resource)]
    capability = LiquidityListCapability(leaf.variants[0])
    for acquire in (lambda: capability.contract, lambda: capability.page_body("", 0)):
        with pytest.raises(CliError) as error:
            acquire()
        assert error.value.code == "UNSUPPORTED_CAPABILITY"
    assert ("liquidity", "pricing", resource, "list") not in cache_bindings()
    assert ("refresh", "liquidity", "pricing", resource) not in cache_bindings()
