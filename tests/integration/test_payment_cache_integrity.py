"""Corrupted cache rows cannot become usable partial Payment results."""

from datetime import datetime, timezone

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.jsonutil import canonical
from dogopencli.temporary_query import publish_candidate
from dogopencli.temporary_query import query_namespace as namespace

CASES = (
    ("channel", "payment.channel.list", "EXTERNAL", ("payment", "channel", "list")),
    (
        "cost",
        "payment.cost.list",
        "FUND_OUT_CHANNEL_TRANS_FEE",
        ("payment", "cost", "list"),
    ),
    (
        "sla",
        "payment.sla.baselines.list",
        "baselines",
        ("payment", "sla", "baselines", "list"),
    ),
)


def records(kind, scope):
    if kind == "channel":
        return [
            {"seqid": i, "abilityId": i, "payoutType": scope, "configVersion": "v1"}
            for i in (1, 2)
        ]
    if kind == "cost":
        return [{"itemId": str(i), "itemType": scope} for i in (1, 2)]
    return [{"id": str(i)} for i in (1, 2)]


def publish(tmp_path, monkeypatch, kind, capability, scope, rows):
    cache_path = tmp_path / "cache.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[cache]\npath = "{cache_path}"\n[sources.payment_{kind}]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config_path))
    now = datetime.now(timezone.utc).isoformat()
    snapshot = SnapshotMeta(
        namespace=namespace(capability, scope, "cdp"),
        capability=capability,
        scope=scope,
        source_kind="cdp",
        snapshot_id="synthetic",
        dataset_id=None,
        simulated=False,
        backend_complete=False,
        dataset_complete=True,
        fetched_at=now,
        loaded_at=now,
        source_observed_from=None,
        source_observed_to=None,
        row_count=len(rows),
    )
    publish_candidate(
        Cache(cache_path),
        snapshot,
        [(i, canonical(row)) for i, row in enumerate(rows, 1)],
    )
    return cache_path
