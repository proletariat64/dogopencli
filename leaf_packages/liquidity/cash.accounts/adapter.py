"""Three-source cash directory using bounded host inquiries and native records."""

import json
import re
from dataclasses import dataclass
from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.query import CustomListResult, QueryRefused
from dogopencli.result_policy import AcquisitionEvidence

TENANT = "GUAPW3SG"
PAGE_SIZE = 1000
IDENTITY = ("aliasName", "currency")
CONTEXT = ("bankId", "instId")
SOURCE_NAMES = ("cash", "baseline", "detail")
BASELINE_FIELDS = frozenset({"accountType", "status"})
CASH_FIELDS = frozenset({"gmtModified", "operator"})


def invalid(message: str) -> None:
    raise CliError(INVALID_RESPONSE, message)


def envelope(body: bytes, *, detail: bool = False) -> dict[str, Any]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict) or type(document.get("resultFlag")) is not bool:
        invalid("invalid business success marker")
    if not document["resultFlag"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    result = document.get("result")
    if not isinstance(result, dict):
        invalid("result is not an object")
    if "success" in result and type(result["success"]) is not bool:
        invalid("inner success is not boolean")
    if result.get("success") is False:
        if detail:
            code = document.get("errorCode", result.get("errorCode"))
            safe_code = (
                code
                if type(code) in (str, int)
                and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", str(code))
                else None
            )
            raise QueryRefused(native_code=safe_code)
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return document


def validate_account(row: Any) -> None:
    if not isinstance(row, dict):
        invalid("account record is not an object")
    for field in IDENTITY:
        if not isinstance(row.get(field), str) or not row[field].strip():
            invalid(f"account source requires nonempty {field}")
    for field in CONTEXT:
        if row.get(field) is not None and not isinstance(row[field], str):
            invalid(f"account source has invalid {field}")
    if "tntInstId" in row and row["tntInstId"] != TENANT:
        invalid("record tenant contradicts query scope")


@dataclass(frozen=True)
class ListInquiry:
    source: str
    contract: EndpointContract
    vo_field: str
    container: str
    page_url: str = LIQUIDITY_STARTUP_URL

    @property
    def name(self) -> str:
        return f"liquidity.cash.accounts.{self.source}"

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        widths = self.contract.allowed_page_sizes or (PAGE_SIZE,)
        if (
            scope
            or type(row_start) is not int
            or row_start < 0
            or type(page_size) is not int
            or page_size not in widths
            or (self.source == "baseline" and row_start % PAGE_SIZE)
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified account list request")
        body = {
            "tntInstId": TENANT,
            self.vo_field: json.dumps(
                {"tntInstId": TENANT, "rowStart": row_start, "pageSize": page_size}
            ),
        }
        if self.source == "cash":
            body["wallet"] = False
        return body

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int | None]:
        document = envelope(body)
        rows = document["result"].get(self.container)
        if not isinstance(rows, list):
            invalid("account record container is not an array")
        for row in rows:
            validate_account(row)
        # Cash uses qualified short-page termination; its native count is not
        # a completeness claim. Baseline retains its independent fixed total.
        total = None if self.source == "cash" else document.get("count")
        if self.source == "baseline" and (type(total) is not int or total < 0):
            invalid("baseline count is not a nonnegative integer")
        return rows, total


def list_inquiry(source: str) -> ListInquiry:
    cash = source == "cash"
    vo = "bankAccountQueryVO" if cash else "bankAccountBaseLineQuery"
    widths = (1000, 100, 10, 1) if cash else (1000,)
    return ListInquiry(
        source=source,
        vo_field=vo,
        container="bankAccountPropertyVOList" if cash else "data",
        contract=EndpointContract(
            method="GET",
            host="iliquidity.alipay.com",
            path="/queryintnalbkactlist.json"
            if cash
            else "/bankAccountBaseLineQuery.json",
            page_size=PAGE_SIZE,
            one_based=False,
            allowed_body_keys=frozenset(
                {"tntInstId", vo, *(("wallet",) if cash else ())}
            ),
            fixed_body_values=(
                ("tntInstId", TENANT),
                *((("wallet", False),) if cash else ()),
            ),
            allowed_page_sizes=widths,
            json_body_contracts=(
                (
                    vo,
                    frozenset({"tntInstId", "rowStart", "pageSize"}),
                    (("tntInstId", TENANT),),
                    frozenset(widths),
                ),
            ),
        ),
    )


class DetailInquiry:
    name = "liquidity.cash.accounts.detail"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/bankAccountBaseLineDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "aliasName"}),
        fixed_body_values=(("tntInstId", TENANT),),
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if parameters or not isinstance(identity, str) or not identity.strip():
            raise CliError(REQUEST_NOT_ALLOWED, "unverified baseline detail request")
        return {"tntInstId": TENANT, "aliasName": identity}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        self.request_body(parameters, identity)
        record = envelope(body, detail=True)["result"].get("data")
        if not isinstance(record, dict) or record.get("aliasName") != identity:
            invalid("detail account differs from lookup")
        if "tntInstId" in record and record["tntInstId"] != TENANT:
            invalid("detail tenant contradicts query scope")
        return record


