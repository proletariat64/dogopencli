"""Saved-plan orchestration for explicitly qualified durable acquisitions."""

import hashlib
from dataclasses import asdict
from datetime import datetime, timezone

from .browser.environment import resolve_environment
from .domains import DomainService
from .errors import CliError, diagnostic, error_exit_code
from .jsonutil import canonical, parse
from .leaves.cli import emit
from .leaves.registry import Registry
from .leaves.runtime import acquire_list
from .sync_contracts import profiles, select_profile
from .sync_plan import coverage_identity, format_bound, recent, today_bounds, windows
from .sync_store import SyncStore


def now():
    return datetime.now(timezone.utc)


def _parameters(leaf, args=None):
    result = {}
    for definition in leaf.manifest["operations"]["list"]["parameters"]:
        name = definition["name"].replace("-", "_")
        value = (
            getattr(args, name, definition.get("default"))
            if args is not None
            else definition.get("default")
        )
        if value is not None:
            result[name] = value
    return result


def _source(config_file, domain):
    environment = resolve_environment(config_file=config_file)
    return {
        "domain": domain,
        "profile": str(environment.profile),
        "cdp_url": environment.cdp_url,
    }


def _target(leaf, profile, parameters, config_file, follow=False):
    parameters = {
        **{
            key.replace("-", "_"): value
            for key, value in profile.native_defaults.items()
        },
        **parameters,
    }
    if profile.unsupported_reason:
        raise CliError("SYNC_UNSUPPORTED", profile.unsupported_reason)
    for definition in leaf.manifest["operations"]["list"]["parameters"]:
        if (
            definition.get("required")
            and definition["name"].replace("-", "_") not in parameters
        ):
            raise CliError(
                "INVALID_ARGUMENT", f"--{definition['name']} is required", exit_code=2
            )
    if follow and (profile.time is None or not profile.time.follow_supported):
        raise CliError(
            "INVALID_ARGUMENT",
            "--follow requires a qualified historical query clock",
            exit_code=2,
        )
    if profile.time is not None and profile.time.partitionable:
        # Validate the original spelling of both boundaries in bounded native
        # requests. A request span limit must not reject a partitionable backfill.
        bounds = windows(
            {"parameters": parameters, "follow": False}, profile, now(), initial=True
        )
        first = next(bounds)
        last = first
        for boundary in bounds:
            last = boundary
        start_key = profile.time.start_parameter.replace("-", "_")
        end_key = profile.time.end_parameter.replace("-", "_")
        if first == last:
            native_scope = leaf.adapter.scope(parameters)
        else:
            native_scope = leaf.adapter.scope(
                {**parameters, **first, start_key: parameters[start_key]}
            )
            leaf.adapter.scope({**parameters, **last, end_key: parameters[end_key]})
    else:
        native_scope = leaf.adapter.scope(parameters)
    if profile.mode == "settings":
        for definition in leaf.manifest["operations"]["list"]["parameters"]:
            key = definition["name"].replace("-", "_")
            if definition.get("local_field") and key in parameters:
                without = {
                    name: value for name, value in parameters.items() if name != key
                }
                if leaf.adapter.scope(without) == native_scope:
                    raise CliError(
                        "INVALID_ARGUMENT",
                        "Settings sync cannot use a display-only filter",
                        exit_code=2,
                    )
    namespace = {
        "source": _source(config_file, leaf.domain),
        "parameters": {
            key: parameters.get(key.replace("-", "_"))
            for key in profile.scope_parameters
        },
    }
    if profile.mode == "settings":
        try:
            namespace["native_scope"] = parse(native_scope)
        except ValueError:
            namespace["native_scope"] = native_scope
    identity_parameters = dict(parameters)
    if follow and profile.time:
        identity_parameters.pop(profile.time.start_parameter.replace("-", "_"), None)
        identity_parameters.pop(profile.time.end_parameter.replace("-", "_"), None)
    identity = {
        "leaf_id": leaf.id,
        "variant": profile.variant,
        "namespace": namespace,
        "follow": follow,
        "parameters": identity_parameters,
    }
    return {
        "leaf_id": leaf.id,
        "relation": leaf.manifest["dataset"]["relation"],
        "variant": profile.variant,
        "namespace": namespace,
        "identity": identity,
        "parameters": parameters,
        "follow": follow,
        "profile": parse(canonical(asdict(profile))),
        "adapter_sha256": leaf.adapter_sha256,
        "manifest": leaf.manifest,
    }


def _authoritative(evidence):
    for attempt in evidence.attempts:
        if attempt.get("planned_chunks") == 0:
            return False
        if attempt.get("kind") == "custom_query" and not attempt.get("request_count"):
            return False
    return True


