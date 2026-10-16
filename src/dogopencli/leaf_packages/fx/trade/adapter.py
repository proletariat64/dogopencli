"""Bounded RiskStandardTrade inquiry; identity and totals remain unproven."""

import json
import time
from types import SimpleNamespace
from typing import Any

from dogopencli.collect import CollectedScope
from dogopencli.errors import (
    AUTH_REQUIRED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    TIMEOUT,
    CliError,
)
from dogopencli.jsonutil import canonical
from dogopencli.plugins.fx.trade import ARRAY_FILTERS, FX_TRADE, query_request
from dogopencli.result_policy import AcquisitionEvidence
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import FetchFailed

MAX_PAGES = 100
ACQUISITION_SECONDS = 120.0


def acquire(
    transport: Any, query: dict[str, Any]
) -> tuple[list[dict[str, Any]], AcquisitionEvidence, int]:
    deadline = time.monotonic() + ACQUISITION_SECONDS
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    total: int | None = None
    reasons = ["IDENTITY_UNPROVEN", "TOTAL_SEMANTICS_UNPROVEN"]
    pages = 0
    for page_no in range(MAX_PAGES):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            reasons.append("ACQUISITION_BUDGET_EXHAUSTED")
            break
        contract = FX_TRADE.contract
        request = QueryRequest(
            capability=FX_TRADE.name,
            method=contract.method,
            host=contract.host,
            path=contract.path,
            body={
                "queryRequest": query,
                "pageSize": contract.page_size,
                "pageNo": page_no,
            },
        )
        try:
            response = transport.execute(request, timeout=remaining)
        except FetchFailed as error:
            # A transport failure withholds the entire candidate.
            raise CliError(TIMEOUT, "FX trade fetch failed", retryable=True) from error
        if response.status in (401, 403):
            raise CliError(
                AUTH_REQUIRED,
                "FX authorization required; run dogopencli login --domain fx",
            )
        if response.status != 200:
            raise CliError(
                INVALID_RESPONSE, f"unexpected FX HTTP status {response.status}"
            )
        page = FX_TRADE.parse_page(response.body)
        if page.page_num != page_no or page.page_size != contract.page_size:
            raise CliError(INVALID_RESPONSE, "FX pagination echo mismatch")
        if total is None:
            total = page.total_count
        elif total != page.total_count:
            raise CliError(
                INVALID_RESPONSE, "FX reported total changed during acquisition"
            )
        pages += 1
        # Detect identical overlap without asserting a business identity.
        duplicate = False
        for row in page.records:
            key = canonical(row)
            if key in seen:
                duplicate = True
            seen.add(key)
        rows.extend(page.records)
        if len(rows) > total:
            raise CliError(INVALID_RESPONSE, "FX arrivals exceed reported total")
        if duplicate:
            reasons.append("UNEXPECTED_DUPLICATE_ROWS")
            break
        if len(rows) == total:
            break
        if len(page.records) < contract.page_size:
            reasons.append("COUNT_SHORTFALL")
            break
    else:
        reasons.append("PAGE_BUDGET_EXHAUSTED")
    if total is None:
        raise CliError(TIMEOUT, "FX acquisition budget exhausted before the first page")
    evidence = AcquisitionEvidence(
        scope_complete=False,
        dataset_complete=False,
        collected_total=len(rows),
        reported_total=total,
        arrivals=len(rows),
        total_semantics="unknown",
        reasons=tuple(dict.fromkeys(reasons)),
    )
    return rows, evidence, pages


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return FX_TRADE

    def scope(self, parameters: dict[str, Any]) -> str:
        values = {key.replace("-", "_"): value for key, value in parameters.items()}
        for flag, _ in ARRAY_FILTERS:
            values.setdefault(flag, [])
            if values[flag] is None:
                values[flag] = []
        for flag in ("scene", "fulfilled", "transact_from", "transact_to"):
            values.setdefault(flag, None)
        return canonical(query_request(SimpleNamespace(**values)))

    def collector(
        self, capability: Any, transport: Any, scope: str, *, progress: Any = None
    ) -> Any:
        deadline = time.monotonic() + ACQUISITION_SECONDS
        rows, evidence, pages = acquire(transport, json.loads(scope))
        if progress:
            progress(pages, pages)
        return CollectedScope(
            rows,
            False,
            evidence.reported_total,
            capability.contract.page_size,
            pages,
            False,
            deadline,
            evidence,
        )

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if any(value is not None and value != [] for value in parameters.values()):
            raise CliError(
                INVALID_ARGUMENT,
                "FX cached filters have no verified row mapping; use --live",
                exit_code=2,
            )
        return records


adapter = Adapter()
