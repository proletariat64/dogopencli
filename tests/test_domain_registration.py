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
