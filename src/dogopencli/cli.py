"""Public CLI: domain query orchestration and business output envelope.

Business commands print a JSON envelope with data/meta/error on stdout;
diagnostics go to stderr. Exit codes (ADR 0004): 0 success, 1 runtime
failure, 2 argument/config error, 130 interrupted.
"""

import argparse
import hashlib
import sys
import traceback
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from . import collect as collect_mod
from . import config as config_mod
from .cache import Cache, SnapshotMeta, namespace
from .cached_query import CachedQuery, is_stale, read_cached_query, snapshot_meta
from .errors import (
    AUTH_REQUIRED,
    BUSINESS_QUERY_FAILED,
    CONFIG_ERROR,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_USAGE,
    INCOMPLETE_RESULT,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    LIVE_SOURCE_UNAVAILABLE,
    NOT_FOUND,
    SOURCE_DATA_INVALID,
    SOURCE_SCOPE_UNAVAILABLE,
    TIMEOUT,
    CliError,
)
from .helpspec import BizNode, add_options
from .helptree import business_entry, help_main, leading_command
from .inquiry import inquiry_session
from .jsonutil import canonical, parse
from .plugins import get_capability
from .plugins.collection import sla as collection_sla
from .plugins.collection import va_capacity as collection_va_capacity
from .plugins.collection import va_rule as collection_va
from .plugins.envelope import is_business_refusal
from .plugins.payment.channel import assign_seqids
from .plugins.payment.sla import SLA_DETAIL, detail_body
from .plugins.payment.sla import parse_detail as parse_payment_sla_detail
from .table import render_table
from .transport import QueryRequest, validate_request
from .transport.cdp import CdpQueryTransport, FetchFailed
from .transport.snapshot import SnapshotTransport, load_dataset

CHANNEL = "payment.channel.list"
COST = "payment.cost.list"
COLLECTION_COST = "collection.cost.list"
SLA = "payment.sla.baselines.list"

