"""Four native rate sources; bank pagination counts quote-date groups."""

import re
from datetime import datetime
from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.query import CustomListResult
from dogopencli.result_policy import AcquisitionEvidence

TENANT = "GUAPW3SG"
SOURCES = ("market", "bank", "expectation-rule", "expection")
PATHS = {
    "market": "/incrementBaseRateList.json",
    "bank": "/queryEnquireRateList.json",
    "expectation-rule": "/queryMarketRateRuleList.json",
    "expection": "/queryFinancialMarketRateRuleList.json",
}
KEYS = {
    "market": ("currency", "rateName", "ratePeriod", "effectiveDate"),
    "bank": ("bankId", "currency", "productTerm", "productType", "quoteDate"),
    "expectation-rule": ("ruleId",),
    "expection": ("ruleId",),
}


def fail(message: str, code: str = "INVALID_RESPONSE") -> None:
    raise CliError(
        code,
        "interest rates: " + message,
        exit_code=2 if code == "INVALID_ARGUMENT" else 1,
    )


def date(value: Any) -> str:
    try:
        if (
            not isinstance(value, str)
            or re.fullmatch(r"[0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None
        ):
            raise ValueError
        return datetime.strptime(value.replace("-", ""), "%Y%m%d").strftime("%Y%m%d")
    except ValueError as error:
        raise CliError(
            "INVALID_ARGUMENT", "rate dates must be YYYYMMDD or YYYY-MM-DD", exit_code=2
        ) from error


def scope_values(parameters: dict, *, required: bool = True) -> dict:
    source = parameters.get("source")
    if source is None and not required:
        return {}
    if source not in SOURCES:
        fail("an explicit native source is required", "INVALID_ARGUMENT")
    scope = {"source": source}
    if source in {"market", "bank"}:
        scope.update(
            beginDate=date(parameters.get("from_date")),
            endDate=date(parameters.get("to_date")),
        )
        if scope["beginDate"] > scope["endDate"]:
            fail("date bounds must be ordered", "INVALID_ARGUMENT")
        zone = parameters.get("timezone") or "GMT+08"
        if zone != "GMT+08":
            fail("only qualified timezone GMT+08 is supported", "INVALID_ARGUMENT")
        scope["timeZone"] = zone
    elif any(
        parameters.get(k) is not None for k in ("from_date", "to_date", "timezone")
    ):
        fail(
            "date/timezone parameters are unavailable for rule sources",
            "INVALID_ARGUMENT",
        )
    return scope


def template(scope: dict) -> dict:
    source = scope["source"]
    if source == "market":
        return {
            "currentArea": "2",
            "tntInstId": TENANT,
            "currency": [],
            "productTerm": [],
            "isPage": "Y",
            **{k: scope[k] for k in ("beginDate", "endDate", "timeZone")},
        }
    if source == "bank":
        return {
            "currentArea": "3",
            "tntInstId": TENANT,
            "timeZone": scope["timeZone"],
            **{
                k: datetime.strptime(scope[k], "%Y%m%d").strftime("%Y-%m-%d")
                for k in ("beginDate", "endDate")
            },
        }
    if source == "expectation-rule":
        return {
            "currentArea": "1",
            "timeZone": "GMT+08",
            "tntInstId": TENANT,
            "rateCategory": "CUSTOMER_TYPE",
            "beginDate": "",
            "endDate": "",
        }
    return {
        "rateCategory": "FINANCIAL_INST_TYPE",
        "rateProvide": "",
        "productTerm": "",
        "isPage": "Y",
        "customizedMarketRateName": "",
        "expectedRateProvider": "",
        "currency": "",
        "rateType": "",
        "ruleStatus": "",
    }


def root(body: bytes) -> Any:
    document = parse(body)
    if not isinstance(document, dict) or type(document.get("success")) is not bool:
        fail("native response must have boolean success")
    if not document["success"]:
        fail("native inquiry failed", "BUSINESS_QUERY_FAILED")
    return document.get("data")


def validate_rows(rows: Any, source: str, scope: dict) -> None:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        fail("native rows must be objects")
    for row in rows:
        if any(
            not isinstance(row.get(k), str) or not row[k].strip() for k in KEYS[source]
        ):
            fail("native rate identity is missing")
        if row.get("tntInstId") not in (None, "", TENANT):
            fail("rate tenant differs from scope")
        if source in {"expectation-rule", "expection"}:
            category = (
                "CUSTOMER_TYPE"
                if source == "expectation-rule"
                else "FINANCIAL_INST_TYPE"
            )
            if row.get("rateCategory") != category:
                fail("rate category differs from selected source")
        else:
            native = row["quoteDate" if source == "bank" else "effectiveDate"]
            try:
                day = date(native)
            except CliError as error:
                raise CliError(
                    "INVALID_RESPONSE", "invalid native rate date"
                ) from error
            if not scope["beginDate"] <= day <= scope["endDate"]:
                fail("native rate date is outside requested scope")


class Inquiry:
    page_url = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"

    def __init__(self, source: str, scope: dict):
        self.source, self.scope = source, scope
        self.name = "liquidity.investment.interest_rates." + source
        self.enabled = source == scope["source"]
        fixed = template(scope) if self.enabled else {}
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path=PATHS[source],
            page_size=1000,
            one_based=False,
            allowed_page_sizes=(1000,),
            allowed_body_keys=frozenset({*fixed, "rowStart", "pageSize"}),
            fixed_body_values=tuple(fixed.items()),
        )

    def page_body(self, scope: str, position: int, page_size: int) -> dict:
        if (
            not self.enabled
            or parse(scope) != self.scope
            or type(position) is not int
            or position < 0
            or position % 1000
            or page_size != 1000
        ):
            fail("unregistered rate paging or scope", "REQUEST_NOT_ALLOWED")
        return {**template(self.scope), "rowStart": position, "pageSize": 1000}

    def parse_rows(self, body: bytes) -> tuple[list[dict], int]:
        result = root(body)
        if (
            not isinstance(result, dict)
            or type(result.get("totalCount")) is not int
            or result["totalCount"] < 0
        ):
            fail("native rate count is invalid")
        rows = result.get("data")
        validate_rows(rows, self.source, self.scope)
        return rows, result["totalCount"]

    def request_body(self, parameters: dict) -> dict:
        if set(parameters) != {"row_start"}:
            fail("invalid bank date-group context", "REQUEST_NOT_ALLOWED")
        return self.page_body(canonical(self.scope), parameters["row_start"], 1000)

    def parse_inquiry(self, body: bytes, parameters: dict) -> dict:
        rows, total = self.parse_rows(body)
        return {"rows": rows, "groups": total}


