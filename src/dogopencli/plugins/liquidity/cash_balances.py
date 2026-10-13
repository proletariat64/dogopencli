"""Cash balance composition: frozen directory binding and native daily chunks.

Only this leaf combines reference inquiries. All transport remains allowlisted,
with one acquisition deadline shared by discovery and balance requests.
"""

import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

from ... import collect as collect_mod
from ...collect import CollectedScope
from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from ...result_policy import AcquisitionEvidence, evidence_for
from .capability import LiquidityListCapability, decode_scope, encode_scope
from .collect import _merge_page, collect_liquidity_scope
from .spec import PROFILE_DATED


def _invalid(message: str) -> CliError:
    return CliError(INVALID_RESPONSE, "cash balances: " + message)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid("missing native string binding " + field)
    return value


def selection(evidence: AcquisitionEvidence) -> dict[str, Any] | None:
    """Persisted provenance, carried atomically with acquisition evidence."""
    return next(
        (
            item
            for item in evidence.attempts
            if item.get("composition") == "cash-balance-selection-v1"
        ),
        None,
    )


def binding_universe(evidence: AcquisitionEvidence) -> str:
    """Semantic equality excludes observation times and acquisition layout."""
    from ...jsonutil import canonical

    frozen = selection(evidence)
    if frozen is None:
        raise _invalid(
            "daily capture has no frozen selection manifest; refresh required"
        )
    entities = frozen.get("entities")
    accounts = frozen.get("accounts")
    if (
        frozen.get("mode") not in ("explicit", "all-directory")
        or not isinstance(entities, list)
        or not isinstance(accounts, list)
    ):
        raise _invalid("invalid frozen selection manifest")
    for entity in entities:
        _text(entity, "entity")
    if len(set(entities)) != len(entities):
        raise _invalid("duplicate frozen entity binding")
    aliases = set()
    for item in accounts:
        if not isinstance(item, dict) or set(item) != {
            "entity",
            "aliasName",
            "currency",
        }:
            raise _invalid("invalid frozen account binding")
        for key in item:
            _text(item[key], key)
        if item["entity"] not in entities or item["aliasName"] in aliases:
            raise _invalid("invalid frozen account universe")
        aliases.add(item["aliasName"])
    return canonical(
        {
            "mode": frozen["mode"],
            "entities": sorted(entities),
            "accounts": sorted(accounts, key=lambda item: item["aliasName"]),
            "timezone": frozen.get("timezone"),
        }
    )


def _dependency(
    session: Any, descriptor: Any, deadline: float
) -> tuple[CollectedScope, dict[str, Any]]:
    capability = LiquidityListCapability(descriptor)
    transport = session.transport(capability)
    try:
        result = collect_liquidity_scope(capability, transport, "", deadline=deadline)
    finally:
        transport.close()
    return result, {
        "endpoint": descriptor.endpoint,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "acquisition": evidence_for(result).record(),
    }


def collect_balances(
    session: Any,
    capability: LiquidityListCapability,
    scope: str,
    *,
    progress: Any = None,
) -> CollectedScope:
    from .leaves import REFERENCE_ENTITIES

    values = decode_scope(scope)
    dated = capability.descriptor.profile == PROFILE_DATED
    all_entities = values.get("__selection") == "all-directory"
    budget = 1800 if all_entities and not dated else 900
    deadline = time.monotonic() + budget
    dependencies = []
    complete = True
    reasons = []
    entities = values.get("entitys", [])
    if all_entities:
        directory, provenance = _dependency(session, REFERENCE_ENTITIES, deadline)
        dependencies.append(provenance)
        entities = sorted(
            {_text(row.get("instId"), "instId") for row in directory.records}
        )
        complete = directory.complete
        reasons.extend(evidence_for(directory).reasons)
    manifest = {
        "composition": "cash-balance-selection-v1",
        "mode": "all-directory" if all_entities else "explicit",
        "entities": entities,
        "accounts": [],
        "dependencies": dependencies,
        "shared_budget_seconds": budget,
        "timezone": "unknown" if dated else values.get("timeZone"),
    }
    if dated:
        result = _collect_daily(
            session, capability, values, entities, manifest, deadline, progress
        )
    elif entities:
        request_scope = encode_scope({**values, "entitys": entities})
        transport = session.transport(capability)
        try:
            result = collect_liquidity_scope(
                capability,
                transport,
                request_scope,
                deadline=deadline,
                progress=progress,
            )
        finally:
            transport.close()
    else:
        # Never send an empty entity array which could mean an unscoped query.
        result = CollectedScope(
            [], True, 0, capability.descriptor.page_size, 0, False, deadline
        )
    native = evidence_for(result)
    dependency_evidence = [
        AcquisitionEvidence.from_record(item["acquisition"]) for item in dependencies
    ]
    complete = (
        native.scope_complete
        and complete
        and all(
            item.scope_complete and item.dataset_complete
            for item in dependency_evidence
        )
    )
    for item in dependency_evidence:
        reasons.extend(item.reasons)
    if not complete and any(not item.scope_complete for item in dependency_evidence):
        reasons.append("DEPENDENCY_INCOMPLETE")
    evidence = replace(
        native,
        scope_complete=complete,
        dataset_complete=complete,
        reasons=tuple(dict.fromkeys([*native.reasons, *reasons])),
        attempts=(*native.attempts, manifest),
    )
    collect_mod.remaining_seconds(deadline)
    return replace(result, complete=complete, evidence=evidence)


