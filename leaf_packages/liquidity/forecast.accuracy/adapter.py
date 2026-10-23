"""One account/day of native forecast records and request-bound accuracy."""

import re
from datetime import datetime
from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.query import CustomListResult
from dogopencli.result_policy import AcquisitionEvidence

TENANT = "GUAPW3SG"
BASE_VO = "bankCashForecastRecordQueryVo"
METRIC_VO = "bankAccountDetailCashFlowQueryVO"
BASE_FIELDS = (
    "id",
    "bankAccountAliasName",
    "currency",
    "valueDate",
    "baseValueDate",
    "recordCreateTime",
    "forecastBalance",
    "cashFlowTransIn",
    "cashFlowTransOut",
    "forecastTaskId",
    "forecastBatchNo",
    "forecastRuleId",
)
METRIC_FIELDS = (
    "cashFlowAccuracy",
    "cashFlowInflow",
    "cashFlowOutflow",
    "flowAccuracy",
    "inflowAccuracy",
    "outflowAccuracy",
    "realTrafficAmount",
    "realizedBalance",
    "realizedInflow",
    "realizedOutflow",
    "trafficForecastAmount",
)
BINDINGS = ("valueDate", "accountNo", "instId", "currency", "bankId")


def fail(message: str, code: str = "INVALID_RESPONSE") -> None:
    raise CliError(
        code,
        "forecast accuracy: " + message,
        exit_code=2 if code == "INVALID_ARGUMENT" else 1,
    )


def values(parameters: dict, *, required: bool = True) -> dict:
    result = {}
    for key in ("account_alias", "record_date"):
        value = parameters.get(key)
        if value is None and not required:
            continue
        if not isinstance(value, str) or not value.strip():
            fail("one account alias and record date are required", "INVALID_ARGUMENT")
        result[key] = value
    if "record_date" in result:
        day = result["record_date"]
        try:
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day) is None:
                raise ValueError
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError as error:
            raise CliError(
                "INVALID_ARGUMENT", "record-date must be YYYY-MM-DD", exit_code=2
            ) from error
    return result


def metric_context(row: dict, alias: str) -> dict:
    if row.get("bankAccountAliasName") != alias:
        fail("base account does not match the requested alias")
    for field in ("id", *BINDINGS):
        if not isinstance(row.get(field), str) or not row[field].strip():
            fail("missing native metric binding: " + field)
    balance = row.get("forecastBalance")
    if balance is None or isinstance(balance, (dict, list, bool)):
        fail("missing native forecastBalance binding")
    return {
        **{field: row[field] for field in BINDINGS},
        "forecastRecordId": row["id"],
        "aliasName": alias,
        "forecastBalance": "0" if balance in ("0.0", "0.00") else balance,
    }


def project(row: dict, metric: dict) -> dict:
    for source, fields in ((row, BASE_FIELDS), (metric, METRIC_FIELDS)):
        if any(isinstance(source.get(field), (dict, list)) for field in fields):
            fail("projected field must be a native scalar or null")
    return {
        **{field: row.get(field) for field in BASE_FIELDS},
        "accuracy": {field: metric.get(field) for field in METRIC_FIELDS},
    }


def occurrence_context(row: dict, alias: str) -> dict:
    context = metric_context(row, alias)
    context.pop("forecastBalance")
    if row.get("tntInstId") != TENANT:
        fail("missing or contradictory native occurrence tenant")
    context["tntInstId"] = row["tntInstId"]
    if "gmtCreate" in row:
        if row["gmtCreate"] is not None and type(row["gmtCreate"]) is not int:
            fail("unverified native gmtCreate binding")
        context["gmtCreate"] = row["gmtCreate"]
    return context


def validate_context(source: dict, context: dict, *, occurrence: bool = False) -> None:
    # Occurrence timestamps describe the occurrence, not the parent acquisition.
    fields = {*BINDINGS, "forecastRecordId", "aliasName", "tntInstId"}
    if not occurrence:
        fields |= {"forecastBalance", "gmtCreate"}
    for field in fields & source.keys() & context.keys():
        if source[field] != context[field]:
            fail("native response contradicts request binding: " + field)


