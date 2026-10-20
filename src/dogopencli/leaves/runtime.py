"""Common inquiry, quality and single-slot cache policy for installed leaves."""

import hashlib
import inspect
import math
from argparse import Namespace
from contextlib import nullcontext
from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.collect import (
    collect_list,
    collect_scope,
    collect_sources,
    execute_bounded,
)
from dogopencli.config import DEFAULT_TTL_HOURS, tomllib
from dogopencli.errors import CliError
from dogopencli.inquiry import inquiry_session
from dogopencli.jsonutil import canonical, parse
from dogopencli.result_policy import (
    AcquisitionEvidence,
    check_complete,
    evidence_for,
    prepare_result,
)
from dogopencli.temporary_query import display_options, is_stale, window_rows

from .query import (
    QueryBudget,
    QueryTools,
    query_capabilities,
    validate_detail_lookup,
    validate_detail_result,
)
from .registry import Leaf


def cache_for(config_file: Path) -> Cache:
    return Cache(config_file.parent / "leaf-cache.sqlite3")


def _ttl(config_file: Path) -> float:
    try:
        document = (
            tomllib.loads(config_file.read_text()) if config_file.exists() else {}
        )
        value = document.get("cache", {}).get("ttl_hours", DEFAULT_TTL_HOURS)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError
        return float(value)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise CliError(
            "CONFIG_ERROR",
            "cache.ttl_hours must be a finite nonnegative number",
            exit_code=2,
        ) from exc


def _validate_records(rows: Any, identity: list[str]) -> list[dict]:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise CliError("INVALID_RESPONSE", "records must be business objects")
    seen = set()
    for row in rows:
        if identity:
            if any(field not in row or row[field] is None for field in identity):
                raise CliError("INVALID_RESPONSE", "record identity is missing")
            key = canonical([row[field] for field in identity])
            if key in seen:
                raise CliError("INVALID_RESPONSE", "record identity is duplicated")
            seen.add(key)
    return rows


def _project(rows: list[dict], fields: list[str] | None) -> list[dict]:
    if fields is None:
        return rows
    if any(field not in row for row in rows for field in fields):
        raise CliError(
            "INVALID_ARGUMENT",
            "requested field is absent from a returned record",
            exit_code=2,
        )
    return [{field: row[field] for field in fields} for row in rows]


def _contract_id(leaf: Leaf, capability: Any) -> str:
    def basic(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: basic(item) for key, item in value.items()}
        if isinstance(value, (set, frozenset)):
            return sorted(basic(item) for item in value)
        if isinstance(value, (list, tuple)):
            return [basic(item) for item in value]
        return value

    operations = {
        name: [
            {key: value for key, value in parameter.items() if key != "description"}
            for parameter in operation.get("parameters", [])
        ]
        for name, operation in leaf.manifest["operations"].items()
    }
    context = {
        "identity": leaf.manifest["identity"],
        "operations": operations,
        "adapter_binding": leaf.manifest["adapter"],
        "adapter_sha256": leaf.adapter_sha256,
    }
    custom = {
        name: {
            key: specification[key]
            for key in ("execution", "queries", "max_requests", "budget_seconds")
        }
        for name, specification in leaf.manifest["operations"].items()
        if specification.get("execution") == "custom"
    }
    if custom:
        context["custom"] = custom
    if isinstance(capability, dict):
        context["sources"] = {
            name: {"name": item.name, "native_contract": basic(asdict(item.contract))}
            for name, item in capability.items()
        }
    else:
        context["capability"] = capability.name
        context["native_contract"] = basic(asdict(capability.contract))
    if "collection" in leaf.manifest:
        context["collection"] = leaf.manifest["collection"]
        policies = leaf.manifest["collection"].get(
            "sources", {"list": leaf.manifest["collection"]}
        )
        if any(
            policy["paging"].get("termination") == "short_page"
            for policy in policies.values()
        ):
            # Old first-short-page snapshots cannot prove the stronger stop rule.
            context["short_page_terminal_batches"] = 2
    return hashlib.sha256(canonical(context).encode()).hexdigest()


