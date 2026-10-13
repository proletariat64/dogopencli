from dogopencli.cache import Cache
from dogopencli.result_policy import AcquisitionEvidence
from dogopencli.temporary_query import prune_slot, publish_slot, read_slot


def test_single_slot_replacement_and_empty_preservation(tmp_path):
    store = Cache(tmp_path / "cache.sqlite")
    evidence = AcquisitionEvidence(
        scope_complete=True, dataset_complete=True, collected_total=1
    )
    first = publish_slot(
        store,
        "payment.channel",
        [{"id": "A"}],
        capability="channel",
        scope={"entity": "A"},
        evidence=evidence,
        fetched_at="2026-01-01T00:00:00+00:00",
    )
    assert (
        publish_slot(
            store,
            "payment.channel",
            [],
            capability="channel",
            scope={},
            evidence=evidence,
            fetched_at="2026-01-02T00:00:00+00:00",
        )
        is None
    )
    assert read_slot(store, "payment.channel") == (first, [{"id": "A"}])
    publish_slot(
        store,
        "payment.channel",
        [{"id": "B"}],
        capability="channel",
        scope={"entity": "B"},
        evidence=evidence,
        fetched_at="2026-01-03T00:00:00+00:00",
    )
    assert read_slot(store, "payment.channel")[1] == [{"id": "B"}]
    assert prune_slot(store, "payment.channel")
    assert not prune_slot(store, "payment.channel")


def test_missing_read_and_prune_do_not_initialize_storage(tmp_path):
    path = tmp_path / "absent" / "cache.sqlite"
    store = Cache(path)
    assert read_slot(store, "fx.trade") == (None, [])
    assert not prune_slot(store, "fx.trade")
    assert not path.parent.exists()


def test_enabled_list_catalog_has_uniform_display_and_prune():
    from dogopencli.catalog import NODES

    for path, node in NODES.items():
        if node.handler in (None, "cmd_liquidity_unsupported") or path[0] in (
            "refresh",
            "describe",
            "auth",
        ):
            continue
        if path[-1] != "list" and path != ("fx", "trade"):
            continue
        options = {option.name: option for option in node.options}
        assert "all" not in options
        assert {"limit", "offset", "format"} <= options.keys()
        assert options["format"].default == "json"
        sibling = (*path[:-1], "prune") if path[-1] == "list" else (*path, "prune")
        assert NODES[sibling].handler == "cmd_prune"


def test_public_help_inventory_declares_uniform_list_operations(capsys):
    import json

    from dogopencli.catalog import NODES
    from dogopencli.cli import main
    from dogopencli.plugins import cache_bindings

    bindings = cache_bindings()
    for path, node in NODES.items():
        if node.handler in (None, "cmd_liquidity_unsupported") or path[0] in (
            "refresh",
            "describe",
            "auth",
        ):
            continue
        if path[-1] != "list" and path != ("fx", "trade"):
            continue
        assert main(["help", *path]) == 0
        document = json.loads(capsys.readouterr().out)
        options = {option["name"]: option for option in document["options"]}
        assert "all" not in options
        assert options["format"]["default"] == "json"
        assert options["limit"]["default"] == 100
        assert options["offset"]["default"] == 0
        assert "live" in options
        capability = bindings[path].name
        assert any(
            candidate[:1] == ("refresh",)
            and other.handler
            and (
                other.cache_capability == capability
                or getattr(bindings.get(candidate), "name", None) == capability
            )
            for candidate, other in NODES.items()
        ), path


def test_format_switch_discards_legacy_once_and_preserves_external_inputs(tmp_path):
    import sqlite3

    store = Cache(tmp_path / "cache.sqlite")
    external = tmp_path / "duckdog.db"
    external.write_bytes(b"external source stays private")
    evidence = AcquisitionEvidence(
        scope_complete=True, dataset_complete=True, collected_total=1
    )
    publish_slot(
        store,
        "payment.channel",
        [{"id": "legacy"}],
        capability="channel",
        scope={},
        evidence=evidence,
        fetched_at="2026-01-01T00:00:00+00:00",
    )
    with sqlite3.connect(tmp_path / "cache.sqlite") as connection:
        connection.execute("DROP TABLE cache_format")
        connection.execute("UPDATE snapshots SET namespace = 'legacy:list:cdp'")
        connection.execute("UPDATE records SET namespace = 'legacy:list:cdp'")
    assert read_slot(store, "payment.channel") == (None, [])
    publish_slot(
        store,
        "payment.channel",
        [{"id": "new"}],
        capability="channel",
        scope={},
        evidence=evidence,
        fetched_at="2026-01-02T00:00:00+00:00",
    )
    assert read_slot(store, "payment.channel")[1] == [{"id": "new"}]
    assert read_slot(store, "payment.channel")[1] == [{"id": "new"}]
    assert external.read_bytes() == b"external source stays private"
