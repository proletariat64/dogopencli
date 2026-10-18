"""Native investment inquiry; no business storage or authentication side effects."""

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

TENANT = "GUAPW3SG"


def business_data(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get("success")) is not bool:
        raise CliError(INVALID_RESPONSE, "response requires a boolean success flag")
    if not document["success"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    data = document.get("data")
    if not isinstance(data, dict):
        raise CliError(INVALID_RESPONSE, "response data is not an object")
    if data.get("success") is False:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return data


def native_identity(record: dict[str, Any], fields: tuple[str, ...]) -> str:
    values = [record.get(field) for field in fields]
    if any(
        type(value) not in (str, int) or (isinstance(value, str) and not value.strip())
        for value in values
    ):
        raise CliError(INVALID_RESPONSE, "record is missing a valid native identity")
    return canonical(values)


@dataclass(frozen=True)
class Inquiry:
    name: str
    contract: EndpointContract
    identity: tuple[str, ...]
    page_url: str = LIQUIDITY_STARTUP_URL

    def page_body(self, scope: str, row_start: int) -> dict[str, Any]:
        values = parse(scope)
        if (
            type(row_start) is not int
            or row_start < 0
            or row_start % self.contract.page_size
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified investment offset")
        return {**values, "rowStart": row_start, "pageSize": self.contract.page_size}

    def identity_key(self, record: dict[str, Any]) -> str:
        return native_identity(record, self.identity)

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        result = business_data(body)
        rows, total = result.get("data"), result.get("totalCount")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CliError(INVALID_RESPONSE, "records are not an object array")
        if type(total) is not int or total < 0:
            raise CliError(INVALID_RESPONSE, "total is not a nonnegative integer")
        for row in rows:
            self.identity_key(row)
        return rows, total


def inquiry(
    values: dict[str, Any], path: str, size: int, identity: tuple[str, ...]
) -> Inquiry:
    return Inquiry(
        name=NAME + ".list",
        contract=EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path=path,
            page_size=size,
            one_based=False,
            allowed_body_keys=frozenset((*values, "rowStart", "pageSize")),
            fixed_body_values=tuple(values.items()) + (("pageSize", size),),
        ),
        identity=identity,
    )


NAME = "liquidity.investment.transactions"


class Adapter:
    def scope(self, parameters: dict[str, Any]) -> str:
        values = {"tntInstId": TENANT}
        return canonical(values)

    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        values = parse(self.scope(parameters))
        return inquiry(values, "/queryIncrementOrderList.json", 5000, ("orderId",))

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
                capability.page_body(scope, page_no * capability.contract.page_size),
                deadline,
            )
            rows, page_total = capability.parse_rows(response.body)
            if total is None:
                total = page_total
                if total > collect.MAX_PAGES * capability.contract.page_size:
                    raise CliError(
                        TIMEOUT, "investment page budget exceeded", retryable=True
                    )
            elif page_total != total:
                raise CliError(
                    INVALID_RESPONSE, "backend total changed during collection"
                )
            if len(rows) > capability.contract.page_size:
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
                            INVALID_RESPONSE,
                            "conflicting content for native identity",
                        )
                    continue
                seen[identity] = content
                ordered.append(row)
            if progress:
                progress(pages, max(-(-total // capability.contract.page_size), pages))
            if pages * capability.contract.page_size >= total:
                break
        else:
            raise CliError(TIMEOUT, "investment page budget exceeded", retryable=True)
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
            capability.contract.page_size,
            pages,
            False,
            deadline,
            evidence,
        )

    def get(
        self, session: Any, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        if not identity.strip():
            raise CliError(
                INVALID_ARGUMENT, "detail identity must be nonempty", exit_code=2
            )
        response = collect.execute_bounded(
            DETAIL, session.transport(DETAIL), {"orderId": identity}
        )
        record = business_data(response.body)
        native_identity(record, ("orderId",))
        if str(record["orderId"]) != identity:
            raise CliError(INVALID_RESPONSE, "detail identity does not match request")
        return record

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        selected = records
        for parameter, field in (
            ("currency", "currency"),
            ("product_code", "productCode"),
        ):
            values = parameters.get(parameter)
            if values:
                selected = [row for row in selected if row.get(field) in values]
        return selected


DETAIL = Inquiry(
    name=NAME + ".get",
    contract=EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/queryIncrementOrderDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"orderId"}),
        encoding="form",
    ),
    identity=("orderId",),
)


adapter = Adapter()
