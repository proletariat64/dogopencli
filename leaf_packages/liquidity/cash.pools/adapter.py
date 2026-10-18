"""BANK cash pool settings: native list and exact string-identity detail."""

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

PAGE_SIZE = 100
TENANT = "GUAPW3SG"


@dataclass(frozen=True)
class Inquiry:
    name: str = "liquidity.cash.pools.list"
    page_url: str = LIQUIDITY_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/cashPoolList.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset(
            {"tntInstId", "cashPoolCategory", "rowStart", "pageSize"}
        ),
        fixed_body_values=(
            ("tntInstId", TENANT),
            ("cashPoolCategory", "BANK"),
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
            raise CliError(REQUEST_NOT_ALLOWED, "unverified cash.pools request")
        return {
            "rowStart": row_start,
            "pageSize": PAGE_SIZE,
            "tntInstId": TENANT,
            "cashPoolCategory": "BANK",
        }

    def identity_key(self, record: dict[str, Any]) -> str:
        value = record.get("id")
        if (
            not isinstance(value, (str, int))
            or isinstance(value, bool)
            or (isinstance(value, str) and not value.strip())
        ):
            raise CliError(INVALID_RESPONSE, "record is missing identity field id")
        return canonical(value)

    def validate_scope(self, record: dict[str, Any]) -> None:
        if record.get("tntInstId") not in (None, "", TENANT):
            raise CliError(
                INVALID_RESPONSE, "native tenant contradicts requested scope"
            )
        if "cashPoolCategory" in record and record["cashPoolCategory"] != "BANK":
            raise CliError(
                INVALID_RESPONSE, "native pool category contradicts BANK scope"
            )

    def validate_members(self, record: dict[str, Any], field: str, echo: str) -> None:
        members = record.get(field)
        if members is None:
            return
        if not isinstance(members, list) or any(
            not isinstance(row, dict) for row in members
        ):
            raise CliError(
                INVALID_RESPONSE, "native member container is not an object array"
            )
        parent = self.identity_key(record)
        seen: set[str] = set()
        for member in members:
            self.validate_scope(member)
            identity = self.identity_key(member)
            if identity in seen:
                raise CliError(INVALID_RESPONSE, "duplicate native member identity")
            seen.add(identity)
            if echo in member and canonical(member[echo]) != parent:
                raise CliError(
                    INVALID_RESPONSE, "native member parent identity does not match"
                )
            if field == "cashPoolMemberVOS":
                self.validate_members(member, "cashPoolSwapRuleVOS", "cashPoolMemberId")

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
                INVALID_RESPONSE, "record container is not a list of objects"
            )
        if type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE, "reported total is not a nonnegative integer"
            )
        for row in rows:
            self.validate_scope(row)
            self.identity_key(row)
            self.validate_members(row, "cashPoolMemberVOS", "cashPoolId")
        return rows, total


CAPABILITY = Inquiry()


@dataclass(frozen=True)
class DetailInquiry:
    name: str = "liquidity.cash.pools.get"
    page_url: str = LIQUIDITY_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/cashPoolDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"id", "tntInstId", "inUse", "cashPoolCategory"}),
        fixed_body_values=(
            ("tntInstId", TENANT),
            ("inUse", "Y"),
            ("cashPoolCategory", "BANK"),
        ),
    )


DETAIL = DetailInquiry()


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
                        TIMEOUT, "cash.pools page budget exceeded", retryable=True
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

    def get(
        self, session: Any, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        response = collect.execute_bounded(
            DETAIL,
            session.transport(DETAIL),
            {
                "id": identity,
                "tntInstId": TENANT,
                "inUse": "Y",
                "cashPoolCategory": "BANK",
            },
        )
        try:
            document = parse(response.body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "response envelope is not an object")
        if type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "detail success flag is not boolean")
        if document["success"] is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        detail = document.get("data")
        if not isinstance(detail, dict):
            raise CliError(INVALID_RESPONSE, "detail is not an object")
        value = detail.get("id")
        if not isinstance(value, str) or not value.strip() or value != identity:
            raise CliError(
                INVALID_RESPONSE,
                "detail id does not match the requested identity",
            )
        CAPABILITY.validate_scope(detail)
        CAPABILITY.validate_members(detail, "cashPoolMemberVOS", "cashPoolId")
        return detail

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