def _collect_daily(
    session: Any,
    capability: LiquidityListCapability,
    values: dict[str, Any],
    entities: list[str],
    manifest: dict[str, Any],
    deadline: float,
    progress: Any,
) -> CollectedScope:
    from .leaves import CASH_ACCOUNTS
    from .projection import _validate_amounts
    from .store import series_value

    roster, provenance = _dependency(session, CASH_ACCOUNTS, deadline)
    manifest["dependencies"].append(provenance)
    binding: dict[str, dict[str, str]] = {}
    excluded = 0
    # Validate the full directory before filtering: an ambiguous alias may not
    # be made safe by hiding its other binding outside the selected universe.
    for row in roster.records:
        alias = _text(row.get("aliasName"), "aliasName")
        account = {
            "aliasName": alias,
            "entity": _text(row.get("instId"), "instId"),
            "currency": _text(row.get("currency"), "currency"),
        }
        if alias in binding and binding[alias] != account:
            raise _invalid("ambiguous account alias binding")
        binding[alias] = account
    requested = values.get("aliasNames", [])
    for alias in requested:
        if alias not in binding or binding[alias]["entity"] not in entities:
            raise _invalid("requested alias has no selected account binding")
    selected = {}
    for alias, account in binding.items():
        if account["entity"] not in entities:
            excluded += 1
        elif not requested or alias in requested:
            selected[alias] = account
    aliases = sorted(selected)
    manifest["accounts"] = [selected[alias] for alias in aliases]
    manifest["excluded_account_count"] = excluded
    manifest["binding_semantics"] = "current-roster-not-historical-ownership"
    start = datetime.strptime(values["queryStartDate"], "%Y%m%d")
    end = datetime.strptime(values["queryDate"], "%Y%m%d")
    chunk_count = -(-len(aliases) // 30) * -(-((end - start).days + 1) // 7)
    if chunk_count > 1000:
        raise CliError(
            INVALID_ARGUMENT,
            "daily scope exceeds 1000 chunks; reduce the date window/account selection",
            exit_code=EXIT_USAGE,
        )
    manifest["planned_chunks"] = chunk_count
    # Parse only native identity initially; entity/currency come from this
    # frozen binding, never from native chart id or account-name conventions.
    parser = LiquidityListCapability(
        replace(capability.descriptor, identity=("data", "statisticalDate"))
    )
    transport = session.transport(capability)
    seen: dict[tuple[str, ...], str] = {}
    rows: list[dict[str, Any]] = []
    arrivals = 0
    chunks = 0
    try:
        for offset in range(0, len(aliases), 30):
            batch = aliases[offset : offset + 30]
            day = start
            while day <= end:
                last = day + timedelta(days=min(6, (end - day).days))
                chunk_start = day.date().isoformat().replace("-", "")
                chunk_end = last.date().isoformat().replace("-", "")
                body = capability.page_body(
                    encode_scope(
                        {
                            "aliasNames": batch,
                            "queryStartDate": chunk_start,
                            "queryDate": chunk_end,
                        }
                    ),
                    0,
                )
                response = collect_mod.execute_bounded(
                    capability, transport, body, deadline
                )
                native, _ = parser.parse_rows(response.body)
                composed = []
                for record in native:
                    _text(record.get("id"), "id")
                    alias = record["data"]
                    if alias not in batch:
                        raise _invalid("returned alias is outside the requested chunk")
                    observed = series_value(capability.descriptor, record, "")
                    if not chunk_start <= observed <= chunk_end:
                        raise _invalid("returned date is outside the requested chunk")
                    if "balance" not in record:
                        raise _invalid("daily observation is missing source balance")
                    _validate_amounts(record, ("balance",), "daily_balances")
                    composed.append(
                        {
                            **{
                                key: record[key]
                                for key in ("id", "data", "statisticalDate", "balance")
                                if key in record
                            },
                            **selected[alias],
                        }
                    )
                arrivals += len(composed)
                _merge_page(capability, seen, rows, composed)
                chunks += 1
                if progress is not None:
                    progress(chunks, chunk_count)
                if last == end:
                    break
                day = last + timedelta(days=1)
    finally:
        transport.close()
    manifest["succeeded_chunks"] = chunks
    evidence = AcquisitionEvidence.for_collection(
        complete=True, reported_total=None, collected_total=len(rows), arrivals=arrivals
    )
    return CollectedScope(
        rows, evidence.scope_complete, None, 0, chunks, False, deadline, evidence
    )
