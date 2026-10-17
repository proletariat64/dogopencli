"""The approved action-first grammar replaces historical leaf commands."""

import json

import pytest


@pytest.fixture
def installed_contract(run_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(tmp_path))
    for identity in (
        "payment.sla.baselines",
        "collection.cost",
        "liquidity.reference.entities",
        "fx.trade",
    ):
        assert run_cli(["plugins", "install", "bundled:" + identity])[0] == 0


@pytest.mark.parametrize(
    "argv",
    [
        ["payment", "sla", "baselines", "list"],
        ["collection", "cost", "list"],
        ["liquidity", "reference", "entities", "list"],
        ["fx", "trade", "--live"],
        ["refresh", "payment", "sla"],
        ["prune", "fx", "trade"],
        ["describe", "liquidity", "reference", "entities", "list"],
        ["liquidity", "list", "reference", "entities"],
        ["payment", "list", "sla.baselines", "--format", "table"],
        ["payment", "describe", "sla.baselines", "--json"],
    ],
)
def test_superseded_paths_and_output_spellings_are_rejected(
    run_cli, installed_contract, argv
):
    code, output, _ = run_cli(argv)
    assert code in (1, 2)
    assert json.loads(output)["error"]["code"] in {"INVALID_ARGUMENT", "LEAF_NOT_FOUND"}


@pytest.mark.parametrize(
    "domain,leaf",
    [
        ("payment", "sla.baselines"),
        ("collection", "cost"),
        ("liquidity", "reference.entities"),
        ("fx", "trade"),
    ],
)
def test_same_dotted_leaf_name_drives_help_describe_and_offline_list(
    run_cli, installed_contract, domain, leaf
):
    code, output, _ = run_cli([domain, "list", leaf, "--help"])
    assert code == 0
    assert json.loads(output)["data"]["command"] == f"dogopencli {domain} list {leaf}"
    code, output, _ = run_cli([domain, "describe", leaf])
    assert code == 0
    document = json.loads(output)["data"]
    assert document["id"] == f"{domain}.{leaf}"
    assert document["name"] == leaf
    code, output, _ = run_cli([domain, "list", leaf])
    assert code == 1
    assert json.loads(output)["error"]["code"] == "CACHE_MISS"


def test_version_works_without_scanning_plugins(run_cli, tmp_path, monkeypatch):
    from dogopencli import __version__
    from dogopencli.leaves.registry import Registry

    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(tmp_path / "unused"))

    def unexpected_scan(*args, **kwargs):
        pytest.fail("version must not scan installed leaves")

    monkeypatch.setattr(Registry, "scan", unexpected_scan)
    code, output, _ = run_cli(["--version"])
    assert code == 0
    assert __version__ in output
    assert not (tmp_path / "unused").exists()
