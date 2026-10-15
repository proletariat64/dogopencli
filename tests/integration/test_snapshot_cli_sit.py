"""Issue #80 acceptance through the public CLI and synthetic SQLite caches."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.jsonutil import canonical


@pytest.fixture
def snapshot_setup(tmp_path, monkeypatch):
    path = tmp_path / "cache.sqlite3"
    config = tmp_path / "config.toml"
    config.write_text(f'[cache]\npath = "{path}"\nttl_hours = 72\n')
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    monkeypatch.delenv("DOGOPENCLI_CONFIG_DIR", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("snapshot must not initialize browser/auth/transport")

    from dogopencli.browser import cdp, environment

    monkeypatch.setattr(cdp, "make_transport", forbidden)
    monkeypatch.setattr(environment, "resolve_environment", forbidden)
    return path, config


def publish(
    path, capability, scope="scope", *, count=2, complete=True, age=0, source="cdp"
):
    acquired = datetime.now(timezone.utc) - timedelta(hours=age)
    timestamp = acquired.isoformat()
    name = "temporary-query:" + capability.removesuffix(".list")
    meta = SnapshotMeta(
        namespace=name,
        capability=capability,
        scope=canonical(
            {"query": {"scope": scope}, "variant": source, "selection": None}
        ),
        source_kind=source,
        snapshot_id="PRIVATE-SNAPSHOT-ID",
        dataset_id=None,
        simulated=False,
        backend_complete=complete,
        dataset_complete=True,
        fetched_at=timestamp,
        loaded_at=timestamp,
        source_observed_from=None,
        source_observed_to=None,
        row_count=count,
    )
    # Snapshot counts storage records; it must not parse the business bodies.
    Cache(path).publish(
        meta,
        [(i, "PRIVATE-BUSINESS-ROW") for i in range(1, count + 1)],
    )
    return name, timestamp


def leaves(node):
    if "availability" in node:
        yield node
    for child in node.get("children", []):
        yield from leaves(child)


def report(run_cli, *path):
    code, out, err = run_cli(["snapshot", *path, "--format", "json"])
    return code, json.loads(out), err


def test_full_tree_missing_cache_is_success_and_never_creates_files(
    run_cli, snapshot_setup
):
    cache, config = snapshot_setup
    before = {p.name for p in cache.parent.iterdir()}
    code, result, err = report(run_cli)
    assert code == 0, err
    assert result["snapshot_version"] == 2
    assert result["application_version"]
    assert datetime.fromisoformat(result["generated_at"].replace("Z", "+00:00"))
    assert result["inspection_complete"] is True
    items = list(leaves(result["tree"]))
    by_path = {leaf["command"]: leaf for leaf in items}
    assert "dogopencli snapshot" in by_path
    assert "dogopencli help" in by_path
    assert "dogopencli login" in by_path
    assert "dogopencli payment channel list" in by_path
    assert "dogopencli liquidity cash balances list" in by_path
    unsupported = [leaf for leaf in items if leaf["availability"] == "unsupported"]
    # 33 deferred, four gated R06 leaves, plus 13 retired list/refresh pairs.
    assert len(unsupported) == 63
    bank_blacklist = by_path["dogopencli liquidity reference blacklist bank list"]
    assert bank_blacklist["availability"] == "supported"
    assert (
        by_path["dogopencli liquidity investment interest-rates get"]["availability"]
        == "supported"
    )
    demands = by_path["dogopencli liquidity operations demands list"]
    assert demands["availability"] == "supported"
    quotes = by_path["dogopencli liquidity investment quotes list"]
    assert quotes["availability"] == "supported"
    assert quotes["cache"]["status"] == "missing"
    assert (
        by_path["dogopencli liquidity investment quotes get"]["availability"]
        == "supported"
    )
    credit_usage = by_path["dogopencli liquidity cash credit-usage list"]
    assert credit_usage["availability"] == "supported"
    assert credit_usage["cache"]["status"] == "missing"
    pool_balances = by_path["dogopencli liquidity cash pool-balances list"]
    assert pool_balances["availability"] == "supported"
    assert pool_balances["cache"]["status"] == "missing"
    assert "dogopencli liquidity reference areas list" not in by_path
    swaps_list = by_path["dogopencli liquidity operations swaps list"]
    assert swaps_list["availability"] == "supported"
    assert swaps_list["cache"]["status"] == "missing"
    strategy_list = by_path["dogopencli liquidity investment strategy-results list"]
    assert strategy_list["availability"] == "supported"
    assert strategy_list["cache"]["status"] == "missing"
    benchmark_list = by_path["dogopencli liquidity investment benchmark-values list"]
    assert benchmark_list["availability"] == "supported"
    assert benchmark_list["cache"]["status"] == "missing"
    assert (
        by_path["dogopencli liquidity operations swaps get"]["availability"]
        == "unsupported"
    )
    assert all(leaf["availability_reason"] for leaf in unsupported)
    assert all(leaf["cache"]["status"] == "not_applicable" for leaf in unsupported)
    assert by_path["dogopencli payment channel list"]["rows"] is None
    assert by_path["dogopencli payment channel list"]["cache"]["status"] == "missing"
    assert not cache.exists()
    assert {p.name for p in cache.parent.iterdir()} == before
    assert config.exists()


@pytest.mark.parametrize("path", [("payment",), ("liquidity", "cash")])
def test_subtree_has_only_selected_paths(run_cli, snapshot_setup, path):
    code, result, err = report(run_cli, *path)
    assert code == 0, err
    selected = "dogopencli " + " ".join(path)
    assert result["tree"]["command"] == selected
    assert all(
        leaf["command"].startswith(selected + " ") for leaf in leaves(result["tree"])
    )
    assert "options" not in canonical(result)


@pytest.mark.parametrize("args", [("not-a-command",), ("--format", "yaml")])
def test_unknown_path_or_format_is_argument_error(run_cli, snapshot_setup, args):
    assert run_cli(["snapshot", *args])[0] == 2


def test_snapshot_help_ignores_invalid_config(run_cli, snapshot_setup):
    _, config = snapshot_setup
    config.write_text("invalid = [")
    for argv in (["help", "snapshot"], ["snapshot", "--help"]):
        code, out, err = run_cli(argv)
        assert code == 0, err
        assert "snapshot" in out


@pytest.mark.parametrize(
    "count,complete,age", [(0, True, 0), (2, True, 0), (3, True, 96), (4, False, 0)]
)
def test_empty_complete_stale_and_partial_storage(
    run_cli, snapshot_setup, count, complete, age
):
    path, _ = snapshot_setup
    _, timestamp = publish(
        path,
        "payment.cost.list",
        "FUND_OUT_CHANNEL_TRANS_FEE",
        count=count,
        complete=complete,
        age=age,
    )
    before = path.read_bytes()
    code, result, err = report(run_cli, "payment", "cost", "list")
    assert code == 0, err
    leaf = result["tree"]
    assert leaf["availability"] == "supported"
    assert leaf["availability_reason"] is None
    assert leaf["rows"] == count
    assert leaf["updated"] == timestamp
    assert leaf["cache"]["complete"] is complete
    assert leaf["cache"]["freshness"] == ("stale" if age > 72 else "fresh")
    assert path.read_bytes() == before
    assert "PRIVATE-" not in canonical(result) + err


def test_latest_slot_replaces_scope_and_quality(run_cli, snapshot_setup):
    path, _ = snapshot_setup
    publish(
        path,
        "payment.cost.list",
        "PRIVATE-ACCOUNT-OLDER",
        count=2,
        complete=False,
        age=96,
    )
    _, newer = publish(path, "payment.cost.list", "PRIVATE-ACCOUNT-NEWER", count=3)
    code, result, err = report(run_cli, "payment", "cost", "list")
    assert code == 0, err
    leaf = result["tree"]
    assert leaf["rows"] == 3
    assert leaf["updated"] == newer
    assert leaf["cache"]["status"] == "present"
    assert len(leaf["cache"]["slots"]) == 1
    assert leaf["cache"]["complete"] is True
    assert "PRIVATE-" not in canonical(result) + err


def test_refresh_refers_to_inquiry_cache_and_controls_have_no_cache(
    run_cli, snapshot_setup
):
    path, _ = snapshot_setup
    publish(path, "payment.cost.list", "FUND_OUT_CHANNEL_TRANS_FEE", count=3)
    code, query, err = report(run_cli, "payment", "cost", "list")
    assert code == 0, err
    code, refresh, err = report(run_cli, "refresh", "payment", "cost")
    assert code == 0, err
    assert refresh["tree"]["rows"] == query["tree"]["rows"]
    assert refresh["tree"]["cache"] == query["tree"]["cache"]
    for command in ("help", "login", "snapshot"):
        code, control, err = report(run_cli, command)
        assert code == 0, err
        assert control["tree"]["cache"]["status"] == "not_applicable"


@pytest.mark.parametrize("failure", ["config", "database"])
def test_inspection_errors_keep_json_tree_and_exit_one(
    run_cli, snapshot_setup, failure
):
    path, config = snapshot_setup
    if failure == "config":
        config.write_text('invalid = ["PRIVATE-CONFIG-SECRET"')
    else:
        path.write_bytes(b"PRIVATE-DATABASE-SECRET")
    code, result, err = report(run_cli, "payment", "cost", "list")
    assert code == 1
    assert result["inspection_complete"] is False
    assert result["inspection_errors"]
    assert result["tree"]["command"] == "dogopencli payment cost list"
    assert result["tree"]["cache"]["status"] == "read_error"
    assert "PRIVATE-" not in canonical(result) + err


def test_unknown_acquisition_time_preserves_known_completeness(run_cli, snapshot_setup):
    path, _ = snapshot_setup
    name, _ = publish(path, "payment.cost.list", "FUND_OUT_CHANNEL_TRANS_FEE")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE snapshots SET fetched_at = '' WHERE namespace = ?", (name,)
        )
    code, result, err = report(run_cli, "payment", "cost", "list")
    assert code == 0, err
    assert result["tree"]["updated"] is None
    assert result["tree"]["cache"]["complete"] is True
    assert result["tree"]["cache"]["freshness"] is None


def test_human_formats_use_same_counts_status_and_time(run_cli, snapshot_setup):
    path, _ = snapshot_setup
    _, timestamp = publish(
        path, "payment.cost.list", "FUND_OUT_CHANNEL_TRANS_FEE", count=7
    )
    for format in ("text", "table"):
        code, out, err = run_cli(
            ["snapshot", "payment", "cost", "list", "--format", format]
        )
        assert code == 0, err
        assert "supported" in out
        assert "dogopencli payment cost list" in out
        assert "complete" in out and "fresh" in out
        assert "7" in out
        assert timestamp in out
        assert "PRIVATE-" not in out + err


def test_snapshot_source_preserves_dataset_and_source_quality(run_cli, snapshot_setup):
    path, _ = snapshot_setup
    _, acquired = publish(
        path,
        "payment.channel.list",
        "EXTERNAL",
        count=3,
        complete=False,
        age=96,
        source="snapshot",
    )
    code, result, err = report(run_cli, "payment", "channel", "list")
    assert code == 0, err
    leaf = result["tree"]
    assert leaf["updated"] == acquired
    capture = leaf["cache"]["slots"][0]
    assert capture["variant"] == "snapshot"
    assert capture["source_complete"] is False
    assert capture["dataset_complete"] is True
    assert capture["complete"] is False
    assert capture["freshness"] == "stale"


def test_native_get_has_no_cache_inventory(run_cli, snapshot_setup):
    code, result, err = report(run_cli, "liquidity", "investment", "quotes", "get")
    assert code == 0, err
    assert result["tree"]["cache"]["status"] == "not_applicable"


def test_retired_baselines_disappear_without_affecting_capabilities_or_sla(
    run_cli, snapshot_setup
):
    code, result, err = report(run_cli, "liquidity", "network")
    assert code == 0, err
    commands = {leaf["command"] for leaf in leaves(result["tree"])}
    assert not any("product-baselines" in command for command in commands)
    assert not any("bank-baselines" in command for command in commands)
    assert "dogopencli liquidity network account-capabilities list" in commands
    code, out, err = run_cli(["help", "liquidity", "network"])
    assert code == 0, err
    assert "product-baselines" not in out
    assert "bank-baselines" not in out
    for action in ("list", "get"):
        code, _, _ = run_cli(["liquidity", "network", "product-baselines", action])
        assert code == 2  # Retired paths are unknown commands, not deferred leaves.
    code, out, err = run_cli(["describe", "payment", "sla", "baselines", "list"])
    assert code == 0, err
    assert json.loads(out)["data_schema"]


@pytest.mark.parametrize(
    "prefix, action",
    [
        ([], ["list"]),
        ([], ["get", "--account", "EXAMPLE"]),
        ([], ["prune"]),
        (["refresh"], []),
        (["help"], ["list"]),
        (["describe"], ["get"]),
        (["snapshot"], ["list"]),
    ],
)
def test_retired_bank_baselines_give_account_guidance_without_network(
    run_cli, snapshot_setup, prefix, action
):
    args = [*prefix, "liquidity", "network", "bank-baselines", *action]
    code, out, err = run_cli(args)
    assert code == 2
    assert "liquidity cash accounts list" in out + err


def test_accounts_describe_exposes_complementary_fields_and_baseline_ownership(
    run_cli, snapshot_setup
):
    code, out, err = run_cli(["describe", "liquidity", "cash", "accounts", "list"])
    assert code == 0, err
    schema = json.loads(out)["data_schema"]
    assert schema["properties"]["accountType"]["x-source"] == "baseline"
    assert schema["properties"]["status"]["x-source"] == "baseline"
    assert "timeZone" in schema["properties"]
    assert "detail_state" in schema["properties"]
    assert schema["additionalProperties"] is True
