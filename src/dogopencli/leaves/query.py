"""Named, bounded inquiry tools for leaf-owned Python orchestration.

These tools enforce registered endpoint contracts for trusted local adapters;
they are not a Python sandbox. The leaf owns business relationships and coverage.
"""

import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from dogopencli import collect as collection
from dogopencli.contracts import EndpointContract
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    TIMEOUT,
    CliError,
    diagnostic,
    normalize_warnings,
)
from dogopencli.jsonutil import canonical
from dogopencli.result_policy import AcquisitionEvidence


@dataclass(frozen=True)
class CustomListResult:
    """Leaf-owned records and business coverage, before host publication."""

    records: list[dict[str, Any]]
    evidence: AcquisitionEvidence


@dataclass(frozen=True)
class CustomGetResult:
    """Custom Get data and independently qualified relationship coverage."""

    data: dict | list[dict]
    evidence: AcquisitionEvidence


def _native_error_meta(native_code: str | int | None) -> dict:
    if type(native_code) in (str, int) and re.fullmatch(
        r"[A-Za-z0-9_.:-]{1,80}", str(native_code)
    ):
        return {"native_code": native_code}
    return {}


class QueryRefused(CliError):
    """A parser-qualified individual-record refusal, retained as incomplete."""

    def __init__(self, *, native_code: str | int | None = None):
        super().__init__(
            BUSINESS_QUERY_FAILED,
            "backend refused record detail",
            meta=_native_error_meta(native_code),
        )


class QueryFailed(CliError):
    """A leaf-qualified detail business failure, distinct from a refusal."""

    def __init__(self, *, native_code: str | int | None = None):
        super().__init__(
            BUSINESS_QUERY_FAILED,
            "backend failed record detail",
            meta=_native_error_meta(native_code),
        )


def validate_detail_lookup(identity: Any) -> None:
    if not isinstance(identity, str) or not identity.strip():
        raise CliError(
            "INVALID_ARGUMENT", "detail lookup must be nonempty", exit_code=2
        )


def validate_detail_result(
    result: Any, specification: dict, context: dict | None = None
) -> None:
    if specification.get("result_shape", "object") == "array":
        if not isinstance(result, list):
            raise CliError(INVALID_RESPONSE, "detail response must be an array")
        rows = result
    else:
        if not isinstance(result, dict) or not result:
            raise CliError(
                INVALID_RESPONSE, "detail response must be a nonempty object"
            )
        rows = [result]
    identity = specification["result_identity"]
    if "request_fields" in identity:
        if not isinstance(context, dict):
            raise CliError(INVALID_RESPONSE, "request identity context is missing")
        for field in identity["request_fields"]:
            value = context.get(field)
            if type(value) not in (str, int) or (
                isinstance(value, str) and not value.strip()
            ):
                raise CliError(
                    INVALID_RESPONSE,
                    "request identity must contain nonempty scalar components",
                )
        return
    paths = identity.get("paths")
    if paths is None:
        paths = [[field] for field in identity["fields"]]
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise CliError(INVALID_RESPONSE, "detail members must be native objects")
        values = []
        for path in paths:
            value = row
            for key in path:
                if not isinstance(value, dict) or key not in value:
                    raise CliError(INVALID_RESPONSE, "detail identity is missing")
                value = value[key]
            if type(value) not in (str, int) or (
                isinstance(value, str) and not value.strip()
            ):
                raise CliError(INVALID_RESPONSE, "detail identity must be a scalar ID")
            values.append(value)
        key = canonical(values)
        if key in seen:
            raise CliError(INVALID_RESPONSE, "detail identity is duplicated")
        seen.add(key)


def query_capabilities(leaf: Any, operation: str, parameters: dict) -> dict[str, Any]:
    """Resolve pure declarations before acquiring a browser or query transport."""
    capabilities = {}
    for name, declaration in leaf.manifest["operations"][operation]["queries"].items():
        capability = leaf.adapter.query_capability(operation, name, parameters)
        if (
            not isinstance(getattr(capability, "contract", None), EndpointContract)
            or not isinstance(getattr(capability, "name", None), str)
            or not capability.name.strip()
            or not isinstance(getattr(capability, "page_url", None), str)
            or not capability.page_url.strip()
        ):
            raise CliError("INVALID_LEAF", "invalid custom inquiry capability")
        if declaration["kind"] == "detail":
            signatures = {
                "request_body": ({}, "identity"),
                "parse_detail": (b"", {}, "identity"),
            }
        elif declaration["kind"] == "inquiry":
            signatures = {"request_body": ({},), "parse_inquiry": (b"", {})}
        else:
            mode = declaration["collection"]["paging"]["mode"]
            parser = (
                "parse_rows" if mode in {"offset", "single_response"} else "parse_page"
            )
            signatures = {
                "page_body": ("scope", 0, 1),
                parser: (b"",),
            }
        for hook, arguments in signatures.items():
            try:
                method = getattr(capability, hook)
                inspect.signature(method).bind(*arguments)
            except (AttributeError, TypeError, ValueError) as error:
                raise CliError(
                    "INVALID_LEAF", "invalid custom inquiry capability hooks"
                ) from error
        capabilities[name] = capability
    return capabilities