class Inquiry:
    page_url = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"

    def __init__(self, name: str):
        self.metric = name == "metric"
        self.occurrences = name in {"occurrences", "occurrences_without_create"}
        self.name = "liquidity.forecast.accuracy." + name
        self.vo = METRIC_VO if self.metric or self.occurrences else BASE_VO
        fields = (
            {*BINDINGS, "forecastRecordId", "aliasName", "forecastBalance"}
            if self.metric
            else {*BINDINGS, "forecastRecordId", "aliasName", "tntInstId", "gmtCreate"}
            if self.occurrences
            else {
                "tntInstId",
                "recordStartTime",
                "recordEndTime",
                "rowStart",
                "pageSize",
                "aliasName",
                "valueStartDay",
                "valueEndDay",
            }
        )
        if name == "occurrences_without_create":
            fields.remove("gmtCreate")
        self.contract = EndpointContract(
            method="GET",
            host="iliquidity.alipay.com",
            path="/cashFlowDetailDay.json"
            if self.metric
            else "/cashFlowDetail.json"
            if self.occurrences
            else "/bankCashForecastRecordAccuracyQuery.json",
            page_size=0,
            one_based=False,
            allowed_body_keys=frozenset({"tntInstId", self.vo}),
            fixed_body_values=(("tntInstId", TENANT),),
            encoding="query",
            json_body_contracts=(
                (
                    self.vo,
                    frozenset(fields),
                    ()
                    if self.metric
                    else (("tntInstId", TENANT),)
                    if self.occurrences
                    else (
                        ("tntInstId", TENANT),
                        ("recordStartTime", "000000"),
                        ("recordEndTime", "235959"),
                        ("rowStart", 0),
                        ("pageSize", 5000),
                    ),
                    frozenset()
                    if self.metric or self.occurrences
                    else frozenset({5000}),
                ),
            ),
        )

    def request_body(self, parameters: dict) -> dict:
        if self.metric or self.occurrences:
            fields = {*BINDINGS, "forecastRecordId", "aliasName"}
            fields |= {"forecastBalance"} if self.metric else {"tntInstId"}
            required = set(parameters) - ({"gmtCreate"} if self.occurrences else set())
            if required != fields:
                fail("invalid dependent request context", "REQUEST_NOT_ALLOWED")
            inner = dict(parameters)
        else:
            scope = values(parameters)
            day = scope["record_date"].replace("-", "")
            inner = {
                "tntInstId": TENANT,
                "recordStartTime": "000000",
                "recordEndTime": "235959",
                "rowStart": 0,
                "pageSize": 5000,
                "aliasName": [scope["account_alias"]],
                "valueStartDay": day,
                "valueEndDay": day,
            }
        return {"tntInstId": TENANT, self.vo: canonical(inner)}

    def parse_inquiry(self, body: bytes, parameters: dict) -> dict:
        document = parse(body)
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            fail("invalid outer success marker")
        if not document["resultFlag"]:
            fail("native inquiry failed", "BUSINESS_QUERY_FAILED")
        result = document.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            fail("invalid inner success marker")
        if not result["success"]:
            fail("native inquiry failed", "BUSINESS_QUERY_FAILED")
        binding = {**parameters, "tntInstId": TENANT}
        if self.metric or self.occurrences:
            validate_context(document, binding)
            validate_context(result, binding)
        if self.metric:
            metric = result.get("bankAccountDetailDayVO")
            if not isinstance(metric, dict):
                fail("metric response must be an object")
            validate_context(metric, binding)
            return result
        rows, total = result.get("dataValue"), result.get("count")
        if (
            not isinstance(rows, list)
            or any(not isinstance(row, dict) for row in rows)
            or (not self.occurrences and (type(total) is not int or total < 0))
        ):
            fail("invalid base records/count")
        if self.occurrences:
            for row in rows:
                validate_context(row, binding, occurrence=True)
                for field, native_type in (
                    ("cashFlowAmount", dict),
                    ("detailAmount", str),
                    ("match", bool),
                ):
                    if (
                        row.get(field) is not None
                        and type(row[field]) is not native_type
                    ):
                        fail("unverified occurrence field type: " + field)
        return result


