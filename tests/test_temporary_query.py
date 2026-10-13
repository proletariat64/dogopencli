from dogopencli.cache import Cache
from dogopencli.result_policy import AcquisitionEvidence
from dogopencli.temporary_query import publish_slot, read_slot, prune_slot


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
