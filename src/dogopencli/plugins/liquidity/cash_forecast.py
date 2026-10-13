"""Bounded cash/forecast contracts accepted by spec #76 (v0.2.3).

Only the production-probed BANK/USD scope is declared. Amount filters stay
null: discovering their wire fields does not verify CLI amount options.
The UAT allowlist is populated only after focused SIT and CLI inquiry UAT.
"""

from .spec import (
    ENV_RESULT_FLAG,
    ENV_SUCCESS,
    PAGE_SINGLE,
    PROFILE_DATED,
    PROFILE_HISTORY,
    RUNTIMES,
    SETTINGS,
    TENANT,
    DetailSpec,
    IdentityOption,
    ListSpec,
    ScopeOption,
)

VERSION = "cash-forecast-v0.2.3"
NOTES = (
    "Inquiry-only contract verified on 2026-10-02; fixed per-leaf page width,"
    " no automatic smaller-page fallback.",
    "null, empty string and zero remain distinct; amounts are not divided by 100.",
    "Capture freshness does not establish source observation freshness;"
    " unverified source times and timezones remain unknown.",
)


# Public calendar-date rule (Issue #127): preferred YYYY-MM-DD, previously
# supported compact YYYYMMDD retained; both normalize to the internal
# compact form before scope and request construction.
_DATE_FMT = "YYYY-MM-DD preferred; compact YYYYMMDD accepted"


def _window(start: str, end: str) -> tuple[ScopeOption, ...]:
    # The retained coverage check bounds each row's valueDate by this
    # window, so the value date is the verified queried date axis.
    return (
        ScopeOption(
            "from",
            start,
            f"Inclusive value date window start ({_DATE_FMT}); pair with --to-date.",
            required=True,
            date=True,
            window="from",
            canonical_flag="--from-date",
        ),
        ScopeOption(
            "to",
            end,
            f"Inclusive value date window end ({_DATE_FMT}); pair with --from-date.",
            required=True,
            date=True,
            window="to",
            canonical_flag="--to-date",
        ),
    )


def _timezone() -> ScopeOption:
    return ScopeOption(
        "timezone",
        "timeZone",
        "Verified source timezone.",
        default="GMT+08",
        choices=("GMT+08",),
        verified="GMT+08",
    )


CASH_BALANCES = ListSpec(
    path=("cash", "balances"),
    kind=RUNTIMES,
    title="account balance snapshots",
    endpoint="/latestBalanceQuery.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("balId",),
    profile=PROFILE_HISTORY,
    page_size=100,
    template={"tntInstId": TENANT},
    scope_options=(
        ScopeOption(
            "entity",
            "entitys",
            "Entity scope; native JSON array.",
            repeat=True,
            default="ALIPAYGM",
            verified="Z21",
        ),
        ScopeOption(
            "account",
            "aliasNames",
            "Optional account aliases.",
            repeat=True,
            canonical_flag="--account-alias",
        ),
        _timezone(),
    ),
    table_columns=(
        "balId",
        "entity",
        "aliasName",
        "currency",
        "curBalance",
        "avlBalance",
        "statementCreateTime",
        "timeZone",
    ),
    projection="balances",
    schema_version=VERSION,
    notes=NOTES,
)

CASH_DAILY_BALANCES = ListSpec(
    path=("cash", "balances"),
    kind=RUNTIMES,
    title="source daily balance observations",
    endpoint="/balStatisticalQuery.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data",),
    identity=("entity", "aliasName", "currency", "statisticalDate"),
    pagination=PAGE_SINGLE,
    paged_request=False,
    profile=PROFILE_DATED,
    series_field="statisticalDate",
    series_format="%Y-%m-%d",
    template={"tntInstId": TENANT, "balanceType": "day"},
    scope_options=(
        ScopeOption(
            "entity",
            "entitys",
            "Native instId selection.",
            repeat=True,
            default="ALIPAYGM",
            virtual=True,
        ),
        ScopeOption(
            "account",
            "aliasNames",
            "Optional account aliases.",
            repeat=True,
            canonical_flag="--account-alias",
        ),
        ScopeOption(
            "from_date",
            "queryStartDate",
            "Inclusive daily start; pair with --to-date.",
            date=True,
            window="from",
        ),
        ScopeOption(
            "to_date",
            "queryDate",
            "Inclusive daily end; pair with --from-date.",
            date=True,
            window="to",
        ),
    ),
    table_columns=("entity", "aliasName", "currency", "statisticalDate", "balance"),
    schema_version="cash-daily-balances-v1",
    notes=(
        "Paired --from-date/--to-date select inclusive source daily observations;"
        " no dates retain latest snapshots. Daily dates use GMT+08"
        " and balance means closing book balance.",
        "Daily labels use the frozen current account roster, not proven"
        " historical ownership."
        " No zero filling or historical current/available/opening balances.",
        "Daily acquisition uses disjoint 30-alias/seven-day chunks, at most 1000"
        " chunks under one 900-second deadline including dependencies.",
    ),
)

