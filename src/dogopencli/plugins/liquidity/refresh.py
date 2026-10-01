"""Liquidity refresh flows: explicit list and per-object detail acquisition.

Only these root refresh commands publish local captures. List acquisition
must be complete and validated before anything is published; incomplete or
failed acquisition preserves the previous valid cache (ADR 0003 practice).
Retention eviction, when it occurs, is deliberate: it warns on stderr,
keeps stdout parseable and publishes records, eviction and coverage in one
transaction (ADR 0017). Detail refresh is independent and object-scoped
(ADR 0016).
"""

import argparse
import sys
from typing import Any

from ... import config as config_mod
from ...cache import Cache
from ...errors import EXIT_OK, INCOMPLETE_RESULT, CliError
from ...inquiry import inquiry_session
from . import details as detail_store
from . import store as capture_store
from .collect import collect_liquidity_scope
from .common import emit, identity_values, load_config, now, provided, scope_flags
from .leaves import DetailLeaf, detail_leaf, list_leaf
from .query import fetch_detail


def run_refresh_list(args: argparse.Namespace) -> int:
    leaf = list_leaf(args.command_path[2:])
    resolved = leaf.resolve(provided(args, scope_flags(leaf)))
    variant = resolved.spec
    capability = leaf.capability(variant)
    config = load_config()
    store = Cache(config.cache_path)
    with store.refresh_lock():
        with inquiry_session(
            config_file=config_mod.config_path(), startup_url=capability.page_url
        ) as session:
            result = collect_liquidity_scope(
                capability,
                session.transport(capability),
                resolved.request_scope,
                progress=lambda done, total: print(
                    f"refresh: collected page {done}/{total}", file=sys.stderr
                ),
            )
        if not result.complete:
            raise CliError(
                INCOMPLETE_RESULT,
                f"{variant.leaf} acquisition is incomplete; the previous"
                " cache is retained",
            )
        fetched_at = now().isoformat()
        loaded_at = now().isoformat()
        plan = capture_store.plan_capture_publish(
            store,
            variant,
            resolved.scope_key,
            resolved.window,
            result.records,
            result.total_count,
            fetched_at,
            loaded_at,
        )
        capture_store.commit_plan(store, variant.name, plan, loaded_at)
    row_count = len(plan.capture_records)
    print(
        f"refresh: published {row_count} rows to {plan.capture_meta.namespace}",
        file=sys.stderr,
    )
    eviction: dict[str, Any] | None = None
    if plan.eviction is not None:
        eviction = {
            "dropped": plan.eviction.dropped,
            "retained": plan.eviction.retained,
            "retained_from": plan.eviction.retained_from,
            "tie_break": plan.eviction.tie_break,
            "evicted": list(plan.eviction.evicted),
        }
        print(
            "refresh: retention evicted"
            f" {plan.eviction.dropped} oldest records;"
            f" retained {plan.eviction.retained} from"
            f" {plan.eviction.retained_from}",
            file=sys.stderr,
        )
    meta = {
        "source": "cache",
        "backend": "cdp",
        "kind": variant.kind,
        "simulated": False,
        "capability": variant.name,
        "scope": resolved.scope_key,
        "requested_window": (
            list(resolved.window) if resolved.window[0] is not None else None
        ),
        "snapshot_id": plan.capture_meta.snapshot_id,
        "fetched_at": fetched_at,
        "loaded_at": loaded_at,
        "stale": False,
        "complete": True,
        "dataset_complete": None,
        "reported_total": result.total_count,
        "matched_total": row_count,
        "returned_count": row_count,
        "has_more": False,
        "retention": eviction,
    }
    emit(
        {
            "namespace": plan.capture_meta.namespace,
            "published": True,
            "row_count": row_count,
        },
        meta,
    )
    return EXIT_OK


def run_refresh_detail(args: argparse.Namespace) -> int:
    # refresh liquidity <resource...> detail <action>
    path = args.command_path[2:]
    leaf: DetailLeaf = detail_leaf((*path[:-2], path[-1]))
    detail = leaf.spec
    values = identity_values(args, leaf)
    config = load_config()
    store = Cache(config.cache_path)
    with store.refresh_lock():
        with inquiry_session(
            config_file=config_mod.config_path(), startup_url=leaf.capability.page_url
        ) as session:
            payload = fetch_detail(session.transport(leaf.capability), leaf, values)
        fetched_at = now().isoformat()
        snapshot = detail_store.upsert_detail(
            store,
            detail.name,
            detail_store.detail_key(values),
            payload,
            fetched_at,
            now().isoformat(),
        )
    print(
        f"refresh: published detail to {snapshot.namespace}",
        file=sys.stderr,
    )
    meta = {
        "source": "cache",
        "backend": "cdp",
        "kind": detail.kind,
        "simulated": False,
        "capability": detail.name,
        "identity": dict(values),
        "snapshot_id": snapshot.snapshot_id,
        "fetched_at": snapshot.fetched_at,
        "loaded_at": snapshot.loaded_at,
        "stale": False,
        "complete": True,
        "dataset_complete": None,
        "matched_total": 1,
        "returned_count": 1,
        "has_more": False,
    }
    emit(
        {
            "namespace": snapshot.namespace,
            "published": True,
            "row_count": 1,
        },
        meta,
    )
    return EXIT_OK


__all__ = ["run_refresh_list", "run_refresh_detail"]