class Detail:
    name = "liquidity.investment.interest_rates.get"
    page_url = Inquiry.page_url
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/queryFinancialInstRateRuleDetail.json",
        page_size=0,
        one_based=False,
        encoding="post-query",
        allowed_body_keys=frozenset({"id", "_output_charset"}),
        fixed_body_values=(("_output_charset", "utf-8"),),
    )

    def request_body(self, parameters: dict, identity: str) -> dict:
        if (
            parameters.get("source") != "expection"
            or not isinstance(identity, str)
            or not identity.strip()
        ):
            fail(
                "Get requires source expection and one native ruleId",
                "INVALID_ARGUMENT",
            )
        return {"id": identity, "_output_charset": "utf-8"}

    def parse_detail(self, body: bytes, parameters: dict, identity: str) -> dict:
        result = root(body)
        if not isinstance(result, dict) or result.get("ruleId") != identity:
            fail("external rule identity differs from lookup")
        validate_rows([result], "expection", {"source": "expection"})
        return result


class Adapter:
    def query_capability(self, operation: str, name: str, parameters: dict) -> Inquiry:
        scope = scope_values(parameters)
        source = name.replace("_", "-")
        if operation != "list" or source not in SOURCES:
            fail("undeclared source", "REQUEST_NOT_ALLOWED")
        return Inquiry(source, scope)

    def detail_capability(self, parameters: dict) -> Detail:
        if parameters.get("source") != "expection":
            fail("only expection has a native Get", "INVALID_ARGUMENT")
        return Detail()

    def scope(self, parameters: dict) -> str:
        return canonical(scope_values(parameters))

    def query_list(self, parameters: dict, tools: Any) -> CustomListResult:
        scope = scope_values(parameters)
        source = scope["source"]
        if source != "bank":
            collected = tools.collect(source.replace("-", "_"), canonical(scope))
            return CustomListResult(collected.records, collected.evidence)
        records, dates, identities, attempts = [], set(), set(), []
        total, position = None, 0
        while total is None or len(dates) < total:
            page = tools.inquire("bank", {"row_start": position})
            rows, count = page["rows"], page["groups"]
            if total is not None and count != total:
                fail("native quote-date total changed")
            total = count
            batch_dates = {row["quoteDate"] for row in rows}
            if len(dates) + len(batch_dates) > total:
                fail("quote-date groups exceed reported total")
            if len(batch_dates) != min(1000, total - len(dates)) or dates & batch_dates:
                fail("quote-date group coverage is incomplete", "INCOMPLETE_RESULT")
            for row in rows:
                key = canonical([row[field] for field in KEYS["bank"]])
                if key in identities:
                    fail("duplicate native bank rate identity")
                identities.add(key)
            dates.update(batch_dates)
            records.extend(rows)
            attempts.append(
                {
                    "row_start": position,
                    "page_size": 1000,
                    "quote_date_groups": len(batch_dates),
                    "rows": len(rows),
                }
            )
            position += 1000
        evidence = AcquisitionEvidence.for_collection(
            complete=True,
            reported_total=total,
            collected_total=len(records),
            arrivals=len(records),
            total_semantics="quote_date_groups",
            attempts=(
                {"source": "bank", "group_count": len(dates), "pages": attempts},
            ),
        )
        return CustomListResult(records, evidence)

    def filter(self, records: list[dict], parameters: dict) -> list[dict]:
        source = parameters.get("source")
        currencies = parameters.get("currency") or []
        if source is not None and source not in SOURCES:
            fail("unknown source", "INVALID_ARGUMENT")
        return [
            row
            for row in records
            if (not currencies or row.get("currency") in currencies)
            and (
                source is None
                or (source == "market" and "rateName" in row)
                or (source == "bank" and "quoteDate" in row)
                or (
                    source == "expectation-rule"
                    and row.get("rateCategory") == "CUSTOMER_TYPE"
                )
                or (
                    source == "expection"
                    and row.get("rateCategory") == "FINANCIAL_INST_TYPE"
                )
            )
        ]


adapter = Adapter()
