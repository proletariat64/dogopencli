"""Verified payment-rule list contracts; production actions remain inquiry-only."""

from dataclasses import dataclass, field
from typing import Any

from ...errors import INVALID_RESPONSE, REQUEST_NOT_ALLOWED, CliError
from .. import EndpointContract, ParsedPage
from ..envelope import success_document


def matches(value: Any, accepted: list[str], array: bool = False) -> bool:
    if array:
        return isinstance(value, list) and any(
            isinstance(item, str) and item in accepted for item in value
        )
    return isinstance(value, str) and value in accepted


def objects(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise CliError(INVALID_RESPONSE, "invalid nested bank-switch configuration")
    return value


def bank_matches(row: dict[str, Any], filters: dict[str, list[str]]) -> bool:
    if "switchNodeCode" in filters and not matches(
        row.get("switchNodeCode"), filters["switchNodeCode"]
    ):
        return False
    nested = set(filters) - {"switchNodeCode"}
    if not nested:
        return True
    for requirement in objects(row.get("fundNavigationNodeSwitchRequirementVOList")):
        if "switchClearingNetwork" in filters and not matches(
            requirement.get("switchClearingNetwork"), filters["switchClearingNetwork"]
        ):
            continue
        for rule in objects(requirement.get("switchRuleVOList")):
            if "status" in filters and not matches(
                rule.get("status"), filters["status"]
            ):
                continue
            target_fields = nested & {"targetNodeCode", "clearingNetworkList"}
            if not target_fields:
                return True
            for ratio in objects(rule.get("ratioList")):
                for target in objects(ratio.get("targetNodeInfoList")):
                    if all(
                        matches(target.get(k), filters[k], k == "clearingNetworkList")
                        for k in target_fields
                    ):
                        return True
    return False


@dataclass
class RuleListCapability:
    slug: str
    endpoint: str
    id_field: str
    filters: tuple[tuple[str, str], ...]
    table_columns: tuple[str, ...]
    array_fields: frozenset[str] = frozenset()
    default_scope: str = "all"
    name: str = field(init=False)
    source_config_key: str = field(init=False)
    contract: EndpointContract = field(init=False)

    def __post_init__(self) -> None:
        key = self.slug.replace("-", "_")
        self.name = f"payment.rules.{key}.list"
        self.source_config_key = f"payment_rules_{key}"
        self.contract = EndpointContract(
            method="POST" if self.is_same_bank_transfer else "GET",
            host="ifundboss.alipay.com"
            if self.is_same_bank_transfer
            else "ifundcontrolprodops.alipay.com",
            path=self.endpoint,
            page_size=1000,
            one_based=self.is_same_bank_transfer,
            allowed_body_keys=frozenset({self.page_key, "pageSize"}),
            fixed_body_values=((self.page_key, self.first_page), ("pageSize", 1000)),
            single_page=True,
        )

    @property
    def is_same_bank_transfer(self) -> bool:
        return self.slug == "same-bank-transfer"

    @property
    def first_page(self) -> int:
        return 1 if self.is_same_bank_transfer else 0

    @property
    def page_key(self) -> str:
        return "pageNum" if self.is_same_bank_transfer else "pageNo"

    @property
    def command_path(self) -> str:
        return f"payment rules {self.slug}"

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if scope != "all" or page_num != self.first_page or page_size != 1000:
            raise CliError(
                REQUEST_NOT_ALLOWED, "only the verified first page is allowed"
            )
        return {self.page_key: self.first_page, "pageSize": 1000}

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        if body != self.page_body("all", self.first_page, 1000):
            raise CliError(REQUEST_NOT_ALLOWED, "backend rule filters disabled")
        return {}

    def validate_row(self, row: Any) -> None:
        if not isinstance(row, dict):
            raise CliError(INVALID_RESPONSE, "rule row must be an object")
        if self.slug == "bank-switch":
            for requirement in objects(
                row.get("fundNavigationNodeSwitchRequirementVOList")
            ):
                for rule in objects(requirement.get("switchRuleVOList")):
                    for ratio in objects(rule.get("ratioList")):
                        objects(ratio.get("targetNodeInfoList"))
        identity = row.get(self.id_field)
        valid = (
            type(identity) is int and identity >= 0
            if self.is_same_bank_transfer
            else isinstance(identity, str) and bool(identity.strip())
        )
        if not valid:
            raise CliError(INVALID_RESPONSE, f"invalid rule identity {self.id_field}")

    def identity_key(self, record: dict[str, Any]) -> str | int:
        return record[self.id_field]

    def sort_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(records, key=self.identity_key)

    def filter_records(
        self, records: list[dict[str, Any]], filters: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        if self.slug == "bank-switch":
            return [row for row in records if bank_matches(row, filters)]
        return [
            row
            for row in records
            if all(
                matches(row.get(k), values, k in self.array_fields)
                for k, values in filters.items()
            )
        ]

    def parse_page(self, body: bytes) -> ParsedPage:
        document = success_document(body)
        data = document.get("resultObj" if self.is_same_bank_transfer else "data")
        if not isinstance(data, dict):
            raise CliError(INVALID_RESPONSE, "missing rule page")
        if self.is_same_bank_transfer and data.get("success") is not True:
            raise CliError(INVALID_RESPONSE, "invalid nested rule success")
        pages_key = "totalPages" if self.is_same_bank_transfer else "totalPageNo"
        for key in (self.page_key, "pageSize", "totalCount", pages_key):
            if type(data.get(key)) is not int or data[key] < 0:
                raise CliError(INVALID_RESPONSE, f"invalid rule pagination {key}")
        rows = data.get(
            "payoutBookDecisionRuleVOList"
            if self.is_same_bank_transfer
            else "businessDataList"
        )
        if (
            not isinstance(rows, list)
            or data[self.page_key] != self.first_page
            or data["pageSize"] != 1000
        ):
            raise CliError(INVALID_RESPONSE, "invalid rule list or pagination echo")
        for row in rows:
            self.validate_row(row)
        total = data["totalCount"]
        pages = 1 if rows else 0
        if self.is_same_bank_transfer:
            # Complete single-page scopes have a verified 0/1 page count.
            # Beyond capacity the native count must remain positive, but no
            # larger-page arithmetic or pagination fallback is verified.
            native_pages = data[pages_key]
            if (total <= 1000 and native_pages != (1 if total else 0)) or (
                total > 1000 and native_pages == 0
            ):
                raise CliError(INVALID_RESPONSE, "rule page count mismatch")
        return ParsedPage(rows, self.first_page, 1000, total, pages)


SAME_BANK_TRANSFER = RuleListCapability(
    slug="same-bank-transfer",
    endpoint="/payout/api/bookDecisionRule/search.json",
    id_field="ruleId",
    filters=(("bank", "debitInstId"), ("status", "ruleStatus")),
    table_columns=("ruleId", "debitInstId", "ruleStatus", "ruleTypeCode", "priority"),
)
COST_REDUCTION = RuleListCapability(
    slug="cost-reduction",
    endpoint="/api/fundOut/costCutFlow/query",
    id_field="groupId",
    filters=(
        ("name", "ruleName"),
        ("business-line", "businessCategory"),
        ("entity", "legalEntity"),
        ("currency", "creditCurrency"),
        ("market", "creditorMarket"),
        ("obo", "needObo"),
        ("fvt", "needFvt"),
        ("status", "status"),
    ),
    array_fields=frozenset({"legalEntity", "needObo", "needFvt"}),
    table_columns=(
        "groupId",
        "ruleName",
        "businessCategory",
        "creditCurrency",
        "status",
        "ratio",
        "ratioBase",
    ),
)
RETRY = RuleListCapability(
    slug="retry",
    endpoint="/api/fundOut/flowOperation/exceptionRetryRule/page",
    id_field="ruleId",
    filters=(
        ("name", "ruleName"),
        ("entity", "bizLegalEntityList"),
        ("business-line", "businessCategoryList"),
        ("bank", "debtorInstList"),
        ("currency", "creditorCurrencyList"),
        ("region", "creditorCountryList"),
        ("bank-account", "debtorAccountNoList"),
        ("clearing-network", "clearingNetworkList"),
        ("status", "status"),
        ("communication-mode", "communicationMode"),
        ("integration-mode", "integrationMode"),
    ),
    array_fields=frozenset(
        {
            "bizLegalEntityList",
            "businessCategoryList",
            "debtorInstList",
            "creditorCurrencyList",
            "creditorCountryList",
            "debtorAccountNoList",
            "clearingNetworkList",
        }
    ),
    table_columns=(
        "ruleId",
        "ruleName",
        "status",
        "exceptionRetryType",
        "communicationMode",
        "integrationMode",
    ),
)
BANK_SWITCH = RuleListCapability(
    slug="bank-switch",
    endpoint="/api/fundNavigation/nodeSwitch/query",
    id_field="switchNodeCode",
    filters=(
        ("source-account", "switchNodeCode"),
        ("source-network", "switchClearingNetwork"),
        ("status", "status"),
        ("target-account", "targetNodeCode"),
        ("target-network", "clearingNetworkList"),
    ),
    table_columns=("switchNodeCode", "fundNavigationNodeSwitchRequirementVOList"),
)
CAPABILITIES = (SAME_BANK_TRANSFER, COST_REDUCTION, RETRY, BANK_SWITCH)
