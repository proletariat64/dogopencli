"""B01 policy refusal through public CLI, fake CDP, and real SQLite."""

import pytest

from dogopencli.jsonutil import parse

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
@pytest.mark.parametrize("action", ("offline", "live", "refresh"))
def test_retired_lists_refuse_without_cache_or_browser(
    setup, run_cli, resource, action
):
    root = ["liquidity", "pricing", resource]
    command = ["refresh", *root] if action == "refresh" else [*root, "list"]
    if action == "live":
        command += ["--live"]
    setup.state.reachable = False
    code, out, _ = run_cli(command)
    result = parse(out)
    assert code == 1
    assert result["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert "retired" in result["error"]["message"]
    assert "#164" in result["error"]["message"]
    assert result["data"] is None
    assert not setup.state.transports
    assert not setup.state.business_requests
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("resource", RESOURCES)
@pytest.mark.parametrize("refresh", (False, True))
def test_discovery_reports_retirement_without_executable_schema(
    setup, run_cli, resource, refresh
):
    root = ["liquidity", "pricing", resource]
    path = ["refresh", *root] if refresh else [*root, "list"]
    for discovery in ("help", "describe"):
        code, out, err = run_cli([discovery, *path])
        assert code == 0, err
        assert "retired" in out and "#164" in out
        if discovery == "describe":
            result = parse(out)
            assert result["read_guide"]["release_status"] == "retired"
            assert "properties" not in result["data_schema"]
    code, out, err = run_cli(["snapshot", *path, "--format", "json"])
    assert code == 0, err
    assert '"availability":"unsupported"' in out.replace(" ", "")
    assert "retired" in out
    assert not setup.state.transports
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("resource", RESOURCES)
def test_legacy_options_refuse_and_preserve_populated_history(setup, run_cli, resource):
    from dogopencli.cache import Cache
    from dogopencli.result_policy import AcquisitionEvidence
    from dogopencli.temporary_query import publish_slot

    store = Cache(setup.cache_path)
    for leaf in (f"liquidity.pricing.{resource}", "liquidity.reference.entities"):
        publish_slot(
            store,
            leaf,
            [{"id": "SYN-HISTORY", "code": "SYN-FACTOR"}],
            capability=f"{leaf}.list",
            scope={},
            variant="historical",
            evidence=AcquisitionEvidence.for_collection(
                complete=True, reported_total=1, collected_total=1
            ),
            fetched_at="2026-10-13T00:00:00+00:00",
        )
    before = setup.cache_path.read_bytes()
    root = ["liquidity", "pricing", resource]
    scope = (
        []
        if resource in ("factors", "strategies")
        else ["--from-date", "2026-08-01", "--to-date", "2026-08-31"]
    )
    for command in (
        [
            *root,
            "list",
            "--live",
            "--limit",
            "0",
            "--offset",
            "1",
            "--format",
            "table",
            "--fields",
            "id",
            "--require-complete",
            *scope,
        ],
        ["refresh", *root, "--require-complete", *scope],
        [*root, "list"],
    ):
        code, out, err = run_cli(command)
        assert code == 1
        if "table" in command:
            assert "UNSUPPORTED_CAPABILITY" in err and "retired" in err
            assert not out
        else:
            assert parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
        assert setup.cache_path.read_bytes() == before
    code, _, _ = run_cli([*root, "prune"])
    assert code == 2  # prune compatibility choice: removed, never deletes history.
    for discovery in ("help", "describe", "snapshot"):
        assert run_cli([discovery, *root, "list"])[0] == 0
        assert setup.cache_path.read_bytes() == before
    assert not setup.state.transports


def test_refusal_never_loads_acquisition_config(setup, run_cli, monkeypatch):
    import dogopencli.cli as cli

    def forbidden(*args, **kwargs):
        pytest.fail("retirement loaded acquisition configuration")

    monkeypatch.setattr(cli.config_mod, "load", forbidden)
    for resource in RESOURCES:
        for command in (
            ["liquidity", "pricing", resource, "list", "--live"],
            ["refresh", "liquidity", "pricing", resource],
        ):
            code, out, _ = run_cli(command)
            assert code == 1
            assert parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"


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


def test_unrelated_active_list_and_shared_contract_remain_allowed(setup, run_cli):
    from dataclasses import replace

    from dogopencli.plugins.liquidity.capability import LiquidityListCapability
    from dogopencli.plugins.liquidity.leaves import PRICING_FACTORS
    from dogopencli.transport import QueryRequest, validate_request

    row = {"aliasName": "SYN-A", "currency": "USD", "curAvlBal": "1.00"}
    setup.state.business_handler = lambda body, index: {
        "status": 200,
        "body": {"success": True, "data": {"data": [row], "totalCount": 1}},
    }
    code, out, err = run_cli(
        [
            "liquidity",
            "cash",
            "waterlevels",
            "list",
            "--live",
            "--account-alias",
            "SYN-A",
        ]
    )
    assert code == 0, err
    assert parse(out)["data"] == [row]
    assert len(setup.state.business_requests) == 1
    # No active getPriceEnv caller exists in the inspected registry. Verify
    # ownership-based retirement preserves the shared contract, without
    # claiming this synthetic owner is an actual supported command.
    owner = LiquidityListCapability(
        replace(PRICING_FACTORS, path=("reference", "synthetic-shared-owner"))
    )
    contract = owner.contract
    assert contract.path == "/getPriceEnv.json"
    validate_request(
        QueryRequest(
            owner.name,
            contract.method,
            contract.host,
            contract.path,
            owner.page_body("", 0),
        ),
        contract,
    )


@pytest.mark.parametrize(
    "resource", ("factors", "strategies", "client-prices", "valuations", "bills")
)
def test_deferred_pricing_gets_stay_unavailable(setup, run_cli, resource):
    code, out, _ = run_cli(["liquidity", "pricing", resource, "get"])
    assert code == 1
    assert parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert not setup.state.transports
