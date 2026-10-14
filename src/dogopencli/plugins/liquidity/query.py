"""Offline replay of one temporary leaf result; bounded explicit live inquiries."""

import argparse
import re
import shlex
import sys
from dataclasses import replace
from typing import Any

from dogopencli.plugins.liquidity.balance_view import (
    export_balance_record,
    export_field_name,
    latest_statement_rows,
    update_notice,
)

from ... import config as config_mod
from ...cache import Cache
from ...cached_query import is_stale
from ...errors import (
    BUSINESS_QUERY_FAILED,
    CACHE_MISS,
    CACHE_STALE,
    EXIT_FAILURE,
    EXIT_OK,
    EXIT_USAGE,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    UNSUPPORTED_CAPABILITY,
    CliError,
)
from ...inquiry import inquiry_session
from ...result_policy import evidence_for, prepare_result
from ...table import render_table
from ...transport.cdp import CdpQueryTransport
from ..envelope import is_business_refusal
from . import spec as spec_mod
from . import store as capture_store
from .capability import LiquidityListCapability
from .cash_balances import selection
from .collect import acquire_liquidity_list
from .common import emit, identity_values, load_config, now, provided, scope_flags
from .leaves import DEFERRED_BY_PATH, DetailLeaf, ListLeaf, detail_leaf, list_leaf
from .qualified_getters import detail_context_meta


def _display_options(args):
    from ...temporary_query import display_options

    return display_options(args)


def _project(
    window: list[dict[str, Any]], fields: list[str] | None
) -> list[dict[str, Any]]:
    if fields is None:
        return window
    return [
        {name: record[name] for name in fields if name in record} for record in window
    ]


def _emit_window(
    args: argparse.Namespace,
    columns: tuple[str, ...],
    window: list[dict[str, Any]],
    meta: dict[str, Any],
    fields: list[str] | None,
    error: dict[str, Any] | None = None,
    *,
    variant: spec_mod.ListSpec | None = None,
    changed_groups: int = 0,
) -> int:
    if variant is not None and variant.path == ("investment", "interest-rates"):
        from .interest_rates import metadata

        meta.update(metadata(variant))
    try:
        meta = prepare_result(
            meta,
            require_complete=args.require_complete,
            mode="live" if args.live else "cache",
        )
    except CliError as error:
        if variant is not None and variant.path == ("cash", "accounts"):
            error.meta = {**meta, **(error.meta or {})}
        raise
    if variant is not None and variant.path == ("cash", "balances"):
        daily = variant.endpoint == "/balStatisticalQuery.json"
        window = [export_balance_record(record, daily=daily) for record in window]
        columns = tuple(export_field_name(name, daily=daily) for name in columns)
        if fields is not None:
            fields = [export_field_name(name, daily=daily) for name in fields]
        notice = update_notice(changed_groups)
        if notice is not None:
            meta["warnings"] = [*meta.get("warnings", []), notice]
            print(f"warning: {notice['code']}: {notice['message']}", file=sys.stderr)
    window = _project(window, fields)
    if args.format == "table":
        selected = tuple(fields) if fields is not None else columns
        sys.stdout.write(render_table(window, selected, meta) + "\n")
    else:
        emit(window, meta, error)
    return EXIT_FAILURE if error is not None else EXIT_OK


def _emit_object(
    args: argparse.Namespace,
    columns: tuple[str, ...],
    record: Any,
    meta: dict[str, Any],
    fields: list[str] | None,
) -> int:
    if args.format == "table" and isinstance(record, dict):
        rows = _project([record], fields)
        selected = tuple(fields) if fields is not None else columns
        if "components" in meta:
            from ...jsonutil import canonical

            sys.stdout.write("components: " + canonical(meta["components"]) + "\n")
            sys.stdout.write(
                "Nested associations are shown as JSON cells when selected.\n"
            )
        sys.stdout.write(render_table(rows, selected, meta) + "\n")
    else:
        if fields is not None and isinstance(record, dict):
            record = _project([record], fields)[0]
        emit(record, meta)
    return EXIT_OK