AUTH_COMMANDS = {"login", "auth", "logout"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _emit(data: Any, meta: Any, error: Any = None) -> None:
    envelope = {"data": data, "error": error, "meta": meta}
    sys.stdout.write(canonical(envelope) + "\n")


def _emit_error(error: CliError, output_format: str = "json") -> int:
    if output_format == "table":
        print(f"error: {error.code}: {error.message}", file=sys.stderr)
        return error.exit_code
    _emit(
        None,
        None,
        {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        },
    )
    return error.exit_code


def _argument_error(message: str) -> CliError:
    return CliError(INVALID_ARGUMENT, message, exit_code=EXIT_USAGE)


def _snapshot_source(config: config_mod.Config, source_key: str):
    source = config.sources[source_key]
    if source.kind != config_mod.SOURCE_SNAPSHOT:
        raise CliError(
            CONFIG_ERROR,
            f"source kind {source.kind} is not available in this build",
            exit_code=EXIT_USAGE,
        )
    return source


def cmd_refresh_channel(args: argparse.Namespace) -> int:
    capability = get_capability(CHANNEL)
    config = config_mod.load([capability.source_config_key])
    source = config.sources[capability.source_config_key]
    if source.kind == config_mod.SOURCE_CDP:
        return _refresh_channel_cdp(args, capability, config, source)
    return _refresh_channel_snapshot(
        args, capability, config, _snapshot_source(config, capability.source_config_key)
    )


def _refresh_channel_cdp(
    args: argparse.Namespace,
    capability: Any,
    config: config_mod.Config,
    source: config_mod.SourceConfig,
) -> int:
    store = Cache(config.cache_path)
    ns = namespace(capability.name, args.payout_type, source.kind)
    with store.refresh_lock():
        with inquiry_session(config_file=config_mod.config_path()) as session:
            transport = session.transport(capability)
            result = collect_mod.collect_scope(
                capability, transport, args.payout_type, progress=_progress
            )
        if not result.complete:
            raise CliError(
                INVALID_RESPONSE,
                "collected channel records are incomplete; the previous "
                "cache is retained",
            )
        rows = assign_seqids(result.records)
        fetched_at = _now().isoformat()
        snapshot = SnapshotMeta(
            namespace=ns,
            capability=capability.name,
            scope=args.payout_type,
            source_kind=source.kind,
            snapshot_id=hashlib.sha256(canonical(rows).encode()).hexdigest(),
            dataset_id=None,
            simulated=False,
            backend_complete=True,
            dataset_complete=True,
            fetched_at=fetched_at,
            loaded_at=_now().isoformat(),
            source_observed_from=None,
            source_observed_to=None,
            row_count=len(rows),
        )
        collect_mod.remaining_seconds(result.deadline)
        store.publish(snapshot, [(row["seqid"], canonical(row)) for row in rows])
    print(f"refresh: published {len(rows)} rows to {ns}", file=sys.stderr)
    stale = is_stale(snapshot, config.ttl_hours, _now())
    _emit(
        {"namespace": ns, "published": True, "row_count": len(rows)},
        snapshot_meta("cache", snapshot, stale, len(rows), len(rows), False),
    )
    return EXIT_OK


def _refresh_channel_snapshot(
    args: argparse.Namespace,
    capability: Any,
    config: config_mod.Config,
    source: config_mod.SourceConfig,
) -> int:
    dataset = load_dataset(source.path, capability.name, source.dataset_id)
    if args.payout_type != dataset.scope:
        raise CliError(
            SOURCE_SCOPE_UNAVAILABLE,
            f"snapshot dataset does not cover scope {args.payout_type}",
        )
    store = Cache(config.cache_path)
    ns = namespace(capability.name, dataset.scope, source.kind)
    with store.refresh_lock():
        transport = SnapshotTransport(dataset, capability)
        collected: list[dict[str, Any]] = []
        total_pages = 0
        page_num = 1
        while True:
            body = capability.page_body(
                dataset.scope, page_num, capability.contract.page_size
            )
            request = QueryRequest(
                capability=capability.name,
                method=capability.contract.method,
                host=capability.contract.host,
                path=capability.contract.path,
                body=body,
            )
            validate_request(request, capability.contract)
            response = transport.execute(request)
            if response.status != 200:
                raise CliError(
                    INVALID_RESPONSE, f"unexpected HTTP status {response.status}"
                )
            page = capability.parse_page(response.body)
            if (
                page.page_num != page_num
                or page.page_size != capability.contract.page_size
            ):
                raise CliError(INVALID_RESPONSE, "pagination echo mismatch")
            if page_num == 1:
                if page.total_count != dataset.row_count:
                    raise CliError(
                        SOURCE_DATA_INVALID,
                        "dataset total does not match manifest row_count",
                    )
                total_pages = page.total_pages
            collected.extend(page.records)
            print(
                f"refresh: collected page {page_num}/{total_pages}",
                file=sys.stderr,
            )
            if page_num >= total_pages:
                break
            page_num += 1
        if len(collected) != dataset.row_count:
            raise CliError(
                SOURCE_DATA_INVALID, "collected rows do not match dataset row_count"
            )
        keyed: list[tuple[int, str]] = []
        seen: set[int] = set()
        for record in collected:
            if "seqid" in record:
                raise CliError(
                    SOURCE_DATA_INVALID, "simulated response leaked a local seqid"
                )
            seqid = dataset.identity.get(canonical(record))
            if seqid is None or seqid in seen:
                raise CliError(
                    SOURCE_DATA_INVALID,
                    "collected record does not match the dataset identity",
                )
            seen.add(seqid)
            keyed.append((seqid, canonical({"seqid": seqid, **record})))
        if seen != set(range(1, dataset.row_count + 1)):
            raise CliError(SOURCE_DATA_INVALID, "collected seqids are not continuous")
        loaded_at = _now().isoformat()
        snapshot = SnapshotMeta(
            namespace=ns,
            capability=capability.name,
            scope=dataset.scope,
            source_kind=source.kind,
            snapshot_id=dataset.dataset_id,
            dataset_id=dataset.dataset_id,
            simulated=dataset.simulated,
            backend_complete=dataset.backend_complete,
            dataset_complete=dataset.dataset_complete,
            fetched_at=dataset.source_observed_from,
            loaded_at=loaded_at,
            source_observed_from=dataset.source_observed_from,
            source_observed_to=dataset.source_observed_to,
            row_count=dataset.row_count,
            source_path=str(source.path.expanduser().resolve()),
        )
        store.publish(snapshot, keyed)
    print(
        f"refresh: published {dataset.row_count} rows to {ns}",
        file=sys.stderr,
    )
    stale = is_stale(snapshot, config.ttl_hours, _now())
    _emit(
        {"namespace": ns, "published": True, "row_count": dataset.row_count},
        snapshot_meta(
            "cache", snapshot, stale, dataset.row_count, dataset.row_count, False
        ),
    )
    return EXIT_OK


# Backend-scalar channel filter fields; every other filter field is a
# verified array parameter on the wire.
CHANNEL_SCALAR_FILTERS = ("financialInstId", "debitInstCountryCode", "status")


def _list_filters(args: argparse.Namespace) -> dict[str, list[str]]:
    raw = {
        "financialInstId": args.financial_inst_id,
        "debitInstCountryCode": args.debit_inst_country_code,
        "status": args.status,
        "debitAccountNameList": args.debit_account_name,
        "debitAccountNoList": args.debit_account_no,
        "clearingSystemNameList": args.clearing_system_name,
        "debitCurrencyList": args.debit_currency,
        "creditCurrencyList": args.credit_currency,
    }
    return {key: list(values) for key, values in raw.items() if values}


def _cmd_channel_list_live(
    args: argparse.Namespace,
    capability: Any,
    source: config_mod.SourceConfig,
    filters: dict[str, list[str]],
    limit: int,
    offset: int,
    fields: list[str] | None,
) -> int:
    body_filters: dict[str, Any] = {}
    for key, values in filters.items():
        if key in CHANNEL_SCALAR_FILTERS:
            if len(values) > 1:
                raise _argument_error(
                    "live queries accept a single value per filter; got "
                    f"{values} for {key}"
                )
            body_filters[key] = values[0]
        else:
            body_filters[key] = values
    with inquiry_session(config_file=config_mod.config_path()) as session:
        transport = session.transport(capability)
        result = collect_mod.collect_scope(
            capability, transport, args.payout_type, body_filters
        )
    if args.require_complete and not result.complete:
        raise CliError(
            INCOMPLETE_RESULT,
            "live collection did not cover the complete matching scope",
        )
    rows = capability.filter_records(assign_seqids(result.records), filters)
    matched_total = len(rows)
    window = rows[offset:] if args.all else rows[offset : offset + limit]
    meta = _live_meta(
        source,
        args.payout_type,
        result.complete,
        matched_total,
        len(window),
        offset,
    )
    return _emit_window(args, capability, window, meta, fields)


def cmd_channel_list(args: argparse.Namespace) -> int:
    capability = get_capability(CHANNEL)
    limit, offset, fields = _display_options(args)
    config = config_mod.load([capability.source_config_key])
    source = config.sources[capability.source_config_key]
    filters = _list_filters(args)
    if source.kind == config_mod.SOURCE_CDP:
        if args.live:
            return _cmd_channel_list_live(
                args, capability, source, filters, limit, offset, fields
            )
    else:
        source = _snapshot_source(config, capability.source_config_key)
        if args.payout_type != capability.default_scope:
            raise CliError(
                SOURCE_SCOPE_UNAVAILABLE, "snapshot source only covers EXTERNAL"
            )
        if args.live:
            raise CliError(
                LIVE_SOURCE_UNAVAILABLE,
                "snapshot source cannot serve live queries; no implicit fallback",
            )
    cached = read_cached_query(
        config,
        source,
        capability.name,
        args.payout_type,
        refresh_command="refresh payment channel",
        require_fresh=args.require_fresh,
        require_complete=args.require_complete,
        now=_now(),
    )
    records = [parse(body) for _, body in cached.stored]
    matched = capability.sort_records(capability.filter_records(records, filters))
    matched_total = len(matched)
    window = matched[offset:] if args.all else matched[offset : offset + limit]
    meta = cached.meta(matched_total, len(window), offset=offset)
    return _emit_window(args, capability, window, meta, fields)


def _display_options(
    args: argparse.Namespace,
) -> tuple[int, int, list[str] | None]:
    if args.all and (args.limit is not None or args.offset is not None):
        raise _argument_error("--all conflicts with explicit --limit/--offset")
    limit = 100 if args.limit is None else args.limit
    if limit <= 0:
        raise _argument_error("--limit must be a positive integer")
    offset = 0 if args.offset is None else args.offset
    if offset < 0:
        raise _argument_error("--offset must not be negative")
    fields: list[str] | None = None
    if args.fields is not None:
        fields = [name.strip() for name in args.fields.split(",") if name.strip()]
        if not fields:
            raise _argument_error("--fields must name at least one field")
    return limit, offset, fields


def _emit_window(
    args: argparse.Namespace,
    capability: Any,
    window: list[dict[str, Any]],
    meta: dict[str, Any],
    fields: list[str] | None,
) -> int:
    if fields is not None:
        window = [
            {name: record[name] for name in fields if name in record}
            for record in window
        ]
    if args.format == "table":
        columns = fields if fields is not None else capability.table_columns
        sys.stdout.write(render_table(window, columns, meta) + "\n")
    else:
        _emit(window, meta)
    return EXIT_OK


def _cdp_source(config: config_mod.Config, source_key: str) -> config_mod.SourceConfig:
    source = config.sources[source_key]
    if source.kind != config_mod.SOURCE_CDP:
        raise CliError(
            CONFIG_ERROR,
            f"source kind {source.kind} is not available for this capability",
            exit_code=EXIT_USAGE,
        )
    return source


def _progress(done: int, total: int) -> None:
    print(f"refresh: collected page {done}/{total}", file=sys.stderr)


def cmd_refresh_cost(args: argparse.Namespace) -> int:
    return _refresh_cost(args, COST)


def cmd_refresh_collection_cost(args: argparse.Namespace) -> int:
    return _refresh_cost(args, COLLECTION_COST)


def _refresh_cost(args: argparse.Namespace, capability_name: str) -> int:
    capability = get_capability(capability_name)
    config = config_mod.load([capability.source_config_key])
    source = _cdp_source(config, capability.source_config_key)
    store = Cache(config.cache_path)
    ns = namespace(capability.name, capability.default_scope, source.kind)
    with store.refresh_lock():
        with inquiry_session(config_file=config_mod.config_path()) as session:
            transport = session.transport(capability)
            result = collect_mod.collect_scope(
                capability,
                transport,
                capability.default_scope,
                progress=_progress,
            )
        if not result.complete:
            raise CliError(
                INVALID_RESPONSE,
                "collected cost records are incomplete after the bounded "
                "rebuild; the previous cache is retained",
            )
        records = capability.sort_records(result.records)
        fetched_at = _now().isoformat()
        snapshot = SnapshotMeta(
            namespace=ns,
            capability=capability.name,
            scope=capability.default_scope,
            source_kind=source.kind,
            snapshot_id=hashlib.sha256(canonical(records).encode()).hexdigest(),
            dataset_id=None,
            simulated=False,
            backend_complete=True,
            dataset_complete=True,
            fetched_at=fetched_at,
            loaded_at=_now().isoformat(),
            source_observed_from=None,
            source_observed_to=None,
            row_count=len(records),
        )
        collect_mod.remaining_seconds(result.deadline)
        store.publish(
            snapshot,
            [(index, canonical(record)) for index, record in enumerate(records, 1)],
        )
    print(f"refresh: published {len(records)} rows to {ns}", file=sys.stderr)
    stale = is_stale(snapshot, config.ttl_hours, _now())
    _emit(
        {"namespace": ns, "published": True, "row_count": len(records)},
        snapshot_meta("cache", snapshot, stale, len(records), len(records), False),
    )
    return EXIT_OK


def _cost_filters(args: argparse.Namespace) -> dict[str, list[str]]:
    raw = {
        "legalEntityCode": args.legal_entity_code,
        "financialInstCode": args.financial_inst_code,
        "bankAccount": args.bank_account,
        "transCurrencyCode": args.trans_currency_code,
        "chargeBearer": args.charge_bearer,
        "clearingNetworkName": args.clearing_network_name,
    }
    return {key: list(values) for key, values in raw.items() if values}


def _cmd_cost_list_live(
    args: argparse.Namespace,
    capability: Any,
    source: config_mod.SourceConfig,
    filters: dict[str, list[str]],
    limit: int,
    offset: int,
    fields: list[str] | None,
) -> int:
    scalars: dict[str, Any] = {}
    for key, values in filters.items():
        if len(values) > 1:
            raise _argument_error(
                f"live queries accept a single value per filter; got {values} for {key}"
            )
        scalars[key] = values[0]
    with inquiry_session(config_file=config_mod.config_path()) as session:
        transport = session.transport(capability)
        result = collect_mod.collect_scope(
            capability, transport, capability.default_scope, scalars
        )
    if args.require_complete and not result.complete:
        raise CliError(
            INCOMPLETE_RESULT,
            "live collection did not cover the complete matching scope",
        )
    records = capability.sort_records(result.records)
    matched_total = len(records)
    window = records[offset:] if args.all else records[offset : offset + limit]
    meta = {
        "source": "live",
        "backend": source.kind,
        "simulated": False,
        "scope": capability.default_scope,
        "snapshot_id": None,
        "dataset_id": None,
        "fetched_at": _now().isoformat(),
        "loaded_at": None,
        "stale": False,
        "complete": result.complete,
        "dataset_complete": None,
        "source_observed_from": None,
        "source_observed_to": None,
        "matched_total": matched_total,
        "returned_count": len(window),
        "has_more": offset + len(window) < matched_total,
    }
    return _emit_window(args, capability, window, meta, fields)


def cmd_cost_list(args: argparse.Namespace) -> int:
    return _cost_list(args, COST, _cost_filters(args), "refresh payment cost")


def cmd_collection_cost_list(args: argparse.Namespace) -> int:
    return _cost_list(args, COLLECTION_COST, {}, "refresh collection cost")


def _cost_list(
    args: argparse.Namespace,
    capability_name: str,
    filters: dict[str, list[str]],
    refresh_command: str,
) -> int:
    capability = get_capability(capability_name)
    limit, offset, fields = _display_options(args)
    config = config_mod.load([capability.source_config_key])
    source = _cdp_source(config, capability.source_config_key)
    if args.live:
        return _cmd_cost_list_live(
            args, capability, source, filters, limit, offset, fields
        )
    cached = read_cached_query(
        config,
        source,
        capability.name,
        capability.default_scope,
        refresh_command=refresh_command,
        require_fresh=args.require_fresh,
        require_complete=args.require_complete,
        now=_now(),
    )
    records = [parse(body) for _, body in cached.stored]
    matched = capability.sort_records(capability.filter_records(records, filters))
    matched_total = len(matched)
    window = matched[offset:] if args.all else matched[offset : offset + limit]
    meta = cached.meta(matched_total, len(window), offset=offset)
    return _emit_window(args, capability, window, meta, fields)


def _fetch_sla_detail(
    transport: CdpQueryTransport, baseline_id: str, deadline: float
) -> dict[str, Any]:
    """One allowlisted detail query with the shared bounded retry policy."""
    request = QueryRequest(
        capability=SLA_DETAIL.name,
        method=SLA_DETAIL.contract.method,
        host=SLA_DETAIL.contract.host,
        path=SLA_DETAIL.contract.path,
        body=detail_body(baseline_id),
    )
    validate_request(request, SLA_DETAIL.contract)
    attempt = 0
    while True:
        if collect_mod._monotonic() >= deadline:
            raise CliError(TIMEOUT, "collection budget exhausted", retryable=True)
        response = None
        failure: CliError | None = None
        try:
            response = collect_mod.execute_before_deadline(transport, request, deadline)
        except FetchFailed as error:
            failure = CliError(
                TIMEOUT,
                f"network failure during business query: {error}",
                retryable=True,
            )
        if failure is None and response is not None:
            if response.status == 200:
                return parse_payment_sla_detail(response.body, baseline_id)
            if response.status not in collect_mod.RETRYABLE_STATUSES:
                if response.status == 401:
                    raise CliError(
                        AUTH_REQUIRED,
                        "the backend rejected the dedicated browser session;"
                        " run: dogopencli login",
                    )
                raise CliError(
                    BUSINESS_QUERY_FAILED,
                    f"unexpected HTTP status {response.status}",
                )
        if attempt >= len(collect_mod.RETRY_WAITS):
            if failure is not None:
                raise failure
            status = response.status if response is not None else "unknown"
            raise CliError(
                BUSINESS_QUERY_FAILED,
                f"HTTP {status} persisted after bounded retries",
                retryable=True,
            )
        wait = collect_mod._retry_after_seconds(response)
        if wait is None:
            wait = collect_mod.RETRY_WAITS[attempt]
        if wait > deadline - collect_mod._monotonic():
            raise CliError(
                TIMEOUT,
                "collection budget exhausted while waiting to retry",
                retryable=True,
            )
        collect_mod._sleep(wait)
        attempt += 1


def cmd_refresh_sla(args: argparse.Namespace) -> int:
    capability = get_capability(SLA)
    config = config_mod.load([capability.source_config_key])
    source = _cdp_source(config, capability.source_config_key)
    store = Cache(config.cache_path)
    ns = namespace(capability.name, capability.default_scope, source.kind)
    with store.refresh_lock():
        with inquiry_session(config_file=config_mod.config_path()) as session:
            transport = session.transport(capability)
            detail_transport = session.transport(SLA_DETAIL)
            deadline = collect_mod._monotonic() + collect_mod.REFRESH_BUDGET_SECONDS
            result = collect_mod.collect_scope(
                capability,
                transport,
                capability.default_scope,
                progress=_progress,
            )
            if not result.complete:
                raise CliError(
                    INVALID_RESPONSE,
                    "collected SLA baselines are incomplete after the bounded "
                    "rebuild; the previous cache is retained",
                )
            baselines = capability.sort_records(result.records)
            details: list[dict[str, Any]] = []
            for index, record in enumerate(baselines, 1):
                details.append(
                    _fetch_sla_detail(detail_transport, record["id"], deadline)
                )
                print(
                    f"refresh: collected detail {index}/{len(baselines)}",
                    file=sys.stderr,
                )
        rows = [
            {"id": baseline["id"], "baseline": baseline, "detail": detail}
            for baseline, detail in zip(baselines, details, strict=True)
        ]
        fetched_at = _now().isoformat()
        snapshot = SnapshotMeta(
            namespace=ns,
            capability=capability.name,
            scope=capability.default_scope,
            source_kind=source.kind,
            snapshot_id=hashlib.sha256(canonical(rows).encode()).hexdigest(),
            dataset_id=None,
            simulated=False,
            backend_complete=True,
            dataset_complete=True,
            fetched_at=fetched_at,
            loaded_at=_now().isoformat(),
            source_observed_from=None,
            source_observed_to=None,
            row_count=len(rows),
        )
        collect_mod.remaining_seconds(deadline)
        store.publish(
            snapshot,
            [(index, canonical(row)) for index, row in enumerate(rows, 1)],
        )
    print(f"refresh: published {len(rows)} rows to {ns}", file=sys.stderr)
    stale = is_stale(snapshot, config.ttl_hours, _now())
    _emit(
        {"namespace": ns, "published": True, "row_count": len(rows)},
        snapshot_meta("cache", snapshot, stale, len(rows), len(rows), False),
    )
    return EXIT_OK


def _sla_filters(args: argparse.Namespace) -> dict[str, list[str]]:
    raw = {
        "bizCategory": args.biz_category,
        "creditorCurrency": args.creditor_currency,
        "regionCode": args.region_code,
        "status": args.status,
    }
    return {key: list(values) for key, values in raw.items() if values}


def _live_meta(
    source: config_mod.SourceConfig,
    scope: str,
    complete: bool,
    matched_total: int,
    returned: int,
    offset: int,
) -> dict[str, Any]:
    return {
        "source": "live",
        "backend": source.kind,
        "simulated": False,
        "scope": scope,
        "snapshot_id": None,
        "dataset_id": None,
        "fetched_at": _now().isoformat(),
        "loaded_at": None,
        "stale": False,
        "complete": complete,
        "dataset_complete": None,
        "source_observed_from": None,
        "source_observed_to": None,
        "matched_total": matched_total,
        "returned_count": returned,
        "has_more": offset + returned < matched_total,
    }


def _cmd_sla_list_live(
    args: argparse.Namespace,
    capability: Any,
    source: config_mod.SourceConfig,
    filters: dict[str, list[str]],
    limit: int,
    offset: int,
    fields: list[str] | None,
) -> int:
    scalars: dict[str, Any] = {}
    for key, values in filters.items():
        if len(values) > 1:
            raise _argument_error(
                f"live queries accept a single value per filter; got {values} for {key}"
            )
        scalars[key] = values[0]
    if args.biz_legal_entity:
        if len(args.biz_legal_entity) > 1:
            raise _argument_error(
                "live queries accept a single value per filter; got "
                f"{args.biz_legal_entity} for bizLegalEntity"
            )
        scalars["bizLegalEntity"] = args.biz_legal_entity[0]
        print(
            "note: --biz-legal-entity is passed through to the backend;"
            " its independent filter effect is unverified",
            file=sys.stderr,
        )
    with inquiry_session(config_file=config_mod.config_path()) as session:
        transport = session.transport(capability)
        result = collect_mod.collect_scope(
            capability, transport, capability.default_scope, scalars
        )
    if args.require_complete and not result.complete:
        raise CliError(
            INCOMPLETE_RESULT,
            "live collection did not cover the complete matching scope",
        )
    records = capability.sort_records(result.records)
    matched_total = len(records)
    window = records[offset:] if args.all else records[offset : offset + limit]
    meta = _live_meta(
        source,
        capability.default_scope,
        result.complete,
        matched_total,
        len(window),
        offset,
    )
    return _emit_window(args, capability, window, meta, fields)


def cmd_sla_list(args: argparse.Namespace) -> int:
    capability = get_capability(SLA)
    limit, offset, fields = _display_options(args)
    config = config_mod.load([capability.source_config_key])
    source = _cdp_source(config, capability.source_config_key)
    if args.biz_legal_entity and not args.live:
        raise _argument_error(
            "--biz-legal-entity cannot filter locally: the list response does not"
            " return the business legal entity field; it is only passed through"
            " with --live and its independent filter effect is unverified"
        )
    filters = _sla_filters(args)
    if args.live:
        return _cmd_sla_list_live(
            args, capability, source, filters, limit, offset, fields
        )
    cached = read_cached_query(
        config,
        source,
        capability.name,
        capability.default_scope,
        refresh_command="refresh payment sla",
        require_fresh=args.require_fresh,
        require_complete=args.require_complete,
        now=_now(),
    )
    records = [parse(body)["baseline"] for _, body in cached.stored]
    matched = capability.sort_records(capability.filter_records(records, filters))
    matched_total = len(matched)
    window = matched[offset:] if args.all else matched[offset : offset + limit]
    meta = cached.meta(matched_total, len(window), offset=offset)
    return _emit_window(args, capability, window, meta, fields)


def _emit_object(
    args: argparse.Namespace,
    capability: Any,
    record: dict[str, Any],
    meta: dict[str, Any],
    fields: list[str] | None,
) -> int:
    if fields is not None:
        record = {name: record[name] for name in fields if name in record}
    if args.format == "table":
        columns = fields if fields is not None else capability.table_columns
        sys.stdout.write(render_table([record], columns, meta) + "\n")
    else:
        _emit(record, meta)
    return EXIT_OK


def cmd_sla_get(args: argparse.Namespace) -> int:
    capability = get_capability(SLA)
    fields: list[str] | None = None
    if args.fields is not None:
        fields = [name.strip() for name in args.fields.split(",") if name.strip()]
        if not fields:
            raise _argument_error("--fields must name at least one field")
    config = config_mod.load([capability.source_config_key])
    source = _cdp_source(config, capability.source_config_key)
    if args.live:
        with inquiry_session(config_file=config_mod.config_path()) as session:
            transport = session.transport(SLA_DETAIL)
            detail = _fetch_sla_detail(
                transport,
                args.id,
                collect_mod._monotonic() + collect_mod.REFRESH_BUDGET_SECONDS,
            )
        meta = _live_meta(source, capability.default_scope, True, 1, 1, 0)
        meta["query"] = {"capability": SLA_DETAIL.name, "id": args.id}
        return _emit_object(args, capability, detail, meta, fields)
    cached = read_cached_query(
        config,
        source,
        capability.name,
        capability.default_scope,
        refresh_command="refresh payment sla",
        require_fresh=args.require_fresh,
        require_complete=args.require_complete,
        now=_now(),
    )
    detail: dict[str, Any] | None = None
    for _, body in cached.stored:
        row = parse(body)
        if row["id"] == args.id:
            detail = row["detail"]
            break
    if detail is None:
        raise CliError(
            NOT_FOUND,
            f"SLA baseline {args.id} is not present in the cached snapshot",
        )
    meta = cached.meta(1, 1)
    return _emit_object(args, capability, detail, meta, fields)


def _collection_sla_cached(
    args: argparse.Namespace,
    config: config_mod.Config,
    source: config_mod.SourceConfig,
) -> tuple[CachedQuery, list[dict[str, Any]]]:
    cap = collection_sla.COLLECTION_SLA
    cached = read_cached_query(
        config,
        source,
        cap.name,
        cap.default_scope,
        refresh_command="refresh collection sla",
        require_fresh=args.require_fresh,
        require_complete=args.require_complete,
        now=_now(),
    )
    pairs = []
    for _, body in cached.stored:
        pair = parse(body)
        if not isinstance(pair, dict):
            raise CliError(INVALID_RESPONSE, "invalid cached SLA configuration pair")
        collection_sla.validate_pair(pair.get("config"), pair.get("detail"))
        pairs.append(pair)
    if len(pairs) != cached.snapshot.row_count or len(
        {pair["config"]["slaConfigId"] for pair in pairs}
    ) != len(pairs):
        raise CliError(
            INCOMPLETE_RESULT, "cached SLA configuration coverage is invalid"
        )
    return cached, pairs


def _fetch_collection_sla_detail(
    transport: CdpQueryTransport,
    identity: str,
    deadline: float,
) -> dict[str, Any]:
    response = collect_mod._execute_bounded(
        collection_sla.COLLECTION_SLA_DETAIL,
        transport,
        {"slaConfigId": identity},
        deadline,
    )
    return collection_sla.parse_detail(response.body, identity)


def cmd_refresh_collection_sla(args: argparse.Namespace) -> int:
    cap = collection_sla.COLLECTION_SLA
    config = config_mod.load([cap.source_config_key])
    source = _cdp_source(config, cap.source_config_key)
    store = Cache(config.cache_path)
    ns = namespace(cap.name, cap.default_scope, source.kind)
    with store.refresh_lock():
        with inquiry_session(config_file=config_mod.config_path()) as session:
            result = collect_mod.collect_scope(
                cap,
                session.transport(cap),
                cap.default_scope,
                progress=_progress,
            )
            if not result.complete:
                raise CliError(INCOMPLETE_RESULT, "collection SLA list is incomplete")
            transport = session.transport(collection_sla.COLLECTION_SLA_DETAIL)
            pairs = []
            for record in cap.sort_records(result.records):
                detail = _fetch_collection_sla_detail(
                    transport, record[cap.id_field], result.deadline
                )
                collection_sla.validate_pair(record, detail)
                pairs.append({"config": record, "detail": detail})
                print(
                    f"refresh: collected detail {len(pairs)}/{len(result.records)}",
                    file=sys.stderr,
                )
        fetched_at = _now().isoformat()
        snapshot = SnapshotMeta(
            namespace=ns,
            capability=cap.name,
            scope=cap.default_scope,
            source_kind=source.kind,
            snapshot_id=hashlib.sha256(canonical(pairs).encode()).hexdigest(),
            dataset_id=None,
            simulated=False,
            backend_complete=True,
            dataset_complete=True,
            fetched_at=fetched_at,
            loaded_at=_now().isoformat(),
            source_observed_from=None,
            source_observed_to=None,
            row_count=len(pairs),
        )
        collect_mod.remaining_seconds(result.deadline)
        store.publish(
            snapshot, [(i, canonical(pair)) for i, pair in enumerate(pairs, 1)]
        )
    _emit(
        {"namespace": ns, "published": True, "row_count": len(pairs)},
        snapshot_meta(
            "cache",
            snapshot,
            is_stale(snapshot, config.ttl_hours, _now()),
            len(pairs),
            len(pairs),
            False,
        ),
    )
    return EXIT_OK


def cmd_collection_sla_list(args: argparse.Namespace) -> int:
    cap = collection_sla.COLLECTION_SLA
    limit, offset, fields = _display_options(args)
    filters: dict[str, list[str]] = {}
    for flag, field in collection_sla.FILTER_FIELDS.items():
        values = getattr(args, flag.replace("-", "_"))
        if any(not value.strip() for value in values):
            raise _argument_error(f"--{flag} must be nonempty")
        if values:
            filters[field] = values
    config = config_mod.load([cap.source_config_key])
    source = _cdp_source(config, cap.source_config_key)
    if args.live:
        with inquiry_session(config_file=config_mod.config_path()) as session:
            result = collect_mod.collect_scope(
                cap, session.transport(cap), cap.default_scope
            )
        if not result.complete:
            raise CliError(INCOMPLETE_RESULT, "collection SLA list is incomplete")
        records = cap.sort_records(cap.filter_records(result.records, filters))
        window = records[offset:] if args.all else records[offset : offset + limit]
        meta = _live_meta(
            source, cap.default_scope, True, len(records), len(window), offset
        )
    else:
        cached, pairs = _collection_sla_cached(args, config, source)
        records = cap.sort_records(
            cap.filter_records([pair["config"] for pair in pairs], filters)
        )
        window = records[offset:] if args.all else records[offset : offset + limit]
        meta = cached.meta(len(records), len(window), offset=offset)
    return _emit_window(args, cap, window, meta, fields)


def cmd_collection_sla_get(args: argparse.Namespace) -> int:
    if not args.id.strip():
        raise _argument_error("--id must be nonempty")
    fields = None
    if args.fields is not None:
        fields = [field.strip() for field in args.fields.split(",") if field.strip()]
        if not fields:
            raise _argument_error("--fields must name at least one field")
    cap = collection_sla.COLLECTION_SLA
    config = config_mod.load([cap.source_config_key])
    source = _cdp_source(config, cap.source_config_key)
    if args.live:
        with inquiry_session(config_file=config_mod.config_path()) as session:
            detail = _fetch_collection_sla_detail(
                session.transport(collection_sla.COLLECTION_SLA_DETAIL),
                args.id,
                collect_mod._monotonic() + collect_mod.REFRESH_BUDGET_SECONDS,
            )
        meta = _live_meta(source, cap.default_scope, True, 1, 1, 0)
        meta["query"] = {
            "capability": collection_sla.COLLECTION_SLA_DETAIL.name,
            "id": args.id,
        }
    else:
        cached, pairs = _collection_sla_cached(args, config, source)
        detail = next(
            (
                pair["detail"]
                for pair in pairs
                if pair["config"]["slaConfigId"] == args.id
            ),
            None,
        )
        if detail is None:
            if not cached.snapshot.backend_complete:
                raise CliError(
                    INCOMPLETE_RESULT,
                    "cannot confirm absence in incomplete SLA snapshot",
                )
            raise CliError(
                NOT_FOUND, "SLA configuration is not present in the cached snapshot"
            )
        meta = cached.meta(1, 1)
    return _emit_object(args, cap, detail, meta, fields)


def _collection_va_cached(
    args: argparse.Namespace,
    config: config_mod.Config,
    source: config_mod.SourceConfig,
) -> tuple[CachedQuery, list[dict[str, Any]]]:
    cap = collection_va.COLLECTION_VA_RULES
    cached = read_cached_query(
        config,
        source,
        cap.name,
        cap.default_scope,
        refresh_command="refresh collection va",
        require_fresh=args.require_fresh,
        require_complete=args.require_complete,
        now=_now(),
    )
    if args.require_complete and not cached.snapshot.dataset_complete:
        raise CliError(
            INCOMPLETE_RESULT,
            "cached VA rule snapshot has details the backend refused;"
            " run: dogopencli refresh collection va",
        )
    pairs = []
    for _, body in cached.stored:
        pair = parse(body)
        collection_va.validate_stored_pair(pair)
        pairs.append(pair)
    if len(pairs) != cached.snapshot.row_count or len(
        {pair["rule"]["vaRuleId"] for pair in pairs}
    ) != len(pairs):
        raise CliError(INCOMPLETE_RESULT, "cached VA rule coverage is invalid")
    return cached, pairs


def _fetch_collection_va_detail(
    transport: CdpQueryTransport,
    identity: str,
    deadline: float,
    *,
    tolerate_refusal: bool = False,
) -> dict[str, Any] | None:
    response = collect_mod._execute_bounded(
        collection_va.COLLECTION_VA_RULES_DETAIL,
        transport,
        {"vaRuleId": identity},
        deadline,
    )
    if tolerate_refusal and is_business_refusal(response.body):
        return None
    return collection_va.parse_detail(response.body, identity)


def cmd_refresh_collection_va(args: argparse.Namespace) -> int:
    cap = collection_va.COLLECTION_VA_RULES
    config = config_mod.load([cap.source_config_key])
    source = _cdp_source(config, cap.source_config_key)
    store = Cache(config.cache_path)
    ns = namespace(cap.name, cap.default_scope, source.kind)
    with store.refresh_lock():
        with inquiry_session(config_file=config_mod.config_path()) as session:
            result = collect_mod.collect_scope(
                cap,
                session.transport(cap),
                cap.default_scope,
                progress=_progress,
            )
            if not result.complete:
                raise CliError(
                    INCOMPLETE_RESULT, "collection VA rule list is incomplete"
                )
            transport = session.transport(collection_va.COLLECTION_VA_RULES_DETAIL)
            pairs = []
            refused = 0
            for record in cap.sort_records(result.records):
                detail = _fetch_collection_va_detail(
                    transport,
                    record[cap.id_field],
                    result.deadline,
                    tolerate_refusal=True,
                )
                if detail is None:
                    refused += 1
                else:
                    collection_va.validate_pair(record, detail)
                pairs.append({"rule": record, "detail": detail})
                print(
                    f"refresh: detail "
                    f"{'refused' if detail is None else 'collected'} "
                    f"{len(pairs)}/{len(result.records)}",
                    file=sys.stderr,
                )
        fetched_at = _now().isoformat()
        snapshot = SnapshotMeta(
            namespace=ns,
            capability=cap.name,
            scope=cap.default_scope,
            source_kind=source.kind,
            snapshot_id=hashlib.sha256(canonical(pairs).encode()).hexdigest(),
            dataset_id=None,
            simulated=False,
            backend_complete=True,
            dataset_complete=refused == 0,
            fetched_at=fetched_at,
            loaded_at=_now().isoformat(),
            source_observed_from=None,
            source_observed_to=None,
            row_count=len(pairs),
        )
        collect_mod.remaining_seconds(result.deadline)
        store.publish(
            snapshot, [(i, canonical(pair)) for i, pair in enumerate(pairs, 1)]
        )
    if refused:
        raise CliError(
            INCOMPLETE_RESULT,
            f"published {len(pairs) - refused}/{len(pairs)} collection VA rule"
            f" details; {refused} refused by the backend",
        )
    _emit(
        {"namespace": ns, "published": True, "row_count": len(pairs)},
        snapshot_meta(
            "cache",
            snapshot,
            is_stale(snapshot, config.ttl_hours, _now()),
            len(pairs),
            len(pairs),
            False,
        ),
    )
    return EXIT_OK


def cmd_collection_va_rules_list(args: argparse.Namespace) -> int:
    cap = collection_va.COLLECTION_VA_RULES
    limit, offset, fields = _display_options(args)
    config = config_mod.load([cap.source_config_key])
    source = _cdp_source(config, cap.source_config_key)
    if args.live:
        with inquiry_session(config_file=config_mod.config_path()) as session:
            result = collect_mod.collect_scope(
                cap, session.transport(cap), cap.default_scope
            )
        if not result.complete:
            raise CliError(INCOMPLETE_RESULT, "collection VA rule list is incomplete")
        records = cap.sort_records(result.records)
        window = records[offset:] if args.all else records[offset : offset + limit]
        meta = _live_meta(
            source, cap.default_scope, True, len(records), len(window), offset
        )
    else:
        cached, pairs = _collection_va_cached(args, config, source)
        records = cap.sort_records([pair["rule"] for pair in pairs])
        window = records[offset:] if args.all else records[offset : offset + limit]
        meta = cached.meta(len(records), len(window), offset=offset)
    return _emit_window(args, cap, window, meta, fields)


def cmd_collection_va_rules_get(args: argparse.Namespace) -> int:
    if not args.id.strip():
        raise _argument_error("--id must be nonempty")
    fields = None
    if args.fields is not None:
        fields = [field.strip() for field in args.fields.split(",") if field.strip()]
        if not fields:
            raise _argument_error("--fields must name at least one field")
    cap = collection_va.COLLECTION_VA_RULES
    config = config_mod.load([cap.source_config_key])
    source = _cdp_source(config, cap.source_config_key)
    if args.live:
        with inquiry_session(config_file=config_mod.config_path()) as session:
            detail = _fetch_collection_va_detail(
                session.transport(collection_va.COLLECTION_VA_RULES_DETAIL),
                args.id,
                collect_mod._monotonic() + collect_mod.REFRESH_BUDGET_SECONDS,
            )
        meta = _live_meta(source, cap.default_scope, True, 1, 1, 0)
        meta["query"] = {
            "capability": collection_va.COLLECTION_VA_RULES_DETAIL.name,
            "id": args.id,
        }
    else:
        cached, pairs = _collection_va_cached(args, config, source)
        pair = next(
            (pair for pair in pairs if pair["rule"]["vaRuleId"] == args.id), None
        )
        if pair is None:
            if not cached.snapshot.backend_complete:
                raise CliError(
                    INCOMPLETE_RESULT,
                    "cannot confirm absence in incomplete VA rule snapshot",
                )
            raise CliError(NOT_FOUND, "VA rule is not present in the cached snapshot")
        detail = pair["detail"]
        if detail is None:
            raise CliError(
                INCOMPLETE_RESULT,
                "VA rule detail was refused by the backend;"
                " run: dogopencli refresh collection va",
            )
        meta = cached.meta(1, 1)
    return _emit_object(args, cap, detail, meta, fields)


def _va_capacity_filters(args: argparse.Namespace) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for flag, field in collection_va_capacity.FILTER_FIELDS.items():
        values = getattr(args, flag.replace("-", "_"))
        if any(not value.strip() for value in values):
            raise _argument_error(f"--{flag} must be nonempty")
        if values:
            filters[field] = values
    return filters


def _collection_va_capacity_cached(
    args: argparse.Namespace,
    config: config_mod.Config,
    source: config_mod.SourceConfig,
) -> tuple[CachedQuery, list[dict[str, Any]]]:
    cap = collection_va_capacity.COLLECTION_VA_CAPACITY
    cached = read_cached_query(
        config,
        source,
        cap.name,
        cap.default_scope,
        refresh_command="refresh collection va capacity",
        require_fresh=args.require_fresh,
        require_complete=args.require_complete,
        now=_now(),
    )
    records = []
    for _, body in cached.stored:
        record = parse(body)
        collection_va_capacity.validate_row(record)
        records.append(record)
    if len(records) != cached.snapshot.row_count or len(
        {record["ruleId"] for record in records}
    ) != len(records):
        raise CliError(INCOMPLETE_RESULT, "cached VA capacity coverage is invalid")
    return cached, records


def cmd_refresh_collection_va_capacity(args: argparse.Namespace) -> int:
    cap = collection_va_capacity.COLLECTION_VA_CAPACITY
    config = config_mod.load([cap.source_config_key])
    source = _cdp_source(config, cap.source_config_key)
    store = Cache(config.cache_path)
    ns = namespace(cap.name, cap.default_scope, source.kind)
    with store.refresh_lock():
        with inquiry_session(config_file=config_mod.config_path()) as session:
            result = collect_mod.collect_scope(
                cap,
                session.transport(cap),
                cap.default_scope,
                progress=_progress,
            )
        if not result.complete:
            raise CliError(
                INCOMPLETE_RESULT,
                "collection VA capacity scope is incomplete; the previous "
                "cache is retained",
            )
        records = cap.sort_records(result.records)
        fetched_at = _now().isoformat()
        snapshot = SnapshotMeta(
            namespace=ns,
            capability=cap.name,
            scope=cap.default_scope,
            source_kind=source.kind,
            snapshot_id=hashlib.sha256(canonical(records).encode()).hexdigest(),
            dataset_id=None,
            simulated=False,
            backend_complete=True,
            dataset_complete=True,
            fetched_at=fetched_at,
            loaded_at=_now().isoformat(),
            source_observed_from=None,
            source_observed_to=None,
            row_count=len(records),
        )
        collect_mod.remaining_seconds(result.deadline)
        store.publish(
            snapshot,
            [(index, canonical(record)) for index, record in enumerate(records, 1)],
        )
    print(f"refresh: published {len(records)} rows to {ns}", file=sys.stderr)
    stale = is_stale(snapshot, config.ttl_hours, _now())
    _emit(
        {"namespace": ns, "published": True, "row_count": len(records)},
        snapshot_meta("cache", snapshot, stale, len(records), len(records), False),
    )
    return EXIT_OK


def cmd_collection_va_capacity_list(args: argparse.Namespace) -> int:
    cap = collection_va_capacity.COLLECTION_VA_CAPACITY
    limit, offset, fields = _display_options(args)
    filters = _va_capacity_filters(args)
    config = config_mod.load([cap.source_config_key])
    source = _cdp_source(config, cap.source_config_key)
    if args.live:
        with inquiry_session(config_file=config_mod.config_path()) as session:
            result = collect_mod.collect_scope(
                cap, session.transport(cap), cap.default_scope
            )
        if not result.complete:
            raise CliError(
                INCOMPLETE_RESULT, "collection VA capacity list is incomplete"
            )
        records = cap.sort_records(cap.filter_records(result.records, filters))
        window = records[offset:] if args.all else records[offset : offset + limit]
        meta = _live_meta(
            source, cap.default_scope, True, len(records), len(window), offset
        )
    else:
        cached, records = _collection_va_capacity_cached(args, config, source)
        records = cap.sort_records(cap.filter_records(records, filters))
        window = records[offset:] if args.all else records[offset : offset + limit]
        meta = cached.meta(len(records), len(window), offset=offset)
    return _emit_window(args, cap, window, meta, fields)


def cmd_describe(args: argparse.Namespace) -> int:
    from .describe import describe, render_text

    description = describe(args.describe_path)
    sys.stdout.write(
        render_text(description)
        if args.format == "text"
        else canonical(description) + "\n"
    )
    return EXIT_OK


class _BusinessParser(argparse.ArgumentParser):
    """Report syntax errors through the business protocol, without argparse IO."""

    def error(self, message: str) -> None:
        raise _argument_error(message)


def _execute(node: BizNode, values: list[str], word_indices: set[int]) -> int:
    """Parse the resolved leaf's remaining argv and run its handler."""
    parser = _BusinessParser(
        prog="dogopencli " + " ".join(node.path),
        description=node.summary,
        add_help=False,
        allow_abbrev=False,
    )
    add_options(parser, node.options)
    try:
        args = parser.parse_args(
            [token for index, token in enumerate(values) if index not in word_indices]
        )
    except CliError as error:
        # No successfully parsed output format exists yet; use the JSON default.
        return _emit_error(error)
    if node.path[0] == "describe":
        args.describe_path = node.path[1:]
    handler = globals()[node.handler]
    try:
        return handler(args)
    except CliError as error:
        return _emit_error(error, getattr(args, "format", "json"))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    except Exception as error:
        diagnostic_id = uuid4().hex
        # Locations only: exception text, source lines and locals can contain data.
        locations = " -> ".join(
            f"{frame.f_code.co_name}:{line}"
            for frame, line in traceback.walk_tb(error.__traceback__)
        )
        print(
            f"INTERNAL_ERROR {diagnostic_id} {type(error).__name__}: {locations}",
            file=sys.stderr,
        )
        return _emit_error(
            CliError(
                "INTERNAL_ERROR", f"unexpected command failure (id: {diagnostic_id})"
            ),
            getattr(args, "format", "json"),
        )


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    word, index = leading_command(values)
    if word == "help":
        return help_main(values[:index] + values[index + 1 :])
    if word in AUTH_COMMANDS:
        # Authentication follows the DI-aligned envelope protocol (ADR 0004),
        # an explicit exception to the business data/meta/error protocol.
        from .auth.cli import main as auth_main

        return auth_main(values, command_hint=word)
    return business_entry(values, _execute)