class Adapter:
    def query_capability(self, operation: str, name: str, parameters: dict) -> Inquiry:
        values(parameters)
        if operation != "list" or name not in {
            "base",
            "metric",
            "occurrences",
            "occurrences_without_create",
        }:
            fail("undeclared inquiry", "REQUEST_NOT_ALLOWED")
        return Inquiry(name)

    def scope(self, parameters: dict) -> str:
        return canonical(values(parameters))

    def query_list(self, parameters: dict, tools: Any) -> CustomListResult:
        scope = values(parameters)
        base = tools.inquire("base")
        rows, total = base["dataValue"], base["count"]
        identities = []
        for row in rows:
            if {"accuracy", "cashflow_details"} & row.keys():
                fail("reserved composition namespace already exists in native base")
            identity = row.get("id")
            if not isinstance(identity, str) or not identity.strip():
                fail("base id must be a nonempty native string")
            if "tntInstId" in row and row["tntInstId"] != TENANT:
                fail("base tenant differs from the requested tenant")
            identities.append(identity)
        if len(rows) != len(set(identities)) or len(rows) != total or len(rows) > 100:
            fail(
                "base coverage or 100-record client budget is unproven",
                "INCOMPLETE_RESULT",
            )
        contexts = [metric_context(row, scope["account_alias"]) for row in rows]
        occurrence_contexts = [
            occurrence_context(row, scope["account_alias"]) for row in rows
        ]
        records = []
        responses = []
        metric_requests = []
        occurrence_requests = []

        def inquire(name: str, context: dict, requests: list, stage: str) -> dict:
            binding = {"tntInstId": TENANT, METRIC_VO: dict(context)}
            attempt = {"request_binding": binding, "status": "attempted"}
            requests.append(attempt)
            try:
                result = tools.inquire(name, context)
            except CliError as error:
                attempt["status"] = "failed"
                attempt["error_code"] = error.code
                error.meta = {
                    **(error.meta or {}),
                    stage + "_binding": binding,
                    "accuracy_composition": {
                        "base_arrivals": len(rows),
                        "base_reported_total": total,
                        "metric_requests": metric_requests,
                        "occurrence_requests": occurrence_requests,
                        "occurrence_responses": responses,
                    },
                }
                raise
            attempt["status"] = "succeeded"
            return result

        for row, context, detail_context in zip(
            rows, contexts, occurrence_contexts, strict=True
        ):
            metric = inquire("metric", context, metric_requests, "metric")[
                "bankAccountDetailDayVO"
            ]
            detail_name = (
                "occurrences"
                if "gmtCreate" in detail_context
                else "occurrences_without_create"
            )
            detail = inquire(
                detail_name, detail_context, occurrence_requests, "occurrence"
            )
            records.append(
                {**project(row, metric), "cashflow_details": detail["dataValue"]}
            )
            responses.append(
                {
                    "request_binding": detail_context,
                    "native_count": detail.get("count"),
                    "native_count_present": "count" in detail,
                    "reported_total": None,
                    "arrivals": len(detail["dataValue"]),
                    "total_semantics": "source_row_occurrences",
                    "coverage_complete": False,
                }
            )
        evidence = AcquisitionEvidence.for_collection(
            complete=not rows,
            reported_total=total,
            collected_total=len(records),
            arrivals=len(rows),
            reasons=("OCCURRENCE_COVERAGE_UNPROVEN",) if rows else (),
            attempts=(
                {
                    "composition": "native-request-binding",
                    "base_arrivals": len(rows),
                    "base_unique": len(identities),
                    "base_reported_total": total,
                    "metric_succeeded": len(records),
                    "metric_required": len(rows),
                    "metric_attempted": len(records),
                    "metric_requests": metric_requests,
                    "occurrence_required": len(rows),
                    "occurrence_attempted": len(responses),
                    "occurrence_succeeded": len(responses),
                    "occurrence_arrivals": sum(item["arrivals"] for item in responses),
                    "occurrence_reported_total": None,
                    "occurrence_responses": responses,
                    "occurrence_requests": occurrence_requests,
                    "client_base_limit": 100,
                    "backend_metric_echo": "not-required",
                },
            ),
        )
        return CustomListResult(records, evidence)

    def filter(self, records: list[dict], parameters: dict) -> list[dict]:
        scope = values(parameters, required=False)
        return [
            row
            for row in records
            if "account_alias" not in scope
            or row.get("bankAccountAliasName") == scope["account_alias"]
        ]


adapter = Adapter()