_GROUP_OPTIONS = (
    ScopeOption(
        "group_code", "userGroupCode", "Optional native group codes.", repeat=True
    ),
    ScopeOption(
        "equi_currency",
        "equiCurrency",
        "Verified equivalent currency.",
        choices=("USD",),
        default="USD",
        verified="USD",
    ),
)
_GROUP_TEMPLATE = {
    "tntInstId": TENANT,
    "bankAccountManageUnitQueryVO": {"tntInstId": TENANT},
}

CASH_GROUPS = ListSpec(
    path=("cash", "groups"),
    kind=SETTINGS,
    title="account group settings",
    endpoint="/bankAccountGroupQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    total=("result", "count"),
    total_checks=(("count",),),
    require_inner_success=True,
    identity=("id",),
    page_size=100,
    vo_field="bankAccountManageUnitQueryVO",
    template=_GROUP_TEMPLATE,
    scope_options=_GROUP_OPTIONS,
    table_columns=("id", "userGroupCode", "groupName", "type"),
    projection="groups_settings",
    schema_version=VERSION,
    notes=(*NOTES, "Members are nested configuration, not an independent getter."),
)

CASH_GROUP_BALANCES = ListSpec(
    path=("cash", "group-balances"),
    kind=RUNTIMES,
    title="group balance snapshots",
    endpoint="/bankAccountGroupQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    total=("result", "count"),
    total_checks=(("count",),),
    require_inner_success=True,
    identity=("id",),
    page_size=100,
    profile=PROFILE_HISTORY,
    vo_field="bankAccountManageUnitQueryVO",
    template=_GROUP_TEMPLATE,
    scope_options=_GROUP_OPTIONS,
    table_columns=("id", "userGroupCode", "groupName", "equiCurrency", "valueDate"),
    projection="group_balances",
    schema_version=VERSION,
    notes=(
        *NOTES,
        "Member observation times are independent; gmtModified is not"
        " a balance observation time. Native original currencies are not summed.",
    ),
)

CASH_POOLS = ListSpec(
    path=("cash", "pools"),
    kind=SETTINGS,
    title="BANK cash pool settings",
    endpoint="/cashPoolList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("id",),
    page_size=100,
    template={"tntInstId": TENANT, "cashPoolCategory": "BANK"},
    table_columns=("id", "cashPoolName", "cashPoolCategory", "mainCurrency", "status"),
    projection="pools_settings",
    schema_version=VERSION,
    notes=(*NOTES, "Fixed BANK category; no per-row detail acquisition."),
)

CASH_POOL_BALANCES = ListSpec(
    path=("cash", "pool-balances"),
    kind=RUNTIMES,
    title="BANK cash pool balance snapshots",
    endpoint="/cashPoolList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("id",),
    page_size=100,
    profile=PROFILE_HISTORY,
    template={"tntInstId": TENANT, "cashPoolCategory": "BANK"},
    table_columns=(
        "id",
        "cashPoolName",
        "valueDate",
        "currentBalance",
        "currentAviBalance",
    ),
    projection="pool_balances",
    schema_version="pool-balances-v1",
    notes=(
        *NOTES,
        "One record per BANK pool; cashPoolMemberVOS contains members identified"
        " by (pool.id, member.id). Pool totals are independent source values,"
        " never recomputed from or added to members.",
        "currentBalance is book balance; currentAviBalance is available for"
        " payments. Neither equality nor ordering between them is required.",
        "Native UI displays pool summary amounts in USD; mainCurrency remains"
        " pool configuration and is not the summary amount currency.",
        "Member original balances use currency; equv balances use bankCurrency."
        " Empty/missing currencies remain unknown; no conversion is performed.",
        "valueDate is the pool balance date only. Member observation times are"
        " unknown. close balances refer to the previous statement day, not"
        " necessarily yesterday. Capture time is not a balance observation time.",
        "masterAccount and isShare remain member-level source flags."
        " Unknown source fields do not imply incomplete collection.",
    ),
)

