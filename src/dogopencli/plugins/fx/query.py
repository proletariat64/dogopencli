"""Bounded live acquisition for the verified individual FX trade inquiry."""

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from ... import config as config_mod
from ...cache import Cache
from ...errors import AUTH_REQUIRED, CACHE_MISS, INVALID_RESPONSE, TIMEOUT, CliError
from ...inquiry import inquiry_session
from ...jsonutil import canonical
from ...result_policy import AcquisitionEvidence, check_complete
from ...temporary_query import (
    display_options,
    prune_slot,
    publish_slot,
    read_slot,
    slot_context,
    window_rows,
)
from ...transport import QueryRequest
from ...transport.cdp import FetchFailed
from .trade import ARRAY_FILTERS, FX_TRADE, argument_error, query_request

MAX_PAGES = 100
ACQUISITION_SECONDS = 120.0


def acquire(transport: Any, query: dict[str, Any]):
    deadline = time.monotonic() + ACQUISITION_SECONDS
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    total: int | None = None
    reasons = ["IDENTITY_UNPROVEN", "TOTAL_SEMANTICS_UNPROVEN"]
    pages = 0
    for page_no in range(MAX_PAGES):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            reasons.append("ACQUISITION_BUDGET_EXHAUSTED")
            break
        contract = FX_TRADE.contract
        request = QueryRequest(
            capability=FX_TRADE.name,
            method=contract.method,
            host=contract.host,
            path=contract.path,
            body={
                "queryRequest": query,
                "pageSize": contract.page_size,
                "pageNo": page_no,
            },
        )
        try:
            response = transport.execute(request, timeout=remaining)
        except FetchFailed as error:
            # A transport failure withholds the entire candidate.
            raise CliError(TIMEOUT, "FX trade fetch failed", retryable=True) from error
        if response.status in (401, 403):
            raise CliError(
                AUTH_REQUIRED,
                "FX authorization required; run dogopencli login --domain fx",
            )
        if response.status != 200:
            raise CliError(
                INVALID_RESPONSE, f"unexpected FX HTTP status {response.status}"
            )
        page = FX_TRADE.parse_page(response.body)
        if page.page_num != page_no or page.page_size != contract.page_size:
            raise CliError(INVALID_RESPONSE, "FX pagination echo mismatch")
        if total is None:
            total = page.total_count
        elif total != page.total_count:
            raise CliError(
                INVALID_RESPONSE, "FX reported total changed during acquisition"
            )
        pages += 1
        # Detect identical overlap without asserting a business identity.
        duplicate = False
        for row in page.records:
            key = canonical(row)
            if key in seen:
                duplicate = True
            seen.add(key)
        rows.extend(page.records)
        if len(rows) > total:
            raise CliError(INVALID_RESPONSE, "FX arrivals exceed reported total")
        if duplicate:
            reasons.append("UNEXPECTED_DUPLICATE_ROWS")
            break
        if len(rows) == total:
            break
        if len(page.records) < contract.page_size:
            reasons.append("COUNT_SHORTFALL")
            break
    else:
        reasons.append("PAGE_BUDGET_EXHAUSTED")
    if total is None:
        raise CliError(TIMEOUT, "FX acquisition budget exhausted before the first page")
    evidence = AcquisitionEvidence(
        scope_complete=False,
        dataset_complete=False,
        collected_total=len(rows),
        reported_total=total,
        arrivals=len(rows),
        total_semantics="unknown",
        reasons=tuple(dict.fromkeys(reasons)),
    )
    return rows, evidence, pages


def _emit(args: Any, rows: list[dict], meta: dict, fields: list[str] | None) -> int:
    from ...cli import _emit_window

    columns = tuple(dict.fromkeys(key for row in rows for key in row))
    return _emit_window(
        args, SimpleNamespace(table_columns=columns), rows, meta, fields
    )


def run_trade(args: Any) -> int:
    if getattr(args, "live", False):
        return _online(args, refresh=False)
    limit, offset, fields = display_options(args)
    # No verified native row mappings exist. Refuse unsupported local filters;
    # never infer fields from a similarly named transport query argument.
    explicit = [flag for flag, _ in ARRAY_FILTERS if getattr(args, flag, [])]
    explicit += [
        flag
        for flag in ("scene", "fulfilled", "transact_from", "transact_to")
        if getattr(args, flag, None) is not None
    ]
    if explicit:
        raise argument_error(
            "FX cached business filters have no verified row mapping; "
            "use --live or refresh fx trade"
        )
    configuration = config_mod.load([])
    snapshot, rows = read_slot(Cache(configuration.cache_path), FX_TRADE.name)
    if snapshot is None:
        raise CliError(CACHE_MISS, "no cached FX trades; run refresh fx trade")
    evidence = AcquisitionEvidence.from_record(snapshot.acquisition)
    window = window_rows(rows, limit, offset)
    meta = {
        "source": "cache",
        "backend": snapshot.source_kind,
        "capability": FX_TRADE.name,
        "fetched_at": snapshot.fetched_at,
        "scope": slot_context(snapshot)["query"],
        "simulated": snapshot.simulated,
        "matched_total": len(rows),
        "returned_count": len(window),
        "offset": offset,
        "has_more": offset + len(window) < len(rows),
        **evidence.meta(),
    }
    return _emit(args, window, meta, fields)


def _online(args: Any, *, refresh: bool) -> int:
    limit, offset, fields = display_options(args)
    query = query_request(args)
    store = Cache(config_mod.load([]).cache_path) if refresh else None
    started = time.monotonic()
    with inquiry_session(
        config_file=config_mod.config_path(), startup_url=FX_TRADE.page_url
    ) as session:
        rows, evidence, pages = acquire(session.transport(FX_TRADE), query)
    fetched_at = datetime.now(timezone.utc).isoformat()
    published = False
    if refresh:
        check_complete(
            evidence,
            require_complete=getattr(args, "require_complete", False),
            mode="refresh",
        )
        # An empty candidate keeps both previous rows and acquisition timestamp.
        if rows:
            assert store is not None
            with store.refresh_lock():
                published = (
                    publish_slot(
                        store,
                        FX_TRADE.name,
                        rows,
                        capability=FX_TRADE.name,
                        scope=query,
                        evidence=evidence,
                        fetched_at=fetched_at,
                    )
                    is not None
                )
    window = window_rows(rows, limit, offset)
    meta = {
        "source": "refresh" if refresh else "live",
        "backend": "cdp",
        "capability": FX_TRADE.name,
        "scope": query,
        "fetched_at": fetched_at,
        "simulated": False,
        "matched_total": len(rows),
        "returned_count": len(window),
        "offset": offset,
        "has_more": offset + len(window) < len(rows),
        "pages_acquired": pages,
        "duration_seconds": round(time.monotonic() - started, 3),
        **evidence.meta(),
    }
    if refresh:
        meta["published"] = published
        if not rows:
            meta["publication_reason"] = "empty acquisition; previous cache preserved"
    return _emit(args, window, meta, fields)


def run_refresh(args: Any) -> int:
    return _online(args, refresh=True)


def run_prune(args: Any) -> int:
    from ...cli import _emit

    removed = prune_slot(Cache(config_mod.load([]).cache_path), FX_TRADE.name)
    _emit({"pruned": removed}, {"source": "cache", "capability": FX_TRADE.name})
    return 0
