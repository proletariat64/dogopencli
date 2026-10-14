"""Publish one full, validated, nonempty acquisition per Liquidity leaf."""

import argparse

from ... import config as config_mod
from ...cache import Cache
from ...errors import EXIT_OK, CliError
from ...inquiry import inquiry_session
from ...result_policy import check_complete, evidence_for, prepare_result
from ...temporary_query import publish_slot, slot_namespace
from .balance_view import latest_statement_rows, update_notice
from .cash_balances import selection
from .collect import acquire_liquidity_list
from .common import emit, load_config, now
from .leaves import list_leaf
from .query import resolve_online_scope, slot_leaf


def run_refresh_list(args: argparse.Namespace) -> int:
    leaf = list_leaf(args.command_path[2:])
    resolved = resolve_online_scope(leaf, args)
    variant = resolved.spec
    capability = leaf.acquisition_capability(
        variant, getattr(args, "page_size", None), online=True
    )
    store = Cache(load_config().cache_path)
    with store.refresh_lock():
        with inquiry_session(
            config_file=config_mod.config_path(), startup_url=capability.page_url
        ) as session:
            result = acquire_liquidity_list(session, capability, resolved.request_scope)
        evidence = evidence_for(result)
        changed_groups = 0
        if variant.projection == "balances":
            _, changed_groups = latest_statement_rows(result.records)
        try:
            check_complete(
                evidence,
                require_complete=getattr(args, "require_complete", False),
                mode="refresh",
            )
        except CliError as error:
            if leaf.path == ("cash", "accounts"):
                from .unified_accounts import account_meta

                error.meta = {**(error.meta or {}), **account_meta(evidence)}
            raise
        fetched_at = now().isoformat()
        frozen = selection(evidence)
        snapshot = publish_slot(
            store,
            slot_leaf(leaf),
            result.records,
            capability=variant.name,
            scope=resolved.request_values,
            evidence=evidence,
            fetched_at=fetched_at,
            variant=variant.endpoint,
            selection=frozen,
        )
    published = snapshot is not None
    meta = prepare_result(
        {
            "source": "live",
            "backend": "cdp",
            "kind": variant.kind,
            "capability": variant.name,
            "variant": variant.endpoint,
            "query": resolved.request_values,
            "scope": resolved.request_values,
            "fetched_at": fetched_at,
            "snapshot_id": snapshot.snapshot_id if snapshot else None,
            **evidence.meta(),
            "published": published,
            "publication_reason": "replaced"
            if published
            else "empty_result_preserved_prior_cache",
            "matched_total": len(result.records),
            "returned_count": len(result.records),
            "has_more": False,
        },
        mode="refresh",
    )
    if leaf.path == ("cash", "accounts"):
        from .unified_accounts import account_meta

        meta.update(account_meta(evidence))
    notice = update_notice(changed_groups)
    if notice:
        meta["warnings"] = [*meta.get("warnings", []), notice]
    if frozen:
        meta["selection"] = frozen
    emit(
        {
            "namespace": slot_namespace(slot_leaf(leaf)),
            "published": published,
            "row_count": len(result.records),
            "publication_reason": meta["publication_reason"],
        },
        meta,
    )
    return EXIT_OK
