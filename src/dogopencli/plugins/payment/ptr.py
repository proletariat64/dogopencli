"""Verified outflow PTR case library; retain only the inquiry projection."""

import math
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from ...errors import (
    INCOMPLETE_RESULT,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from ...jsonutil import canonical
from .. import EndpointContract, ParsedPage
from ..envelope import success_document

if TYPE_CHECKING:
    from ...collect import CollectedScope
    from .. import Capability

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
MONEY_INTS = frozenset({"cent", "centFactor"})


def _optional(value: Any, expected: type) -> bool:
    return value is None or type(value) is expected


def _project(row: Any) -> dict[str, Any]:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("id"), str)
        or not row["id"].strip()
    ):
        raise CliError(INVALID_RESPONSE, "PTR case requires a nonempty string identity")
    if not isinstance(row.get("fundOutAbilityBaselineVO"), dict):
        raise CliError(INVALID_RESPONSE, "PTR case requires an outflow baseline object")
    result: dict[str, Any] = {}
    for key in STRINGS | TIMESTAMPS | {"verifyResult"}:
        if key not in row:
            continue
        expected = str if key in STRINGS else int if key in TIMESTAMPS else bool
        if not _optional(row[key], expected):
            raise CliError(INVALID_RESPONSE, "invalid PTR case field type")
        result[key] = row[key]
    baseline = row["fundOutAbilityBaselineVO"]
    selected = {k: v for k, v in baseline.items() if k in BASELINE}
    if any(not _optional(v, str) for v in selected.values()):
        raise CliError(INVALID_RESPONSE, "invalid PTR baseline field type")
    result["fundOutAbilityBaselineVO"] = selected
    for key in ("creditorAmount", "debtorAmount"):
        if key not in row:
            continue
        money = row[key]
        if money is None:
            result[key] = None
            continue
        if not isinstance(money, dict):
            raise CliError(INVALID_RESPONSE, "invalid PTR money object")
        selected = {
            k: v
            for k, v in money.items()
            if k in MONEY_STRINGS | MONEY_INTS | {"amount"}
        }
        for field, value in selected.items():
            if value is None:
                continue
            valid = (
                _optional(value, str)
                if field in MONEY_STRINGS
                else _optional(value, int)
                if field in MONEY_INTS
                else (
                    type(value) is int
                    or type(value) is float
                    and math.isfinite(value)
                    or isinstance(value, Decimal)
                    and value.is_finite()
                )
            )
            if not valid:
                raise CliError(INVALID_RESPONSE, "invalid PTR money field type")
        result[key] = selected
    return result