CASH_POOLS_GET = DetailSpec(
    path=("cash", "pools"),
    action="get",
    kind=SETTINGS,
    title="native BANK cash pool settings detail",
    endpoint="/cashPoolDetail.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data",),
    identity=(
        IdentityOption(
            "pool_id", "id", "Native pool.id; not an account alias.", echo="id"
        ),
    ),
    tenant_field=True,
    template={"inUse": "Y", "cashPoolCategory": "BANK"},
    projection="pools_settings",
    schema_version=VERSION,
    list_leaf=("cash", "pools"),
    table_columns=("id", "cashPoolName", "cashPoolCategory", "mainCurrency", "status"),
    notes=(*NOTES, "Independent native detail/cache, fixed BANK and inUse=Y."),
)

CASH_CREDIT_LINES = ListSpec(
    path=("cash", "credit-lines"),
    kind=SETTINGS,
    title="credit line settings",
    endpoint="/queryBankCreditLineByParams.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    total=("count",),
    total_checks=(("result", "count"),),
    require_inner_success=True,
    identity=("id",),
    page_size=100,
    vo_field="bankCreditLineQuery",
    template={"tntInstId": TENANT},
    table_columns=("id", "creditLineType", "currency", "amount", "status"),
    projection="credit_lines_settings",
    schema_version=VERSION,
    notes=(
        *NOTES,
        "Complete native list only; no unverified source filters."
        " Members are nested credit/account configuration, not a getter.",
    ),
)

CASH_CREDIT_USAGE = ListSpec(
    path=("cash", "credit-usage"),
    kind=RUNTIMES,
    title="credit line usage snapshots",
    endpoint="/queryBankCreditLineByParams.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    total=("count",),
    total_checks=(("result", "count"),),
    require_inner_success=True,
    identity=("id",),
    page_size=100,
    profile=PROFILE_HISTORY,
    vo_field="bankCreditLineQuery",
    template={"tntInstId": TENANT},
    table_columns=(
        "id",
        "creditLineType",
        "currency",
        "amount",
        "usedAmount",
        "availableAmount",
        "shareTag",
    ),
    projection="credit_usage",
    schema_version="credit-usage-v1",
    notes=(
        "Inquiry-only native GET contract verified 2026-10-05; fixed tenant and"
        " page width 100, no unverified filters or detail calls.",
        "One source line per record, with bankAccountCreditLineList members"
        " identified by (line.id, member.id). creditLineId echoes the parent.",
        "Projected business values are preserved, not parsed, normalized"
        " or checked against business rules. No sums, exchange rates, assigned"
        " caps or used/available inequalities are computed.",
        "Parent currency is Credit CCY; member creditCurrency is CreditLine CCY"
        " and currency is the account currency. Both native amount families stay"
        " separate; blank currencies and shared account limits are not inferred.",
        "shareTag and member mergeFlag/isMasterAccount are source flags."
        " mergeFlag is UI grouping, not a new identity or tree level; members"
        " are never collapsed or summed.",
        "Usage observation time is unknown. fetched_at is capture time;"
        " gmtModified and validity dates are not usage observation times."
        " Unknown business fields do not imply incomplete collection.",
    ),
)

CASH_STATEMENTS_EOD = ListSpec(
    path=("cash", "statements", "end-of-day"),
    kind=RUNTIMES,
    title="dated end-of-day cash statements",
    endpoint="/bankAccountDetailDayQuery.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("instId", "bankAccountAliasName", "currency", "valueDate", "bankTransNo"),
    profile=PROFILE_DATED,
    series_field="valueDate",
    page_size=1000,
    template={"tntInstId": TENANT},
    scope_options=(
        ScopeOption(
            "entity",
            "instIds",
            "Institution ids; native JSON array.",
            required=True,
            repeat=True,
        ),
        ScopeOption(
            "account",
            "bankAccountAliasName",
            "Account aliases; not numbers.",
            required=True,
            repeat=True,
            canonical_flag="--account-alias",
        ),
        ScopeOption("currency", "currency", "Statement currency.", required=True),
        _timezone(),
        *_window("queryDateBegin", "queryDateEnd"),
    ),
    table_columns=(
        "bankTransNo",
        "valueDate",
        "transDate",
        "transTime",
        "fundDirection",
        "amount",
        "currency",
    ),
    series_format="%Y%m%d",
    projection="eod",
    schema_version=VERSION,
    notes=(
        *NOTES,
        "valueDate, transDate, transTime and date are distinct."
        " Cr/Dr is sourced, never guessed from amount sign."
        " Empty transaction identities are rejected, never silently dropped.",
    ),
)