def _local_filters(
    args: argparse.Namespace, variant: spec_mod.ListSpec
) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for entry in variant.filters:
        flag, field = entry[0], entry[1]
        public = entry[2] if len(entry) > 2 else "--" + flag.replace("_", "-")
        values = getattr(args, flag, [])
        if any(not value.strip() for value in values):
            raise CliError(
                INVALID_ARGUMENT,
                f"{public} must be nonempty",
                exit_code=EXIT_USAGE,
            )
        if values:
            filters[field] = list(values)
    return filters


def _matches(record: dict[str, Any], filters: dict[str, list[str]]) -> bool:
    return all(record.get(field) in values for field, values in filters.items())


def _match(
    records: list[dict[str, Any]], filters: dict[str, list[str]]
) -> list[dict[str, Any]]:
    return [record for record in records if _matches(record, filters)]


def slot_leaf(leaf):
    return "liquidity." + ".".join(leaf.path)


def resolve_online_scope(leaf, args):
    values = provided(args, scope_flags(leaf))
    any_options = [
        key
        for key, value in values.items()
        if value == "ANY" or isinstance(value, list) and "ANY" in value
    ]
    frozen = None
    if any_options:
        if (
            leaf.path != ("cash", "balances")
            or any_options != ["entity"]
            or values["entity"] != ["ANY"]
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "ANY supports only cash balances --entity ANY, without"
                " explicit entities",
                exit_code=EXIT_USAGE,
            )
        from ...duckdog import resolve_selector

        entities = resolve_selector(
            "liquidity/reference/entities",
            "instId",
            config_file=config_mod.config_path(),
        )
        values["entity"] = entities
        frozen = {
            "mode": "ANY",
            "selector": "liquidity/reference/entities",
            "column": "instId",
            "values": entities,
        }
    resolved = leaf.resolve(values)
    if frozen is not None:
        request = {**resolved.request_values, "__selection": frozen}
        from .capability import encode_scope

        resolved = replace(
            resolved, request_values=request, request_scope=encode_scope(request)
        )
    return resolved


