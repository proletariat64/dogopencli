"""Realtime settings and dependent history/route inquiries, with explicit coverage."""

from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.query import CustomGetResult
from dogopencli.result_policy import AcquisitionEvidence

TENANT = "GUAPW3SG"
PAGE_SIZE = 5000
FIELDS = (
    "id",
    "routeId",
    "version",
    "scene",
    "fundAction",
    "debitAliasName",
    "debitBankId",
    "debitCurrency",
    "debitLegalEntityCode",
    "creditAliasName",
    "creditBankId",
    "creditCurrency",
    "creditLegalEntityCode",
    "clearingNetworkName",
    "clearingNetworkType",
    "networkStatus",
    "runStatus",
    "processStatus",
    "operationCalendar",
    "operationDateType",
    "operationTime",
    "operationTool",
    "singlePaymentLimit",
    "timeZone",
    "gmtCreate",
    "gmtModified",
)
HISTORY_SCOPE = ("creditAliasName", "debitAliasName", "fundAction")
HOST = "iliquidity.alipay.com"
ENTRY = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
BASE = "/api/ai/decision/network/"


def invalid(message: str) -> None:
    raise CliError(INVALID_RESPONSE, message)


def envelope(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except (ValueError, UnicodeError) as error:
        raise CliError(INVALID_RESPONSE, "network response is not JSON") from error
    if not isinstance(document, dict) or type(document.get("success")) is not bool:
        invalid("network response requires boolean success")
    if not document["success"]:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return document


def validate_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        invalid("network rows must be an array")
    seen = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not row["id"].strip()
        ):
            invalid("network requires nonblank native id")
        value = canonical(row)
        if row["id"] in seen and seen[row["id"]] != value:
            invalid("conflicting native network id before projection")
        seen[row["id"]] = value
    return rows


def project(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row[field] for field in FIELDS if field in row}


def exact(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value.strip().upper() != "ANY"
    )


