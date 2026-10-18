"""Account buffer state, scoped by native alias, with full native records."""

import time
from dataclasses import dataclass
from typing import Any

from dogopencli import collect
from dogopencli.collect import CollectedScope
from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    TIMEOUT,
    CliError,
)
from dogopencli.jsonutil import canonical, parse
from dogopencli.result_policy import AcquisitionEvidence

PAGE_SIZE = 1000


@dataclass(frozen=True)
class Inquiry:
    name: str = "liquidity.cash.waterlevels.list"
    page_url: str = LIQUIDITY_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/bufferReportList.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"aliasNameList", "rowStart", "pageSize"}),
        fixed_body_values=(("pageSize", PAGE_SIZE),),
    )

    def page_body(self, scope: str, row_start: int) -> dict[str, Any]:
        values = parse(scope)
        if (
            not isinstance(values, dict)
            or set(values) != {"aliasNameList"}
            or not isinstance(values["aliasNameList"], list)
            or len(values["aliasNameList"]) != 1
            or not isinstance(values["aliasNameList"][0], str)
            or not values["aliasNameList"][0].strip()
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified waterlevel request")
        return {
            "aliasNameList": values["aliasNameList"],
            "rowStart": row_start,
            "pageSize": PAGE_SIZE,
        }

    def identity_key(self, record: dict[str, Any]) -> str:
        values = [record.get(field) for field in ("aliasName", "currency")]
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise CliError(
                INVALID_RESPONSE,
                "waterlevel requires native aliasName and currency strings",
            )
        return canonical(values)

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "response envelope is not an object")
        if type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "success is not boolean")
        if document["success"] is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        result = document.get("data")
        if not isinstance(result, dict):
            raise CliError(INVALID_RESPONSE, "response result is not an object")
        if result.get("success") is False:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        rows, total = result.get("data"), result.get("totalCount")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(
                INVALID_RESPONSE,
                "record container is not a list of objects",
            )
        if type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE,
                "reported total is not a nonnegative integer",
            )
        for row in rows:
            self.identity_key(row)
        return rows, total


CAPABILITY = Inquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        self.scope(parameters)
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        alias = parameters.get("account_alias")
        if not isinstance(alias, str) or not alias.strip():
            raise CliError(INVALID_ARGUMENT, "account-alias requires a nonempty string")
        return canonical({"aliasNameList": [alias]})

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
            alias = parse(scope)["aliasNameList"][0]
            if any(row["aliasName"] != alias for row in rows):
                raise CliError(
                    INVALID_RESPONSE, "waterlevel alias contradicts requested scope"
                )
            if total is None:
                total = page_total
                if total > collect.MAX_PAGES * PAGE_SIZE:
                    raise CliError(
                        TIMEOUT,
                        "cash.waterlevels page budget exceeded",
                        retryable=True,
                    )
            elif page_total != total:
                raise CliError(
                    INVALID_RESPONSE,
                    "backend total changed during collection",
                )
            if len(rows) > PAGE_SIZE:
                raise CliError(
                    INVALID_RESPONSE,
                    "page returned more rows than the verified page size",
                )
            if len(rows) < min(PAGE_SIZE, total - arrivals):
                raise CliError(
                    INVALID_RESPONSE,
                    "short native page before the reported total",
                )
            pages += 1
            arrivals += len(rows)
            for row in rows:
                identity, content = capability.identity_key(row), canonical(row)
                if identity in seen:
                    if seen[identity] != content:
                        raise CliError(
                            INVALID_RESPONSE,
                            "conflicting content for native id",
                        )
                    continue
                seen[identity] = content
                ordered.append(row)
            if progress:
                progress(pages, max(-(-total // PAGE_SIZE), pages))
            if pages * PAGE_SIZE >= total:
                break
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
        selected = parameters.get("currency") or []
        return [
            row for row in records if not selected or row.get("currency") in selected
        ]


adapter = Adapter()
