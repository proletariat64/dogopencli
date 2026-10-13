"""Catalog-wide argument-contract conformance (Issue #127/#133, T01/T11).

Enumerates the actual installed catalog and asserts that text help, JSON
help, parser behavior, and refresh scope declarations agree on preferred
flags, legacy aliases, formats, effective defaults, modes, cardinality, and
constraints. The catalog size is observed, never frozen.
"""

import json

from dogopencli.catalog import NODES
from dogopencli.helpspec import HELP_VERSION

BUSINESS_DOMAINS = ("payment", "collection", "liquidity")
SHARED = (
    "limit",
    "offset",
    "all",
    "live",
    "fields",
    "format",
    "require_fresh",
    "require_complete",
)


def business_lists():
    return {
        path: node
        for path, node in NODES.items()
        if path and path[-1] == "list" and node.handler and path[0] in BUSINESS_DOMAINS
    }


def refreshes():
    return {
        path: node
        for path, node in NODES.items()
        if path and path[0] == "refresh" and node.handler
    }


def test_catalog_enumeration_observed_not_frozen():
    lists = business_lists()
    assert lists  # sanity: the catalog is populated
    per_domain = {domain: 0 for domain in BUSINESS_DOMAINS}
    for path in lists:
        per_domain[path[0]] += 1
    assert all(count > 0 for count in per_domain.values())


def test_every_list_option_carries_a_versioned_contract():
    for path, node in business_lists().items():
        for option in node.options:
            contract = option.argument_contract
            assert contract is not None, (path, option.name)
            assert contract["value_type"], (path, option.name)
            modes = contract["modes"]
            assert set(modes) == {"cache", "live", "refresh"}, (path, option.name)
            for mode, entry in modes.items():
                assert set(entry) >= {"available"}, (path, option.name, mode)
                if entry["available"]:
                    assert "role" in entry, (path, option.name, mode)


def test_shared_options_are_identical_across_lists():
    baseline: dict[str, tuple] = {}
    for path, node in business_lists().items():
        names = {option.name for option in node.options}
        for name in SHARED:
            if name == "format" and name not in names:
                continue  # describe/refresh variants use their own format
            if name not in names:
                continue
            option = next(o for o in node.options if o.name == name)
            shape = (
                option.flag,
                option.legacy_flags,
                option.kind,
                json.dumps(option.argument_contract, sort_keys=True),
            )
            if path == ("liquidity", "cash", "balances", "list") and name == "all":
                # #147 deliberately broadens only this leaf's unscoped ALL.
                # The public spelling/type stay shared; its selection role does not.
                assert shape[:3] == ("--all", (), "bool")
                assert option.argument_contract is not None
                assert option.argument_contract["modes"]["refresh"]["available"]
                continue
            if name in baseline:
                assert shape == baseline[name], (path, name)
            else:
                baseline[name] = shape
    assert set(baseline) == set(SHARED)


def test_deprecated_flags_match_legacy_aliases_and_help_json(run_cli):
    for path, node in business_lists().items():
        code, out, err = run_cli(["help", *path])
        assert code == 0 and err == ""
        doc = json.loads(out)
        assert doc["help_version"] == HELP_VERSION
        by_name = {entry["name"]: entry for entry in doc["options"]}
        for option in node.options:
            entry = by_name[option.name]
            assert entry["flags"] == [option.flag, *option.legacy_flags]
            contract = entry["argument_contract"]
            assert contract["version"] == 1
            assert contract.get("deprecated_flags", []) == list(option.legacy_flags)


def test_text_help_names_preferred_flags(run_cli):
    for path in business_lists():
        code, out, err = run_cli(["help", *path, "--format", "text"])
        assert code == 0 and err == ""
        for option in business_lists()[path].options:
            assert option.flag in out, (path, option.flag)


def test_refresh_and_list_scope_declarations_agree():
    """Refresh scope options mirror the list leaf's scope options (#127 T20)."""
    for path, node in business_lists().items():
        if path[0] != "liquidity":
            continue
        refresh_path = ("refresh", *path[:-1])
        refresh = refreshes().get(refresh_path)
        if refresh is None:
            continue
        list_contracts = {
            option.name: option.argument_contract
            for option in node.options
            if option.name not in SHARED
        }
        refresh_contracts = {
            option.name: option.argument_contract
            for option in refresh.options
            if option.name not in SHARED
        }
        # Refresh scope options must be a subset of the list's scope options
        # with identical contracts (local-only filters stay off refresh).
        for name, contract in refresh_contracts.items():
            assert name in list_contracts, (refresh_path, name)
            assert contract == list_contracts[name], (refresh_path, name)


def test_help_is_side_effect_free(run_cli, tmp_path, monkeypatch):
    """Help touches no config, cache, browser, or network (T11)."""
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "missing.toml"))
    code, out, err = run_cli(["help", "liquidity", "cash", "balances", "list"])
    assert code == 0
    assert list(tmp_path.iterdir()) == []