class ListInquiry:
    name = "liquidity.network.realtime.list"
    page_url = ENTRY
    contract = EndpointContract(
        method="POST",
        host=HOST,
        path=BASE + "queryDecisionNetwork.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset({"rowStart", "pageSize"}),
        fixed_body_values=(("rowStart", 0), ("pageSize", PAGE_SIZE)),
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope != "all"
            or type(page_num) is not int
            or page_num != 0
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "only fixed first network page is allowed"
            )
        return {"rowStart": 0, "pageSize": PAGE_SIZE}

    def parse_page(self, body: bytes) -> ParsedPage:
        data = envelope(body).get("data")
        if isinstance(data, dict) and "success" in data:
            if type(data["success"]) is not bool:
                invalid("network source inner success must be boolean")
            if not data["success"]:
                raise CliError(
                    BUSINESS_QUERY_FAILED, "backend reported a business failure"
                )
        if (
            not isinstance(data, dict)
            or type(data.get("totalCount")) is not int
            or data["totalCount"] < 0
        ):
            invalid("network source requires native nonnegative totalCount")
        rows = validate_rows(data.get("data"))
        if len(rows) > PAGE_SIZE:
            invalid("network source exceeds fixed page size")
        total = data["totalCount"]
        return ParsedPage(
            [project(row) for row in rows], 0, PAGE_SIZE, total, -(-total // PAGE_SIZE)
        )


class RootInquiry:
    name = "liquidity.network.realtime.get"
    page_url = ENTRY
    contract = EndpointContract(
        method="POST",
        host=HOST,
        path=BASE + "detail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"id"}),
    )

    def request_body(self, parameters: dict[str, Any], identity: str) -> dict[str, Any]:
        if not exact(identity):
            raise CliError(
                INVALID_ARGUMENT, "exact network id is required", exit_code=2
            )
        return {"id": identity}

    def parse_detail(
        self, body: bytes, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        row = envelope(body).get("data")
        validate_rows([row])
        if row["id"] != identity:
            invalid("network detail identity contradicts request")
        return project(row)


class HistoryInquiry:
    name = "liquidity.network.realtime.history"
    page_url = ENTRY
    contract = EndpointContract(
        method="POST",
        host=HOST,
        path=BASE + "queryLog.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset(HISTORY_SCOPE),
    )

    def request_body(self, parameters: dict[str, Any]) -> dict[str, Any]:
        if not all(exact(parameters.get(field)) for field in HISTORY_SCOPE):
            raise CliError(
                INVALID_ARGUMENT, "history requires exact root context", exit_code=2
            )
        return {
            field: [parameters[field]] if field != "fundAction" else parameters[field]
            for field in HISTORY_SCOPE
        }

    def parse_inquiry(
        self, body: bytes, parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        self.request_body(parameters)
        rows = validate_rows(envelope(body).get("data"))
        for row in rows:
            if (
                type(row.get("version")) is not int
                or row.get("scene") != "REALTIME"
                or any(row.get(field) != parameters[field] for field in HISTORY_SCOPE)
                or row.get("tntInstId") not in (None, "", TENANT)
            ):
                invalid("network history version, scene or context is invalid")
        return [project(row) for row in rows]


class RouteInquiry:
    name = "liquidity.network.realtime.route"
    page_url = ENTRY
    contract = EndpointContract(
        method="GET",
        host=HOST,
        path="/queryWhaleRouteDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"routeId", "aliasName", "tntInstId"}),
        fixed_body_values=(("tntInstId", TENANT),),
    )

    def request_body(self, parameters: dict[str, Any]) -> dict[str, Any]:
        if not all(exact(parameters.get(field)) for field in ("routeId", "aliasName")):
            raise CliError(
                INVALID_ARGUMENT, "route requires exact root context", exit_code=2
            )
        return {
            "routeId": parameters["routeId"],
            "aliasName": parameters["aliasName"],
            "tntInstId": TENANT,
        }

    def parse_inquiry(self, body: bytes, parameters: dict[str, Any]) -> dict[str, Any]:
        expected = self.request_body(parameters)
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "quota response is not JSON") from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            invalid("quota requires boolean resultFlag")
        if not document["resultFlag"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        result = document.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            invalid("quota requires boolean inner success")
        if not result["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        data = result.get("data")
        if not isinstance(data, dict):
            invalid("quota aggregate must be an object")
        for field, value in expected.items():
            if field in data and data[field] not in (None, ""):
                if type(data[field]) is not str or data[field] != value:
                    invalid("route quota context contradicts selected network")
        for section in ("dynamicQuotas", "staticQuotas"):
            if not isinstance(data.get(section), list) or any(
                not isinstance(item, dict) for item in data[section]
            ):
                invalid("quota requires both native arrays of objects")
        return data


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> ListInquiry:
        return ListInquiry()

    def scope(self, parameters: dict[str, Any]) -> str:
        return "all"

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return sorted(records, key=lambda row: row["id"])

    def query_capability(
        self, operation: str, name: str, parameters: dict[str, Any]
    ) -> Any:
        if operation != "get" or name not in ("root", "history", "route"):
            raise CliError(REQUEST_NOT_ALLOWED, "undeclared network inquiry")
        return {"root": RootInquiry, "history": HistoryInquiry, "route": RouteInquiry}[
            name
        ]()

    def query_get(
        self, parameters: dict[str, Any], identity: str, tools: Any
    ) -> CustomGetResult:
        root = tools.detail("root", identity)
        components = {
            "network": {
                "status": "succeeded",
                "complete": True,
                "identity": {"id": root["id"]},
                "source_version": root.get("version"),
            }
        }
        history = None
        history_component = {
            "status": "unverified",
            "complete": False,
            "reasons": ["HISTORY_CONTEXT_UNVERIFIED"],
        }
        if root.get("scene") == "REALTIME" and all(
            exact(root.get(field)) for field in HISTORY_SCOPE
        ):
            context = {field: root[field] for field in HISTORY_SCOPE}
            history = tools.inquire("history", context)
            history_component = {
                "status": "succeeded",
                "complete": True,
                "returned_count": len(history),
                "reported_count": None,
                "coverage_basis": "qualified_single_response",
                "request_scope": HistoryInquiry().request_body(context),
                "reasons": [],
            }
        components["operationHistory"] = history_component
        route = None
        route_component = {
            "status": "unverified",
            "complete": False,
            "reasons": ["ROUTE_ASSOCIATION_UNVERIFIED"],
        }
        if "routeId" in root and root["routeId"] in (None, ""):
            route_component = {
                "status": "inapplicable",
                "complete": True,
                "reasons": [],
            }
        elif exact(root.get("routeId")) and exact(root.get("debitAliasName")):
            context = {"routeId": root["routeId"], "aliasName": root["debitAliasName"]}
            route = tools.inquire("route", context)
            route_component = {
                "status": "succeeded",
                "complete": True,
                "reasons": [],
                "identity": RouteInquiry().request_body(context),
                "member_counts": {
                    field: len(route[field])
                    for field in ("dynamicQuotas", "staticQuotas")
                },
                "reported_count_unit": "unknown",
            }
        components["routeDetails"] = route_component
        reasons = tuple(
            reason
            for component in components.values()
            for reason in component.get("reasons", [])
        )
        evidence = AcquisitionEvidence.for_collection(
            complete=not reasons,
            reported_total=None,
            collected_total=1,
            arrivals=1,
            reasons=reasons,
            attempts=(
                {
                    "components": components,
                    "snapshot_consistency": (
                        "sequential source reads; no atomic snapshot guarantee"
                    ),
                },
            ),
        )
        return CustomGetResult(
            {**root, "operationHistory": history, "routeDetails": route}, evidence
        )


adapter = Adapter()
