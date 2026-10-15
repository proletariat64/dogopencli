"""S01 account-operation strategies in the native default version view (#191)."""

from typing import Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from .spec import ENV_SUCCESS, SETTINGS, ListSpec, ScopeOption

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
FIELDS = (
    "accountType",
    "aliasName",
    "bankId",
    "coverAlgorithm",
    "currency",
    "entity",
    "operationStrategy",
    "status",
    "processStatus",
    "version",
    "lastModifiedTime",
)
NATIVE_FILTERS = (
    ("entity", "fundEntityList", "entity"),
    ("bank", "fundBankIdList", "bankId"),
    ("alias", "aliasNameList", "aliasName"),
    ("currency", "currencyList", "currency"),
    ("account_type", "accountTypeList", "accountType"),
    ("operation_strategy", "operationStrategyList", "operationStrategy"),
)
ACCOUNT_STRATEGIES = ListSpec(
    path=("operations", "account_strategies"),
    kind=SETTINGS,
    title="account operation strategies in the native default version view",
    endpoint="/strategyManage/queryList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("aliasName", "currency", "version"),
    page_size=5000,
    projection="account_strategies",
    schema_version="account-strategies-v1",
    scope_options=(
        *(
            ScopeOption(
                flag,
                native,
                "Native source filter; repeat for OR within this dimension.",
                repeat=True,
                choices=tuple(STRATEGY_LABELS) if flag == "operation_strategy" else (),
            )
            for flag, native, _ in NATIVE_FILTERS
        ),
        ScopeOption(
            "cover_algorithm",
            "coverAlgorithm",
            "Native algorithm coverage flag.",
            choices=("Y", "N"),
        ),
    ),
    table_columns=FIELDS,
    notes=(
        "Source: operations management / StrategyManagement, separate from rules/*.",
        "No filters means the native default version view, not all history or "
        "approval states. No status request parameter is accepted or sent; native "
        "Invalid rows remain visible.",
        "status is configuration status; processStatus is approval status. Native "
        "numeric version remains unchanged; no latest-version or approval "
        "selection.",
        "operationStrategy preserves native comma-separated display text, order "
        "and duplicate members. Offline filtering matches known strategy members, "
        "including Self-Built Cash Pool.",
        "Seven optional native filters use OR within each dimension and AND across "
        "dimensions. Offline replay only filters the last saved scope and cannot "
        "acquire extra versions.",
        "coverAlgorithm Y/N does not prove an algorithm ran. lastModifiedTime is "
        "source time, distinct from capture time; its timezone stays unknown.",
        "Fixed pageSize 5000 with rowStart and independent terminal probe; display "
        "windows never change acquisition coverage.",
    ),
)


def validate_strategy_query(values: dict[str, Any]) -> None:
    """Validate only the seven authorized native dimensions, without defaults."""
    allowed = {native for _, native, _ in NATIVE_FILTERS} | {"coverAlgorithm"}
    if set(values) - allowed:
        raise CliError(
            INVALID_ARGUMENT,
            "unsupported account strategy query parameter",
            exit_code=EXIT_USAGE,
        )
    for flag, native, _ in NATIVE_FILTERS:
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
                f"--{flag.replace('_', '-')} needs nonempty repeated values",
                exit_code=EXIT_USAGE,
            )
        if native == "operationStrategyList" and any(
            item not in STRATEGY_LABELS for item in items
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "unknown operation strategy code",
                exit_code=EXIT_USAGE,
            )
    if "coverAlgorithm" in values and values["coverAlgorithm"] not in ("Y", "N"):
        raise CliError(
            INVALID_ARGUMENT, "--cover-algorithm must be Y or N", exit_code=EXIT_USAGE
        )


def project_strategy(row: dict[str, Any]) -> dict[str, Any]:
    """Preserve necessary source fields and native version type."""
    for field in ("aliasName", "currency"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise CliError(
                INVALID_RESPONSE, f"account strategy {field} must be a native string"
            )
    if isinstance(row.get("version"), bool) or not isinstance(row.get("version"), int):
        raise CliError(
            INVALID_RESPONSE, "account strategy version must be a native integer"
        )
    return {field: row[field] for field in FIELDS if field in row}


def strategy_row_matches(row: dict[str, Any], values: dict[str, Any]) -> bool:
    """Match explicit saved-row filters; never normalize source display text."""
    for _, native, field in NATIVE_FILTERS:
        wanted = values.get(native)
        if not wanted:
            continue
        if native == "operationStrategyList":
            display = row.get(field)
            if not isinstance(display, str):
                return False
            members = {part.strip() for part in display.split(",")}
            if not any(
                members.intersection(STRATEGY_LABELS.get(code, ())) for code in wanted
            ):
                return False
        elif row.get(field) not in wanted:
            return False
    return (
        "coverAlgorithm" not in values
        or row.get("coverAlgorithm") == values["coverAlgorithm"]
    )


def validate_strategy_rows_scope(
    rows: list[dict[str, Any]], values: dict[str, Any]
) -> None:
    for row in rows:
        if not strategy_row_matches(row, values):
            raise CliError(
                INVALID_RESPONSE, "account strategy row is outside the requested scope"
            )