def _run_chunk(store, target, leaf, profile, config_file, chunk):
    attempt = store.start_attempt(target["id"], chunk, started_at=now().isoformat())
    try:
        with store.acquisition():
            rows, evidence, metadata = acquire_list(
                leaf, {**target["parameters"], **chunk}, config_file
            )
        result = store.publish(
            attempt,
            rows,
            key_fields=profile.key_fields,
            mode=profile.mode,
            evidence={
                "complete": evidence.scope_complete and evidence.dataset_complete,
                "authoritative": _authoritative(evidence),
                "acquisition": evidence.record(),
                **metadata,
            },
            acquired_at=metadata["fetched_at"],
            version_field=profile.version_field,
            version_kind=profile.version_kind or "number",
            allow_empty_key_components=profile.allow_empty_key_components,
        )
        return {
            "leaf": leaf.id,
            "variant": profile.variant,
            "state": "complete",
            **result,
            "warnings": metadata["warnings"],
            "chunk": chunk,
        }
    except KeyboardInterrupt:
        store.fail_attempt(
            attempt,
            diagnostic("INTERRUPTED", "Acquisition interrupted"),
            finished_at=now().isoformat(),
        )
        raise
    except Exception as error:
        detail = (
            error.diagnostic(component=leaf.id)
            if isinstance(error, CliError)
            else diagnostic(
                "INTERNAL_ERROR", "Acquisition or publication failed", component=leaf.id
            )
        )
        store.fail_attempt(attempt, detail, finished_at=now().isoformat())
        return {
            "leaf": leaf.id,
            "variant": profile.variant,
            "state": "failed",
            "error": detail,
        }


def _enrollment_identity(leaf, variant, config_file):
    return {
        "enrollment": leaf.id,
        "variant": variant,
        "source": _source(config_file, leaf.domain),
    }


def _blocked_enrollment(leaf, profile, config_file, error):
    variant = profile.variant if profile else "unqualified"
    return {
        "leaf_id": leaf.id,
        "relation": leaf.manifest["dataset"]["relation"],
        "variant": variant,
        "namespace": {"source": _source(config_file, leaf.domain), "parameters": {}},
        "identity": _enrollment_identity(leaf, variant, config_file),
        "parameters": {},
        "follow": False,
        "profile": parse(canonical(asdict(profile))) if profile else {"time": None},
        "adapter_sha256": leaf.adapter_sha256,
        "manifest": leaf.manifest,
        "blocked": error.diagnostic(component=leaf.id),
    }


def _record_block(store, target, detail):
    attempt = store.start_attempt(target["id"], {}, started_at=now().isoformat())
    store.fail_attempt(attempt, detail, finished_at=now().isoformat())
    return {
        "leaf": target["leaf_id"],
        "variant": target["variant"],
        "target_id": target["id"],
        "state": "failed",
        "error": detail,
    }