class PtrListCapability:
    slug = "cases"
    name = "payment.ptr.cases.list"
    source_config_key = "payment_ptr_cases"
    default_scope = "outflow-library"
    command_path = "payment ptr cases"
    id_field = "id"
    table_columns: tuple[str, ...] = (
        "id",
        "caseName",
        "caseType",
        "creditorCurrency",
        "obo",
        "fvt",
        "verifyResult",
    )
    filters = (
        ("id", "id"),
        ("name", "caseName"),
        ("channel", "fundOutAbilityBaselineVO.financialInstCode"),
        ("debtor-account", "fundOutAbilityBaselineVO.debtorAccountAliasName"),
        ("debtor-currency", "fundOutAbilityBaselineVO.debtorCurrency"),
        ("creditor-currency", "creditorCurrency"),
        ("clearing-system", "fundOutAbilityBaselineVO.clearingSystemName"),
        ("obo", "obo"),
        ("fvt", "fvt"),
        ("case-type", "caseType"),
        ("baseline-id", "baselineId"),
        ("creditor-account-alias", "creditorAccountAliasName"),
    )
    contract = EndpointContract(
        method="GET",
        host="iglobalfundcontrol.alipay.com",
        path="/api/ptr/case/query.json",
        page_size=5000,
        one_based=False,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
        fixed_body_values=(("pageNo", 0), ("pageSize", 5000)),
    )

    @property
    def data_schema(self) -> dict[str, Any]:
        properties: dict[str, Any] = {
            key: {"type": ["string", "null"]} for key in sorted(STRINGS)
        }
        properties.update(
            {key: {"type": ["integer", "null"]} for key in sorted(TIMESTAMPS)}
        )
        properties["id"] = {"type": "string", "minLength": 1, "pattern": r"\S"}
        properties["verifyResult"] = {"type": ["boolean", "null"]}
        properties["fundOutAbilityBaselineVO"] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                key: {"type": ["string", "null"]} for key in sorted(BASELINE)
            },
        }
        money_properties: dict[str, Any] = {
            key: {"type": ["string", "null"]} for key in sorted(MONEY_STRINGS)
        }
        money_properties.update(
            {key: {"type": ["integer", "null"]} for key in sorted(MONEY_INTS)}
        )
        money_properties["amount"] = {"type": ["number", "null"]}
        for key in ("creditorAmount", "debtorAmount"):
            properties[key] = {
                "type": ["object", "null"],
                "additionalProperties": False,
                "properties": money_properties,
            }
        return {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "fundOutAbilityBaselineVO"],
                "properties": properties,
            },
        }

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope != self.default_scope
            or type(page_num) is not int
            or page_num != 0
            or type(page_size) is not int
            or page_size != 5000
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "only the verified PTR full page is allowed"
            )
        return {"pageNo": 0, "pageSize": 5000}

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        if any(
            type(body.get(key)) is not int for key in ("pageNo", "pageSize")
        ) or body != self.page_body(self.default_scope, 0, 5000):
            raise CliError(REQUEST_NOT_ALLOWED, "backend PTR filters are disabled")
        return {}

    def validate_row(self, row: Any) -> None:
        if _project(row) != row:
            raise CliError(
                INVALID_RESPONSE, "PTR cached row contains unapproved fields"
            )

    def identity_key(self, record: dict[str, Any]) -> str:
        return record["id"]

    def sort_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(records, key=self.identity_key)

    def filter_records(
        self, records: list[dict[str, Any]], filters: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        allowed = {field for _, field in self.filters}
        if any(
            field not in allowed
            or not isinstance(values, list)
            or not values
            or any(not isinstance(v, str) or not v.strip() for v in values)
            for field, values in filters.items()
        ):
            raise CliError(INVALID_ARGUMENT, "invalid PTR exact-match filter")

        def matches(row: dict[str, Any]) -> bool:
            for path, values in filters.items():
                value: Any = row
                for part in path.split("."):
                    value = value.get(part) if isinstance(value, dict) else None
                if not isinstance(value, str) or value not in values:
                    return False
            return True

        return [row for row in records if matches(row)]

    def parse_page(self, body: bytes) -> ParsedPage:
        data = success_document(body)
        if (
            any(
                type(data.get(k)) is not int or data[k] < 0
                for k in ("pageNo", "pageSize", "totalCount")
            )
            or data["pageNo"] != 0
            or data["pageSize"] != 5000
        ):
            raise CliError(INVALID_RESPONSE, "invalid PTR pagination echo")
        rows = data.get("resultDataList")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "missing PTR case list")
        total = data["totalCount"]
        if total > 5000 or total != len(rows):
            raise CliError(
                INCOMPLETE_RESULT, "PTR scope exceeds verified full-page coverage"
            )
        projected = [_project(row) for row in rows]
        if len({row["id"] for row in projected}) != len(projected):
            raise CliError(INCOMPLETE_RESULT, "duplicate PTR identities")
        return ParsedPage(projected, 0, 5000, total, 1 if total else 0)


CASES = PtrListCapability()


def collect_stable(
    capability: "Capability",
    transport: Any,
    scope: str,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> "CollectedScope":
    from ...collect import collect_scope, remaining_seconds

    first = collect_scope(capability, transport, scope, progress=progress)
    second = collect_scope(
        capability,
        transport,
        scope,
        budget_seconds=remaining_seconds(first.deadline),
        progress=progress,
    )
    remaining_seconds(first.deadline)
    if (
        not first.complete
        or not second.complete
        or first.total_count != second.total_count
        or canonical(capability.sort_records(first.records))
        != canonical(capability.sort_records(second.records))
    ):
        raise CliError(INCOMPLETE_RESULT, "PTR library changed between complete reads")
    return replace(first, records=capability.sort_records(first.records))
