"""Outflow PTR library inquiries with two complete retained-content reads."""

import math
from decimal import Decimal
from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INCOMPLETE_RESULT,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.query import CustomListResult

STRINGS = frozenset(
    {
        "id",
        "baselineId",
        "caseAutomationRuleId",
        "caseName",
        "caseType",
        "creditorAccountAliasName",
        "creditorAccountType",
        "creditorCurrency",
        "fvt",
        "obo",
        "purposeCode",
        "referenceObo",
        "verifyFundOutOrderId",
    }
)
TIMESTAMPS = frozenset({"gmtCreate", "gmtModified", "verifyTime"})
BASELINE = frozenset(
    {
        "clearingSystemName",
        "communicationMode",
        "creditorCurrency",
        "debtorAccountAliasName",
        "debtorCurrency",
        "financialInstCode",
        "integrationMode",
        "regulatoryRequiredObo",
        "supportFvt",
        "supportObo",
        "supportReferenceObo",
    }
)
MONEY_STRINGS = frozenset({"currency", "currencyCode", "currencyValue"})
MONEY_INTEGERS = frozenset({"cent", "centFactor"})
FILTERS = {
    "id": "id",
    "name": "caseName",
    "channel": "fundOutAbilityBaselineVO.financialInstCode",
    "debtor_account": "fundOutAbilityBaselineVO.debtorAccountAliasName",
    "debtor_currency": "fundOutAbilityBaselineVO.debtorCurrency",
    "creditor_currency": "creditorCurrency",
    "clearing_system": "fundOutAbilityBaselineVO.clearingSystemName",
    "obo": "obo",
    "fvt": "fvt",
    "case_type": "caseType",
    "baseline_id": "baselineId",
    "creditor_account_alias": "creditorAccountAliasName",
}
SCOPE = "outflow-library"


def invalid(message: str) -> None:
    raise CliError(INVALID_RESPONSE, message)


def project_money(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        invalid("PTR money must be an object or null")
    retained = {}
    for key in MONEY_STRINGS | MONEY_INTEGERS | {"amount"}:
        if key not in value:
            continue
        item = value[key]
        if key == "amount":
            valid = (
                item is None
                or type(item) is int
                or type(item) is float
                and math.isfinite(item)
                or isinstance(item, Decimal)
                and item.is_finite()
            )
        else:
            valid = item is None or type(item) is (str if key in MONEY_STRINGS else int)
        if not valid:
            invalid("invalid retained PTR money type")
        retained[key] = item
    return retained


def project(row: Any) -> dict[str, Any]:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("id"), str)
        or not row["id"].strip()
    ):
        invalid("PTR case requires a nonblank native string id")
    baseline = row.get("fundOutAbilityBaselineVO")
    if not isinstance(baseline, dict):
        invalid("PTR case requires an outflow baseline object")
    retained = {}
    for key in STRINGS | TIMESTAMPS | {"verifyResult"}:
        if key not in row:
            continue
        item = row[key]
        expected = str if key in STRINGS else int if key in TIMESTAMPS else bool
        if item is not None and type(item) is not expected:
            invalid("invalid retained PTR case type")
        retained[key] = item
    selected = {key: value for key, value in baseline.items() if key in BASELINE}
    if any(value is not None and type(value) is not str for value in selected.values()):
        invalid("invalid retained PTR baseline type")
    retained["fundOutAbilityBaselineVO"] = selected
    for key in ("creditorAmount", "debtorAmount"):
        if key in row:
            retained[key] = project_money(row[key])
    return retained


def validate_filters(parameters: dict[str, Any]) -> None:
    for name in FILTERS:
        values = parameters.get(name)
        if values is not None and (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "PTR filters require nonblank exact strings",
                exit_code=2,
            )


class Cases:
    name = "payment.ptr.cases.list"
    page_url = "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/productPTRManagement/caseLibrary"
    contract = EndpointContract(
        method="GET",
        host="iglobalfundcontrol.alipay.com",
        path="/api/ptr/case/query.json",
        page_size=5000,
        one_based=False,
        single_page=True,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
        fixed_body_values=(("pageNo", 0), ("pageSize", 5000)),
        encoding="query",
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, int]:
        if (
            scope != SCOPE
            or type(page_num) is not int
            or page_num != 0
            or type(page_size) is not int
            or page_size != 5000
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "only the fixed PTR case page is allowed"
            )
        return {"pageNo": 0, "pageSize": 5000}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            data = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                INVALID_RESPONSE, "PTR response is not valid JSON"
            ) from error
        if not isinstance(data, dict) or type(data.get("success")) is not bool:
            invalid("PTR response requires boolean success")
        if not data["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        if any(
            type(data.get(key)) is not int or data[key] < 0
            for key in ("pageNo", "pageSize", "totalCount")
        ):
            invalid("PTR pagination requires nonnegative integers")
        rows, total = data.get("resultDataList"), data["totalCount"]
        if (
            not isinstance(rows, list)
            or data["pageNo"] != 0
            or data["pageSize"] != 5000
        ):
            invalid("invalid PTR list or pagination echo")
        if total > 5000 or total != len(rows):
            raise CliError(
                INCOMPLETE_RESULT, "PTR scope exceeds verified full-page coverage"
            )
        retained = [project(row) for row in rows]
        if len({row["id"] for row in retained}) != len(retained):
            raise CliError(INCOMPLETE_RESULT, "duplicate PTR case identities")
        return ParsedPage(retained, 0, 5000, total, 1 if total else 0)


CAPABILITY = Cases()


class Adapter:
    def query_capability(
        self, operation: str, name: str, parameters: dict[str, Any]
    ) -> Cases:
        validate_filters(parameters)
        if operation != "list" or name != "cases":
            raise CliError(REQUEST_NOT_ALLOWED, "undeclared PTR inquiry")
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        validate_filters(parameters)
        return SCOPE

    def query_list(self, parameters: dict[str, Any], tools: Any) -> CustomListResult:
        scope = self.scope(parameters)
        first = tools.collect("cases", scope)
        second = tools.collect("cases", scope)
        first_rows = sorted(first.records, key=lambda row: row["id"])
        second_rows = sorted(second.records, key=lambda row: row["id"])
        if (
            not first.evidence.scope_complete
            or not first.evidence.dataset_complete
            or not second.evidence.scope_complete
            or not second.evidence.dataset_complete
            or first.evidence.reported_total != second.evidence.reported_total
            or canonical(first_rows) != canonical(second_rows)
        ):
            raise CliError(
                INCOMPLETE_RESULT, "PTR library changed between complete reads"
            )
        return CustomListResult(first_rows, first.evidence)

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        validate_filters(parameters)
        selected = records
        for parameter, path in FILTERS.items():
            values = parameters.get(parameter)
            if not values:
                continue
            matched = []
            for row in selected:
                value: Any = row
                for part in path.split("."):
                    value = value.get(part) if isinstance(value, dict) else None
                if isinstance(value, str) and value in values:
                    matched.append(row)
            selected = matched
        return sorted(selected, key=lambda row: row["id"])


adapter = Adapter()
