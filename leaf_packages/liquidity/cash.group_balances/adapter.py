"""Group balance snapshots: native USD-equivalent inquiry and full records."""

import json
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

PAGE_SIZE = 100
TENANT = "GUAPW3SG"


@dataclass(frozen=True)
class Inquiry:
    name: str = "liquidity.cash.group_balances.list"
    page_url: str = LIQUIDITY_STARTUP_URL
    group_codes: tuple[str, ...] = ()

    @property
    def contract(self) -> EndpointContract:
        keys = {"tntInstId", "equiCurrency", "rowStart", "pageSize"}
        if self.group_codes:
            keys.add("userGroupCode")
        return EndpointContract(
            method="GET",
            host="iliquidity.alipay.com",
            path="/bankAccountGroupQuery.json",
            page_size=PAGE_SIZE,
            one_based=False,
            allowed_body_keys=frozenset({"tntInstId", "bankAccountManageUnitQueryVO"}),
            fixed_body_values=(("tntInstId", TENANT),),
            json_body_contracts=(
                (
                    "bankAccountManageUnitQueryVO",
                    frozenset(keys),
                    (("tntInstId", TENANT), ("equiCurrency", "USD")),
                    frozenset({PAGE_SIZE}),
                ),
            ),
        )

    def scope(self) -> str:
        values: dict[str, Any] = {"equiCurrency": "USD"}
        if self.group_codes:
            values["userGroupCode"] = list(self.group_codes)
        return canonical(values)

    def page_body(self, scope: str, row_start: int) -> dict[str, Any]:
        if (
            scope != self.scope()
            or type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "unverified cash.group_balances request"
            )
        values = json.loads(scope)
        return {
            "tntInstId": TENANT,
            "bankAccountManageUnitQueryVO": json.dumps(
                {
                    "tntInstId": TENANT,
                    **values,
                    "rowStart": row_start,
                    "pageSize": PAGE_SIZE,
                }
            ),
        }

    def identity_key(self, record: dict[str, Any]) -> str:
        value = record.get("id")
        if (
            not isinstance(value, (str, int))
            or isinstance(value, bool)
            or (isinstance(value, str) and not value.strip())
        ):
            raise CliError(
                INVALID_RESPONSE,
                "record is missing identity field id",
            )
        return canonical(value)

    def validate_scope(self, record: dict[str, Any]) -> None:
        if "equiCurrency" in record and record["equiCurrency"] != "USD":
            raise CliError(
                INVALID_RESPONSE,
                "native equivalent currency contradicts requested scope",
            )
        if "tntInstId" in record and record["tntInstId"] != TENANT:
            raise CliError(
                INVALID_RESPONSE, "native tenant contradicts requested scope"
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

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict):
            raise CliError(INVALID_RESPONSE, "response envelope is not an object")
        if type(document.get("resultFlag")) is not bool:
            raise CliError(INVALID_RESPONSE, "resultFlag is not boolean")
        if document["resultFlag"] is not True:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        result = document.get("result")
        if not isinstance(result, dict):
            raise CliError(INVALID_RESPONSE, "response result is not an object")
        if result.get("success") is False:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        if type(result.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "inner success is not boolean")
        rows, total = result.get("data"), result.get("count")
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
        if type(document.get("count")) is not int or document["count"] != total:
            raise CliError(INVALID_RESPONSE, "reported totals disagree")
        for row in rows:
            self.validate_scope(row)
            if self.group_codes and row.get("userGroupCode") not in self.group_codes:
                raise CliError(
                    INVALID_RESPONSE, "native group contradicts requested selection"
                )
            self.identity_key(row)
            self.validate_members(row, "memberList", "bankAccountGroupId")
        return rows, total


def inquiry(parameters: dict[str, Any]) -> Inquiry:
    if parameters.get("equi_currency", "USD") != "USD":
        raise CliError(INVALID_ARGUMENT, "only USD equivalent currency is verified")
    codes = parameters.get("group_code") or []
    if not isinstance(codes, list) or any(
        not isinstance(code, str) or not code.strip() for code in codes
    ):
        raise CliError(INVALID_ARGUMENT, "group codes must be nonempty strings")
    return Inquiry(group_codes=tuple(sorted(set(codes))))


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return inquiry(parameters)

    def scope(self, parameters: dict[str, Any]) -> str:
        return inquiry(parameters).scope()

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
                        TIMEOUT,
                        "cash.group_balances page budget exceeded",
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
        codes = inquiry(parameters).group_codes
        return [
            row for row in records if not codes or row.get("userGroupCode") in codes
        ]


adapter = Adapter()
