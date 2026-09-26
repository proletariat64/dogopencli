"""Collection VA Rule acquisition, snapshot reads and Detail Refusal policy.

ADR 0010 belongs here: only an explicit refusal permits publication with a
missing detail, and that publication still fails. Other failures preserve
old data. The CLI need not interpret null details or completeness flags.
"""

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ... import collect
from ...cache import Cache, SnapshotMeta, namespace
from ...cached_query import CachedQuery, read_cached_query
from ...config import Config, SourceConfig
from ...errors import INCOMPLETE_RESULT, NOT_FOUND, CliError
from ...inquiry import InquirySession
from ...jsonutil import canonical
from ...transport.cdp import CdpQueryTransport
from ..envelope import is_business_refusal
from . import va_rule


@dataclass(frozen=True)
class VaRuleSnapshot:
    """Validated rule/detail pairs with domain-aware offline detail lookup."""

    cached: CachedQuery
    _pairs: list[dict[str, Any]]

    @property
    def rows(self) -> list[dict[str, Any]]:
        return [pair["rule"] for pair in self._pairs]

    def detail(self, identity: str) -> dict[str, Any]:
        pair = next(
            (pair for pair in self._pairs if pair["rule"]["vaRuleId"] == identity),
            None,
        )
        if pair is None:
            if not self.cached.snapshot.backend_complete:
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
) -> SnapshotMeta:
    """Publish the newest acquisition, then fail if any detail was refused."""
    cap = va_rule.COLLECTION_VA_RULES
    store = Cache(config.cache_path)
    ns = namespace(cap.name, cap.default_scope, source.kind)
    with store.refresh_lock():
        with session_factory() as session:
            result = collect.collect_scope(
                cap, session.transport(cap), cap.default_scope, progress=progress
            )
            if not result.complete:
                raise CliError(
                    INCOMPLETE_RESULT, "collection VA rule list is incomplete"
                )
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
        fetched_at = now().isoformat()
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
            loaded_at=now().isoformat(),
            source_observed_from=None,
            source_observed_to=None,
            row_count=len(pairs),
        )
        collect.remaining_seconds(result.deadline)
        store.publish(
            snapshot, [(i, canonical(pair)) for i, pair in enumerate(pairs, 1)]
        )
    if refused:
        raise CliError(
            INCOMPLETE_RESULT,
            f"published {len(pairs) - refused}/{len(pairs)} collection VA rule"
            f" details; {refused} refused by the backend",
        )
    return snapshot
