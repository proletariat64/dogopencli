"""Investment benchmark rules: native id and fixed empty date scope."""

import time
from dataclasses import dataclass
from typing import Any

from dogopencli import collect
from dogopencli.collect import CollectedScope
from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    TIMEOUT,
    CliError,
)
from dogopencli.jsonutil import canonical, parse
from dogopencli.result_policy import AcquisitionEvidence

PAGE_SIZE = 5000
TENANT = "GUAPW3SG"


@dataclass(frozen=True)
class BenchmarkInquiry:
    name: str = "liquidity.investment.benchmarks.list"
    page_url: str = LIQUIDITY_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/queryStrategyBenchmarkRuleList.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset(
            {
                "tntInstId",
                "timeZone",
                "valueDateStart",
                "valueDateEnd",
                "rowStart",
                "pageSize",
            }
        ),
        fixed_body_values=(
            ("tntInstId", TENANT),
            ("timeZone", "GMT+08"),
            ("valueDateStart", ""),
            ("valueDateEnd", ""),
            ("pageSize", PAGE_SIZE),
        ),
    )

    def page_body(self, scope: str, row_start: int) -> dict[str, Any]:
        if (
            scope
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified benchmark request")
        return {
            "tntInstId": TENANT,
            "timeZone": "GMT+08",
            "valueDateStart": "",
            "valueDateEnd": "",
            "rowStart": row_start,
            "pageSize": PAGE_SIZE,
        }

    def identity_key(self, record: dict[str, Any]) -> str:
        value = record.get("id")
        if (
            value is None
            or isinstance(value, (bool, dict, list))
            or (isinstance(value, str) and not value.strip())
        ):
            raise CliError(INVALID_RESPONSE, "record is missing identity field id")
        return canonical(value)

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "response envelope is not an object")
        if document.get("success") is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        result = document.get("data")
        if not isinstance(result, dict):
            raise CliError(INVALID_RESPONSE, "response data is not an object")
        if result.get("success") is False:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        rows, total = result.get("data"), result.get("totalCount")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(
                INVALID_RESPONSE, "record container is not a list of objects"
            )
        if type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE, "reported total is not a nonnegative integer"
            )
        for row in rows:
            self.identity_key(row)
        return rows, total


CAPABILITY = BenchmarkInquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return ""

    def collector(
        self, capability: Any, transport: Any, scope: str, *, progress: Any = None
    ) -> CollectedScope:
        deadline = time.monotonic() + collect.REFRESH_BUDGET_SECONDS
        ordered: list[dict[str, Any]] = []
        seen: dict[str, str] = {}
        total: int | None = None
        arrivals = 0
        pages = 0
        for page_no in range(collect.MAX_PAGES):
            collect.remaining_seconds(deadline)
            response = collect.execute_bounded(
                capability,
                transport,
                capability.page_body(scope, page_no * PAGE_SIZE),
                deadline,
            )
            rows, page_total = capability.parse_rows(response.body)
            if total is None:
                total = page_total
                if total > collect.MAX_PAGES * PAGE_SIZE:
                    raise CliError(
                        TIMEOUT, "benchmark page budget exceeded", retryable=True
                    )
            elif page_total != total:
                raise CliError(
                    INVALID_RESPONSE, "backend total changed during collection"
                )
            if len(rows) > PAGE_SIZE:
                raise CliError(
                    INVALID_RESPONSE,
                    "page returned more rows than the verified page size",
                )
            if not rows and arrivals < total:
                raise CliError(
                    INVALID_RESPONSE,
                    "collection made no progress: empty page before the total",
                )
            pages += 1
            arrivals += len(rows)
            for row in rows:
                identity, content = capability.identity_key(row), canonical(row)
                if identity in seen:
                    if seen[identity] != content:
                        raise CliError(
                            INVALID_RESPONSE, "conflicting content for native id"
                        )
                    continue
                seen[identity] = content
                ordered.append(row)
            if progress:
                progress(pages, max(-(-total // PAGE_SIZE), pages))
            if pages * PAGE_SIZE >= total:
                break
        else:
            raise CliError(TIMEOUT, "benchmark page budget exceeded", retryable=True)
        collect.remaining_seconds(deadline)
        evidence = AcquisitionEvidence.for_collection(
            complete=arrivals == total == len(ordered),
            reported_total=total,
            collected_total=len(ordered),
            arrivals=arrivals,
        )
        return CollectedScope(
            ordered,
            evidence.scope_complete,
            total,
            PAGE_SIZE,
            pages,
            False,
            deadline,
            evidence,
        )

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