def _offline_selection(args, leaf, variant, context, records):
    from .capability import scope_values

    explicit = {
        key: value
        for key, value in provided(args, scope_flags(leaf)).items()
        if value is not None and value != []
    }
    if getattr(args, "page_size", None) is not None:
        raise CliError(
            INVALID_ARGUMENT,
            "--page-size requires --live or refresh",
            exit_code=EXIT_USAGE,
        )
    source = context.get("query", {})
    selection_meta = context.get("selection")
    if explicit.get("entity") == ["ANY"]:
        if not selection_meta or selection_meta.get("mode") != "ANY":
            raise CliError(
                INVALID_ARGUMENT,
                "cached ANY selection unavailable; omit ANY for replay or"
                " use --live --entity ANY",
                exit_code=EXIT_USAGE,
            )
        explicit["entity"] = selection_meta["values"]
    elif any(
        value == "ANY" or isinstance(value, list) and "ANY" in value
        for value in explicit.values()
    ):
        raise CliError(
            INVALID_ARGUMENT,
            "unsupported offline ANY; omit ANY or use --live",
            exit_code=EXIT_USAGE,
        )
    options = {option.flag: option for option in variant.scope_options}
    if set(explicit) - set(options):
        raise CliError(
            INVALID_ARGUMENT,
            "filter unavailable for saved contract variant; use --live or refresh",
            exit_code=EXIT_USAGE,
        )
    if any(option.window for option in options.values()) and any(
        options[key].window for key in explicit
    ):
        supplied_windows = {key for key in explicit if options[key].window}
        required_windows = {key for key, option in options.items() if option.window}
        if supplied_windows != required_windows:
            raise CliError(
                INVALID_ARGUMENT,
                "date bounds must be provided together",
                exit_code=EXIT_USAGE,
            )
    normalized, requested_window = scope_values(
        tuple(
            replace(option, required=False, default=None)
            for option in variant.scope_options
        ),
        explicit,
    )
    mapping = {entry[0]: entry[1] for entry in variant.filters}
    mapping.update(
        {
            ("cash", "waterlevels"): {"account": "aliasName"},
            ("forecast", "cashflows"): {
                "account": "bankAccountAliasName",
                "currency": "currency",
            },
            ("forecast", "results"): {"account": "bankAccountAliasName"},
            ("forecast", "accuracy"): {"account": "bankAccountAliasName"},
            ("operations", "prefunds"): {"status": "status"},
        }.get(leaf.path, {})
    )
    mapping.update(
        {"entity": "entity", "account": "aliasName"}
        if leaf.path == ("cash", "balances")
        else {}
    )
    coverage = True
    rows = records
    for key in explicit:
        option = options[key]
        if key == "timezone":
            raise CliError(
                INVALID_ARGUMENT,
                "--timezone is source-only; use --live or refresh",
                exit_code=EXIT_USAGE,
            )
        value = normalized.get(option.field)
        acquired = source.get(option.field)
        if option.virtual and option.match:
            if value != acquired:
                raise CliError(
                    INVALID_ARGUMENT,
                    "filter differs from saved contract variant; use --live or refresh",
                    exit_code=EXIT_USAGE,
                )
            continue
        if option.window:
            if not variant.series_field or variant.profile != spec_mod.PROFILE_DATED:
                raise CliError(
                    INVALID_ARGUMENT,
                    "date filter unavailable for saved variant; use --live or refresh",
                    exit_code=EXIT_USAGE,
                )
            bound = str(value).replace("-", "")[:8]
            if acquired is None:
                coverage = None
            elif (
                option.window == "from"
                and str(value) < str(acquired)
                or option.window == "to"
                and str(value) > str(acquired)
            ):
                coverage = False
            rows = [
                row
                for row in rows
                if (
                    capture_store.series_value(variant, row, "") >= bound
                    if option.window == "from"
                    else capture_store.series_value(variant, row, "") <= bound
                    if option.window == "to"
                    else capture_store.series_value(variant, row, "") == bound
                )
            ]
            continue
        field = mapping.get(key)
        if field is None and option.field in variant.table_columns:
            field = option.field
        if field is None:
            raise CliError(
                INVALID_ARGUMENT,
                f"{option.public_flag} has no reliable local row mapping; use"
                " --live or refresh",
                exit_code=EXIT_USAGE,
            )
        values = value if isinstance(value, list) else [value]
        old = acquired if isinstance(acquired, list) else [acquired]
        if acquired is None:
            coverage = None if coverage is not False else False
        elif not set(values).issubset(set(old)):
            coverage = False
        rows = [row for row in rows if row.get(field) in values]
    filters = _local_filters(args, variant)
    explicit.update(
        {
            entry[0]: getattr(args, entry[0], [])
            for entry in variant.filters
            if getattr(args, entry[0], [])
        }
    )
    return _match(rows, filters), explicit, coverage, requested_window


def _validate_cached_rows(leaf, variant, context, records):
    from .capability import encode_scope
    from .projection import _validate_amounts, project_record

    capability = leaf.capability(variant)
    scope = context.get("query")
    if not isinstance(scope, dict):
        raise CliError(INVALID_RESPONSE, "cached acquisition scope is invalid")
    seen = set()
    for record in records:
        identity = capability.identity_key(record)
        if variant.identity and identity in seen:
            raise CliError(
                INVALID_RESPONSE, "cached result has duplicate native identities"
            )
        seen.add(identity)
        if variant.projection:
            validated_record = record
            if variant.projection == "rule_status" and "tntInstId" not in record:
                # Native tenant was verified before publication and deliberately
                # excluded by this leaf's public projection.
                validated_record = {**record, "tntInstId": "GUAPW3SG"}
            project_record(variant.projection, validated_record)
        if variant.endpoint == "/balStatisticalQuery.json":
            if "balance" not in record:
                raise CliError(
                    INVALID_RESPONSE, "cached daily balance is missing source balance"
                )
            _validate_amounts(record, ("balance",), "daily_balances")
        if variant.profile == spec_mod.PROFILE_DATED:
            capture_store.series_value(variant, record, "")
    capability.validate_rows_scope(records, encode_scope(scope))
    if variant.projection == "balances":
        latest_statement_rows(records)


