"""Public CLI: command registration and business output envelope.

Business commands print a JSON envelope with data/meta/error on stdout;
diagnostics go to stderr. Exit codes (ADR 0004): 0 success, 1 runtime
failure, 2 argument/config error, 130 interrupted.
"""

import argparse
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from . import __version__
from . import collect as collect_mod
from . import config as config_mod
from .browser import errors as auth_errors
from .browser.cdp import make_transport
from .browser.coordination import acquire_browser_control
from .browser.environment import resolve_environment
from .browser.errors import AuthError
from .browser.probe import check_authentication
from .cache import Cache, SnapshotMeta, namespace
from .errors import (
    AUTH_REQUIRED,
    BROWSER_UNAVAILABLE,
    BUSINESS_QUERY_FAILED,
    CACHE_MISS,
    CACHE_STALE,
    CONFIG_ERROR,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_USAGE,
    INCOMPLETE_RESULT,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    LIVE_SOURCE_UNAVAILABLE,
    LOCKED,
    NOT_FOUND,
    SOURCE_DATA_INVALID,
    SOURCE_SCOPE_UNAVAILABLE,
    TIMEOUT,
    CliError,
)
from .jsonutil import canonical, parse
from .plugins import get_capability
from .plugins.payment.channel import SCOPES, STATUSES, assign_seqids
from .plugins.payment.sla import SLA_DETAIL, detail_body, parse_detail
from .table import render_table
from .transport import QueryRequest, validate_request
from .transport.cdp import CdpQueryTransport, FetchFailed
from .transport.snapshot import SnapshotTransport, load_dataset, read_manifest

CHANNEL = "payment.channel.list"
COST = "payment.cost.list"
SLA = "payment.sla.baselines.list"

AUTH_COMMANDS = {"login", "auth", "logout"}
AUTH_VALUE_OPTIONS = {"--config-dir", "--format"}


def _auth_command_token(argv: list[str]) -> str | None:
    """First command-word token; auth globals may precede the command."""
    skip_next = False
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token in AUTH_VALUE_OPTIONS:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        return token
    return None


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


def _meta_dict(
    source: str | None,
    snapshot: SnapshotMeta,
    stale: bool,
    matched_total: int,
    returned_count: int,
    has_more: bool,
) -> dict[str, Any]:
    return {
        "source": source,
        "backend": snapshot.source_kind,
        "simulated": snapshot.simulated,
        "scope": snapshot.scope,
        "snapshot_id": snapshot.snapshot_id,
        "dataset_id": snapshot.dataset_id,
        "fetched_at": snapshot.fetched_at,
        "loaded_at": snapshot.loaded_at,
        "stale": stale,
        "complete": snapshot.backend_complete,
        "dataset_complete": snapshot.dataset_complete,
        "source_observed_from": snapshot.source_observed_from,
        "source_observed_to": snapshot.source_observed_to,
        "matched_total": matched_total,
        "returned_count": returned_count,
        "has_more": has_more,
    }


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


