"""Domain components compose through one registration contract."""

from dataclasses import replace

import pytest

from dogopencli import plugins
from dogopencli.catalog import build_domain_catalog


def test_each_domain_can_be_removed_without_residual_catalog_paths():
    domains = plugins.domain_plugins()
    assert [domain.id for domain in domains] == [
        "payment",
        "collection",
        "fx",
        "liquidity",
    ]
    assert domains[0].entry_point == domains[1].entry_point
    for removed in domains:
        remaining = tuple(domain for domain in domains if domain.id != removed.id)
        catalog = build_domain_catalog(remaining)
        assert not any(removed.id in path[:2] for path in catalog)
        assert all((domain.id,) in catalog for domain in remaining)


def test_every_refresh_has_explicit_operation_and_cache_ownership():
    for domain in plugins.domain_plugins():
        for leaf in domain.leaves:
            for node in leaf.refresh_commands:
                assert (node.path, "refresh") in leaf.operations
                if leaf.enabled and getattr(leaf.capability, "cache_enabled", True):
                    assert node.path in leaf.cache_paths


def test_sample_domain_supplies_execution_binding_without_core_changes(monkeypatch):
    from types import SimpleNamespace

    from dogopencli.helpspec import BizNode

    query = BizNode(("sample", "list"), "List sample.", handler="sample_list")

    def run(args):
        return 0

    sample = plugins.DomainComponent(
        id="sample",
        entry_point="https://example.test/shared",
        leaves=(
            plugins.leaf_registration(
                SimpleNamespace(name="sample.rows"), commands=(query,)
            ),
        ),
        groups=(BizNode(("sample",), "Sample domain."),),
        handlers={"sample_list": run},
    )
    monkeypatch.setattr(plugins, "_DOMAINS", (sample,))
    assert plugins.handler_for("sample_list") is run
    assert build_domain_catalog((sample,))[("sample", "list")].handler == "sample_list"


def test_invalid_domain_replacement_preserves_installed_registry():
    installed = plugins.domain_plugins()
    first_leaf = installed[0].leaves[0]
    before = plugins.get_capability(first_leaf.id)
    with pytest.raises(ValueError, match="duplicate domain"):
        plugins.register_domains((*installed, installed[0]))
    assert plugins.domain_plugins() == installed
    assert plugins.get_capability(first_leaf.id) is before


@pytest.mark.parametrize("defect", ["missing", "reserved", "group"])
def test_invalid_execution_bindings_leave_registry_unchanged(defect):
    from dogopencli.helpspec import BizNode

    installed = plugins.domain_plugins()
    original = installed[0]
    leaf = original.leaves[0]
    capability = plugins.get_capability(leaf.id)
    commands = plugins.command_nodes()
    if defect == "reserved":
        invalid = replace(original, handlers={"cmd_refresh_cost": lambda args: 0})
    elif defect == "group":
        invalid = replace(
            original,
            groups=(
                *original.groups,
                BizNode((original.id, "unbound"), "Unbound.", handler="missing"),
            ),
        )
    else:
        broken = replace(
            leaf,
            commands=(replace(leaf.commands[0], handler="missing_execution_handler"),),
        )
        invalid = replace(original, leaves=(broken, *original.leaves[1:]))
    replacement = (invalid, *installed[1:])
    with pytest.raises(ValueError, match="handler|executable"):
        plugins.register_domains(replacement)
    with pytest.raises(ValueError, match="handler|executable"):
        build_domain_catalog(replacement)
    assert plugins.domain_plugins() == installed
    assert plugins.get_capability(leaf.id) is capability
    assert plugins.command_nodes() == commands


@pytest.mark.parametrize("defect", ["empty", "children", "executable_group"])
def test_catalog_invariant_failure_does_not_publish_registry(defect):
    from dogopencli.helpspec import BizNode

    installed = plugins.domain_plugins()
    domain = installed[0]
    if defect == "empty":
        groups = (*domain.groups, BizNode((domain.id, "empty"), "Empty group."))
        invalid = replace(domain, groups=groups)
    elif defect == "children":
        groups = (
            replace(domain.groups[0], children=(("invented", "Invented child."),)),
            *domain.groups[1:],
        )
        invalid = replace(domain, groups=groups)
    else:
        groups = (
            *domain.groups,
            BizNode((domain.id, "run"), "Ungated execution.", handler="sample_run"),
        )
        invalid = replace(
            domain, groups=groups, handlers={"sample_run": lambda args: 0}
        )
    commands = plugins.command_nodes()
    with pytest.raises(ValueError):
        plugins.register_domains((invalid, *installed[1:]))
    assert plugins.domain_plugins() == installed
    assert plugins.command_nodes() == commands


@pytest.mark.parametrize("defect", ["ownership", "parent", "cache", "handler"])
def test_domain_contributions_are_validated_before_assembly(defect):
    from dogopencli.helpspec import BizNode

    original = plugins.domain_plugins()[0]
    leaf = original.leaves[0]
    if defect == "ownership":
        leaf = replace(
            leaf, commands=(replace(leaf.commands[0], path=("other", "list")),)
        )
    elif defect == "parent":
        leaf = replace(
            leaf,
            commands=(
                replace(leaf.commands[0], path=(original.id, "missing", "list")),
            ),
        )
    elif defect == "cache":
        leaf = replace(leaf, cache_paths=((original.id, "missing", "list"),))
    else:
        leaf = replace(
            leaf, commands=(BizNode((original.id, "list"), "Missing handler."),)
        )
    invalid = replace(
        original,
        leaves=(leaf,),
        refresh_order=(),
        groups=(BizNode((original.id,), "Domain."),),
    )
    with pytest.raises(ValueError):
        build_domain_catalog((invalid,))


def test_inquiry_operations_use_shared_list_get_vocabulary():
    from types import SimpleNamespace

    from dogopencli.helpspec import BizNode

    registration = plugins.leaf_registration(
        SimpleNamespace(name="sample.rows"),
        commands=(
            BizNode(("sample", "trade"), "Trade query.", handler="sample_trade"),
        ),
    )
    assert registration.operations == ((("sample", "trade"), "list"),)


def test_refresh_root_is_assembled_from_leaf_owned_groups():
    from types import SimpleNamespace

    from dogopencli.helpspec import BizNode

    domain = plugins.DomainComponent(
        id="sample",
        entry_point="https://example.test/",
        handlers={"sample_list": lambda args: 0, "sample_refresh": lambda args: 0},
        leaves=(
            plugins.leaf_registration(
                SimpleNamespace(name="sample.items", cache_enabled=False),
                groups=(
                    BizNode(("sample",), "Sample."),
                    BizNode(("refresh", "sample"), "Refresh sample."),
                ),
                commands=(BizNode(("sample", "list"), "List.", handler="sample_list"),),
                refresh_commands=(
                    BizNode(
                        ("refresh", "sample", "items"),
                        "Refresh items.",
                        handler="sample_refresh",
                    ),
                ),
            ),
        ),
    )
    catalog = build_domain_catalog((domain,))
    assert ("refresh", "sample", "items") in catalog
    assert catalog[("refresh",)].children == (("sample", "Refresh sample."),)