QUERIES = {
    "cash": list_inquiry("cash"),
    "baseline": list_inquiry("baseline"),
    "detail": DetailInquiry(),
}


def index_accounts(
    records: list[dict[str, Any]], *, baseline: bool = False
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed, aliases = {}, set()
    for record in records:
        validate_account(record)
        identity = tuple(record[field] for field in IDENTITY)
        if identity in indexed or (baseline and identity[0] in aliases):
            invalid("account source has ambiguous native identities")
        indexed[identity] = record
        aliases.add(identity[0])
    return indexed


def agree(left: dict[str, Any], right: dict[str, Any]) -> None:
    for field in (*IDENTITY, *CONTEXT):
        if field not in right:
            continue
        if field in CONTEXT:
            if right[field] is not None and not isinstance(right[field], str):
                invalid(f"account source has invalid {field}")
            if left.get(field) in (None, "") or right[field] in (None, ""):
                continue
        if left.get(field) != right[field]:
            invalid(f"account sources disagree on identity field {field}")


def assemble_row(
    sources: dict[str, dict[str, Any]], refusal: dict[str, Any] | None
) -> dict[str, Any]:
    fields = dict.fromkeys(field for record in sources.values() for field in record)
    row, owners, conflicts = {}, {}, {}
    for field in fields:
        if field in {"source_metadata", "detail_state"}:
            continue
        values = {
            name: record[field] for name, record in sources.items() if field in record
        }
        if field in BASELINE_FIELDS | CASH_FIELDS:
            if len({canonical(value) for value in values.values()}) > 1:
                conflicts[field] = values
        else:
            # Retain the native conflicting arrivals against the owner at that
            # point; baseline takes ownership before comparing detail.
            previous = None
            for name in SOURCE_NAMES:
                if name not in values:
                    continue
                if previous is not None and canonical(values[previous]) != canonical(
                    values[name]
                ):
                    conflicts.setdefault(field, {}).update(
                        {previous: values[previous], name: values[name]}
                    )
                if previous is None or name == "baseline":
                    previous = name
        permitted = (
            ("baseline",)
            if field in BASELINE_FIELDS
            else ("cash",)
            if field in CASH_FIELDS
            else ("baseline", "cash", "detail")
        )
        owner = next((name for name in permitted if name in values), None)
        if owner is not None:
            row[field], owners[field] = values[owner], owner
    row["detail_state"] = (
        "succeeded" if "detail" in sources else "refused" if refusal else "missing"
    )
    row["source_metadata"] = {
        "schema_version": 2,
        "presence": {name: name in sources for name in SOURCE_NAMES},
        "matched": "cash" in sources and "baseline" in sources,
        "provenance": owners,
        "raw": sources,
        "conflicts": conflicts,
        "detail_error": refusal,
    }
    return row


class Adapter:
    def query_capability(
        self, operation: str, name: str, parameters: dict[str, Any]
    ) -> Any:
        if operation != "list" or name not in QUERIES:
            raise CliError(REQUEST_NOT_ALLOWED, "undeclared account inquiry")
        return QUERIES[name]

    def scope(self, parameters: dict[str, Any]) -> str:
        return ""

    def query_list(self, parameters: dict[str, Any], query: Any) -> CustomListResult:
        cash = query.collect("cash", "")
        baseline = query.collect("baseline", "")
        if baseline.evidence.duplicate_count:
            invalid("baseline source has ambiguous account aliases")
        indexes = {
            "cash": index_accounts(cash.records),
            "baseline": index_accounts(baseline.records, baseline=True),
        }
        matched = indexes["cash"].keys() & indexes["baseline"].keys()
        for identity in matched:
            agree(indexes["cash"][identity], indexes["baseline"][identity])
        details, refusals = {}, {}
        for identity, account in indexes["baseline"].items():
            try:
                detail = query.detail("detail", account["aliasName"], parameters={})
            except QueryRefused as error:
                refusal = {
                    "code": BUSINESS_QUERY_FAILED,
                    "message": "backend refused account detail",
                }
                if error.meta.get("native_code") is not None:
                    refusal["native_code"] = error.meta["native_code"]
                refusals[identity] = refusal
                continue
            agree(account, detail)
            if identity in indexes["cash"]:
                agree(indexes["cash"][identity], detail)
            details[identity] = detail
        identities = list(indexes["cash"]) + [
            key for key in indexes["baseline"] if key not in indexes["cash"]
        ]
        records = []
        for identity in identities:
            sources = {
                name: index[identity]
                for name, index in (*indexes.items(), ("detail", details))
                if identity in index
            }
            records.append(assemble_row(sources, refusals.get(identity)))
        lists_complete = (
            cash.complete
            and baseline.complete
            and len(matched) == len(indexes["cash"]) == len(indexes["baseline"])
        )
        detail_complete = len(details) == len(indexes["baseline"])
        reasons = [*cash.evidence.reasons, *baseline.evidence.reasons]
        if len(matched) != len(indexes["cash"]) or len(matched) != len(
            indexes["baseline"]
        ):
            reasons.append("ACCOUNT_SOURCE_MISMATCH")
        if not detail_complete:
            reasons.append("DETAIL_COVERAGE_INCOMPLETE")
        attempt = {
            "kind": "unified_cash_accounts",
            "schema_version": 2,
            "sources": {
                "cash": cash.evidence.record(),
                "baseline": baseline.evidence.record(),
            },
            "list_coverage": {
                "complete": lists_complete,
                "matched": len(matched),
                "cash_only": len(indexes["cash"]) - len(matched),
                "baseline_only": len(indexes["baseline"]) - len(matched),
            },
            "detail_coverage": {
                "complete": detail_complete,
                "required": len(indexes["baseline"]),
                "attempted": len(indexes["baseline"]),
                "succeeded": len(details),
                "refused": len(refusals),
                "failed": 0,
            },
            "field_inventory": {
                name: sorted(
                    {
                        field
                        for row in records
                        for field in row["source_metadata"]["raw"].get(name, {})
                    }
                )
                for name in SOURCE_NAMES
            },
        }
        evidence = AcquisitionEvidence.for_collection(
            complete=lists_complete and detail_complete,
            reported_total=None,
            collected_total=len(records),
            arrivals=len(records),
            reasons=tuple(dict.fromkeys(reasons)),
            attempts=(attempt,),
        )
        return CustomListResult(records=records, evidence=evidence)

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        selected = records
        for option, field in (
            ("currency", "currency"),
            ("bank", "bankId"),
            ("status", "status"),
            ("account_no", "accountNo"),
            ("account_alias", "aliasName"),
        ):
            values = parameters.get(option) or []
            if isinstance(values, str):
                values = [values]
            if values:
                selected = [row for row in selected if row.get(field) in values]
        return selected


adapter = Adapter()