FORECAST_RESULTS = ListSpec(
    path=("forecast", "results"),
    kind=RUNTIMES,
    title="dated native forecast records",
    endpoint="/bankCashForecastRecordQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    require_inner_success=True,
    identity=("id",),
    profile=PROFILE_DATED,
    series_field="valueDate",
    page_size=5000,
    vo_field="bankCashForecastRecordQueryVo",
    template={
        "tntInstId": TENANT,
        "bankCashForecastRecordQueryVo": {
            "tntInstId": TENANT,
            "expectInflowStart": None,
            "expectInflowEnd": None,
            "expectOutflowStart": None,
            "expectOutflowEnd": None,
            "expectMinBalance": None,
            "expectMaxBalance": None,
        },
    },
    scope_options=(
        *_window("valueStartDay", "valueEndDay"),
        ScopeOption(
            "record_from_time",
            "recordStartTime",
            "Record creation time of day HH:mm:ss (legacy compact HHmmss accepted);"
            " source timezone unknown.",
            default="00:00:00",
            time=True,
        ),
        ScopeOption(
            "record_to_time",
            "recordEndTime",
            "Record creation time of day HH:mm:ss (legacy compact HHmmss accepted);"
            " source timezone unknown.",
            default="23:59:59",
            time=True,
        ),
        ScopeOption(
            "account",
            "aliasName",
            "Optional native account aliases.",
            repeat=True,
            canonical_flag="--account-alias",
        ),
    ),
    table_columns=(
        "id",
        "bankAccountAliasName",
        "currency",
        "baseValueDate",
        "valueDate",
        "forecastBalance",
        "recordCreateTime",
    ),
    series_format="%Y%m%d",
    projection="forecast_results",
    schema_version=VERSION,
    notes=(
        *NOTES,
        "Only native prediction fields; no realized-balance or accuracy"
        " per-row requests. No timezone request or inferred server timezone."
        " Amount filters remain null; CLI amount filters are not released.",
        "Known backend count/order instability: when acquisition is incomplete,"
        " accounts-compatible live returns available rows with INCOMPLETE_RESULT,"
        " complete=false and exit 1;"
        " strict live rejects partial data. A changed native total fails closed"
        " with INVALID_RESPONSE. Failed refresh never publishes or replaces"
        " complete cache. Compatibility is not backend repair or completeness.",
    ),
)

ACCEPTED_LIST_SPECS = (
    CASH_BALANCES,
    CASH_DAILY_BALANCES,
    CASH_GROUPS,
    CASH_GROUP_BALANCES,
    CASH_POOLS,
    CASH_POOL_BALANCES,
    CASH_CREDIT_LINES,
    CASH_CREDIT_USAGE,
    CASH_STATEMENTS_EOD,
    FORECAST_RESULTS,
)
ACCEPTED_DETAIL_SPECS = (CASH_POOLS_GET,)
# Complete-scope contracts use the existing per-leaf UAT release gate.
# The user separately accepts forecast's existing cash-accounts compatibility:
# incomplete data remains nonzero/unpublished, and changing totals fail closed.
# Fresh 2026-10-02 native UAT proves 20135 arrivals / 20129 unique records,
# strict total-change refusal, failed-refresh rollback and isolated offline read.
# This exception never marks the source dataset complete or fixes the backend.
UAT_COMPLETE_PASSED: frozenset[str] = frozenset(
    {
        CASH_BALANCES.name,
        CASH_GROUPS.name,
        CASH_GROUP_BALANCES.name,
        CASH_POOLS.name,
        CASH_POOL_BALANCES.name,
        CASH_POOLS_GET.name,
        CASH_CREDIT_LINES.name,
        CASH_CREDIT_USAGE.name,
        CASH_STATEMENTS_EOD.name,
    }
)
UAT_COMPATIBILITY_PASSED = frozenset({FORECAST_RESULTS.name})
UAT_PASSED = UAT_COMPLETE_PASSED | UAT_COMPATIBILITY_PASSED
# Explicit activation after local CI/apex review and per-leaf UAT evidence.
RELEASED = UAT_PASSED
CI_BLOCKER = (
    "Spec #76 candidates require a reviewed release allowlist after focused SIT,"
    " native CLI UAT and authenticated local CI/review checks."
)
UAT_BLOCKERS: dict[str, str] = {}
WITHDRAWN_GETTERS = frozenset(
    {
        ("cash", "groups", "get"),
        ("cash", "credit-lines", "get"),
        ("forecast", "results", "get"),
    }
)