@dataclass
class QueryBudget:
    """One deadline and physical-request allowance, including transport retries."""

    deadline: float
    maximum: int
    requests: int = 0

    def reserve(self) -> None:
        collection.remaining_seconds(self.deadline)
        if self.requests >= self.maximum:
            raise CliError(TIMEOUT, "custom inquiry request budget exhausted")
        self.requests += 1


class _QueryTransport:
    def __init__(self, transport: Any, budget: QueryBudget):
        self._transport = transport
        self._budget = budget

    def execute(self, request: Any, *, timeout: float) -> Any:
        self._budget.reserve()
        return self._transport.execute(
            request,
            timeout=min(timeout, collection.remaining_seconds(self._budget.deadline)),
        )

    def close(self) -> None:
        self._transport.close()


class QueryTools:
    """Execute only named List/Detail declarations under one operation budget."""

    def __init__(
        self,
        leaf: Any,
        operation: str,
        parameters: dict,
        capabilities: dict[str, Any],
        transport_factory: Callable[[Any], Any],
        *,
        state_file: Path | None = None,
        config_file: Path | None = None,
        budget: QueryBudget | None = None,
        deadline: float | None = None,
    ):
        self._leaf = leaf
        self._operation = operation
        self._parameters = parameters
        self._declarations = leaf.manifest["operations"][operation]
        self._capabilities = capabilities
        self._transport_factory = transport_factory
        self._state_file = state_file
        self._config_file = config_file
        end = collection._monotonic() + self._declarations["budget_seconds"]
        if deadline is not None:
            end = min(end, deadline)
        self._budget = budget or QueryBudget(end, self._declarations["max_requests"])
        self._fatal: CliError | None = None
        self._incomplete = False
        self._required_incomplete = False
        self._required_failure: CliError | None = None
        self._queries: dict[str, dict] = {}
        self._coverage: dict | None = None
        self._transports: dict[str, _QueryTransport] = {}

    @property
    def deadline(self) -> float:
        return self._budget.deadline

    def __enter__(self) -> "QueryTools":
        return self

    def __exit__(self, kind: Any, error: Any, traceback: Any) -> None:
        try:
            if isinstance(error, CliError):
                error.meta = {**(error.meta or {}), "query_evidence": self.evidence()}
        finally:
            self.close()

    def close(self) -> None:
        """Release operation-owned targets, including on cancellation."""
        transports, self._transports = self._transports, {}
        for transport in transports.values():
            transport.close()

    def _transport(self, name: str, capability: Any) -> _QueryTransport:
        if name not in self._transports:
            self._transports[name] = _QueryTransport(
                self._transport_factory(capability), self._budget
            )
        return self._transports[name]

    def _query(self, name: str, kind: str) -> tuple[Any, dict, dict]:
        if self._fatal is not None:
            raise self._fatal
        declaration = (
            self._declarations["queries"].get(name) if isinstance(name, str) else None
        )
        if declaration is None or declaration["kind"] != kind:
            error = CliError(REQUEST_NOT_ALLOWED, "custom inquiry is not declared")
            self._fatal = error
            raise error
        collection.remaining_seconds(self.deadline)
        trace = self._queries.setdefault(
            name, {"kind": kind, "calls": 0, "requests": 0, "succeeded": 0}
        )
        if "applicability" in trace:
            self._fatal = CliError(
                INVALID_RESPONSE, "query contradicts recorded applicability"
            )
            raise self._fatal
        trace["calls"] += 1
        return self._capabilities[name], declaration, trace

    def collect(self, name: str, scope: str = "") -> collection.CollectedScope:
        capability, declaration, trace = self._query(name, "list")
        before = self._budget.requests
        try:
            if not isinstance(scope, str):
                raise CliError(INVALID_RESPONSE, "custom List scope must be a string")
            policy = declaration["collection"]
            duration = policy.get(
                "budget_seconds", self._declarations["budget_seconds"]
            )
            transport = self._transport(name, capability)
            result = collection.collect_list(
                capability,
                transport,
                scope,
                policy,
                domain=self._leaf.domain,
                leaf_id=self._leaf.id + ":" + self._operation + ":" + name,
                state_file=self._state_file,
                _deadline=min(
                    self.deadline,
                    collection._monotonic() + duration,
                ),
            )
            evidence = result.evidence
            if evidence is None:
                raise CliError(INVALID_RESPONSE, "custom source evidence is missing")
            incomplete = not (evidence.scope_complete and evidence.dataset_complete)
            self._incomplete |= incomplete
            self._required_incomplete |= incomplete and not (
                declaration.get("supplementary") is True and evidence.usable_incomplete
            )
            trace["succeeded"] += 1
            trace.setdefault("collections", []).append(
                {"scope": scope, "acquisition": evidence.record()}
            )
            return result
        except CliError as error:
            self._fatal = error
            trace["error"] = {"code": error.code, "retryable": error.retryable}
            raise
        except Exception as error:
            failure = CliError(INVALID_RESPONSE, "custom List inquiry failed")
            self._fatal = failure
            trace["error"] = {"code": failure.code, "retryable": False}
            raise failure from error
        finally:
            trace["requests"] += self._budget.requests - before

    def detail(
        self, name: str, identity: str, parameters: dict | None = None
    ) -> dict | list[dict]:
        capability, declaration, trace = self._query(name, "detail")
        before = self._budget.requests
        parsed_business_error = False
        try:
            validate_detail_lookup(identity)
            context = self._parameters if parameters is None else parameters
            if not isinstance(context, dict):
                raise CliError(
                    INVALID_RESPONSE, "custom detail context must be an object"
                )
            body = capability.request_body(context, identity)
            transport = self._transport(name, capability)
            response = collection.execute_bounded(
                capability, transport, body, self.deadline
            )
            try:
                result = capability.parse_detail(response.body, context, identity)
            except (QueryRefused, QueryFailed):
                parsed_business_error = True
                raise
            validate_detail_result(result, declaration)
            trace["succeeded"] += 1
            return result
        except (QueryRefused, QueryFailed) as error:
            if parsed_business_error:
                self._incomplete = True
                status = "refused" if isinstance(error, QueryRefused) else "failed"
                trace[status] = trace.get(status, 0) + 1
                trace["diagnostics"] = normalize_warnings(
                    [
                        *trace.get("diagnostics", []),
                        diagnostic(
                            error.code,
                            error.message,
                            severity="warning",
                            component=name,
                            retryable=error.retryable,
                            native_code=(error.meta or {}).get("native_code"),
                            consequence="promised detail coverage is incomplete",
                        ),
                    ]
                )
                qualified = declaration.get(
                    "supplementary"
                ) is True and status in declaration.get("retained_errors", [])
                self._required_incomplete |= not qualified
                if not qualified and self._required_failure is None:
                    self._required_failure = error
            else:
                self._fatal = error
                trace["error"] = {"code": error.code, "retryable": error.retryable}
            raise
        except CliError as error:
            self._fatal = error
            trace["error"] = {"code": error.code, "retryable": error.retryable}
            raise
        except Exception as error:
            failure = CliError(INVALID_RESPONSE, "custom detail inquiry failed")
            self._fatal = failure
            trace["error"] = {"code": failure.code, "retryable": False}
            raise failure from error
        finally:
            trace["requests"] += self._budget.requests - before

    def inquire(self, name: str, parameters: dict | None = None) -> dict | list[dict]:
        """Read one declared native aggregate without inventing response identity."""
        capability, declaration, trace = self._query(name, "inquiry")
        before = self._budget.requests
        try:
            context = self._parameters if parameters is None else parameters
            if not isinstance(context, dict):
                raise CliError(
                    INVALID_RESPONSE, "custom inquiry context must be an object"
                )
            body = capability.request_body(context)
            response = collection.execute_bounded(
                capability, self._transport(name, capability), body, self.deadline
            )
            result = capability.parse_inquiry(response.body, context)
            if declaration["result_shape"] == "object":
                valid = isinstance(result, dict) and bool(result)
            else:
                valid = isinstance(result, list) and all(
                    isinstance(row, dict) for row in result
                )
            if not valid:
                raise CliError(
                    INVALID_RESPONSE, "custom inquiry has invalid native shape"
                )
            trace["succeeded"] += 1
            return result
        except CliError as error:
            self._fatal = error
            trace["error"] = {"code": error.code, "retryable": error.retryable}
            raise
        except Exception as error:
            failure = CliError(INVALID_RESPONSE, "custom inquiry failed")
            self._fatal = failure
            trace["error"] = {"code": failure.code, "retryable": False}
            raise failure from error
        finally:
            trace["requests"] += self._budget.requests - before

    def account_directory(self, source: str) -> dict | None:
        """Read an explicitly enabled local ownership source without publishing."""
        if self._fatal is not None:
            raise self._fatal
        try:
            collection.remaining_seconds(self.deadline)
            if self._declarations.get(
                "account_directory"
            ) is not True or source not in ("duckdog", "cache"):
                raise CliError(
                    REQUEST_NOT_ALLOWED, "account directory source is not declared"
                )
            if self._config_file is None:
                raise CliError(
                    INVALID_RESPONSE, "account directory configuration is missing"
                )
            from .account_sources import read_account_directory

            result = read_account_directory(source, self._config_file)
            collection.remaining_seconds(self.deadline)
            self._queries.setdefault(
                "account_directory",
                {"kind": "local_source", "calls": 0, "requests": 0, "succeeded": 0},
            )
            trace = self._queries["account_directory"]
            trace["calls"] += 1
            trace["succeeded"] += 1
            trace.setdefault("sources", []).append(
                {"source": source, "available": result is not None}
            )
            return result
        except CliError as error:
            self._fatal = error
            raise
        except Exception as error:
            failure = CliError(INVALID_RESPONSE, "account directory source failed")
            self._fatal = failure
            raise failure from error

    def entity_selector(self) -> list[str]:
        """Freeze only the registered read-only entity selector for explicit ANY."""
        if self._fatal is not None:
            raise self._fatal
        try:
            collection.remaining_seconds(self.deadline)
            if self._declarations.get("entity_selector") is not True:
                raise CliError(REQUEST_NOT_ALLOWED, "entity selector is not declared")
            if self._config_file is None:
                raise CliError(
                    INVALID_RESPONSE, "entity selector configuration is missing"
                )
            from dogopencli.duckdog import resolve_selector

            result = resolve_selector(
                "liquidity/reference/entities", "instId", config_file=self._config_file
            )
            collection.remaining_seconds(self.deadline)
            self._queries.setdefault(
                "entity_selector",
                {"kind": "local_selector", "calls": 0, "requests": 0, "succeeded": 0},
            )
            trace = self._queries["entity_selector"]
            trace["calls"] += 1
            trace["succeeded"] += 1
            trace["selected_count"] = len(result)
            return result
        except CliError as error:
            self._fatal = error
            raise
        except Exception as error:
            failure = CliError(INVALID_RESPONSE, "entity selector failed")
            self._fatal = failure
            raise failure from error

    def record_applicability(
        self, name: str, *, applicable: bool | None, reason: str, based_on: str
    ) -> None:
        """Record an unqueried conditional branch, grounded in a native result.

        False means verified inapplicable; None means unresolved coverage. Reasons
        are safe stable codes, never native fields, identities or response text.
        """
        import re

        if self._fatal is not None:
            raise self._fatal
        if not isinstance(name, str) or not isinstance(based_on, str):
            self._fatal = CliError(
                INVALID_RESPONSE, "invalid query applicability evidence"
            )
            raise self._fatal
        declaration = self._declarations["queries"].get(name)
        basis = self._queries.get(based_on, {})
        if (
            declaration is None
            or name in self._queries
            or applicable is not False
            and applicable is not None
            or not isinstance(reason, str)
            or re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", reason) is None
            or based_on not in self._declarations["queries"]
            or not basis.get("succeeded")
        ):
            self._fatal = CliError(
                INVALID_RESPONSE, "invalid query applicability evidence"
            )
            raise self._fatal
        collection.remaining_seconds(self.deadline)
        self._queries[name] = {
            "kind": declaration["kind"],
            "calls": 0,
            "requests": 0,
            "succeeded": 0,
            "applicability": {
                "status": "inapplicable" if applicable is False else "unverified",
                "reason": reason,
                "based_on": based_on,
            },
        }
        if applicable is None:
            self._incomplete = True
            self._required_incomplete |= declaration.get("supplementary") is not True

    def evidence(self) -> dict:
        """Return query facts without lookup identities, rows, or auth material."""
        from copy import deepcopy

        return {
            "kind": "custom_query",
            "operation": self._operation,
            "request_count": self._budget.requests,
            "queries": deepcopy(self._queries),
            **(
                {"coverage": deepcopy(self._coverage)}
                if self._coverage is not None
                else {}
            ),
        }

    def _finish(self) -> None:
        try:
            if self._fatal is not None:
                raise self._fatal
            collection.remaining_seconds(self.deadline)
        finally:
            self.close()

    def finish_list(self, result: CustomListResult) -> collection.CollectedScope:
        self._finish()
        if self._required_failure is not None:
            raise self._required_failure
        if (
            not isinstance(result, CustomListResult)
            or not isinstance(result.records, list)
            or any(not isinstance(row, dict) for row in result.records)
            or not isinstance(result.evidence, AcquisitionEvidence)
        ):
            raise CliError(INVALID_RESPONSE, "invalid custom List result")
        native_witness = any(
            trace.get("succeeded", 0)
            for name, trace in self._queries.items()
            if name in self._declarations["queries"]
        )
        selector = self._queries.get("entity_selector", {})
        empty_universe = (
            selector.get("succeeded", 0)
            and selector.get("selected_count") == 0
            and not result.records
            and result.evidence.collected_total == 0
        )
        if not (native_witness or empty_universe):
            raise CliError(INVALID_RESPONSE, "custom List lacks source evidence")
        if any(
            trace.get("applicability", {}).get("status") == "unverified"
            and self._declarations["queries"][name].get("supplementary") is not True
            for name, trace in self._queries.items()
            if name in self._declarations["queries"]
        ):
            raise CliError(
                INVALID_RESPONSE, "custom List has unverified required queries"
            )
        evidence = AcquisitionEvidence.from_record(result.evidence.record())
        if evidence.collected_total != len(result.records) or (
            self._incomplete and (evidence.scope_complete or evidence.dataset_complete)
        ):
            raise CliError(INVALID_RESPONSE, "custom List coverage contradicts queries")
        evidence = replace(evidence, attempts=(*evidence.attempts, self.evidence()))
        return collection.CollectedScope(
            result.records,
            evidence.scope_complete,
            evidence.reported_total,
            0,
            self._budget.requests,
            False,
            self.deadline,
            evidence,
        )

    def finish_get(self, result: Any, identity: str | None = None) -> dict | list[dict]:
        self._finish()
        if self._required_failure is not None:
            raise self._required_failure
        if self._required_incomplete:
            raise CliError(
                INVALID_RESPONSE, "custom Get has incomplete required queries"
            )
        if not any(
            trace.get("succeeded", 0)
            for name, trace in self._queries.items()
            if name in self._declarations["queries"]
        ):
            raise CliError(INVALID_RESPONSE, "custom Get lacks required query evidence")
        if any(name not in self._queries for name in self._declarations["queries"]):
            raise CliError(INVALID_RESPONSE, "custom Get lacks required query evidence")
        if isinstance(result, CustomGetResult):
            if not isinstance(result.evidence, AcquisitionEvidence):
                raise CliError(INVALID_RESPONSE, "custom Get coverage is invalid")
            evidence = AcquisitionEvidence.from_record(result.evidence.record())
            count = len(result.data) if isinstance(result.data, list) else 1
            if evidence.collected_total != count or evidence.reported_total is not None:
                raise CliError(
                    INVALID_RESPONSE, "custom Get coverage contradicts result"
                )
            if self._incomplete and (
                evidence.scope_complete
                or evidence.dataset_complete
                or not evidence.usable_incomplete
            ):
                raise CliError(
                    INVALID_RESPONSE, "custom Get coverage contradicts queries"
                )
            result = result.data
        else:
            evidence = AcquisitionEvidence(
                scope_complete=False,
                dataset_complete=False,
                collected_total=len(result) if isinstance(result, list) else 1,
                reasons=("COVERAGE_UNPROVEN",),
            )
        evidence = replace(evidence, attempts=(*evidence.attempts, self.evidence()))
        self._coverage = evidence.record()
        context = None
        if "request_fields" in self._declarations["result_identity"]:
            context = {
                **self._parameters,
                self._declarations["lookup"]["name"]: identity,
            }
        validate_detail_result(result, self._declarations, context)
        return result