def _list_capabilities(leaf: Leaf, parameters: dict) -> Any:
    if leaf.manifest["operations"]["list"].get("execution") == "custom":
        return query_capabilities(leaf, "list", parameters)
    sources = leaf.manifest.get("collection", {}).get("sources")
    if sources is None:
        return leaf.adapter.capability(parameters)
    return {name: leaf.adapter.source_capability(name, parameters) for name in sources}


def get_detail(
    leaf: Leaf,
    session: Any,
    parameters: dict,
    identity: str,
    *,
    capability: Any = None,
    deadline: float | None = None,
    query_tools: QueryTools | None = None,
    query_budget: QueryBudget | None = None,
) -> dict | list[dict]:
    """Acquire one validated native root through the restricted host transport."""
    validate_detail_lookup(identity)
    if leaf.manifest["operations"]["get"].get("execution") == "custom":
        tools = query_tools or QueryTools(
            leaf,
            "get",
            parameters,
            capability or query_capabilities(leaf, "get", parameters),
            session.transport,
            deadline=deadline,
            budget=query_budget,
        )
        with tools:
            return tools.finish_get(leaf.adapter.query_get(parameters, identity, tools))
    capability = capability or leaf.adapter.detail_capability(parameters)
    for name, arguments in (
        ("request_body", (parameters, identity)),
        ("parse_detail", (b"", parameters, identity)),
    ):
        method = getattr(capability, name, None)
        try:
            if not callable(method):
                raise TypeError
            inspect.signature(method).bind(*arguments)
        except (TypeError, ValueError) as error:
            raise CliError("INVALID_LEAF", "invalid detail capability hooks") from error
    transport = session.transport(capability)
    try:
        response = execute_bounded(
            capability,
            transport,
            capability.request_body(parameters, identity),
            deadline,
        )
    finally:
        transport.close()
    result = capability.parse_detail(response.body, parameters, identity)
    validate_detail_result(result, leaf.manifest["operations"]["get"])
    return result


def _compose_details(
    leaf: Leaf,
    session: Any,
    rows: list[dict],
    fields: list[str] | None,
    deadline: float,
    offset: int,
) -> list[dict]:
    if leaf.manifest["operations"]["get"].get("result_shape", "object") != "object":
        raise CliError("INVALID_LEAF", "array Get cannot bind to List records")
    binding = leaf.manifest["operations"]["get"]["list_binding"]
    combined = []
    query_budget = None
    get_specification = leaf.manifest["operations"]["get"]
    if get_specification.get("execution") == "custom":
        from dogopencli.collect import _monotonic

        query_budget = QueryBudget(
            min(deadline, _monotonic() + get_specification["budget_seconds"]),
            get_specification["max_requests"],
        )
    for index, row in enumerate(rows, offset + 1):
        try:
            identity = row.get(binding["identity_field"])
            if type(identity) not in (str, int) or not str(identity).strip():
                raise CliError("INVALID_RESPONSE", "List binding identity is invalid")
            parameters = {}
            for definition in leaf.manifest["operations"]["get"]["parameters"]:
                name = definition["name"]
                source = binding.get("parameters", {}).get(name)
                if source is not None:
                    if source not in row:
                        raise CliError(
                            "INVALID_RESPONSE",
                            f"List binding field {source} is missing",
                        )
                    value = row[source]
                elif "default" in definition:
                    value = definition["default"]
                else:
                    continue
                values = value if definition.get("multiple") else [value]
                kind = definition["type"]

                def valid(item: Any, kind: str = kind) -> bool:
                    if kind == "string":
                        return isinstance(item, str)
                    if kind == "boolean":
                        return isinstance(item, bool)
                    if kind == "integer":
                        return type(item) is int
                    return (
                        type(item) is int
                        or (isinstance(item, Decimal) and item.is_finite())
                        or (type(item) is float and math.isfinite(item))
                    )

                if (
                    not isinstance(values, list)
                    or (definition.get("required") and not values)
                    or any(not valid(item) for item in values)
                    or (
                        "choices" in definition
                        and any(item not in definition["choices"] for item in values)
                    )
                ):
                    raise CliError(
                        "INVALID_RESPONSE",
                        f"List binding context {name} has invalid type or choice",
                    )
                parameters[name.replace("-", "_")] = value
            record = get_detail(
                leaf,
                session,
                parameters,
                str(identity),
                deadline=deadline,
                query_budget=query_budget,
            )
            combined.append({"record": _project([row], fields)[0], "detail": record})
        except CliError as error:
            raise CliError(
                error.code,
                f"Detail for output row {index}: {error.message}",
                retryable=error.retryable,
                exit_code=error.exit_code,
                meta={**(error.meta or {}), "detail_row": index},
            ) from error
        except Exception as error:
            raise CliError(
                "INTERNAL_ERROR",
                f"Detail for output row {index}: unexpected detail failure",
                meta={"detail_row": index},
            ) from error
    return combined


