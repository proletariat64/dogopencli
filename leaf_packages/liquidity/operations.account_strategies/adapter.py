"""Native account operation strategies through the host offset List SDK."""

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

PAGE_SIZE = 5000
FILTERS = (
    ("entity", "fundEntityList", "entity"),
    ("bank", "fundBankIdList", "bankId"),
    ("alias", "aliasNameList", "aliasName"),
    ("currency", "currencyList", "currency"),
    ("account_type", "accountTypeList", "accountType"),
    ("operation_strategy", "operationStrategyList", "operationStrategy"),
)
STRATEGY_LABELS = {
    "BANK_SWEEPING": ("Bank Sweeping Agreement",),
    "SELF_BUILD_CASH_POOL": ("Self-Build Cash Pool", "Self-Built Cash Pool"),
    "PROGRAMMABLE_PAYMENT": ("Programmable Payment",),
    "AI_GLOBAL_DECISION": ("AI Global Decision",),
    "EOD_BAL_ESTIMATION": ("EOD Bal Estimation Decision",),
    "T0_DECISION": ("T0 Decision",),
    "RT_DECISION": ("RT Decision",),
    "NO_NEED": ("No Need",),
}


def validate_native_filters(values: Any) -> None:
    allowed = {native for _, native, _ in FILTERS} | {"coverAlgorithm"}
    if not isinstance(values, dict) or set(values) - allowed:
        raise CliError(
            INVALID_ARGUMENT, "unsupported account strategy scope", exit_code=2
        )
    for _, native, _ in FILTERS:
        if native not in values:
            continue
        items = values[native]
        if (
            not isinstance(items, list)
            or not items
            or any(not isinstance(item, str) or not item.strip() for item in items)
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "native filters require nonblank string arrays",
                exit_code=2,
            )
        if native == "operationStrategyList" and any(
            item not in STRATEGY_LABELS for item in items
        ):
            raise CliError(
                INVALID_ARGUMENT, "unknown operation strategy code", exit_code=2
            )
    if "coverAlgorithm" in values and values["coverAlgorithm"] not in ("Y", "N"):
        raise CliError(INVALID_ARGUMENT, "cover-algorithm requires Y or N", exit_code=2)


def native_filters(parameters: dict[str, Any]) -> dict[str, Any]:
    values = {}
    for flag, native, _ in FILTERS:
        selected = parameters.get(flag)
        if selected is None or selected == []:
            continue
        if not isinstance(selected, list) or any(
            not isinstance(item, str) or not item.strip() for item in selected
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "filters require nonblank repeated strings",
                exit_code=2,
            )
        values[native] = sorted(set(selected))
    if parameters.get("cover_algorithm") is not None:
        values["coverAlgorithm"] = parameters["cover_algorithm"]
    validate_native_filters(values)
    return values


def row_matches(row: dict[str, Any], values: dict[str, Any]) -> bool:
    for _, native, field in FILTERS:
        wanted = values.get(native)
        if not wanted:
            continue
        if native == "operationStrategyList":
            display = row.get(field)
            if not isinstance(display, str):
                return False
            members = {part.strip() for part in display.split(",")}
            if not any(members.intersection(STRATEGY_LABELS[code]) for code in wanted):
                return False
        elif row.get(field) not in wanted:
            return False
    return (
        "coverAlgorithm" not in values
        or row.get("coverAlgorithm") == values["coverAlgorithm"]
    )


class Inquiry:
    name = "liquidity.operations.account_strategies.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/strategyManage/queryList.json",
        page_size=PAGE_SIZE,
        one_based=False,
        allowed_body_keys=frozenset(
            {"rowStart", "pageSize", "coverAlgorithm"}
            | {native for _, native, _ in FILTERS}
        ),
        fixed_body_values=(("pageSize", PAGE_SIZE),),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict[str, Any]:
        if (
            type(row_start) is not int
            or row_start < 0
            or row_start % PAGE_SIZE
            or type(page_size) is not int
            or page_size != PAGE_SIZE
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified strategy offset or width")
        try:
            values = parse(scope)
            validate_native_filters(values)
        except (ValueError, UnicodeError, CliError) as error:
            raise CliError(
                REQUEST_NOT_ALLOWED, "unverified account strategy scope"
            ) from error
        return {**values, "rowStart": row_start, "pageSize": PAGE_SIZE}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "strategy success marker must be boolean")
        if not document["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected account strategy inquiry"
            )
        data = document.get("data")
        if not isinstance(data, dict):
            raise CliError(INVALID_RESPONSE, "strategy result data is not an object")
        total = data.get("totalCount")
        if type(total) is not int or total < 0:
            raise CliError(
                INVALID_RESPONSE, "strategy total must be a nonnegative integer"
            )
        if "pageSize" in data and (
            type(data["pageSize"]) is not int or data["pageSize"] != PAGE_SIZE
        ):
            raise CliError(INVALID_RESPONSE, "strategy page size echo is invalid")
        if "rowStart" in data and (
            type(data["rowStart"]) is not int
            or data["rowStart"] < 0
            or data["rowStart"] % PAGE_SIZE
        ):
            raise CliError(INVALID_RESPONSE, "strategy offset echo is invalid")
        rows = data.get("data")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "strategy records are not an array")
        for row in rows:
            if (
                not isinstance(row, dict)
                or any(
                    not isinstance(row.get(field), str) or not row[field].strip()
                    for field in ("aliasName", "currency")
                )
                or type(row.get("version")) is not int
            ):
                raise CliError(
                    INVALID_RESPONSE, "invalid native account strategy identity"
                )
        return rows, total

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        values = parse(scope)
        validate_native_filters(values)
        if any(not row_matches(row, values) for row in rows):
            raise CliError(
                INVALID_RESPONSE, "strategy row is outside the requested native scope"
            )


CAPABILITY = Inquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        native_filters(parameters)
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_filters(parameters))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        values = native_filters(parameters)
        return [row for row in records if row_matches(row, values)]


adapter = Adapter()
