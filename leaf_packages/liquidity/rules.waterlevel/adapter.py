"""Native inquiry-only rules.waterlevel contract; no legacy runtime dependencies."""

import json
import time
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

TENANT = "GUAPW3SG"


def result(body: bytes, marker: str = "resultFlag") -> dict[str, Any]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get(marker)) is not bool:
        raise CliError(INVALID_RESPONSE, "invalid business success marker")
    if not document[marker]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    node = document.get("result")
    if not isinstance(node, dict):
        raise CliError(INVALID_RESPONSE, "result is not an object")
    if "success" in node:
        if type(node["success"]) is not bool:
            raise CliError(INVALID_RESPONSE, "inner success is not boolean")
        if not node["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return node


def validate_row(row: Any, field: str) -> None:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get(field), (str, int))
        or isinstance(row[field], bool)
        or (isinstance(row[field], str) and not row[field].strip())
    ):
        raise CliError(INVALID_RESPONSE, "native identity must be a nonempty string")
    if "tntInstId" in row and row["tntInstId"] != TENANT:
        raise CliError(INVALID_RESPONSE, "record tenant contradicts query scope")


class DetailInquiry:
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, leaf: str, path: str, field: str):
        self.name = "liquidity." + leaf + ".get"
        self.contract = EndpointContract(
            method="GET",
            host="iliquidity.alipay.com",
            path=path,
            page_size=0,
            one_based=False,
            allowed_body_keys=frozenset({"tntInstId", field}),
            fixed_body_values=(("tntInstId", TENANT),),
            encoding="query",
        )


DETAIL = DetailInquiry(
    "rules.waterlevel", "/bankAccountBufferListByAliasName.json", "aliasName"
)

PAGE_SIZE = 5000


class Inquiry:
    name = "liquidity.rules.waterlevel.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/bankAccountBufferQuery.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "bankAccountBufferQueryVO"}),
        fixed_body_values=(("tntInstId", TENANT),),
        json_body_contracts=(
            (
                "bankAccountBufferQueryVO",
                frozenset(
                    {
                        "tntInstId",
                        "startCreditDate",
                        "endCreditDate",
                        "rowStart",
                        "pageSize",
                    }
                ),
                (
                    ("tntInstId", TENANT),
                    ("startCreditDate", None),
                    ("endCreditDate", None),
                ),
                frozenset({PAGE_SIZE}),
            ),
        ),
    )

    def page_body(self, scope: str, row_start: int) -> dict[str, Any]:
        if (
            scope
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified waterlevel request")
        return {
            "tntInstId": TENANT,
            "bankAccountBufferQueryVO": json.dumps(
                {
                    "tntInstId": TENANT,
                    "startCreditDate": None,
                    "endCreditDate": None,
                    "rowStart": row_start,
                    "pageSize": PAGE_SIZE,
                }
            ),
        }

    def identity_key(self, row: dict[str, Any]) -> str:
        validate_row(row, "bufferId")
        return canonical(row["bufferId"])

    def parse_rows(self, body: bytes):
        node = result(body)
        rows, total = node.get("dataValue"), node.get("count")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "invalid buffer records or count")
        for row in rows:
            self.identity_key(row)
        return rows, total


CAPABILITY = Inquiry()


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
                        TIMEOUT, "rules.waterlevel page budget exceeded", retryable=True
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
                            INVALID_RESPONSE, "conflicting content for native bufferId"
                        )
                    continue
                seen[identity] = content
                ordered.append(row)
            if progress:
                progress(pages, max(-(-total // PAGE_SIZE), pages))
            if pages * PAGE_SIZE >= total:
                break
        else:
            raise CliError(
                TIMEOUT, "rules.waterlevel page budget exceeded", retryable=True
            )
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
        values = parameters.get("currency") or []
        if isinstance(values, str):
            values = [values]
        return [row for row in records if not values or row.get("currency") in values]

    def get(self, session: Any, parameters: dict[str, Any], identity: str) -> Any:
        response = collect.execute_bounded(
            DETAIL,
            session.transport(DETAIL),
            {"aliasName": identity, "tntInstId": TENANT},
        )
        detail = result(response.body, "resultFlag").get("dataValue")
        if not isinstance(detail, list):
            raise CliError(INVALID_RESPONSE, "account buffer detail is not an array")
        for row in detail:
            validate_row(row, "bufferId")
            if row.get("aliasName") != identity:
                raise CliError(
                    INVALID_RESPONSE, "detail account does not match request"
                )
        return detail


adapter = Adapter()
