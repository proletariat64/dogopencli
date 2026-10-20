"""Explicit account capacity snapshots through named native detail inquiries."""

from dataclasses import replace
from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.query import CustomListResult
from dogopencli.result_policy import AcquisitionEvidence

FIELDS = (
    "aliasName",
    "currency",
    "accountAvailableBalance",
    "availableIod",
    "availableResource",
    "cashPoolSupportAvailableResource",
    "outFlowCapacity",
    "totalIod",
    "usedIod",
    "valueTime",
)


def aliases(parameters: dict[str, Any]) -> list[str]:
    values = parameters.get("account_alias")
    if (
        not isinstance(values, list)
        or not 1 <= len(values) <= 10
        or any(not isinstance(value, str) or not value.strip() for value in values)
        or len(set(values)) != len(values)
    ):
        raise CliError(
            INVALID_ARGUMENT,
            "--account-alias needs 1–10 distinct nonempty native aliases",
            exit_code=2,
        )
    return sorted(values)


class CapacityInquiry:
    name = "liquidity.risk.account_capacity.capacity"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/api/fund/capacity/queryFundCapacityByAliasName.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"aliasName"}),
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if parameters or not isinstance(identity, str) or not identity.strip():
            raise CliError(REQUEST_NOT_ALLOWED, "unverified account capacity request")
        return {"aliasName": identity}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        self.request_body(parameters, identity)
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                INVALID_RESPONSE, "capacity response is not valid JSON"
            ) from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "capacity success marker must be boolean")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected capacity inquiry")
        record = document.get("data")
        if not isinstance(record, dict) or record.get("aliasName") != identity:
            raise CliError(INVALID_RESPONSE, "capacity aliasName echo mismatch")
        return record


CAPACITY = CapacityInquiry()


class Adapter:
    def query_capability(
        self, operation: str, name: str, parameters: dict[str, Any]
    ) -> CapacityInquiry:
        aliases(parameters)
        if operation != "list" or name != "capacity":
            raise CliError(REQUEST_NOT_ALLOWED, "undeclared account capacity inquiry")
        return CAPACITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical({"aliasName": aliases(parameters)})

    def query_list(self, parameters: dict[str, Any], tools: Any) -> CustomListResult:
        requested = aliases(parameters)
        records = []
        for alias in requested:
            native = tools.detail("capacity", alias, parameters={})
            records.append(
                {field: native[field] for field in FIELDS if field in native}
            )
        evidence = replace(
            AcquisitionEvidence.for_collection(
                complete=True,
                reported_total=None,
                collected_total=len(records),
                arrivals=len(records),
                total_semantics="requested_accounts",
            ),
            requested_count=len(requested),
            resolved_count=len(records),
        )
        return CustomListResult(records=records, evidence=evidence)

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if not parameters.get("account_alias"):
            return records
        selected = aliases(parameters)
        return [row for row in records if row["aliasName"] in selected]


adapter = Adapter()
