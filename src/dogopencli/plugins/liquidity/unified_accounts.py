"""Composite account directory; source quality stays distinct from normalization."""

import re
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, NoReturn

from ... import collect as collect_mod
from ...collect import CollectedScope
from ...errors import INVALID_RESPONSE, CliError
from ...inquiry import InquirySession
from ...jsonutil import canonical, parse
from ...result_policy import AcquisitionEvidence
from ...transport.cdp import CdpQueryTransport
from .capability import LiquidityListCapability
from .collect import _merge_page, collect_liquidity_scope
from .leaves import NETWORK_BANK_BASELINES, internal_detail_leaf

SCHEMA_VERSION = 2
IDENTITY_FIELDS = ("aliasName", "currency", "bankId", "instId")
SOURCE_FIELDS = ("accountType", "status")
CASH_MODIFICATION_FIELDS = ("gmtModified", "operator")
ACQUISITION_BUDGET_SECONDS = 1800.0


def _invalid(message: str) -> NoReturn:
    raise CliError(INVALID_RESPONSE, message)


def _accounts(
    records: list[dict[str, Any]],
    *,
    require_unique_alias: bool = False,
) -> dict[tuple[str, str], dict[str, Any]]:
    accounts = {}
    aliases = set()
    for row in records:
        for field in IDENTITY_FIELDS[:2]:
            if not isinstance(row.get(field), str) or not row[field].strip():
                _invalid(f"account source requires nonempty {field}")
        for field in IDENTITY_FIELDS[2:]:
            if row.get(field) is not None and not isinstance(row[field], str):
                _invalid(f"account source has invalid {field}")
        alias = row["aliasName"]
        identity = (alias, row["currency"])
        if identity in accounts or require_unique_alias and alias in aliases:
            _invalid("account source has ambiguous native identities")
        accounts[identity] = row
        aliases.add(alias)
    return accounts


def _same_identity(left: dict[str, Any], right: dict[str, Any]) -> None:
    for field in IDENTITY_FIELDS:
        if field in IDENTITY_FIELDS[2:] and any(
            row.get(field) is not None and not isinstance(row[field], str)
            for row in (left, right)
        ):
            _invalid(f"account source has invalid {field}")
        if field in IDENTITY_FIELDS[2:] and (
            left.get(field) in (None, "") or right.get(field) in (None, "")
        ):
            continue
        if field in right and right[field] != left.get(field):
            _invalid(f"account sources disagree on identity field {field}")


