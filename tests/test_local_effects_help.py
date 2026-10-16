"""Public help distinguishes local operational writes from production mutation."""

import json

import pytest


@pytest.mark.parametrize(
    "path",
    [
        ("payment", "channel", "list"),
        ("payment", "sla", "baselines", "get"),
        ("collection", "cost", "list"),
        ("fx", "trade"),
        ("liquidity", "cash", "accounts", "list"),
    ],
)
def test_business_help_discloses_operational_writes(run_cli, path):
    code, out, error = run_cli(["help", *path])
    assert code == 0 and error == ""
    document = json.loads(out)
    assert document["effects"]["mutates"] is True
    assert all(
        variant["effects"]["mutates"] is True
        for variant in document.get("effects_variants", [])
    )
    assert any("observation" in text.lower() for text in document["constraints"])
    assert any("production" in text.lower() for text in document["constraints"])


@pytest.mark.parametrize(
    "path,network,browser",
    [
        (("domain", "enable"), False, False),
        (("domain", "disable"), False, False),
        (("auth", "check"), True, True),
        (("gui",), True, False),
    ],
)
def test_control_help_discloses_local_writes_without_creating_state(
    run_cli, monkeypatch, tmp_path, path, network, browser
):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "config.toml"))
    code, out, error = run_cli(["help", *path])
    assert code == 0 and error == ""
    document = json.loads(out)
    assert document["effects"] == {
        "mutates": True,
        "network": network,
        "browser_required": browser,
        "destructive": False,
    }
    assert any("local" in text.lower() for text in document["constraints"])
    assert any("production" in text.lower() for text in document["constraints"])
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("domain", "list"),
        ("domain", "show"),
        ("domain", "leaves"),
        ("describe", "payment", "channel", "list"),
    ],
)
def test_inventory_and_description_help_remain_nonmutating(run_cli, path):
    code, out, error = run_cli(["help", *path])
    assert code == 0 and error == ""
    assert json.loads(out)["effects"] == {
        "mutates": False,
        "network": False,
        "browser_required": False,
        "destructive": False,
    }


def test_disabled_leaf_help_has_no_execution_effects(run_cli):
    from dogopencli.plugins import domain_plugins

    for domain in domain_plugins():
        for leaf in domain.leaves:
            if leaf.enabled:
                continue
            for node in (*leaf.commands, *leaf.refresh_commands):
                code, out, error = run_cli(["help", *node.path])
                assert code == 0 and error == ""
                document = json.loads(out)
                assert document["effects"] == {
                    "mutates": False,
                    "network": False,
                    "browser_required": False,
                    "destructive": False,
                }
                assert document.get("effects_variants", []) == []