def execute(invocation):
    config_file = invocation.config_file
    cutoff = now()
    registry = Registry(config_file).scan()
    service = DomainService(config_file, registry=registry)
    selected = []
    path = invocation.node.path
    explicit = len(path) == 3
    if explicit:
        leaf = registry.get(path[0], path[2])
        parameters = _parameters(leaf, invocation.args)
        profile = select_profile(leaf.manifest, parameters)
        target = _target(leaf, profile, parameters, config_file, invocation.args.follow)
        # Validate boundaries before saving a plan or contacting the source.
        next(windows(target, profile, cutoff, initial=True))
        selected = [(target, leaf, profile)]
    results = []
    blocked_enrollments = []
    if getattr(invocation.args, "all", False):
        for leaf in registry.leaves.values():
            if "list" not in leaf.manifest["operations"]:
                continue
            declarations = profiles(leaf.manifest)
            if not declarations:
                error = CliError(
                    "SYNC_UNSUPPORTED", "No qualified synchronization declaration"
                )
                blocked_enrollments.append(
                    _blocked_enrollment(leaf, None, config_file, error)
                )
                results.append(
                    {"leaf": leaf.id, "state": "failed", "error": error.diagnostic()}
                )
            for profile in declarations:
                try:
                    if profile.unsupported_reason:
                        raise CliError("SYNC_UNSUPPORTED", profile.unsupported_reason)
                    parameters = {
                        **_parameters(leaf),
                        **{
                            key.replace("-", "_"): value
                            for key, value in {
                                **profile.parameters,
                                **profile.match,
                            }.items()
                        },
                    }
                    follow = False
                    if profile.time:
                        start, end = today_bounds(profile.time, cutoff)
                        parameters[profile.time.start_parameter.replace("-", "_")] = (
                            format_bound(start, profile.time)
                        )
                        parameters[profile.time.end_parameter.replace("-", "_")] = (
                            format_bound(end, profile.time)
                        )
                        follow = True
                    target = _target(leaf, profile, parameters, config_file, follow)
                    target["identity"] = _enrollment_identity(
                        leaf, profile.variant, config_file
                    )
                    selected.append((target, leaf, profile))
                except CliError as error:
                    blocked_enrollments.append(
                        _blocked_enrollment(leaf, profile, config_file, error)
                    )
                    results.append(
                        {
                            "leaf": leaf.id,
                            "variant": profile.variant,
                            "state": "failed",
                            "error": error.diagnostic(),
                        }
                    )
        selected.sort(
            key=lambda entry: (
                entry[2].priority,
                entry[0]["leaf_id"],
                entry[0]["variant"],
            )
        )
    if not registry.database_path().is_file():
        if results:
            return results
        raise CliError(
            "SYNC_NO_PLAN", "No saved sync targets; use dogopencli sync --all"
        )
    with SyncStore(registry.database_path()) as store:
        for blocked in blocked_enrollments:
            old = next(
                (
                    saved
                    for saved in store.targets()
                    if canonical(saved["identity"]) == canonical(blocked["identity"])
                ),
                None,
            )
            if old and store.coverage(old["id"]):
                blocked = {**old, "blocked": blocked["blocked"]}
            store.save_target(blocked)
        if explicit or getattr(invocation.args, "all", False):
            previous = {
                canonical(target["identity"]): target for target in store.targets()
            }
            saved_selection = []
            for target, leaf, profile in selected:
                old = previous.get(canonical(target["identity"]))
                if explicit and old is None:
                    blocked = next(
                        (
                            saved
                            for saved in previous.values()
                            if saved.get("blocked")
                            and not store.coverage(saved["id"])
                            and saved["leaf_id"] == target["leaf_id"]
                            and saved["variant"] in {target["variant"], "unqualified"}
                            and saved["namespace"]["source"]
                            == target["namespace"]["source"]
                        ),
                        None,
                    )
                    if blocked is not None:
                        target["id"] = blocked["id"]
                if old and target["follow"] and profile.time:
                    from .sync_plan import parse_bound

                    start_key = profile.time.start_parameter.replace("-", "_")
                    if start_key in old["parameters"] and parse_bound(
                        old["parameters"][start_key], profile.time
                    ) < parse_bound(target["parameters"][start_key], profile.time):
                        target["parameters"][start_key] = old["parameters"][start_key]
                saved_target = store.save_target(target)
                if explicit:
                    for blocked in previous.values():
                        if (
                            blocked.get("blocked")
                            and blocked["id"] != saved_target["id"]
                            and not store.coverage(blocked["id"])
                            and blocked["leaf_id"] == target["leaf_id"]
                            and blocked["variant"] in {target["variant"], "unqualified"}
                            and blocked["namespace"]["source"]
                            == target["namespace"]["source"]
                        ):
                            store.save_target(
                                {**blocked, "resolved_by": saved_target["id"]}
                            )
                saved_selection.append((saved_target, leaf, profile))
            selected = saved_selection
        else:
            for target in store.targets():
                if target.get("resolved_by"):
                    continue
                if target.get("blocked"):
                    results.append(_record_block(store, target, target["blocked"]))
                    continue
                domain, name = target["leaf_id"].split(".", 1)
                try:
                    leaf = registry.get(domain, name)
                    profile = next(
                        (
                            p
                            for p in profiles(leaf.manifest)
                            if p.variant == target["variant"]
                        ),
                        None,
                    )
                    if (
                        profile is None
                        or canonical(parse(canonical(asdict(profile))))
                        != canonical(target["profile"])
                        or leaf.adapter_sha256 != target["adapter_sha256"]
                        or canonical(leaf.manifest) != canonical(target["manifest"])
                    ):
                        raise CliError(
                            "SYNC_CONTRACT_CHANGED",
                            "Saved target contract changed; "
                            "published data requires explicit migration",
                        )
                    if target["namespace"]["source"] != _source(config_file, domain):
                        raise CliError(
                            "SYNC_SOURCE_CHANGED",
                            "Configured source changed; saved target is blocked",
                        )
                    selected.append((target, leaf, profile))
                except CliError as error:
                    results.append(_record_block(store, target, error.diagnostic()))
        if not selected and not results:
            raise CliError(
                "SYNC_NO_PLAN", "No saved sync targets; use dogopencli sync --all"
            )
        all_targets = store.targets()
        completed = {}
        for saved in all_targets:
            key = coverage_identity(saved)
            completed.setdefault(key, set()).update(
                canonical(item["chunk"]) for item in store.coverage(saved["id"])
            )
        blocked_domains = {}
        for target, leaf, profile in selected:
            if leaf.domain in blocked_domains:
                results.append(
                    _record_block(store, target, blocked_domains[leaf.domain])
                )
                continue
            if not service.inventory(leaf.domain)[0]["enabled"]:
                results.append(
                    _record_block(
                        store,
                        target,
                        diagnostic("DOMAIN_DISABLED", "Domain is disabled"),
                    )
                )
                continue
            key = coverage_identity(target)
            chunks = []
            for chunk in windows(target, profile, cutoff, initial=explicit):
                done = canonical(chunk) in completed.get(key, set())
                refresh = profile.time is None or (
                    target["follow"] and recent(chunk, profile, cutoff)
                )
                if not explicit and done and not refresh:
                    continue
                result = _run_chunk(store, target, leaf, profile, config_file, chunk)
                chunks.append(result)
                if result["state"] == "complete":
                    completed.setdefault(key, set()).add(canonical(chunk))
                elif result["error"]["code"] in {"AUTH_REQUIRED", "auth_required"}:
                    blocked_domains[leaf.domain] = result["error"]
                    break
            results.append(
                {
                    "leaf": leaf.id,
                    "variant": profile.variant,
                    "target_id": target["id"],
                    "state": "failed"
                    if any(c["state"] == "failed" for c in chunks)
                    else "complete",
                    "chunks": chunks,
                    "acquired_chunks": len(chunks),
                }
            )
    return results


