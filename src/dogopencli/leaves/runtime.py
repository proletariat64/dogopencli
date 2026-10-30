"""Common inquiry, quality and single-slot cache policy for installed leaves."""

import hashlib
import inspect
import math
from argparse import Namespace
from collections.abc import Callable
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.collect import (
    collect_list,
    collect_sources,
    execute_bounded,
)
from dogopencli.config import cache_ttl_hours
from dogopencli.errors import CliError
from dogopencli.inquiry import inquiry_session
from dogopencli.jsonutil import canonical, parse
from dogopencli.progress import report
from dogopencli.result_policy import (
    SOURCE_ROW_OCCURRENCES,
    AcquisitionEvidence,
    check_complete,
    prepare_result,
)
from dogopencli.temporary_query import display_options, is_stale, window_rows

from .query import (
    CustomGetResult,
    QueryBudget,
    QueryTools,
    query_capabilities,
    validate_detail_lookup,
    validate_detail_result,
)
from .registry import Leaf, _typed


def cache_for(config_file: Path) -> Cache:
    return Cache(config_file.parent / "leaf-cache.sqlite3")


def _validate_records(
    rows: Any, identity: list[str], primary_id: dict | None = None
) -> list[dict]:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise CliError("INVALID_RESPONSE", "records must be business objects")
    seen = set()
    empty_components = (
        set(primary_id["fields"])
        if primary_id is not None
        and primary_id.get("type") == "hash"
        and primary_id.get("allow_empty_components") is True
        else set()
    )
    for row in rows:
        if identity:
            if any(
                field not in row
                or (row[field] is None and field not in empty_components)
                for field in identity
            ):
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
        "acquisition_schema": 2,
        "identity": leaf.manifest["identity"],
        "operations": operations,
        "adapter_binding": leaf.manifest["adapter"],
        "adapter_sha256": leaf.adapter_sha256,
    }
    custom = {
        name: {
            key: specification[key]
            for key in (
                "execution",
                "queries",
                "max_requests",
                "budget_seconds",
                "account_directory",
                "entity_selector",
            )
            if key in specification
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
) -> CustomGetResult:
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
            data = tools.finish_get(
                leaf.adapter.query_get(parameters, identity, tools), identity
            )
            return CustomGetResult(
                data, AcquisitionEvidence.from_record(tools.evidence()["coverage"])
            )
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
    report(
        phase="get",
        source=capability.name,
        candidate=None,
        request_attempts=0,
        root_rows_received=None,
        source_rows_selected=None,
        source_pages=None,
        source_rows_received=None,
        source_total_rows=None,
    )
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
    report(root_rows_received=len(result) if isinstance(result, list) else 1)
    return CustomGetResult(
        result,
        AcquisitionEvidence.for_collection(
            complete=True,
            reported_total=None,
            collected_total=len(result) if isinstance(result, list) else 1,
            arrivals=len(result) if isinstance(result, list) else 1,
            total_semantics="unknown",
            coverage_basis="qualified_single_response",
            attempts=(
                {"component": "native_root", "status": "succeeded", "complete": True},
            ),
        ),
    )


def _compose_details(
    leaf: Leaf,
    session: Any,
    rows: list[dict],
    fields: list[str] | None,
    deadline: float,
    offset: int,
) -> tuple[list[dict], list[AcquisitionEvidence]]:
    if leaf.manifest["operations"]["get"].get("result_shape", "object") != "object":
        raise CliError("INVALID_LEAF", "array Get cannot bind to List records")
    binding = leaf.manifest["operations"]["get"]["list_binding"]
    combined = []
    acquisitions = []
    query_budget = None
    get_specification = leaf.manifest["operations"]["get"]
    if get_specification.get("execution") == "custom":
        from dogopencli.collect import _monotonic

        query_budget = QueryBudget(
            min(deadline, _monotonic() + get_specification["budget_seconds"]),
            get_specification["max_requests"],
        )
    report(phase="detail", detail_rows_completed=0, detail_rows_expected=len(rows))
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
            check_complete(record.evidence, require_complete=False, mode="get")
            acquisitions.append(record.evidence)
            report(
                phase="detail",
                detail_rows_completed=len(acquisitions),
                detail_rows_expected=len(rows),
            )
            combined.append(
                {"record": _project([row], fields)[0], "detail": record.data}
            )
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
    return combined, acquisitions


def freeze_list_parameters(
    leaf: Leaf, parameters: dict, config_file: Path, *, acquisition: bool = True
) -> dict:
    """Read local selectors only, rejecting drift in an already frozen request."""
    specification = leaf.manifest["operations"].get("list", {})
    if acquisition and specification.get("freeze_parameters"):
        original = deepcopy(parameters)
        supplied = deepcopy(parameters)
        frozen = leaf.adapter.freeze_parameters(supplied)
        definitions = {
            item["name"].replace("-", "_"): item for item in specification["parameters"]
        }
        if (
            supplied != original
            or not isinstance(frozen, dict)
            or any(
                key not in frozen or frozen[key] != value
                for key, value in original.items()
            )
            or any(key not in definitions for key in frozen.keys() - original.keys())
        ):
            raise CliError(
                "INVALID_ARGUMENT",
                "Parameter freezing must preserve supplied scope and declared names",
                exit_code=2,
            )
        for key, value in frozen.items():
            if key not in definitions:
                continue
            definition = definitions[key]
            values = value if definition.get("multiple") else [value]
            if not isinstance(values, list) or any(
                not _typed(item, definition["type"])
                or isinstance(item, float)
                and not math.isfinite(item)
                or "choices" in definition
                and item not in definition["choices"]
                for item in values
            ):
                raise CliError(
                    "INVALID_ARGUMENT",
                    "Frozen parameter has an invalid type or choice",
                    exit_code=2,
                )
        parameters = deepcopy(frozen)
    if specification.get("entity_selector") is True and parameters.get("entity") == [
        "ANY"
    ]:
        from dogopencli.duckdog import resolve_selector

        entities = resolve_selector(
            "liquidity/reference/entities", "instId", config_file=config_file
        )
        if (
            "_resolved_entities" in parameters
            and parameters["_resolved_entities"] != entities
        ):
            raise CliError(
                "WORKFLOW_ERROR", "Frozen entity selection changed; create a new plan"
            )
        return {**parameters, "_resolved_entities": entities}
    return parameters


def planned_get_scope(leaf: Leaf, parameters: dict, identity: str) -> tuple[Any, dict]:
    """Describe the declared detail inquiry without opening a browser."""
    validate_detail_lookup(identity)
    return {"identity": identity, "parameters": parameters}, planned_detail_environment(
        leaf, parameters
    )


def planned_detail_environment(leaf: Leaf, parameters: dict) -> dict:
    """Describe declared Get sources without requiring a particular row identity."""
    custom = leaf.manifest["operations"]["get"].get("execution") == "custom"
    capability = (
        query_capabilities(leaf, "get", parameters)
        if custom
        else leaf.adapter.detail_capability(parameters)
    )
    capabilities = capability.values() if custom else [capability]
    return {
        "domain": leaf.domain,
        "queries": [
            {
                "method": item.contract.method,
                "host": item.contract.host,
                "path": item.contract.path,
                "page_url": getattr(item, "page_url", None),
            }
            for item in capabilities
        ],
    }


def planned_list_scope(leaf: Leaf, parameters: dict) -> tuple[Any, dict]:
    """Validate native scope offline and describe its inquiry environment."""
    capability = _list_capabilities(leaf, parameters)
    scope = leaf.adapter.scope(parameters)
    try:
        scope = parse(scope)
    except (ValueError, TypeError):
        pass
    capabilities = capability.values() if isinstance(capability, dict) else [capability]
    environment = {
        "domain": leaf.domain,
        "queries": [
            {
                "method": item.contract.method,
                "host": item.contract.host,
                "path": item.contract.path,
                "page_url": getattr(item, "page_url", None),
            }
            for item in capabilities
        ],
    }
    return scope, environment


def execute(
    leaf: Leaf,
    operation: str,
    parameters: dict,
    args: Namespace,
    config_file: Path,
    *,
    capture: Callable[[list[dict], dict], None] | None = None,
) -> tuple[Any, dict]:
    """Execute one supported action; publication always uses the full candidate."""

    def now() -> datetime:
        return datetime.now(timezone.utc)

    specification = leaf.manifest["operations"].get("list", {})
    resolved_entities: list[str] | None = None
    if (
        operation in {"list", "refresh"}
        and specification.get("execution") != "custom"
        and leaf.manifest.get("collection") is None
    ):
        raise CliError(
            "INVALID_LEAF", "standard List requires a collection declaration"
        )
    if operation in {"list", "refresh"}:
        parameters = freeze_list_parameters(
            leaf,
            parameters,
            config_file,
            acquisition=operation == "refresh" or args.live,
        )
        resolved_entities = parameters.get("_resolved_entities")

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
                    leaf,
                    "get",
                    parameters,
                    capability,
                    session.transport,
                    config_file=config_file,
                )
            record = get_detail(
                leaf,
                session,
                parameters,
                args.detail_identity,
                capability=capability,
                query_tools=tools,
            )
        coverage = record.evidence
        decision = check_complete(
            coverage,
            require_complete=getattr(args, "require_complete", False),
            mode="get",
        )
        is_array = leaf.manifest["operations"]["get"].get("result_shape") == "array"
        rows = record.data if is_array else [record.data]
        projected = _project(rows, fields)
        data = projected if is_array else projected[0]
        metadata = {
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
            **coverage.meta(),
            **decision.meta(mode="get"),
            "warnings": list(decision.warnings),
        }
        if capture is not None:
            capture(rows, {**metadata, "scope": metadata["query"]})
        return data, metadata
    definitions = leaf.manifest["operations"]["list"].get("parameters", [])
    local_parameters = {
        definition["name"].replace("-", "_")
        for definition in definitions
        if definition.get("local_field")
    }
    live = operation == "refresh" or args.live
    ttl = cache_ttl_hours(config_file)
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
                        config_file=config_file,
                        resolved_entities=resolved_entities,
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
                else:
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
                rows = _validate_records(
                    collected.records,
                    leaf.manifest.get("identity", []),
                    leaf.manifest.get("collection", {}).get("primary_id"),
                )
                evidence = collected.evidence
                if not isinstance(evidence, AcquisitionEvidence):
                    raise CliError(
                        "INVALID_RESPONSE", "List acquisition evidence is missing"
                    )
                query = parameters
                stale = False
                decision = check_complete(
                    evidence,
                    require_complete=args.require_complete,
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
                    source_list_acquisition = evidence.record()
                    details, detail_acquisitions = _compose_details(
                        leaf,
                        session,
                        selected if capture is not None else window,
                        None if capture is not None else fields,
                        collected.deadline,
                        0 if capture is not None else offset,
                    )
                    source_occurrences = (
                        evidence.total_semantics == SOURCE_ROW_OCCURRENCES
                    )
                    evidence = replace(
                        evidence,
                        reported_total=None
                        if source_occurrences
                        else evidence.reported_total,
                        arrivals=None if source_occurrences else evidence.arrivals,
                        unique_count=None
                        if source_occurrences
                        else evidence.unique_count,
                        duplicate_count=None
                        if source_occurrences
                        else evidence.duplicate_count,
                        scope_complete=evidence.scope_complete
                        and all(item.scope_complete for item in detail_acquisitions),
                        dataset_complete=evidence.dataset_complete
                        and all(item.dataset_complete for item in detail_acquisitions),
                        reasons=tuple(
                            dict.fromkeys(
                                (
                                    *evidence.reasons,
                                    *(
                                        reason
                                        for item in detail_acquisitions
                                        for reason in item.reasons
                                    ),
                                )
                            )
                        ),
                        coverage_basis=None,
                        sources=None,
                        total_semantics=(
                            "unknown"
                            if evidence.total_semantics
                            in {"assembled_roots", SOURCE_ROW_OCCURRENCES}
                            else evidence.total_semantics
                        ),
                        attempts=(
                            {
                                "kind": "composition",
                                "source_acquisition": source_list_acquisition,
                                "detail_acquisition": [
                                    item.record() for item in detail_acquisitions
                                ],
                            },
                        ),
                        usable_incomplete=(
                            (evidence.scope_complete and evidence.dataset_complete)
                            or evidence.usable_incomplete
                        )
                        and all(
                            (item.scope_complete and item.dataset_complete)
                            or item.usable_incomplete
                            for item in detail_acquisitions
                        ),
                    )
                    try:
                        decision = check_complete(
                            evidence,
                            require_complete=args.require_complete,
                            mode="live",
                        )
                    except CliError as error:
                        error.meta = {
                            **(error.meta or {}),
                            "source_acquisition": source_list_acquisition,
                            "detail_acquisition": [
                                item.record() for item in detail_acquisitions
                            ],
                        }
                        raise

                if capture is not None:
                    local_filters = {
                        key: value
                        for key, value in query.items()
                        if key in local_parameters
                    }
                    saved_scope = effective_scope
                    saved_metadata = {
                        "query": query,
                        "scope": saved_scope,
                        "fetched_at": fetched_at,
                        **evidence.meta(),
                        **decision.meta(mode=operation),
                        "warnings": list(decision.warnings),
                    }
                    if local_filters:
                        # These records are a complete local selection of an
                        # acquired source, not the full native response scope.
                        saved_metadata.update(
                            scope={
                                "native_scope": effective_scope,
                                "local_filters": local_filters,
                            },
                            local_filters=local_filters,
                            source_acquisition=evidence.record(),
                            coverage_basis="local_selection_of_native_acquisition",
                            reported_total=None,
                            collected_total=len(selected),
                        )
                        saved_metadata.pop("acquisition", None)
                        saved_metadata["selection"] = {
                            "filters": local_filters,
                            "record_count": len(selected),
                            "complete": evidence.scope_complete
                            and evidence.dataset_complete,
                        }
                    if args.with_detail:
                        saved_metadata.update(
                            with_detail=True,
                            scope={
                                "list_scope": saved_metadata["scope"],
                                "composition": "declared_get",
                            },
                            source_acquisition=source_list_acquisition,
                            detail_acquisition=[
                                item.record() for item in detail_acquisitions
                            ],
                        )
                    capture(details if args.with_detail else selected, saved_metadata)
                    if args.with_detail:
                        details = [
                            {**item, "record": _project([item["record"]], fields)[0]}
                            for item in window_rows(details, limit, offset)
                        ]

            published = decision.publishable
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
                    leaf.manifest.get("collection", {}).get("primary_id"),
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
            if (
                specification.get("entity_selector") is True
                and "_resolved_entities" in parameters
            ):
                if parameters["_resolved_entities"] != query.get("_resolved_entities"):
                    raise CliError(
                        "CACHE_MISS",
                        "saved ANY entity selection differs; refresh before replay",
                    )
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
                    dataset_complete=(
                        False
                        if evidence.coverage_basis == "qualified_single_response"
                        else evidence.dataset_complete
                    ),
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
                    "source_acquisition": source_list_acquisition,
                    "detail_acquisition": [
                        item.record() for item in detail_acquisitions
                    ],
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
