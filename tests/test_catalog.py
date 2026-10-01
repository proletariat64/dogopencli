"""The static declarations bind help, navigation and execution together."""

from dataclasses import replace

import pytest

from dogopencli import cli
from dogopencli.catalog import NODES, build_catalog
from dogopencli.helpspec import BizNode
from dogopencli.plugins import command_nodes


def test_every_executable_is_discoverable_and_dispatches(run_cli, monkeypatch):
    leaves = [node for node in NODES.values() if node.handler]
    assert all(
        NODES[node.path].handler == node.handler
        and NODES[node.path].options == node.options
        for node in command_nodes()
    )
    for node in leaves:
        handler = node.handler
        assert handler is not None
        assert callable(getattr(cli, handler))
        assert NODES[node.path[:-1]].children.count((node.path[-1], node.summary)) == 1
        calls = []
        monkeypatch.setattr(
            cli, handler, lambda args, calls=calls: calls.append(args) or 0
        )
        argv = list(node.path)
        for option in node.options:
            if option.required:
                # Choice-restricted options need a declared value.
                value = option.choices[0] if option.choices else "synthetic"
                argv.extend((option.flag, value))
        assert run_cli(argv) == (0, "", "")
        assert len(calls) == 1


def test_new_leaf_only_needs_its_declaration():
    declarations = [replace(node, children=()) for node in NODES.values()]
    added = BizNode(("payment", "cost", "inspect"), "Inspect cost.", handler="inspect")
    catalog = build_catalog((*declarations, added))
    assert catalog[added.path] == added
    assert ("inspect", "Inspect cost.") in catalog[added.path[:-1]].children


@pytest.mark.parametrize(
    "extra, message",
    [
        (BizNode(("payment",), "Duplicate"), "duplicate"),
        (BizNode(("missing", "leaf"), "Orphan", handler="run"), "missing parent"),
        (BizNode(("empty",), "No handler or children"), "either group or executable"),
        (
            BizNode(("bad",), "Bad handler", handler=True),  # type: ignore[arg-type]
            "invalid handler",
        ),
    ],
)
def test_reject_inconsistent_declarations(extra, message):
    declarations = [replace(node, children=()) for node in NODES.values()]
    with pytest.raises(ValueError, match=message):
        build_catalog((*declarations, extra))


def test_executable_parent_keeps_handler_and_children():
    """An executable node may parent children (bare refresh collection va)."""
    parent = BizNode(("payment", "cost", "inspect"), "Inspect cost.", handler="run")
    child = BizNode(
        ("payment", "cost", "inspect", "child"), "Inspect child.", handler="run_child"
    )
    declarations = [replace(node, children=()) for node in NODES.values()]
    catalog = build_catalog((*declarations, parent, child))
    assert catalog[parent.path].handler == "run"
    assert ("child", "Inspect child.") in catalog[parent.path].children


def test_plugin_registration_supplies_query_refresh_and_navigation(monkeypatch):
    """Adding a collection inquiry needs no catalog-specific assembly code."""
    from dogopencli import plugins
    from dogopencli.plugins.collection.cost import COLLECTION_COST_CAPABILITY

    for name in (
        "_REGISTRY",
        "_COMMANDS",
        "_REFRESH_COMMANDS",
        "_GROUPS",
        "_DESCRIPTIONS",
    ):
        monkeypatch.setattr(plugins, name, dict(getattr(plugins, name)))
    capability = replace(COLLECTION_COST_CAPABILITY, name="collection.fixture.list")
    group = BizNode(("collection", "fixture"), "Fixture inquiries.")
    query = BizNode((*group.path, "list"), "List fixture.", handler="fixture_list")
    refresh = BizNode(
        ("refresh", "collection", "fixture"),
        "Refresh fixture.",
        handler="fixture_refresh",
    )
    existing_refresh = plugins.refresh_nodes()
    plugins.register(
        capability,
        commands=(query,),
        refresh_commands=(refresh,),
        groups=(group,),
        description=lambda node: {"name": node.path[-1]},
    )
    declarations = [replace(node, children=()) for node in NODES.values()]
    added = [
        node
        for node in (
            *plugins.group_nodes(),
            *plugins.command_nodes(),
            *plugins.refresh_nodes(),
        )
        if node.path not in NODES
    ]
    catalog = build_catalog((*declarations, *added))
    assert plugins.refresh_nodes() == (*existing_refresh, refresh)
    assert catalog[query.path].handler == "fixture_list"
    assert catalog[refresh.path].handler == "fixture_refresh"
    assert catalog[group.path].children == (("list", "List fixture."),)
    assert plugins.get_description(query) == {"name": "list"}
    assert plugins.get_capability(capability.name) is capability