def _cash_list(
    capability: LiquidityListCapability,
    transport: CdpQueryTransport,
    scope: str,
    deadline: float,
    progress: Callable[[int, int], None] | None,
) -> CollectedScope:
    seen, records = {}, []
    native_total = None
    arrivals = pages = start = 0
    deficient_pages = []
    size = capability.descriptor.page_size
    while True:
        response = collect_mod.execute_bounded(
            capability, transport, capability.page_body(scope, start), deadline
        )
        rows, total = capability.parse_rows(response.body)
        capability.validate_rows_scope(rows, scope)
        if total is None:
            _invalid("cash directory requires native count")
        if native_total is None:
            native_total = total
            if total > size * collect_mod.MAX_PAGES:
                _invalid("cash directory exceeds bounded page budget")
        elif native_total != total:
            _invalid("cash directory total changed during collection")
        if len(rows) > size:
            _invalid("cash directory page exceeds request size")
        native_span = min(size, total - start)
        if len(rows) < native_span:
            deficient_pages.append(
                {
                    "kind": "cash_native_page",
                    "row_start": start,
                    "native_span": native_span,
                    "returned": len(rows),
                }
            )
        arrivals += len(rows)
        pages += 1
        _merge_page(capability, seen, records, rows)
        if progress:
            progress(pages, max(1, -(-total // size)))
        if start + size >= total:
            break
        start += size
    evidence = AcquisitionEvidence.for_collection(
        complete=arrivals == len(records) == native_total,
        reported_total=native_total,
        collected_total=len(records),
        arrivals=arrivals,
        attempts=tuple(deficient_pages),
    )
    return CollectedScope(
        records,
        evidence.scope_complete,
        native_total,
        size,
        pages,
        False,
        deadline,
        evidence,
    )


def _detail_refusal(body: bytes) -> dict[str, Any] | None:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict):
        _invalid("detail envelope is not an object")
    result = document.get("result")
    # A failed outer request includes permission failures, not evidence of an
    # individual account refusal. Its normal envelope error must propagate.
    refused = (
        document.get("resultFlag") is True
        and isinstance(result, dict)
        and result.get("success") is False
    )
    if not refused:
        return None
    error = {
        "code": "BUSINESS_QUERY_FAILED",
        "message": "backend refused account detail",
    }
    native_code = document.get("errorCode")
    if native_code is None and isinstance(result, dict):
        native_code = result.get("errorCode")
    if isinstance(native_code, (str, int)) and re.fullmatch(
        r"[A-Za-z0-9_.:-]{1,80}", str(native_code)
    ):
        error["native_code"] = native_code
    return error


def _merge(
    cash: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
    detail: dict[str, Any] | None,
    refusal: dict[str, Any] | None,
) -> dict[str, Any]:
    row, provenance, conflicts = {}, {}, {}
    sources = {"cash": cash, "baseline": baseline, "detail": detail}
    for source, record in sources.items():
        for field, value in (record or {}).items():
            if field == "source_metadata" or field == "detail_state":
                continue
            if field in SOURCE_FIELDS and source != "baseline":
                continue
            if field in CASH_MODIFICATION_FIELDS and source != "cash":
                continue
            if field not in row:
                row[field], provenance[field] = value, source
            elif canonical(row[field]) != canonical(value):
                conflicts[field] = {
                    **conflicts.get(field, {}),
                    provenance[field]: row[field],
                    source: value,
                }
            if source == "baseline":
                row[field], provenance[field] = value, source
    # Keep competing native classifications in qualified source metadata.
    for field in (*SOURCE_FIELDS, *CASH_MODIFICATION_FIELDS):
        values = {
            source: record[field]
            for source, record in sources.items()
            if record is not None and field in record
        }
        if len({canonical(value) for value in values.values()}) > 1:
            conflicts[field] = values
    row["detail_state"] = (
        "succeeded" if detail is not None else "refused" if refusal else "missing"
    )
    row["source_metadata"] = {
        "schema_version": SCHEMA_VERSION,
        "presence": {source: record is not None for source, record in sources.items()},
        "matched": cash is not None and baseline is not None,
        "provenance": provenance,
        "raw": {
            source: record for source, record in sources.items() if record is not None
        },
        "conflicts": conflicts,
        "detail_error": refusal,
    }
    return row


def collect_accounts(
    session: InquirySession,
    capability: LiquidityListCapability,
    scope: str,
    *,
    progress: Callable[[int, int], None] | None = None,
    hint_path: Path | None = None,
) -> CollectedScope:
    deadline = time.monotonic() + ACQUISITION_BUDGET_SECONDS
    started = time.monotonic()
    cash_transport = session.transport(capability)
    cash = _cash_list(capability, cash_transport, scope, deadline, progress)
    cash_by_identity = _accounts(cash.records)
    accepted = None
    normalized_cash = cash.evidence
    if cash.total_count - len(cash.records) == 1 and cash.evidence.duplicate_count == 0:
        from .account_hole import verify_hole

        if hint_path is None:
            from .common import load_config

            hint_path = Path(str(load_config().cache_path) + ".account-hole-hints.json")
        deficient_interval = None
        if len(cash.evidence.attempts) == 1:
            page = cash.evidence.attempts[0]
            if page["native_span"] - page["returned"] == 1:
                deficient_interval = (
                    page["row_start"],
                    page["row_start"] + page["native_span"],
                )
        accepted = verify_hole(
            capability,
            cash_transport,
            scope,
            cash.records,
            cash.total_count,
            deadline,
            hint_path=hint_path,
            deficient_interval=deficient_interval,
        )
        if accepted:
            normalized_cash = AcquisitionEvidence.for_collection(
                complete=True,
                reported_total=accepted["effective_total"],
                collected_total=len(cash.records),
                arrivals=cash.evidence.arrivals,
            )
    baseline_capability = LiquidityListCapability(
        replace(NETWORK_BANK_BASELINES, page_size=1000)
    )
    baseline = collect_liquidity_scope(
        baseline_capability,
        session.transport(baseline_capability),
        "",
        deadline=deadline,
    )
    baseline_by_identity = _accounts(baseline.records, require_unique_alias=True)
    for identity in cash_by_identity.keys() & baseline_by_identity.keys():
        _same_identity(cash_by_identity[identity], baseline_by_identity[identity])
    detail_capability = internal_detail_leaf(
        ("network", "bank-baselines", "get")
    ).capability
    detail_transport = session.transport(detail_capability)
    details, refusals = {}, {}
    inventory = {"cash": set(), "baseline": set(), "detail": set()}
    for source, result in (("cash", cash), ("baseline", baseline)):
        for row in result.records:
            inventory[source].update(row)
    for done, (identity, account) in enumerate(baseline_by_identity.items(), 1):
        values = {"account": account["aliasName"]}
        response = collect_mod.execute_bounded(
            detail_capability,
            detail_transport,
            detail_capability.detail_body(values),
            min(deadline, time.monotonic() + 30),
        )
        refusal = _detail_refusal(response.body)
        if refusal is not None:
            refusals[identity] = refusal
        else:
            detail = detail_capability.parse_detail(response.body, values)
            _same_identity(account, detail)
            details[identity] = detail
            inventory["detail"].update(detail)
        print(
            f"accounts: details {done}/{len(baseline_by_identity)}; "
            f"elapsed {time.monotonic() - started:.1f}s",
            file=sys.stderr,
        )
    identities = list(cash_by_identity) + [
        identity
        for identity in baseline_by_identity
        if identity not in cash_by_identity
    ]
    rows = [
        _merge(
            cash_by_identity.get(identity),
            baseline_by_identity.get(identity),
            details.get(identity),
            refusals.get(identity),
        )
        for identity in identities
    ]
    matched = len(cash_by_identity.keys() & baseline_by_identity.keys())
    lists_complete = (
        normalized_cash.scope_complete
        and baseline.complete
        and matched == len(cash_by_identity) == len(baseline_by_identity)
    )
    detail_complete = len(details) == len(baseline_by_identity)
    reasons = list(normalized_cash.reasons) + list(baseline.evidence.reasons)
    if matched != len(cash_by_identity) or matched != len(baseline_by_identity):
        reasons.append("ACCOUNT_SOURCE_MISMATCH")
    if not detail_complete:
        reasons.append("DETAIL_COVERAGE_INCOMPLETE")
    attempt = {
        "kind": "unified_cash_accounts",
        "schema_version": SCHEMA_VERSION,
        "sources": {
            "cash": cash.evidence.record(),
            "baseline": baseline.evidence.record(),
        },
        "list_coverage": {
            "complete": lists_complete,
            "matched": matched,
            "cash_only": len(cash_by_identity) - matched,
            "baseline_only": len(baseline_by_identity) - matched,
        },
        "detail_coverage": {
            "complete": detail_complete,
            "required": len(baseline_by_identity),
            "attempted": len(baseline_by_identity),
            "succeeded": len(details),
            "refused": len(refusals),
            "failed": 0,
        },
        "field_inventory": {
            source: sorted(fields) for source, fields in inventory.items()
        },
        "accepted_diagnostics": [accepted] if accepted else [],
    }
    evidence = AcquisitionEvidence.for_collection(
        complete=lists_complete and detail_complete,
        reported_total=len(rows),
        collected_total=len(rows),
        arrivals=len(rows),
        reasons=tuple(dict.fromkeys(reasons)),
        attempts=(attempt,),
    )
    return replace(
        cash,
        records=rows,
        complete=evidence.scope_complete,
        total_count=len(rows),
        evidence=evidence,
    )


def account_meta(evidence: AcquisitionEvidence) -> dict[str, Any]:
    attempt = next(
        (
            item
            for item in evidence.attempts
            if item.get("kind") == "unified_cash_accounts"
        ),
        None,
    )
    if attempt is None or attempt.get("schema_version") != SCHEMA_VERSION:
        _invalid(
            "cash account cache schema is incompatible; run dogopencli refresh "
            "liquidity cash accounts"
        )
    required = {
        "sources",
        "list_coverage",
        "detail_coverage",
        "field_inventory",
        "accepted_diagnostics",
    }
    if not required.issubset(attempt):
        _invalid("cached unified account evidence is missing components")
    if any(
        not isinstance(attempt[key], dict)
        for key in required - {"accepted_diagnostics"}
    ):
        _invalid("cached unified account evidence has invalid components")
    if not isinstance(attempt["accepted_diagnostics"], list):
        _invalid("cached accepted-hole evidence is invalid")
    return {
        key: attempt[key]
        for key in (
            "sources",
            "list_coverage",
            "detail_coverage",
            "field_inventory",
            "accepted_diagnostics",
        )
    }


def validate_cached_accounts(
    records: list[dict[str, Any]], evidence: AcquisitionEvidence
) -> dict[str, Any]:
    meta = account_meta(evidence)
    _accounts(records)
    for row in records:
        source = row.get("source_metadata")
        if (
            not isinstance(source, dict)
            or source.get("schema_version") != SCHEMA_VERSION
        ):
            _invalid(
                "cash account cache schema is incompatible; "
                "refresh liquidity cash accounts"
            )
        raw = source.get("raw")
        if (
            not isinstance(raw, dict)
            or not raw
            or any(
                name not in ("cash", "baseline", "detail")
                or not isinstance(value, dict)
                for name, value in raw.items()
            )
        ):
            _invalid("cached account provenance is invalid")
        cash, baseline, detail = (
            raw.get(name) for name in ("cash", "baseline", "detail")
        )
        if cash is not None and baseline is not None:
            _same_identity(cash, baseline)
        if detail is not None:
            if baseline is None:
                _invalid("cached detail has no baseline provenance")
            _same_identity(baseline, detail)
        refusal = source.get("detail_error")
        if refusal is not None and (
            not isinstance(refusal, dict)
            or refusal.get("code") != "BUSINESS_QUERY_FAILED"
            or refusal.get("message") != "backend refused account detail"
            or detail is not None
            or baseline is None
        ):
            _invalid("cached detail refusal evidence is invalid")
        rebuilt = _merge(cash, baseline, detail, refusal)
        if canonical(rebuilt) != canonical(row):
            _invalid("cached account fields disagree with source provenance")
    qualities = {}
    for source in ("cash", "baseline"):
        source_records = [
            row["source_metadata"]["raw"][source]
            for row in records
            if source in row["source_metadata"]["raw"]
        ]
        _accounts(source_records, require_unique_alias=source == "baseline")
        quality = AcquisitionEvidence.from_record(meta["sources"].get(source))
        qualities[source] = quality
        count = sum(source in row["source_metadata"]["raw"] for row in records)
        if quality.collected_total != count:
            _invalid("cached account source count conflicts")
    details = meta["detail_coverage"]
    succeeded = sum(row["detail_state"] == "succeeded" for row in records)
    refused = sum(row["detail_state"] == "refused" for row in records)
    required = sum("baseline" in row["source_metadata"]["raw"] for row in records)
    if details != {
        "complete": succeeded == required,
        "required": required,
        "attempted": required,
        "succeeded": succeeded,
        "refused": refused,
        "failed": 0,
    }:
        _invalid("cached account detail evidence conflicts")
    matched = sum(row["source_metadata"]["matched"] for row in records)
    cash, baseline = qualities["cash"], qualities["baseline"]
    accepted = meta["accepted_diagnostics"]
    cash_complete = cash.scope_complete
    if accepted:
        if len(accepted) != 1 or not isinstance(accepted[0], dict):
            _invalid("cached accepted-hole evidence is invalid")
        hole = accepted[0]
        offset = hole.get("hole_offset")
        verification = hole.get("verification")
        if (
            hole.get("code") != "VERIFIED_BACKEND_HOLE"
            or hole.get("native_total") != cash.reported_total
            or hole.get("effective_total") != cash.collected_total
            or cash.reported_total != cash.collected_total + 1
            or cash.duplicate_count != 0
            or type(offset) is not int
            or not 0 < offset < cash.reported_total - 1
            or not isinstance(verification, dict)
            or not isinstance(verification.get("probes"), list)
        ):
            _invalid("cached accepted-hole counts conflict")
        probes = verification["probes"]
        expected = {
            (offset, 1, 0): 3,
            (offset - 1, 1, 1): 2,
            (offset + 1, 1, 1): 2,
            (offset - 1, 3, 2): 1,
        }
        for (start, size, returned), minimum in expected.items():
            if (
                sum(
                    probe
                    == {"row_start": start, "page_size": size, "returned": returned}
                    for probe in probes
                )
                < minimum
            ):
                _invalid("cached accepted-hole verification is missing probes")
        cash_complete = True
    list_complete = (
        cash_complete
        and baseline.scope_complete
        and matched == cash.collected_total == baseline.collected_total
    )
    if meta["list_coverage"] != {
        "complete": list_complete,
        "matched": matched,
        "cash_only": cash.collected_total - matched,
        "baseline_only": baseline.collected_total - matched,
    }:
        _invalid("cached unified list coverage conflicts")
    complete = list_complete and succeeded == required
    if evidence.scope_complete != complete or evidence.dataset_complete != complete:
        _invalid("cached unified completeness conflicts")
    reasons = [] if cash_complete else list(cash.reasons)
    reasons += list(baseline.reasons)
    if matched != cash.collected_total or matched != baseline.collected_total:
        reasons.append("ACCOUNT_SOURCE_MISMATCH")
    if succeeded != required:
        reasons.append("DETAIL_COVERAGE_INCOMPLETE")
    if evidence.reasons != tuple(dict.fromkeys(reasons)):
        _invalid("cached unified incomplete reasons conflict")
    return meta