def run_list(args):
    from ...result_policy import AcquisitionEvidence
    from ...temporary_query import read_slot, slot_context, window_rows

    leaf = list_leaf(args.command_path[1:-1])
    limit, offset, fields = _display_options(args)
    if not args.live and getattr(args, "page_size", None) is not None:
        raise CliError(
            INVALID_ARGUMENT,
            "--page-size requires --live or refresh",
            exit_code=EXIT_USAGE,
        )
    config = load_config()
    if args.live:
        resolved = resolve_online_scope(leaf, args)
        capability = leaf.acquisition_capability(
            resolved.spec, getattr(args, "page_size", None), online=True
        )
        return _run_list_live(
            args,
            leaf,
            resolved,
            _local_filters(args, resolved.spec),
            limit,
            offset,
            fields,
            config,
            capability,
        )
    from .capability import scope_values

    explicit = {
        key: value
        for key, value in provided(args, scope_flags(leaf)).items()
        if value is not None and value != []
    }
    normalized, _ = scope_values(
        tuple(replace(option, required=False, default=None) for option in leaf.options),
        explicit,
    )
    snapshot, records = read_slot(Cache(config.cache_path), slot_leaf(leaf))
    if snapshot is None:
        raise CliError(
            CACHE_MISS,
            "no cached liquidity result; run: dogopencli refresh liquidity "
            + " ".join(leaf.path)
            + _hint_options(leaf, normalized),
        )
    context = slot_context(snapshot)
    variant = next(
        (item for item in leaf.variants if item.endpoint == context.get("variant")),
        None,
    )
    if variant is None:
        raise CliError(
            INVALID_RESPONSE, "cached contract variant is invalid; refresh required"
        )
    if leaf.path == ("cash", "accounts"):
        from .unified_accounts import validate_cached_accounts

        account_quality = validate_cached_accounts(
            records, AcquisitionEvidence.from_record(snapshot.acquisition)
        )
    else:
        account_quality = {}
    if leaf.path == ("investment", "interest-rates"):
        expected_source = next(
            option.match for option in variant.scope_options if option.flag == "source"
        )
        if context.get("query", {}).get("source") != expected_source:
            raise CliError(
                INVALID_RESPONSE,
                "cached interest-rate source identity is untrustworthy;"
                " explicit refresh required",
            )
    _validate_cached_rows(leaf, variant, context, records)
    rows, filters, coverage, requested_window = _offline_selection(
        args, leaf, variant, context, records
    )
    evidence = AcquisitionEvidence.from_record(snapshot.acquisition)
    source_acquisition = evidence.record()
    if coverage is not True:
        evidence = replace(
            evidence,
            scope_complete=False,
            dataset_complete=False,
            reasons=tuple(
                dict.fromkeys([*evidence.reasons, "REQUESTED_SCOPE_UNPROVEN"])
            ),
        )
    stale = is_stale(snapshot, config.ttl_hours, now())
    if args.require_fresh and stale:
        raise CliError(CACHE_STALE, "cached result is stale; refresh required")
    changed_groups = 0
    if variant.projection == "balances":
        rows, changed_groups = latest_statement_rows(rows)
    window = window_rows(rows, limit, offset)
    meta = {
        "source": "cache",
        "simulated": False,
        "dataset_id": None,
        "source_observed_from": None,
        "source_observed_to": None,
        "loaded_at": snapshot.loaded_at,
        "backend": "cdp",
        "kind": variant.kind,
        "capability": variant.name,
        "variant": variant.endpoint,
        "query": context.get("query"),
        "scope": context.get("query"),
        "local_filters": filters,
        "requested_window": list(requested_window)
        if requested_window[0] is not None
        else None,
        "requested_scope_covered": coverage,
        "source_acquisition": source_acquisition,
        **account_quality,
        "snapshot_id": snapshot.snapshot_id,
        "fetched_at": snapshot.fetched_at,
        "stale": stale,
        **evidence.meta(),
        "matched_total": len(rows),
        "returned_count": len(window),
        "has_more": offset + len(window) < len(rows),
    }
    if not rows:
        meta["cache_only_explanation"] = (
            "No matching records in the saved acquisition; backend"
            " absence is not established."
        )
    if context.get("selection"):
        meta["selection"] = context["selection"]
    return _emit_window(
        args,
        variant.table_columns,
        window,
        meta,
        fields,
        variant=variant,
        changed_groups=changed_groups,
    )