def execute(
    leaf: Leaf, operation: str, parameters: dict, args: Namespace, config_file: Path
) -> tuple[Any, dict]:
    """Execute one supported action; publication always uses the full candidate."""

    def now() -> datetime:
        return datetime.now(timezone.utc)

    store = cache_for(config_file)
    namespace = "leaf:" + leaf.id
    limit, offset, fields = display_options(args)
    if operation == "prune":
        with store.refresh_lock():
            removed = store.remove(namespace)
        return {"leaf": leaf.id, "pruned": removed}, {"source": "cache"}
    if operation == "get":
        validate_detail_lookup(args.detail_identity)
        custom_get = leaf.manifest["operations"]["get"].get("execution") == "custom"
        capability = (
            query_capabilities(leaf, "get", parameters)
            if custom_get
            else leaf.adapter.detail_capability(parameters)
        )
        startup = next(iter(capability.values())) if custom_get else capability
        tools = None
        with inquiry_session(
            config_file=config_file, startup_url=startup.page_url
        ) as session:
            if custom_get:
                tools = QueryTools(
                    leaf, "get", parameters, capability, session.transport
                )
            record = get_detail(
                leaf,
                session,
                parameters,
                args.detail_identity,
                capability=capability,
                query_tools=tools,
            )
        is_array = leaf.manifest["operations"]["get"].get("result_shape") == "array"
        rows = record if is_array else [record]
        projected = _project(rows, fields)
        data = projected if is_array else projected[0]
        return data, {
            "source": "live",
            "leaf": leaf.id,
            "operation": "get",
            "query": {"identity": args.detail_identity, "parameters": parameters},
            "fetched_at": now().isoformat(),
            "returned_count": len(rows),
            "detail_scope": "custom" if custom_get else "native_root",
            "detail_coverage": (
                "Leaf-defined custom query; relationships and coverage follow "
                "the declared leaf contract."
                if custom_get
                else "One native root response; separate histories, logs and "
                "child pages are not acquired."
            ),
            **({"query_evidence": tools.evidence()} if tools is not None else {}),
        }
    definitions = leaf.manifest["operations"]["list"].get("parameters", [])
    local_parameters = {
        definition["name"].replace("-", "_")
        for definition in definitions
        if definition.get("local_field")
    }
    live = operation == "refresh" or args.live
    ttl = _ttl(config_file)
    with store.refresh_lock() if operation == "refresh" else nullcontext():
        if operation == "refresh" and leaf.installation_token is not None:
            try:
                status = leaf.path.stat()
                current_token = (status.st_dev, status.st_ino, status.st_ctime_ns)
            except OSError as error:
                raise CliError(
                    "LEAF_NOT_FOUND", "Leaf was removed before refresh started"
                ) from error
            if current_token != leaf.installation_token:
                raise CliError(
                    "LEAF_NOT_FOUND", "Leaf installation changed; run refresh again"
                )
        if live:
            capability = _list_capabilities(leaf, parameters)
            scope = leaf.adapter.scope(parameters)
            try:
                effective_scope = parse(scope)
            except ValueError:
                effective_scope = scope
            contract_id = _contract_id(leaf, capability)
            fetched_at = now().isoformat()
            collection = leaf.manifest.get("collection")
            custom_list = (
                leaf.manifest["operations"]["list"].get("execution") == "custom"
            )
            sources = (
                {
                    name: (item, leaf.adapter.source_scope(name, parameters))
                    for name, item in capability.items()
                }
                if collection is not None and "sources" in collection
                else None
            )
            startup = (
                next(iter(capability.values()))
                if sources is not None or custom_list
                else capability
            )
            with inquiry_session(
                config_file=config_file,
                startup_url=getattr(startup, "page_url", None),
            ) as session:
                if custom_list:
                    with QueryTools(
                        leaf,
                        "list",
                        parameters,
                        capability,
                        session.transport,
                        state_file=config_file.parent / "collection-state.json",
                    ) as tools:
                        collected = tools.finish_list(
                            leaf.adapter.query_list(parameters, tools)
                        )
                elif sources is not None:
                    collected = collect_sources(
                        sources,
                        session.transport,
                        leaf.adapter.assemble,
                        parameters,
                        collection,
                        domain=leaf.domain,
                        leaf_id=leaf.id,
                        state_file=config_file.parent / "collection-state.json",
                    )
                elif collection is not None:
                    transport = session.transport(capability)
                    collected = collect_list(
                        capability,
                        transport,
                        scope,
                        collection,
                        domain=leaf.domain,
                        leaf_id=leaf.id,
                        state_file=config_file.parent / "collection-state.json",
                    )
                else:
                    transport = session.transport(capability)
                    collector = getattr(leaf.adapter, "collector", collect_scope)
                    collected = collector(capability, transport, scope)
                rows = _validate_records(
                    collected.records, leaf.manifest.get("identity", [])
                )
                evidence = evidence_for(collected)
                query = parameters
                stale = False
                check_complete(
                    evidence,
                    require_complete=(
                        args.require_complete
                        or (
                            operation == "refresh"
                            and ("collection" in leaf.manifest or custom_list)
                        )
                    ),
                    mode=operation,
                )
                selected = (
                    leaf.adapter.filter(
                        rows,
                        {
                            key: value
                            for key, value in parameters.items()
                            if key in local_parameters
                        },
                    )
                    if operation == "list"
                    else rows
                )
                window = window_rows(selected, limit, offset)
                _project(window, fields)
                if args.with_detail:
                    details = _compose_details(
                        leaf, session, window, fields, collected.deadline, offset
                    )
            published = operation == "refresh" and bool(rows)
            if published:
                snapshot = SnapshotMeta(
                    namespace=namespace,
                    capability=leaf.id,
                    scope=canonical(
                        {
                            "parameters": query,
                            "native_scope": effective_scope,
                            "contract_id": contract_id,
                        }
                    ),
                    source_kind="cdp",
                    snapshot_id=hashlib.sha256(canonical(rows).encode()).hexdigest(),
                    dataset_id=None,
                    simulated=False,
                    backend_complete=evidence.scope_complete,
                    dataset_complete=evidence.dataset_complete,
                    fetched_at=fetched_at,
                    loaded_at=fetched_at,
                    source_observed_from=None,
                    source_observed_to=None,
                    row_count=len(rows),
                    acquisition=evidence.record(),
                )
                store.publish(
                    snapshot,
                    [(index, canonical(row)) for index, row in enumerate(rows, 1)],
                )
            rows = selected
        else:
            snapshot, stored = store.read(namespace)
            if snapshot is None:
                raise CliError(
                    "CACHE_MISS",
                    f"no cached snapshot; run: dogopencli {leaf.domain} "
                    f"refresh {leaf.name}",
                )
            try:
                rows = _validate_records(
                    [parse(body) for _, body in stored],
                    leaf.manifest.get("identity", []),
                )
                context = parse(snapshot.scope)
                query = context["parameters"]
                effective_scope = context["native_scope"]
                contract_id = context["contract_id"]
                if (
                    not isinstance(query, dict)
                    or len(rows) != snapshot.row_count
                    or [i for i, _ in stored] != list(range(1, len(rows) + 1))
                ):
                    raise ValueError
            except (ValueError, TypeError, KeyError) as exc:
                raise CliError(
                    "INVALID_RESPONSE", "cached snapshot is invalid"
                ) from exc
            capability = _list_capabilities(leaf, query)
            if contract_id != _contract_id(leaf, capability):
                raise CliError(
                    "CACHE_CONTRACT_CHANGED",
                    "Leaf contract changed; refresh before replay",
                )
            evidence = AcquisitionEvidence.from_record(snapshot.acquisition)
            fetched_at = snapshot.fetched_at
            stale = is_stale(snapshot, ttl, now())
            if args.require_fresh and stale:
                raise CliError("CACHE_STALE", "saved acquisition is stale")
            check_complete(
                evidence, require_complete=args.require_complete, mode="cache"
            )
            for definition in definitions:
                key = definition["name"].replace("-", "_")
                if key in args.explicit_parameters and not definition.get(
                    "local_field"
                ):
                    raise CliError(
                        "INVALID_ARGUMENT",
                        f"--{definition['name']} has no supported offline filter",
                        exit_code=2,
                    )
            rows = leaf.adapter.filter(
                rows,
                {
                    key: value
                    for key, value in parameters.items()
                    if key in args.explicit_parameters
                },
            )
        matched = len(rows)
        displayed = (
            details
            if args.with_detail
            else _project(window_rows(rows, limit, offset), fields)
        )
        source_acquisition = evidence.record()
        requested_coverage = True
        if not live:
            requested_parameters = {
                **query,
                **{
                    key: value
                    for key, value in parameters.items()
                    if key in args.explicit_parameters
                },
            }
            same_native_scope = leaf.adapter.scope(
                requested_parameters
            ) == leaf.adapter.scope(query)
            requested_coverage = all(
                key not in args.explicit_parameters
                or (key in local_parameters and same_native_scope)
                or parameters.get(key) == value
                or canonical(parameters.get(key)) == canonical(value)
                for key, value in query.items()
            )
            if not requested_coverage:
                evidence = replace(
                    evidence,
                    scope_complete=False,
                    reasons=tuple(
                        dict.fromkeys((*evidence.reasons, "COVERAGE_UNPROVEN"))
                    ),
                )
                check_complete(
                    evidence, require_complete=args.require_complete, mode="cache"
                )
        meta = {
            "leaf": leaf.id,
            "operation": operation,
            "source": "live" if live else "cache",
            "backend": "cdp",
            "simulated": False,
            "query": query,
            "scope": effective_scope,
            "contract_id": contract_id,
            "fetched_at": fetched_at,
            "stale": stale,
            "matched_total": matched,
            "returned_count": len(displayed),
            "has_more": offset + len(displayed) < matched,
            **evidence.meta(),
            "unique_count": evidence.unique_count,
            "duplicate_count": evidence.duplicate_count,
            "total_semantics": evidence.total_semantics,
        }
        if args.with_detail:
            custom_detail = (
                leaf.manifest["operations"]["get"].get("execution") == "custom"
            )
            meta.update(
                {
                    "with_detail": True,
                    "detail_scope": "custom" if custom_detail else "native_root",
                    "detail_count": len(displayed),
                    "detail_window": {"offset": offset, "limit": limit},
                    "detail_coverage": (
                        "Only selected List rows; each custom Get follows its "
                        "declared leaf relationship and coverage contract. "
                        "Detail success does not expand List coverage."
                        if custom_detail
                        else "Only selected List rows; "
                        "one native root response per row. "
                        "Separate histories, logs and child pages are not acquired. "
                        "Detail success does not expand List coverage."
                    ),
                }
            )
        if not live:
            meta["source_acquisition"] = source_acquisition
            meta["requested_coverage"] = requested_coverage
            meta["local_filters"] = {
                key: value
                for key, value in parameters.items()
                if key in args.explicit_parameters
            }
            if not matched:
                meta["cache_only_absence"] = (
                    "No matching saved records; backend absence is not established."
                )
        if operation == "refresh":
            meta["published"] = published
            return {
                "leaf": leaf.id,
                "published": published,
                "row_count": len(rows),
            }, prepare_result(meta, mode="refresh")
        return displayed, prepare_result(meta, mode="live" if live else "cache")