def _stale(snapshot: SnapshotMeta, ttl_hours: float, now: datetime) -> bool:
    return now > _parse_time(snapshot.fetched_at) + timedelta(hours=ttl_hours)


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
        environment = resolve_environment(config_mod.config_path().parent)
        control = _browser_control(environment)
        try:
            _check_auth(environment)
            transport = CdpQueryTransport(
                make_transport(environment.cdp_url),
                capability,
                page_url=environment.startup_url,
            )
            try:
                result = collect_mod.collect_scope(
                    capability, transport, args.payout_type, progress=_progress
                )
            finally:
                transport.close()
        finally:
            control.release()
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
        store.publish(snapshot, [(row["seqid"], canonical(row)) for row in rows])
    print(f"refresh: published {len(rows)} rows to {ns}", file=sys.stderr)
    stale = _stale(snapshot, config.ttl_hours, _now())
    _emit(
        {"namespace": ns, "published": True, "row_count": len(rows)},
        _meta_dict(None, snapshot, stale, len(rows), len(rows), False),
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
        )
        store.publish(snapshot, keyed)
    print(
        f"refresh: published {dataset.row_count} rows to {ns}",
        file=sys.stderr,
    )
    stale = _stale(snapshot, config.ttl_hours, _now())
    _emit(
        {"namespace": ns, "published": True, "row_count": dataset.row_count},
        _meta_dict(None, snapshot, stale, dataset.row_count, dataset.row_count, False),
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
    environment = resolve_environment(config_mod.config_path().parent)
    control = _browser_control(environment)
    try:
        _check_auth(environment)
        transport = CdpQueryTransport(
            make_transport(environment.cdp_url),
            capability,
            page_url=environment.startup_url,
        )
        try:
            result = collect_mod.collect_scope(
                capability, transport, args.payout_type, body_filters
            )
        finally:
            transport.close()
    finally:
        control.release()
    if args.require_complete and not result.complete:
        raise CliError(
            INCOMPLETE_RESULT,
            "live collection did not cover the complete matching scope",
        )
    rows = assign_seqids(result.records)
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
        if args.live:
            raise CliError(
                LIVE_SOURCE_UNAVAILABLE,
                "snapshot source cannot serve live queries; no implicit fallback",
            )
        manifest = read_manifest(source.path, capability.name)
        if args.payout_type != manifest["scope"]:
            raise CliError(
                SOURCE_SCOPE_UNAVAILABLE,
                f"snapshot source only covers scope {manifest['scope']}",
            )
    store = Cache(config.cache_path)
    ns = namespace(capability.name, args.payout_type, source.kind)
    snapshot, stored = store.read(ns)
    if snapshot is None:
        raise CliError(
            CACHE_MISS,
            "no cached snapshot; run: dogopencli refresh payment channel",
        )
    if source.dataset_id is not None and snapshot.dataset_id != source.dataset_id:
        raise CliError(
            CACHE_MISS,
            "cached dataset does not match the configured source identity;"
            " run: dogopencli refresh payment channel",
        )
    now = _now()
    stale = _stale(snapshot, config.ttl_hours, now)
    if args.require_fresh and stale:
        raise CliError(
            CACHE_STALE,
            f"cached snapshot is older than {config.ttl_hours:g} hours"
            f" (fetched_at {snapshot.fetched_at})",
        )
    if args.require_complete and not snapshot.backend_complete:
        raise CliError(
            INCOMPLETE_RESULT,
            "cached snapshot does not cover the complete backend scope",
        )
    records = [parse(body) for _, body in stored]
    matched = capability.sort_records(capability.filter_records(records, filters))
    matched_total = len(matched)
    window = matched[offset:] if args.all else matched[offset : offset + limit]
    meta = _meta_dict(
        "cache",
        snapshot,
        stale,
        matched_total,
        len(window),
        offset + len(window) < matched_total,
    )
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


def _map_auth_error(error: AuthError) -> CliError:
    if error.code == auth_errors.AUTH_REQUIRED:
        return CliError(AUTH_REQUIRED, error.message)
    if error.code == auth_errors.BROWSER_BUSY:
        return CliError(LOCKED, error.message, retryable=True)
    return CliError(BROWSER_UNAVAILABLE, error.message, retryable=True)


def _check_auth(environment: Any) -> None:
    try:
        check_authentication(environment)
    except AuthError as error:
        raise _map_auth_error(error) from error


def _browser_control(environment: Any):
    try:
        return acquire_browser_control(environment.profile, shared=True)
    except AuthError as error:
        raise _map_auth_error(error) from error


def _progress(done: int, total: int) -> None:
    print(f"refresh: collected page {done}/{total}", file=sys.stderr)


def cmd_refresh_cost(args: argparse.Namespace) -> int:
    capability = get_capability(COST)
    config = config_mod.load([capability.source_config_key])
    source = _cdp_source(config, capability.source_config_key)
    store = Cache(config.cache_path)
    ns = namespace(capability.name, capability.default_scope, source.kind)
    with store.refresh_lock():
        environment = resolve_environment(config_mod.config_path().parent)
        control = _browser_control(environment)
        try:
            _check_auth(environment)
            transport = CdpQueryTransport(
                make_transport(environment.cdp_url),
                capability,
                page_url=environment.startup_url,
            )
            try:
                result = collect_mod.collect_scope(
                    capability,
                    transport,
                    capability.default_scope,
                    progress=_progress,
                )
            finally:
                transport.close()
        finally:
            control.release()
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
        store.publish(
            snapshot,
            [(index, canonical(record)) for index, record in enumerate(records, 1)],
        )
    print(f"refresh: published {len(records)} rows to {ns}", file=sys.stderr)
    stale = _stale(snapshot, config.ttl_hours, _now())
    _emit(
        {"namespace": ns, "published": True, "row_count": len(records)},
        _meta_dict(None, snapshot, stale, len(records), len(records), False),
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
    environment = resolve_environment(config_mod.config_path().parent)
    control = _browser_control(environment)
    try:
        _check_auth(environment)
        transport = CdpQueryTransport(
            make_transport(environment.cdp_url),
            capability,
            page_url=environment.startup_url,
        )
        try:
            result = collect_mod.collect_scope(
                capability, transport, capability.default_scope, scalars
            )
        finally:
            transport.close()
    finally:
        control.release()
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
    capability = get_capability(COST)
    limit, offset, fields = _display_options(args)
    config = config_mod.load([capability.source_config_key])
    source = _cdp_source(config, capability.source_config_key)
    filters = _cost_filters(args)
    if args.live:
        return _cmd_cost_list_live(
            args, capability, source, filters, limit, offset, fields
        )
    store = Cache(config.cache_path)
    ns = namespace(capability.name, capability.default_scope, source.kind)
    snapshot, stored = store.read(ns)
    if snapshot is None:
        raise CliError(
            CACHE_MISS,
            "no cached snapshot; run: dogopencli refresh payment cost",
        )
    now = _now()
    stale = _stale(snapshot, config.ttl_hours, now)
    if args.require_fresh and stale:
        raise CliError(
            CACHE_STALE,
            f"cached snapshot is older than {config.ttl_hours:g} hours"
            f" (fetched_at {snapshot.fetched_at})",
        )
    if args.require_complete and not snapshot.backend_complete:
        raise CliError(
            INCOMPLETE_RESULT,
            "cached snapshot does not cover the complete backend scope",
        )
    records = [parse(body) for _, body in stored]
    matched = capability.sort_records(capability.filter_records(records, filters))
    matched_total = len(matched)
    window = matched[offset:] if args.all else matched[offset : offset + limit]
    meta = _meta_dict(
        "cache",
        snapshot,
        stale,
        matched_total,
        len(window),
        offset + len(window) < matched_total,
    )
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
            response = transport.execute(request)
        except FetchFailed as error:
            failure = CliError(
                TIMEOUT,
                f"network failure during business query: {error}",
                retryable=True,
            )
        if failure is None and response is not None:
            if response.status == 200:
                return parse_detail(response.body, baseline_id)
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
        environment = resolve_environment(config_mod.config_path().parent)
        control = _browser_control(environment)
        try:
            _check_auth(environment)
            cdp_transport = make_transport(environment.cdp_url)
            transport = CdpQueryTransport(
                cdp_transport, capability, page_url=environment.startup_url
            )
            detail_transport = CdpQueryTransport(
                cdp_transport, SLA_DETAIL, page_url=environment.startup_url
            )
            try:
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
            finally:
                transport.close()
                detail_transport.close()
        finally:
            control.release()
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
        store.publish(
            snapshot,
            [(index, canonical(row)) for index, row in enumerate(rows, 1)],
        )
    print(f"refresh: published {len(rows)} rows to {ns}", file=sys.stderr)
    stale = _stale(snapshot, config.ttl_hours, _now())
    _emit(
        {"namespace": ns, "published": True, "row_count": len(rows)},
        _meta_dict(None, snapshot, stale, len(rows), len(rows), False),
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
    environment = resolve_environment(config_mod.config_path().parent)
    control = _browser_control(environment)
    try:
        _check_auth(environment)
        transport = CdpQueryTransport(
            make_transport(environment.cdp_url),
            capability,
            page_url=environment.startup_url,
        )
        try:
            result = collect_mod.collect_scope(
                capability, transport, capability.default_scope, scalars
            )
        finally:
            transport.close()
    finally:
        control.release()
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
    store = Cache(config.cache_path)
    ns = namespace(capability.name, capability.default_scope, source.kind)
    snapshot, stored = store.read(ns)
    if snapshot is None:
        raise CliError(
            CACHE_MISS,
            "no cached snapshot; run: dogopencli refresh payment sla",
        )
    now = _now()
    stale = _stale(snapshot, config.ttl_hours, now)
    if args.require_fresh and stale:
        raise CliError(
            CACHE_STALE,
            f"cached snapshot is older than {config.ttl_hours:g} hours"
            f" (fetched_at {snapshot.fetched_at})",
        )
    if args.require_complete and not snapshot.backend_complete:
        raise CliError(
            INCOMPLETE_RESULT,
            "cached snapshot does not cover the complete backend scope",
        )
    records = [parse(body)["baseline"] for _, body in stored]
    matched = capability.sort_records(capability.filter_records(records, filters))
    matched_total = len(matched)
    window = matched[offset:] if args.all else matched[offset : offset + limit]
    meta = _meta_dict(
        "cache",
        snapshot,
        stale,
        matched_total,
        len(window),
        offset + len(window) < matched_total,
    )
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
        environment = resolve_environment(config_mod.config_path().parent)
        control = _browser_control(environment)
        try:
            _check_auth(environment)
            transport = CdpQueryTransport(
                make_transport(environment.cdp_url),
                SLA_DETAIL,
                page_url=environment.startup_url,
            )
            try:
                detail = _fetch_sla_detail(
                    transport,
                    args.id,
                    collect_mod._monotonic() + collect_mod.REFRESH_BUDGET_SECONDS,
                )
            finally:
                transport.close()
        finally:
            control.release()
        meta = _live_meta(source, capability.default_scope, True, 1, 1, 0)
        return _emit_object(args, capability, detail, meta, fields)
    store = Cache(config.cache_path)
    ns = namespace(capability.name, capability.default_scope, source.kind)
    snapshot, stored = store.read(ns)
    if snapshot is None:
        raise CliError(
            CACHE_MISS,
            "no cached snapshot; run: dogopencli refresh payment sla",
        )
    now = _now()
    stale = _stale(snapshot, config.ttl_hours, now)
    if args.require_fresh and stale:
        raise CliError(
            CACHE_STALE,
            f"cached snapshot is older than {config.ttl_hours:g} hours"
            f" (fetched_at {snapshot.fetched_at})",
        )
    if args.require_complete and not snapshot.backend_complete:
        raise CliError(
            INCOMPLETE_RESULT,
            "cached snapshot does not cover the complete backend scope",
        )
    detail: dict[str, Any] | None = None
    for _, body in stored:
        row = parse(body)
        if row["id"] == args.id:
            detail = row["detail"]
            break
    if detail is None:
        raise CliError(
            NOT_FOUND,
            f"SLA baseline {args.id} is not present in the cached snapshot",
        )
    meta = _meta_dict("cache", snapshot, stale, 1, 1, False)
    return _emit_object(args, capability, detail, meta, fields)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dogopencli",
        description="Inquiry-only CLI for the payment product operations platform.",
    )
    parser.add_argument(
        "--version", action="version", version=f"dogopencli {__version__}"
    )
    groups = parser.add_subparsers(dest="group", required=True)

    refresh = groups.add_parser("refresh", help="explicitly rebuild local caches")
    refresh_domains = refresh.add_subparsers(dest="domain", required=True)
    refresh_payment = refresh_domains.add_parser("payment")
    refresh_targets = refresh_payment.add_subparsers(dest="target", required=True)
    refresh_channel = refresh_targets.add_parser(
        "channel", help="import the configured channel source into the cache"
    )
    refresh_channel.add_argument("--payout-type", choices=SCOPES, default="EXTERNAL")
    refresh_targets.add_parser(
        "cost", help="rebuild the payment cost cache through the CDP session"
    )
    refresh_targets.add_parser(
        "sla", help="rebuild the payment SLA baseline cache through the CDP session"
    )

    payment = groups.add_parser("payment", help="payment product queries")
    payment_targets = payment.add_subparsers(dest="target", required=True)
    channel = payment_targets.add_parser("channel", help="payment channel queries")
    channel_actions = channel.add_subparsers(dest="action", required=True)
    listing = channel_actions.add_parser(
        "list", help="list channels from the local cache"
    )
    listing.add_argument("--payout-type", choices=SCOPES, default="EXTERNAL")
    listing.add_argument("--financial-inst-id", action="append", default=[])
    listing.add_argument("--debit-inst-country-code", action="append", default=[])
    listing.add_argument("--status", choices=STATUSES, action="append", default=[])
    listing.add_argument("--debit-account-name", action="append", default=[])
    listing.add_argument("--debit-account-no", action="append", default=[])
    listing.add_argument("--clearing-system-name", action="append", default=[])
    listing.add_argument("--debit-currency", action="append", default=[])
    listing.add_argument("--credit-currency", action="append", default=[])
    listing.add_argument("--limit", type=int, default=None)
    listing.add_argument("--offset", type=int, default=None)
    listing.add_argument("--all", action="store_true")
    listing.add_argument("--live", action="store_true")
    listing.add_argument("--require-fresh", action="store_true")
    listing.add_argument("--require-complete", action="store_true")
    listing.add_argument("--format", choices=("json", "table"), default="json")
    listing.add_argument("--fields", default=None)

    cost = payment_targets.add_parser("cost", help="payment cost queries")
    cost_actions = cost.add_subparsers(dest="action", required=True)
    cost_listing = cost_actions.add_parser(
        "list", help="list cost configurations from the local cache or live"
    )
    cost_listing.add_argument("--legal-entity-code", action="append", default=[])
    cost_listing.add_argument("--financial-inst-code", action="append", default=[])
    cost_listing.add_argument("--bank-account", action="append", default=[])
    cost_listing.add_argument("--trans-currency-code", action="append", default=[])
    cost_listing.add_argument("--charge-bearer", action="append", default=[])
    cost_listing.add_argument("--clearing-network-name", action="append", default=[])
    cost_listing.add_argument("--limit", type=int, default=None)
    cost_listing.add_argument("--offset", type=int, default=None)
    cost_listing.add_argument("--all", action="store_true")
    cost_listing.add_argument("--live", action="store_true")
    cost_listing.add_argument("--require-fresh", action="store_true")
    cost_listing.add_argument("--require-complete", action="store_true")
    cost_listing.add_argument("--format", choices=("json", "table"), default="json")
    cost_listing.add_argument("--fields", default=None)

    sla = payment_targets.add_parser("sla", help="payment SLA baseline queries")
    sla_collections = sla.add_subparsers(dest="collection", required=True)
    baselines = sla_collections.add_parser(
        "baselines", help="SLA baseline list and detail queries"
    )
    sla_actions = baselines.add_subparsers(dest="action", required=True)
    sla_listing = sla_actions.add_parser(
        "list", help="list SLA baselines from the local cache or live"
    )
    sla_listing.add_argument("--biz-category", action="append", default=[])
    sla_listing.add_argument("--creditor-currency", action="append", default=[])
    sla_listing.add_argument("--region-code", action="append", default=[])
    sla_listing.add_argument("--status", action="append", default=[])
    sla_listing.add_argument(
        "--biz-legal-entity",
        action="append",
        default=[],
        help="live passthrough only; independent filter effect unverified",
    )
    sla_listing.add_argument("--limit", type=int, default=None)
    sla_listing.add_argument("--offset", type=int, default=None)
    sla_listing.add_argument("--all", action="store_true")
    sla_listing.add_argument("--live", action="store_true")
    sla_listing.add_argument("--require-fresh", action="store_true")
    sla_listing.add_argument("--require-complete", action="store_true")
    sla_listing.add_argument("--format", choices=("json", "table"), default="json")
    sla_listing.add_argument("--fields", default=None)
    sla_get = sla_actions.add_parser(
        "get", help="show one SLA baseline detail from the local cache or live"
    )
    sla_get.add_argument("--id", required=True)
    sla_get.add_argument("--live", action="store_true")
    sla_get.add_argument("--require-fresh", action="store_true")
    sla_get.add_argument("--require-complete", action="store_true")
    sla_get.add_argument("--format", choices=("json", "table"), default="json")
    sla_get.add_argument("--fields", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    token = _auth_command_token(values)
    if token in AUTH_COMMANDS:
        # Authentication follows the DI-aligned envelope protocol (ADR 0004),
        # an explicit exception to the business data/meta/error protocol.
        from .auth.cli import main as auth_main

        return auth_main(values, command_hint=token)
    args = build_parser().parse_args(values)
    try:
        if args.group == "refresh":
            if args.target == "cost":
                return cmd_refresh_cost(args)
            if args.target == "sla":
                return cmd_refresh_sla(args)
            return cmd_refresh_channel(args)
        if args.target == "cost":
            return cmd_cost_list(args)
        if args.target == "sla":
            if args.action == "get":
                return cmd_sla_get(args)
            return cmd_sla_list(args)
        return cmd_channel_list(args)
    except CliError as error:
        return _emit_error(error, getattr(args, "format", "json"))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
