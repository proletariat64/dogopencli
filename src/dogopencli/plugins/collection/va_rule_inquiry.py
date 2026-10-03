"""Collection VA Rule acquisition, snapshot reads and Detail Refusal policy.

Only an explicit refusal permits publication with a missing detail. Safe
list coverage gaps and detail refusals retain distinct evidence; strict
mode rejects before publication. Other failures preserve old data.
"""

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from ... import collect
from ...cache import Cache, SnapshotMeta, namespace
from ...cached_query import CachedQuery, read_cached_query
from ...config import Config, SourceConfig
from ...errors import INCOMPLETE_RESULT, NOT_FOUND, CliError
from ...inquiry import InquirySession
from ...jsonutil import canonical
from ...result_policy import check_complete, evidence_for
from ...transport.cdp import CdpQueryTransport
from ..envelope import is_business_refusal
from . import va_rule


@dataclass(frozen=True)
class VaRuleSnapshot:
    """Validated rule/detail pairs with domain-aware offline detail lookup."""

    _cached: CachedQuery
    _pairs: list[dict[str, Any]]

    @property
    def rows(self) -> list[dict[str, Any]]:
        return [pair["rule"] for pair in self._pairs]

    def meta(
        self, matched_total: int, returned_count: int, *, offset: int = 0
    ) -> dict[str, Any]:
        """Expose result metadata without exposing serialized cache storage."""
        return self._cached.meta(matched_total, returned_count, offset=offset)

    def detail(self, identity: str) -> dict[str, Any]:
        pair = next(
            (pair for pair in self._pairs if pair["rule"]["vaRuleId"] == identity),
            None,
        )
        if pair is None:
            if not self._cached.snapshot.backend_complete:
                raise CliError(
                    INCOMPLETE_RESULT,
                    "cannot confirm absence in incomplete VA rule snapshot",
                )
            raise CliError(NOT_FOUND, "VA rule is not present in the cached snapshot")
        if pair["detail"] is None:
            raise CliError(
                INCOMPLETE_RESULT,
                "VA rule detail was refused by the backend;"
                " run: dogopencli refresh collection va",
            )
        return pair["detail"]


def read_snapshot(
    config: Config,
    source: SourceConfig,
    *,
    require_fresh: bool,
    require_complete: bool,
    now: datetime,
) -> VaRuleSnapshot:
    cap = va_rule.COLLECTION_VA_RULES
    cached = read_cached_query(
        config,
        source,
        cap.name,
        cap.default_scope,
        refresh_command="refresh collection va",
        require_fresh=require_fresh,
        require_complete=require_complete,
        now=now,
    )
    if require_complete and not cached.snapshot.dataset_complete:
        raise CliError(
            INCOMPLETE_RESULT,
            "cached VA rule snapshot has details the backend refused;"
            " run: dogopencli refresh collection va",
        )
    pairs = cached.validated_records(
        va_rule.validate_stored_pair,
        lambda record: record["rule"]["vaRuleId"],
        coverage_error="cached VA rule coverage is invalid",
    )
    return VaRuleSnapshot(cached, pairs)


def fetch_detail(transport: CdpQueryTransport, identity: str) -> dict[str, Any]:
    """Explicit live get is strict; refusal tolerance is private to refresh."""
    response = collect.execute_bounded(
        va_rule.COLLECTION_VA_RULES_DETAIL, transport, {"vaRuleId": identity}
    )
    return va_rule.parse_detail(response.body, identity)


def refresh(
    config: Config,
    source: SourceConfig,
    *,
    session_factory: Callable[[], AbstractContextManager[InquirySession]],
    now: Callable[[], datetime],
    progress: Callable[[int, int], None],
    detail_progress: Callable[[str], None],
    require_complete: bool = False,
) -> SnapshotMeta:
    """Publish a validated candidate, preserving actual list/detail quality."""
    cap = va_rule.COLLECTION_VA_RULES
    store = Cache(config.cache_path)
    ns = namespace(cap.name, cap.default_scope, source.kind)
    with store.refresh_lock():
        with session_factory() as session:
            result = collect.collect_scope(
                cap, session.transport(cap), cap.default_scope, progress=progress
            )
            evidence = evidence_for(result)
            check_complete(evidence, require_complete=require_complete, mode="refresh")
            transport = session.transport(va_rule.COLLECTION_VA_RULES_DETAIL)
            pairs = []
            refused = 0
            for record in cap.sort_records(result.records):
                identity = record[cap.id_field]
                response = collect.execute_bounded(
                    va_rule.COLLECTION_VA_RULES_DETAIL,
                    transport,
                    {"vaRuleId": identity},
                    result.deadline,
                )
                if is_business_refusal(response.body):
                    detail = None
                    refused += 1
                else:
                    detail = va_rule.parse_detail(response.body, identity)
                    va_rule.validate_pair(record, detail)
                pairs.append({"rule": record, "detail": detail})
                detail_progress(
                    f"refresh: detail "
                    f"{'refused' if detail is None else 'collected'} "
                    f"{len(pairs)}/{len(result.records)}"
                )
            if evidence.attempts:
                evidence = replace(
                    evidence,
                    attempts=(
                        *evidence.attempts[:-1],
                        {
                            **evidence.attempts[-1],
                            "details_requested": len(pairs),
                            "details_collected": len(pairs) - refused,
                            "details_refused": refused,
                        },
                    ),
                )
            if refused:
                evidence = replace(
                    evidence,
                    dataset_complete=False,
                    reasons=evidence.reasons + ("DETAIL_REFUSED",),
                )
            check_complete(evidence, require_complete=require_complete, mode="refresh")
        fetched_at = now().isoformat()
        snapshot = SnapshotMeta(
            namespace=ns,
            capability=cap.name,
            scope=cap.default_scope,
            source_kind=source.kind,
            snapshot_id=hashlib.sha256(canonical(pairs).encode()).hexdigest(),
            dataset_id=None,
            simulated=False,
            backend_complete=evidence.scope_complete,
            dataset_complete=evidence.dataset_complete,
            fetched_at=fetched_at,
            loaded_at=now().isoformat(),
            source_observed_from=None,
            source_observed_to=None,
            row_count=len(pairs),
            acquisition=evidence.record(),
        )
        collect.remaining_seconds(result.deadline)
        store.publish(
            snapshot, [(i, canonical(pair)) for i, pair in enumerate(pairs, 1)]
        )
    return snapshot
