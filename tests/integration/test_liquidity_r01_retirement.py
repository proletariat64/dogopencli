"""R01 public refusal preserves storage and never opens transport."""

import pytest

from dogopencli.jsonutil import parse

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
@pytest.mark.parametrize("action", ("offline", "live", "refresh"))
def test_retired_lists_refuse_without_storage_browser_or_config(
    setup, run_cli, monkeypatch, path, action
):
    import dogopencli.cli as cli

    def forbidden(*args, **kwargs):
        pytest.fail("retirement loaded acquisition configuration")

    monkeypatch.setattr(cli.config_mod, "load", forbidden)
    setup.state.reachable = False
    root = ["liquidity", *path]
    command = ["refresh", *root] if action == "refresh" else [*root, "list"]
    if action == "live":
        command += ["--live"]
    code, out, _ = run_cli(command)
    result = parse(out)
    assert code == 1
    assert result["error"]["code"] == "LEAF_DISABLED"
    assert result["error"]["message"].startswith("Leaf is disabled:")
    assert result["data"] is None
    assert not setup.state.transports
    assert not setup.state.business_requests
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("path", RESOURCES)
@pytest.mark.parametrize("refresh", (False, True))
def test_discovery_agrees_with_retirement(setup, run_cli, path, refresh):
    root = ["liquidity", *path]
    command = ["refresh", *root] if refresh else [*root, "list"]
    for action in ("help", "describe", "snapshot"):
        code, out, err = run_cli(
            [action, *command, *(["--format", "json"] if action == "snapshot" else [])]
        )
        assert code == 0, err
        if action == "describe":
            assert "retired" in out and "#167" in out
        elif action == "help":
            assert "Disabled" in out
        if action == "describe":
            result = parse(out)
            assert result["read_guide"]["release_status"] == "retired"
            assert "properties" not in result["data_schema"]
        if action == "snapshot":
            assert '"availability": "unsupported"' in out
    assert not setup.state.transports
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "path, options",
    [
        (("cash", "groups"), ["--equi-currency", "USD", "--group-code", "SYN-G"]),
        (("investment", "strategies"), []),
        (("rules", "notification"), []),
        (("ledger", "customers"), []),
        (("ledger", "accounts"), ["--book-type", "INNER", "--currency", "USD"]),
        (("ledger", "accounts"), ["--book-type", "OUTER", "--currency", "USD"]),
        (("reference", "business-lines"), ["--currency", "USD"]),
        (("reference", "calendars"), []),
    ],
)
def test_valid_legacy_options_never_replay_or_modify_history(
    setup, run_cli, path, options
):
    from dogopencli.cache import Cache
    from dogopencli.result_policy import AcquisitionEvidence
    from dogopencli.temporary_query import publish_slot

    store = Cache(setup.cache_path)
    for leaf in ("liquidity." + ".".join(path), "liquidity.reference.entities"):
        publish_slot(
            store,
            leaf,
            [{"id": "SYN-HISTORY"}],
            capability=leaf + ".list",
            scope={},
            variant="historical",
            evidence=AcquisitionEvidence.for_collection(
                complete=True, reported_total=1, collected_total=1
            ),
            fetched_at="2026-10-13T00:00:00+00:00",
        )
    before = setup.cache_path.read_bytes()
    root = ["liquidity", *path]
    refresh_options = (
        options[: options.index("--currency")] if "--currency" in options else options
    )
    for command in (
        [*root, "list", *options],
        [
            *root,
            "list",
            "--live",
            "--limit",
            "0",
            "--offset",
            "1",
            "--fields",
            "id",
            "--format",
            "table",
            "--require-complete",
            *options,
        ],
        ["refresh", *root, "--require-complete", *refresh_options],
    ):
        code, out, err = run_cli(command)
        assert code == 1
        if "table" in command:
            assert not out
            assert "LEAF_DISABLED" in err and "disabled" in err
        else:
            result = parse(out)
            assert result["data"] is None
            assert result["error"]["code"] == "LEAF_DISABLED"
        assert setup.cache_path.read_bytes() == before
    for command in ([*root, "prune"], ["prune", *root]):
        assert run_cli(command)[0] == 2
        assert setup.cache_path.read_bytes() == before
    assert not setup.state.transports
    assert not setup.state.business_requests


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


def test_ledger_retirement_reason_is_business_confirmation(setup, run_cli):
    for resource in ("customers", "accounts"):
        _, out, _ = run_cli(["describe", "liquidity", "ledger", resource, "list"])
        reason = parse(out)["read_guide"]["reason"]
        assert "confirmed unused by business decision" in reason
        assert "recent source timestamps" in reason
        assert "years" not in reason
    _, out, _ = run_cli(["describe", "liquidity", "reference", "calendars", "list"])
    assert "historical calendar coverage" in parse(out)["read_guide"]["reason"]


def test_shared_group_endpoint_still_serves_active_balance_inquiry(setup, run_cli):
    row = {
        "id": "SYN-G",
        "userGroupCode": "SYN-GROUP",
        "currentBalance": "10.00",
        "memberList": [],
    }
    setup.state.business_handler = lambda body, index: {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": 1,
            "result": {"success": True, "data": [row], "count": 1},
        },
    }
    code, out, err = run_cli(["liquidity", "cash", "group-balances", "list", "--live"])
    assert code == 0, (out, err)
    assert parse(out)["data"][0]["id"] == "SYN-G"
    assert len(setup.state.business_requests) == 1
    assert not setup.cache_path.exists()


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