def _public_hint_value(option: spec_mod.ScopeOption, value: Any) -> str:
    """Inverse of public normalization: internal value to public form (#127).

    Hints print canonical spellings: ISO calendar dates, colon clocks, and
    T-form datetimes (Z for the verified-UTC rule-status interval), so a
    parsed hint re-resolves to the identical scope.
    """
    text = str(value)
    if option.date:
        match = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})", text)
        if match:
            return "-".join(match.groups())
        expanded = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}", text)
        if expanded:  # day-start/day-end expansion inverts to its day
            return expanded.group(1)
        return text
    if option.time:
        match = re.fullmatch(r"(\d{2})(\d{2})(\d{2})", text)
        if match:
            return ":".join(match.groups())
        return text
    if option.datetime_zone is not None:
        naive = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})", text)
        if naive:
            suffix = "Z" if option.datetime_zone == "utc" else ""
            return f"{naive.group(1)}T{naive.group(2)}{suffix}"
        return text
    return text


def _hint_options(leaf: ListLeaf, values: dict[str, Any]) -> str:
    parts = []
    for option in leaf.options:
        value = values.get(option.field)
        if value is None:
            continue
        flag = option.public_flag
        items = value if isinstance(value, list) else [value]
        parts.extend(
            f"{flag} {shlex.quote(_public_hint_value(option, item))}" for item in items
        )
    return (" " + " ".join(parts)) if parts else ""


def _run_list_live(
    args: argparse.Namespace,
    leaf: ListLeaf,
    resolved: Any,
    filters: dict[str, list[str]],
    limit: int,
    offset: int,
    fields: list[str] | None,
    config: config_mod.Config,
    capability: LiquidityListCapability,
) -> int:
    variant = resolved.spec
    unit = "chunk" if variant.endpoint == "/balStatisticalQuery.json" else "page"
    with inquiry_session(
        config_file=config_mod.config_path(), startup_url=capability.page_url
    ) as session:
        result = acquire_liquidity_list(
            session,
            capability,
            resolved.request_scope,
            progress=lambda done, total: print(
                f"live: collected {unit} {done}/{total}", file=sys.stderr
            ),
        )
    evidence = evidence_for(result)
    rows = result.records
    changed_groups = 0
    if variant.projection == "balances":
        rows, changed_groups = latest_statement_rows(rows)
    rows = _match(rows, filters)
    matched_total = len(rows)
    window = rows[offset:] if limit == 0 else rows[offset : offset + limit]
    meta = {
        "source": "live",
        "backend": "cdp",
        "kind": variant.kind,
        "simulated": False,
        "capability": variant.name,
        "scope": resolved.request_values,
        "query": resolved.request_values,
        "variant": variant.endpoint,
        "requested_window": (
            list(resolved.window) if resolved.window[0] is not None else None
        ),
        "snapshot_id": None,
        "dataset_id": None,
        "fetched_at": now().isoformat(),
        "loaded_at": None,
        "stale": False,
        **evidence.meta(),
        "source_observed_from": None,
        "source_observed_to": None,
        "reported_total": result.total_count,
        "matched_total": matched_total,
        "returned_count": len(window),
        "has_more": offset + len(window) < matched_total,
    }
    if leaf.path == ("cash", "accounts"):
        from .unified_accounts import account_meta

        meta.update(account_meta(evidence))
    frozen = selection(evidence)
    if frozen is not None:
        meta["selection"] = frozen
    return _emit_window(
        args,
        variant.table_columns,
        window,
        meta,
        fields,
        variant=variant,
        changed_groups=changed_groups,
    )


