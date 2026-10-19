"""Native bank-switch source trees through the host List SDK."""

from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse

FILTERS = (
    ("source_account", "switchNodeCode"),
    ("source_network", "switchClearingNetwork"),
    ("status", "status"),
    ("target_account", "targetNodeCode"),
    ("target_network", "clearingNetworkList"),
)
REQUIREMENTS = "fundNavigationNodeSwitchRequirementVOList"


def objects(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise CliError(INVALID_RESPONSE, "bank-switch children require object arrays")
    return value


def validate_filters(parameters: dict[str, Any]) -> None:
    for name, _ in FILTERS:
        values = parameters.get(name)
        if values is not None and (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise CliError(
                INVALID_ARGUMENT, "filters require nonblank exact strings", exit_code=2
            )


def matches(value: Any, values: list[str], *, array: bool = False) -> bool:
    if array:
        return isinstance(value, list) and any(
            isinstance(item, str) and item in values for item in value
        )
    return isinstance(value, str) and value in values


def selected(row: dict[str, Any], parameters: dict[str, Any]) -> bool:
    if parameters.get("source_account") and not matches(
        row.get("switchNodeCode"), parameters["source_account"]
    ):
        return False
    if not any(parameters.get(name) for name, _ in FILTERS[1:]):
        return True
    for requirement in objects(row.get(REQUIREMENTS)):
        if parameters.get("source_network") and not matches(
            requirement.get("switchClearingNetwork"), parameters["source_network"]
        ):
            continue
        for rule in objects(requirement.get("switchRuleVOList")):
            if parameters.get("status") and not matches(
                rule.get("status"), parameters["status"]
            ):
                continue
            if not (
                parameters.get("target_account") or parameters.get("target_network")
            ):
                return True
            for ratio in objects(rule.get("ratioList")):
                for target in objects(ratio.get("targetNodeInfoList")):
                    if all(
                        not parameters.get(name)
                        or matches(
                            target.get(field),
                            parameters[name],
                            array=name == "target_network",
                        )
                        for name, field in FILTERS[3:]
                    ):
                        return True
    return False


class Inquiry:
    name = "payment.rules.bank_switch.list"
    page_url = (
        "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
        "bankSwitchOperation/bankSwitchManage"
    )
    contract = EndpointContract(
        method="GET",
        host="ifundcontrolprodops.alipay.com",
        path="/api/fundNavigation/nodeSwitch/query",
        page_size=1000,
        one_based=False,
        encoding="query",
        single_page=True,
        allowed_body_keys=frozenset({"pageNo", "pageSize"}),
        fixed_body_values=(("pageNo", 0), ("pageSize", 1000)),
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope != "all"
            or type(page_num) is not int
            or page_num != 0
            or type(page_size) is not int
            or page_size != 1000
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "only the verified first page is allowed"
            )
        return {"pageNo": 0, "pageSize": 1000}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "response requires boolean success")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        data = document.get("data")
        if not isinstance(data, dict) or any(
            type(data.get(key)) is not int or data[key] < 0
            for key in ("pageNo", "pageSize", "totalCount", "totalPageNo")
        ):
            raise CliError(INVALID_RESPONSE, "invalid native pagination fields")
        rows, total = data.get("businessDataList"), data["totalCount"]
        if (
            not isinstance(rows, list)
            or data["pageNo"] != 0
            or data["pageSize"] != 1000
        ):
            raise CliError(INVALID_RESPONSE, "invalid native list or page echo")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("switchNodeCode"), str)
                or not row["switchNodeCode"].strip()
            ):
                raise CliError(
                    INVALID_RESPONSE, "source identity requires nonblank string"
                )
            for requirement in objects(row.get(REQUIREMENTS)):
                for rule in objects(requirement.get("switchRuleVOList")):
                    for ratio in objects(rule.get("ratioList")):
                        objects(ratio.get("targetNodeInfoList"))
        return ParsedPage(rows, 0, 1000, total, -(-total // 1000))


CAPABILITY = Inquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        validate_filters(parameters)
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        validate_filters(parameters)
        return "all"

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        validate_filters(parameters)
        return sorted(
            (row for row in records if selected(row, parameters)),
            key=lambda row: row["switchNodeCode"],
        )


adapter = Adapter()