def status(invocation):
    registry = invocation.registry
    state = SyncStore.status(registry.database_path())
    cutoff = now()
    coverage = {}
    for target in state["targets"]:
        coverage.setdefault(coverage_identity(target), set()).update(
            canonical(row["chunk"])
            for row in state["coverage"]
            if row["target_id"] == target["id"]
        )
    output = []
    for target in state["targets"]:
        item = {
            key: target.get(key)
            for key in (
                "id",
                "leaf_id",
                "variant",
                "parameters",
                "follow",
                "row_count",
                "last_attempt",
                "last_success",
            )
        }
        item["source_identity"] = (
            "configured browser context; "
            "authenticated principal is not exposed by the source"
        )
        item["freshness"] = "as_observed" if target.get("last_success") else "unknown"
        leaf = registry.leaves.get(target["leaf_id"])
        if target.get("resolved_by"):
            item["state"] = "resolved"
            item["resolved_by"] = target["resolved_by"]
        elif leaf is None:
            item["state"] = "inactive"
            item["reason"] = "Leaf is not installed"
        elif target.get("blocked"):
            item["state"] = "blocked"
            item["reason"] = target["blocked"]
        elif (
            canonical(leaf.manifest) != canonical(target["manifest"])
            or hashlib.sha256(
                (leaf.path / leaf.manifest["adapter"].split(":", 1)[0]).read_bytes()
            ).hexdigest()
            != target["adapter_sha256"]
        ):
            item["state"] = "blocked"
            item["reason"] = "Leaf contract changed"
        elif target["namespace"]["source"] != _source(
            invocation.config_file, leaf.domain
        ):
            item["state"] = "blocked"
            item["reason"] = "Configured source changed"
        else:
            profile = next(
                p for p in profiles(leaf.manifest) if p.variant == target["variant"]
            )
            desired = list(windows(target, profile, cutoff))
            known = coverage.get(coverage_identity(target), set())
            item["gaps"] = [chunk for chunk in desired if canonical(chunk) not in known]
            item["time_basis"] = (
                profile.time.basis if profile.time else "acquisition observation"
            )
            item["state"] = "pending" if item["gaps"] else "covered_as_observed"
            item["refresh_due"] = profile.time is None or target["follow"]
        output.append(item)
    return {
        "targets": output,
        "coverage": state["coverage"],
        "attempts": state["attempts"],
        "checked_at": cutoff.isoformat(),
        "remote_changes": "unknown",
    }


def main(invocation):
    try:
        if invocation.node.path == ("sync", "status"):
            emit(status(invocation), output_format=invocation.args.format)
            return 0
        results = execute(invocation)
        failed = any(item["state"] == "failed" for item in results)
        warnings = [
            warning
            for result in results
            for chunk in result.get("chunks", [])
            for warning in chunk.get("warnings", [])
        ]
        emit(
            {"targets": results},
            {
                "outcome": "failed" if failed else "warning" if warnings else "success",
                "warnings": warnings,
            },
            output_format=invocation.args.format,
        )
        return 1 if failed else 0
    except CliError as error:
        emit(None, error=error.diagnostic(), output_format=invocation.args.format)
        return error_exit_code(error.code)
    except Exception:
        emit(
            None,
            error=diagnostic(
                "INTERNAL_ERROR",
                "Unexpected synchronization failure; completed chunks retained",
            ),
            output_format=invocation.args.format,
        )
        return 1
    except KeyboardInterrupt:
        emit(
            None,
            error=diagnostic(
                "INTERRUPTED", "Sync interrupted; completed chunks retained"
            ),
            output_format=invocation.args.format,
        )
        return 130