def run_detail(args: argparse.Namespace) -> int:
    leaf = detail_leaf(args.command_path[1:])
    detail = leaf.spec
    if detail.path == ("investment", "interest-rates"):
        from .interest_rates import SOURCES

        source = getattr(args, "source", None)
        if source not in SOURCES:
            raise CliError(
                INVALID_ARGUMENT,
                "get requires an explicit recognized --source",
                exit_code=EXIT_USAGE,
            )
        if source != "expection":
            raise CliError(
                UNSUPPORTED_CAPABILITY,
                "genuine interest-rate get supports only expection",
            )
    values = identity_values(args, leaf)
    # Validation of required/typed identity happens in detail_body.
    leaf.capability.detail_body(values)
    fields: list[str] | None = None
    if args.fields is not None:
        fields = [name.strip() for name in args.fields.split(",") if name.strip()]
        if not fields:
            raise CliError(
                INVALID_ARGUMENT,
                "--fields must name at least one field",
                exit_code=EXIT_USAGE,
            )
    with inquiry_session(
        config_file=config_mod.config_path(), startup_url=leaf.capability.page_url
    ) as session:
        from .decision_history import fetch_native_detail

        deadline = None
        if detail.name in (
            "liquidity.network.realtime.get",
            "liquidity.operations.prefunds.get",
        ):
            from ... import collect as collect_mod

            deadline = collect_mod._monotonic() + collect_mod.REFRESH_BUDGET_SECONDS
            if detail.name == "liquidity.operations.prefunds.get":
                from .prefund_detail import fetch_selected

                payload, application_reported = fetch_selected(
                    session, leaf, values, deadline=deadline
                )
            else:
                payload = fetch_detail(
                    session.transport(leaf.capability), leaf, values, deadline=deadline
                )
        else:
            payload = fetch_native_detail(session, leaf, values)
        captured_at = now().isoformat()
        component_meta = {}
        if detail.name == "liquidity.network.realtime.get":
            from .network_detail import component_result

            payload, component_meta = component_result(
                session, payload, captured_at, deadline=deadline
            )
        if detail.name == "liquidity.operations.prefunds.get":
            from .prefund_detail import component_result

            payload, component_meta = component_result(
                session,
                payload,
                captured_at,
                deadline=deadline,
                application_reported=application_reported,
            )
    meta = {
        "source": "live",
        "backend": "cdp",
        "kind": detail.kind,
        "simulated": False,
        "capability": detail.name,
        "identity": dict(values),
        "fetched_at": captured_at,
        "loaded_at": None,
        "stale": False,
        "complete": True,
        "dataset_complete": None,
        "matched_total": 1,
        "returned_count": 1,
        "has_more": False,
    }
    if detail.path == ("investment", "interest-rates"):
        meta.update(
            {
                "rate_source": "expection",
                "contract": detail.endpoint,
                "raw_rate_units": "unconfirmed; no scale conversion",
            }
        )
    if detail.schema_version:
        meta["request_scope"] = (
            {"tntInstId": spec_mod.TENANT} if detail.sends_tenant else {}
        )
    if detail.schema_version and isinstance(payload, dict) and "version" in payload:
        meta["source_version"] = payload["version"]
    meta.update(detail_context_meta(detail, values, payload))
    if detail.name in (
        "liquidity.network.realtime.get",
        "liquidity.operations.prefunds.get",
    ):
        meta.update(component_meta)
        try:
            meta = prepare_result(
                meta,
                require_complete=getattr(args, "require_complete", False),
                mode="live",
            )
        except CliError as error:
            error.meta = {**meta, **(error.meta or {})}
            raise
    return _emit_object(args, detail.table_columns, payload, meta, fields)


def fetch_detail(
    transport: CdpQueryTransport,
    leaf: DetailLeaf,
    values: dict[str, str],
    *,
    deadline: float | None = None,
) -> Any:
    from ... import collect as collect_mod

    response = collect_mod.execute_bounded(
        leaf.capability, transport, leaf.capability.detail_body(values), deadline
    )
    if is_business_refusal(response.body):
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return leaf.capability.parse_detail(response.body, values)


def run_unsupported(args: argparse.Namespace) -> int:
    from .retirement import retired_command, retirement_reason

    if retired_command(args.command_path):
        raise CliError(UNSUPPORTED_CAPABILITY, retirement_reason(args.command_path))
    leaf = DEFERRED_BY_PATH.get(args.command_path[1:])
    reason = leaf.reason if leaf is not None else "unsupported liquidity leaf"
    raise CliError(
        UNSUPPORTED_CAPABILITY,
        f"{' '.join(args.command_path)} is deferred: {reason}",
    )
