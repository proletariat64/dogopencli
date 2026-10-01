"""The liquidity leaf catalog: shipped contracts and evidence-based deferrals.

Every leaf in issue #72's populated candidate catalog appears here exactly
once. Shipped leaves carry the verified contract observed on 2026-10-01
(exact method/path/encoding/payload, envelope, container/total paths, typed
identity, offline profile). Deferred leaves stay discoverable as unsupported
commands whose execution fails with their evidence reason; they never return
placeholder datasets. Evidence:
docs/research/general/2026-10-01-liquidity-live-probes.md.
"""

from dataclasses import dataclass
from typing import Any

from ...errors import INVALID_ARGUMENT, CliError
from ...helpspec import (
    ALL,
    CACHE_FLAGS,
    CACHE_SEMANTICS,
    DISPLAY_WINDOW,
    FIELDS,
    FORMAT_TABLE,
    LIMIT,
    LIVE,
    OFFSET,
    QUERY_EFFECTS_VARIANTS,
    QUERY_OUTPUT,
    REFRESH_CDP_EFFECTS,
    REFRESH_OUTPUT,
    BizNode,
    OptionSpec,
    opt,
)
from .capability import (
    LiquidityDetailCapability,
    LiquidityListCapability,
    encode_scope,
    scope_values,
)
from .spec import (
    ENC_FORM,
    ENV_BASE_RESULT,
    ENV_RESULT_FLAG,
    ENV_RESULT_SUCCESS,
    ENV_SUCCESS,
    PAGE_SINGLE,
    PROFILE_DATED,
    PROFILE_HISTORY,
    PROFILE_SNAPSHOT,
    REFERENCE,
    RUNTIMES,
    SETTINGS,
    TENANT,
    DeferredLeaf,
    DetailSpec,
    IdentityOption,
    ListSpec,
    ScopeOption,
)

VERIFIED_DATE = "2026-10-01"
_PAGE_ECHO_NOTE = (
    "Pagination: verified rowStart/pageSize=10 offset collection against the"
    " reported total; any changed total, identity conflict or coverage gap"
    " fails acquisition and preserves the previous cache."
)
_SINGLE_NOTE = (
    "Single verified request: this observed route returns its whole scoped"
    " set in one response; there is no offset collection."
)
_DATE_FMT = "Dates are YYYYMMDD."
_NULL_NOTE = (
    "null, empty string and zero are distinct preserved source states;"
    " timestamp units and time zones stay as sourced unless verified."
)


def _account(summary: str, field: str = "aliasNameList", **kwargs: Any) -> ScopeOption:
    return ScopeOption(
        "account", field, summary, required=True, list_of_one=True, **kwargs
    )


def _timezone() -> ScopeOption:
    return ScopeOption(
        "timezone",
        "timeZone",
        "Source time zone; GMT+08 is the live-verified value.",
        default="GMT+08",
        verified="GMT+08",
    )


def _window(field_from: str, field_to: str) -> tuple[ScopeOption, ScopeOption]:
    return (
        ScopeOption(
            "from_date",
            field_from,
            f"Business window start, sent as {field_from}. {_DATE_FMT}",
            required=True,
            date=True,
            window="from",
        ),
        ScopeOption(
            "to_date",
            field_to,
            f"Business window end, sent as {field_to}. {_DATE_FMT}",
            required=True,
            date=True,
            window="to",
        ),
    )


def _inst_id() -> ScopeOption:
    return ScopeOption(
        "inst_id",
        "instIds",
        "Entity/institution id; Z21 is the live-verified value.",
        default="Z21",
        list_of_one=True,
        verified="Z21",
    )


# --- list specifications -------------------------------------------------

CASH_WATERLEVELS = ListSpec(
    path=("cash", "waterlevels"),
    kind=RUNTIMES,
    title="account water levels",
    endpoint="/bufferReportList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("aliasName", "currency"),
    profile=PROFILE_HISTORY,
    scope_options=(_account("Account alias whose water levels to acquire."),),
    filters=(("currency", "currency"),),
    table_columns=("aliasName", "currency", "valueDate", "curAvlBal", "timeZone"),
    notes=(
        "Latest observed buffer/water-level state per account; captures are"
        " retained with capture time as the history axis.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

CASH_STATEMENTS_INTRADAY = ListSpec(
    path=("cash", "statements", "intraday"),
    kind=RUNTIMES,
    title="intraday cash statements",
    endpoint="/bankAccountDetailQuery.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("bankTransNo",),
    profile=PROFILE_DATED,
    series_field="valueDate",
    template={"tntInstId": TENANT},
    scope_options=(
        _account("Account alias.", "bankAccountAliasName"),
        ScopeOption("currency", "currency", "Statement currency.", required=True),
        _inst_id(),
        _timezone(),
        *_window("queryDateBegin", "queryDateEnd"),
    ),
    filters=(("fund_direction", "fundDirection"),),
    table_columns=(
        "bankTransNo",
        "transDate",
        "transTime",
        "fundDirection",
        "amount",
        "currency",
        "valueDate",
    ),
    notes=(
        "Record schema is live-verified on a populated previous-day scope;"
        " an empty window is a valid empty dataset, not missing coverage.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

FORECAST_ADJUSTMENTS = ListSpec(
    path=("forecast", "adjustments"),
    kind=RUNTIMES,
    title="forecast adjustments",
    endpoint="/bankCashForecastAdjustmentQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("id",),
    profile=PROFILE_HISTORY,
    vo_field="bankCashForecastAdjustmentQueryVO",
    template={
        "tntInstId": TENANT,
        "bankCashForecastAdjustmentQueryVO": {
            "tntInstId": TENANT,
            "startValueDate": None,
            "endValueDate": None,
        },
    },
    table_columns=("id", "aliasName", "amount", "currency", "valueDate", "valueTime"),
    notes=(
        "The verified request carries no date filters (null bounds): the"
        " acquisition is the full current adjustment set.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

FORECAST_CASHFLOWS = ListSpec(
    path=("forecast", "cashflows"),
    kind=RUNTIMES,
    title="forecast cash flows",
    endpoint="/queryCashFlowData.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "bankAccountCashFlowVOList"),
    total=None,
    pagination=PAGE_SINGLE,
    paged_request=False,
    identity=("bankAccountNo", "originalBizNo", "expectValueDate", "fundDirection"),
    profile=PROFILE_DATED,
    series_field="expectValueDate",
    vo_field="cashFlowDataQueryVO",
    template={
        "tntInstId": TENANT,
        "cashFlowDataQueryVO": {"minAmount": None, "maxAmount": None},
    },
    scope_options=(
        ScopeOption(
            "inst_id",
            "instId",
            "Entity id; Z21 is the live-verified value.",
            default="Z21",
            verified="Z21",
        ),
        _account("Account alias.", "aliasName"),
        ScopeOption(
            "currency",
            "currency",
            "Currency; the wire shape is a single-element list.",
            required=True,
            list_of_one=True,
        ),
        *_window("beginValueDay", "endValueDay"),
    ),
    table_columns=(
        "bankAccountNo",
        "bankAccountAliasName",
        "fundDirection",
        "amountStr",
        "expectValueDate",
    ),
    notes=(
        "No reported total exists; the single response is the complete"
        " scoped set. Record schema is live-verified on a populated"
        " previous-day scope.",
        _NULL_NOTE,
    ),
)

OPERATIONS_FORWARDS = ListSpec(
    path=("operations", "forwards"),
    kind=RUNTIMES,
    title="forward orders",
    endpoint="/forwardOrderList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("orderNo",),
    profile=PROFILE_HISTORY,
    template={"tntInstId": TENANT},
    table_columns=(
        "orderNo",
        "currencyPair",
        "buyAmount",
        "sellAmount",
        "tradeDate",
        "valueDate",
    ),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

OPERATIONS_ASSET_TRADES = ListSpec(
    path=("operations", "asset-trades"),
    kind=RUNTIMES,
    title="asset transfer orders",
    endpoint="/assetTransferOrderListQuery.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("orderNo",),
    profile=PROFILE_DATED,
    series_field="tradingDate",
    template={"tntInstId": TENANT},
    scope_options=(
        _timezone(),
        *_window("tradingDateBegin", "tradingDateEnd"),
    ),
    table_columns=(
        "orderNo",
        "tradingDate",
        "transactionType",
        "assetTransferAmount",
        "assetTransferCurrency",
        "orderStatus",
    ),
    notes=(
        "Record schema is live-verified on a populated previous-day scope.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

OPERATIONS_PREFUNDS = ListSpec(
    path=("operations", "prefunds"),
    kind=RUNTIMES,
    title="pre-funding orders",
    endpoint="/queryPreFundingOrderList.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("id",),
    profile=PROFILE_HISTORY,
    vo_field="preFundingOrderQueryVO",
    template={"tntInstId": TENANT, "timeZone": "GMt+8"},
    scope_options=(
        ScopeOption(
            "status",
            "statusList",
            "Order status; repeatable. Live-verified sets:"
            " APPROVED,CLOSED and SUBMITTED,REJECTED,CLOSED_SUBMITTED.",
            required=True,
            repeat=True,
            choices=("APPROVED", "CLOSED", "SUBMITTED", "REJECTED", "CLOSED_SUBMITTED"),
        ),
    ),
    filters=(("currency", "currency"),),
    table_columns=(
        "id",
        "prefundingBizNo",
        "amount",
        "currency",
        "status",
        "startDate",
        "endDate",
    ),
    notes=(
        "The top-level timeZone value GMt+8 is the exact live-verified"
        " casing and is sent unchanged.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

INVESTMENT_HOLDINGS = ListSpec(
    path=("investment", "holdings"),
    kind=RUNTIMES,
    title="investment holdings",
    endpoint="/portfolioQueryList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("investmentNo",),
    profile=PROFILE_DATED,
    series_field="valueDate",
    template={"tntInstId": TENANT, "status": ["ACTIVE", "INACTIVE"]},
    scope_options=(
        ScopeOption(
            "date",
            "date",
            f"Business date of the holdings snapshot. {_DATE_FMT}",
            required=True,
            date=True,
            window="both",
        ),
    ),
    filters=(
        ("currency", "currency"),
        ("product_code", "productCode"),
    ),
    table_columns=(
        "investmentNo",
        "productCode",
        "amount",
        "currency",
        "valueDate",
        "expiryDate",
        "status",
    ),
    notes=(
        "The status filter [ACTIVE, INACTIVE] is the live-verified fixed"
        " scope. Holdings detail uses the native investmentNo as orderId.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

INVESTMENT_TRANSACTIONS = ListSpec(
    path=("investment", "transactions"),
    kind=RUNTIMES,
    title="investment transactions",
    endpoint="/queryIncrementOrderList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("orderId",),
    profile=PROFILE_HISTORY,
    template={"tntInstId": TENANT},
    filters=(("currency", "currency"), ("product_code", "productCode")),
    table_columns=(
        "orderId",
        "productCode",
        "transactionType",
        "amount",
        "currency",
        "transactionDate",
        "orderStatus",
    ),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

INVESTMENT_INTEREST_RATES = ListSpec(
    path=("investment", "interest-rates"),
    kind=RUNTIMES,
    title="market base interest rates",
    endpoint="/incrementBaseRateList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("currency", "rateName", "ratePeriod", "effectiveDate"),
    profile=PROFILE_DATED,
    series_field="effectiveDate",
    template={"tntInstId": TENANT, "currency": [], "productTerm": [], "isPage": "Y"},
    scope_options=(
        ScopeOption(
            "source",
            "source",
            "Rate source; only the market base-rate route is verified. The"
            " bank-quoted route stays deferred (empty tested scopes).",
            required=True,
            choices=("market",),
            virtual=True,
            match="market",
        ),
        _timezone(),
        *_window("beginDate", "endDate"),
    ),
    filters=(("currency", "currency"),),
    table_columns=(
        "rateName",
        "currency",
        "ratePeriod",
        "rateValue",
        "effectiveDate",
        "rateProvide",
    ),
    notes=(
        "Only the market base-rate route is registered; the bank-quoted"
        " route returned empty tested scopes and stays deferred.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

INVESTMENT_COMPOUND_LEDGER = ListSpec(
    path=("investment", "compound-ledger"),
    kind=RUNTIMES,
    title="compound investment orders",
    endpoint="/compoundOrderList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("orderNo",),
    profile=PROFILE_HISTORY,
    template={"tntInstId": TENANT},
    table_columns=(
        "orderNo",
        "portfolioStrategyName",
        "portfolioAmount",
        "currency",
        "valueDate",
        "expireDate",
        "orderStatus",
    ),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

INVESTMENT_RETURNS_ACCRUAL = ListSpec(
    path=("investment", "returns"),
    kind=RUNTIMES,
    title="accrual investment returns",
    endpoint="/accrualBaseList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("investmentNo", "transactionDate"),
    profile=PROFILE_DATED,
    series_field="transactionDate",
    template={"tntInstId": TENANT, "transactionId": []},
    scope_options=(
        ScopeOption(
            "basis",
            "basis",
            "Return basis: accrual or cash route.",
            required=True,
            choices=("accrual", "cash"),
            virtual=True,
            match="accrual",
        ),
        _timezone(),
        *_window("queryBeginTime", "queryEndTime"),
    ),
    table_columns=(
        "investmentNo",
        "productCode",
        "interestAmount",
        "interestRate",
        "currency",
        "transactionDate",
    ),
    notes=(
        "Record schema is live-verified on a populated previous-day scope.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

INVESTMENT_RETURNS_CASH = ListSpec(
    path=("investment", "returns"),
    kind=RUNTIMES,
    title="cash investment returns",
    endpoint="/cashBaseList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("transactionId",),
    profile=PROFILE_DATED,
    series_field="settlementDate",
    template={
        "tntInstId": TENANT,
        "postingDateBegin": "",
        "postingDateEnd": "",
    },
    scope_options=(
        ScopeOption(
            "basis",
            "basis",
            "Return basis: accrual or cash route.",
            required=True,
            choices=("accrual", "cash"),
            virtual=True,
            match="cash",
        ),
        _timezone(),
        *_window("settlementDateBegin", "settlementDateEnd"),
    ),
    table_columns=(
        "transactionId",
        "productCode",
        "principalAmount",
        "interestIncome",
        "currency",
        "settlementDate",
    ),
    notes=(
        "Record schema is live-verified on a populated previous-day scope;"
        " the posting-date filters are the verified empty strings.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

RISK_METRICS = ListSpec(
    path=("risk", "metrics"),
    kind=RUNTIMES,
    title="risk metric values",
    endpoint="/api/metric/manyMetricQuery.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data",),
    total=None,
    pagination=PAGE_SINGLE,
    paged_request=False,
    identity=("id",),
    profile=PROFILE_HISTORY,
    template={"tntInstId": TENANT},
    scope_options=(
        ScopeOption(
            "metric",
            "metricName",
            "Metric name; the two live-verified populated metrics.",
            required=True,
            choices=("CONCENTRATION_RATE", "CREDIT_USAGE_RATE"),
        ),
    ),
    table_columns=("metricName", "metricLabel", "value", "reportDate", "reportTime"),
    notes=(
        "No reported total exists; the single response is the complete"
        " metric series. Single-metric and open-balance routes returned"
        " envelope-only evidence and stay deferred; CURRENCY_T3_LCR was"
        " empty in every tested scope.",
        _NULL_NOTE,
    ),
)

LEDGER_BALANCES = ListSpec(
    path=("ledger", "balances"),
    kind=RUNTIMES,
    title="ledger balances",
    endpoint="/balanceBookquery.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("accountNo", "currency", "valueDate", "accountingDate"),
    profile=PROFILE_DATED,
    series_field="valueDate",
    template={
        "tntInstId": TENANT,
        "accountingStartDate": "",
        "accountingEndDate": "",
        "parentCustomerNo": None,
    },
    scope_options=(
        ScopeOption(
            "book_type",
            "bookType",
            "Ledger book type.",
            required=True,
            choices=("INNER", "OUTER"),
        ),
        _timezone(),
        *_window("valueDateStart", "valueDateEnd"),
    ),
    filters=(("currency", "currency"),),
    table_columns=(
        "accountNo",
        "customerName",
        "closeBalance",
        "currency",
        "valueDate",
        "accountingDate",
    ),
    notes=(
        "The window filters the valueDate dimension; the accounting-date"
        " filters stay at their verified empty strings.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

PRICING_CLIENT_PRICES = ListSpec(
    path=("pricing", "client-prices"),
    kind=RUNTIMES,
    title="client prices",
    endpoint="/getClientPriceList.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    total=("result", "count"),
    identity=("id",),
    profile=PROFILE_DATED,
    series_field="costDate",
    vo_field="clientPriceQueryVO",
    template={
        "tntInstId": TENANT,
        "clientPriceQueryVO": {"status": ["DEPRECATED", "WAIT_FOR_AUDIT", "DRAFT"]},
    },
    scope_options=_window("startCostDate", "endCostDate"),
    table_columns=(
        "id",
        "customerName",
        "customerNo",
        "rate",
        "pricingCurrency",
        "costDate",
        "status",
    ),
    notes=(
        "The status filter [DEPRECATED, WAIT_FOR_AUDIT, DRAFT] is the"
        " live-verified populated scope; ACTIVATED stayed empty in every"
        " tested scope and is not exposed. Record schema is live-verified"
        " on a populated previous-day scope.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

PRICING_COST_PRICES = ListSpec(
    path=("pricing", "cost-prices"),
    kind=RUNTIMES,
    title="cost prices",
    endpoint="/costPriceList.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("id",),
    profile=PROFILE_DATED,
    series_field="costDate",
    vo_field="costPriceQueryVO",
    template={"tntInstId": TENANT, "costPriceQueryVO": {}},
    scope_options=_window("costStartDate", "costEndDate"),
    table_columns=(
        "id",
        "serviceType",
        "period",
        "value",
        "currency",
        "costDate",
        "version",
    ),
    notes=(
        "Record schema is live-verified on a populated previous-day scope.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

PRICING_FACTOR_VALUES = ListSpec(
    path=("pricing", "factor-values"),
    kind=RUNTIMES,
    title="pricing factor values",
    endpoint="/costFactorList.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("id",),
    profile=PROFILE_DATED,
    series_field="costDate",
    vo_field="costFactorQueryVO",
    template={"tntInstId": TENANT, "costFactorQueryVO": {}},
    scope_options=_window("costStartDate", "costEndDate"),
    table_columns=(
        "id",
        "factorType",
        "indicator",
        "value",
        "currency",
        "costDate",
        "version",
    ),
    notes=(
        "Record schema is live-verified on a populated previous-day scope.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

# --- settings leaf specifications ----------------------------------------

INVESTMENT_PRODUCTS = ListSpec(
    path=("investment", "products"),
    kind=SETTINGS,
    title="liquidity product definitions",
    endpoint="/incrementProductsPage.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("incrementProductId",),
    pagination=PAGE_SINGLE,
    profile=PROFILE_SNAPSHOT,
    template={"tntInstId": TENANT},
    filters=(
        ("currency", "currency"),
        ("bank", "bankId"),
        ("status", "status"),
    ),
    table_columns=(
        "incrementProductId",
        "incrementProductCode",
        "incrementProductName",
        "currency",
        "bankId",
        "status",
        "version",
    ),
    notes=(
        "Single-response route: requests at offsets 0 and 10 returned the"
        " same complete 908-row set on 2026-10-01; the response must cover"
        " the reported total. Product definitions are settings, including"
        " their configured interest rules and versions.",
        _NULL_NOTE,
    ),
)

INVESTMENT_STRATEGIES = ListSpec(
    path=("investment", "strategies"),
    kind=SETTINGS,
    title="investment strategy rules",
    endpoint="/queryIncrementStrategyRuleList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("strategyRuleCode",),
    profile=PROFILE_SNAPSHOT,
    template={"tntInstId": TENANT, "timeZone": "GMT+08"},
    table_columns=("strategyRuleCode", "status", "marketExpectation", "gmtModified"),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

INVESTMENT_BENCHMARKS = ListSpec(
    path=("investment", "benchmarks"),
    kind=SETTINGS,
    title="strategy benchmark rules",
    endpoint="/queryStrategyBenchmarkRuleList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("id",),
    profile=PROFILE_SNAPSHOT,
    template={
        "tntInstId": TENANT,
        "timeZone": "GMT+08",
        "valueDateStart": "",
        "valueDateEnd": "",
    },
    table_columns=(
        "id",
        "strategyBenchmarkType",
        "value",
        "valueType",
        "currency",
        "effectiveDate",
    ),
    notes=(
        "The value-date filters stay at their verified empty strings.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

RISK_THRESHOLDS = ListSpec(
    path=("risk", "thresholds"),
    kind=SETTINGS,
    title="risk event thresholds",
    endpoint="/api/risk/benchmark/riskEventBenchmarkQuery.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("benchmarkId",),
    profile=PROFILE_SNAPSHOT,
    template={"tntInstId": TENANT},
    table_columns=("benchmarkId", "riskEventType", "status", "version", "gmtModified"),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

RULES_FUNDING = ListSpec(
    path=("rules", "funding"),
    kind=SETTINGS,
    title="funding action relations",
    endpoint="/fundRiskActionRelationQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("id",),
    profile=PROFILE_SNAPSHOT,
    vo_field="fundRiskActionRelationQueryVO",
    template={
        "tntInstId": TENANT,
        "fundRiskActionRelationQueryVO": {"tntInstId": TENANT},
    },
    table_columns=(
        "id",
        "relationName",
        "fundInstId",
        "status",
        "effectiveness",
        "version",
    ),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

RULES_OPERATION = ListSpec(
    path=("rules", "operation"),
    kind=SETTINGS,
    title="operation rules",
    endpoint="/riskActionRuleListQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("ruleId",),
    profile=PROFILE_SNAPSHOT,
    vo_field="riskActionRuleListQueryVO",
    template={"tntInstId": TENANT, "riskActionRuleListQueryVO": {"tntInstId": TENANT}},
    filters=(("status", "ruleStatus"),),
    table_columns=("ruleId", "ruleName", "riskActionType", "ruleStatus", "version"),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

RULES_REALTIME = ListSpec(
    path=("rules", "realtime"),
    kind=SETTINGS,
    title="realtime rules",
    endpoint="/api/realtime/rule/getAll.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("id",),
    profile=PROFILE_SNAPSHOT,
    table_columns=("id", "ruleName", "aliasName", "currency", "runStatus", "version"),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

RULES_ACTION_MAPPING = ListSpec(
    path=("rules", "action-mapping"),
    kind=SETTINGS,
    title="client agreement action mappings",
    endpoint="/clientAgreementConfigQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("id",),
    profile=PROFILE_SNAPSHOT,
    vo_field="clientAgreementConfigQueryVO",
    template={
        "tntInstId": TENANT,
        "clientAgreementConfigQueryVO": {"tntInstId": TENANT},
    },
    table_columns=("id", "bizType", "bizDirection", "fundActionName", "status"),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

RULES_FX_SETTLEMENT = ListSpec(
    path=("rules", "fx-settlement"),
    kind=SETTINGS,
    title="FX settlement account rules",
    endpoint="/fxBankAccountConfigQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("id",),
    profile=PROFILE_SNAPSHOT,
    vo_field="fxBankAccountPropertyConfigQueryVO",
    template={
        "tntInstId": TENANT,
        "fxBankAccountPropertyConfigQueryVO": {"tntInstId": TENANT},
    },
    filters=(("currency", "currency"),),
    table_columns=(
        "id",
        "accountNo",
        "bankId",
        "currency",
        "direction",
        "status",
        "runStatus",
    ),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

RULES_NOTIFICATION = ListSpec(
    path=("rules", "notification"),
    kind=SETTINGS,
    title="notification rules",
    endpoint="/messageNoticeConfigQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("id",),
    profile=PROFILE_SNAPSHOT,
    vo_field="messageNoticeConfigQueryVO",
    template={"tntInstId": TENANT, "messageNoticeConfigQueryVO": {"tntInstId": TENANT}},
    table_columns=("id", "configName", "moduleCode", "operateType", "used"),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

RULES_FORECAST = ListSpec(
    path=("rules", "forecast"),
    kind=SETTINGS,
    title="forecast rules",
    endpoint="/bankCashForecastRuleQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("ruleId",),
    profile=PROFILE_SNAPSHOT,
    vo_field="bankCashForecastRuleQueryVO",
    template={
        "tntInstId": TENANT,
        "bankCashForecastRuleQueryVO": {"tntInstId": TENANT, "instId": ["Z21"]},
    },
    table_columns=(
        "ruleId",
        "ruleName",
        "ruleType",
        "accountNo",
        "currency",
        "ruleStatus",
    ),
    notes=(
        "The instId filter [Z21] is the live-verified fixed scope.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

RULES_WATERLEVEL = ListSpec(
    path=("rules", "waterlevel"),
    kind=SETTINGS,
    title="water level buffer rules",
    endpoint="/bankAccountBufferQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("bufferId",),
    profile=PROFILE_SNAPSHOT,
    vo_field="bankAccountBufferQueryVO",
    template={
        "tntInstId": TENANT,
        "bankAccountBufferQueryVO": {
            "tntInstId": TENANT,
            "startCreditDate": None,
            "endCreditDate": None,
        },
    },
    filters=(("currency", "currency"),),
    table_columns=(
        "bufferId",
        "aliasName",
        "currency",
        "sumBuffer",
        "status",
        "version",
    ),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

NETWORK_BANK_BASELINES = ListSpec(
    path=("network", "bank-baselines"),
    kind=SETTINGS,
    title="bank account baselines",
    endpoint="/bankAccountBaseLineQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    total=("count",),
    identity=("aliasName",),
    profile=PROFILE_SNAPSHOT,
    vo_field="bankAccountBaseLineQuery",
    template={"tntInstId": TENANT, "bankAccountBaseLineQuery": {"tntInstId": TENANT}},
    filters=(
        ("currency", "currency"),
        ("bank", "bankId"),
        ("status", "status"),
    ),
    table_columns=(
        "aliasName",
        "bankId",
        "currency",
        "accountType",
        "status",
        "timeZone",
    ),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

NETWORK_ACCOUNT_CAPABILITIES = ListSpec(
    path=("network", "account-capabilities"),
    kind=SETTINGS,
    title="account service capabilities",
    endpoint="/serviceInfoQuery.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("id",),
    profile=PROFILE_SNAPSHOT,
    template={"tntInstId": TENANT},
    table_columns=(
        "id",
        "aliasName",
        "businessName",
        "currency",
        "status",
        "runStatus",
    ),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

PRICING_STRATEGIES = ListSpec(
    path=("pricing", "strategies"),
    kind=SETTINGS,
    title="pricing strategies",
    endpoint="/pricingStrategyQuery.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("id",),
    profile=PROFILE_SNAPSHOT,
    template={"tntInstId": TENANT, "status": ["valid", "pause"]},
    table_columns=(
        "id",
        "customerName",
        "customerNo",
        "serviceType",
        "status",
        "period",
    ),
    notes=(
        "The status filter [valid, pause] is the live-verified fixed scope.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

REFERENCE_ENTITIES = ListSpec(
    path=("reference", "entities"),
    kind=SETTINGS,
    title="maintained entity information",
    endpoint="/entityMaintQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "entityMaintVOList"),
    total=("count",),
    identity=("id",),
    profile=PROFILE_SNAPSHOT,
    vo_field="entityMaintQueryVO",
    template={"tntInstId": TENANT, "entityMaintQueryVO": {"tntInstId": TENANT}},
    table_columns=("id", "instId", "instName", "instCode", "state"),
    notes=(
        "Maintained entity information is a settings leaf, consistent with"
        " the live-source correction of 2026-10-01.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

# --- reference leaf specifications ----------------------------------------

CASH_ACCOUNTS = ListSpec(
    path=("cash", "accounts"),
    kind=REFERENCE,
    title="cash accounts",
    endpoint="/queryintnalbkactlist.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "bankAccountPropertyVOList"),
    total=("count",),
    identity=("id",),
    profile=PROFILE_SNAPSHOT,
    vo_field="bankAccountQueryVO",
    template={
        "tntInstId": TENANT,
        "bankAccountQueryVO": {"tntInstId": TENANT},
        "wallet": False,
    },
    filters=(
        ("currency", "currency"),
        ("bank", "bankId"),
        ("status", "status"),
        ("account_no", "accountNo"),
        ("alias", "aliasName"),
    ),
    table_columns=(
        "id",
        "aliasName",
        "accountNo",
        "bankId",
        "currency",
        "accountType",
        "status",
    ),
    notes=(
        "The wallet flag stays at its verified false; wallet membership is"
        " not established and no wallet filter is exposed.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

LEDGER_CUSTOMERS = ListSpec(
    path=("ledger", "customers"),
    kind=REFERENCE,
    title="ledger customers",
    endpoint="/bookCustomer/queryList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("customerNo", "version"),
    profile=PROFILE_SNAPSHOT,
    template={"tntInstId": TENANT, "timeZone": "GMT+08", "parentCustomerNo": None},
    table_columns=("customerNo", "customerName", "customerLevel", "status", "version"),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

LEDGER_ACCOUNTS = ListSpec(
    path=("ledger", "accounts"),
    kind=REFERENCE,
    title="ledger accounts",
    endpoint="/bookCustomerAccount/queryList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("accountNo", "bookType", "currency"),
    profile=PROFILE_SNAPSHOT,
    template={"tntInstId": TENANT, "timeZone": "GMT+08", "parentCustomerNo": None},
    scope_options=(
        ScopeOption(
            "book_type",
            "bookType",
            "Ledger book type.",
            required=True,
            choices=("INNER", "OUTER"),
        ),
    ),
    filters=(("currency", "currency"),),
    table_columns=("accountNo", "customerName", "bookType", "currency", "status"),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

REFERENCE_BANKS = ListSpec(
    path=("reference", "banks"),
    kind=REFERENCE,
    title="banks",
    endpoint="/queryParaBank.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "bankVoList"),
    total=("count",),
    identity=("bankId",),
    profile=PROFILE_SNAPSHOT,
    vo_field="paraBankVO",
    template={"tntInstId": TENANT, "paraBankVO": {"tntInstId": TENANT}},
    filters=(("country", "cityCode"),),
    table_columns=("bankId", "bankName", "bankSwiftCode", "cityCode", "state"),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

REFERENCE_BUSINESS_LINES = ListSpec(
    path=("reference", "business-lines"),
    kind=REFERENCE,
    title="business lines",
    endpoint="/bankAccountBusinessLineQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    identity=("id",),
    profile=PROFILE_SNAPSHOT,
    vo_field="bankAccountBusinessLineQueryVO",
    template={
        "tntInstId": TENANT,
        "bankAccountBusinessLineQueryVO": {"tntInstId": TENANT},
    },
    filters=(("currency", "currency"),),
    table_columns=(
        "id",
        "aliasName",
        "accountNo",
        "bankId",
        "businessLine",
        "currency",
    ),
    notes=(_PAGE_ECHO_NOTE, _NULL_NOTE),
)

REFERENCE_CALENDARS = ListSpec(
    path=("reference", "calendars"),
    kind=REFERENCE,
    title="calendars",
    endpoint="/queryCalendars.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    total=("count",),
    identity=("calendarBaseId",),
    profile=PROFILE_SNAPSHOT,
    vo_field="calendarQuery",
    template={
        "tntInstId": TENANT,
        "calendarQuery": {
            "tntInstId": TENANT,
            "calendarType": "ALL",
            "years": [],
            "months": [],
            "days": [],
        },
    },
    table_columns=(
        "calendarBaseId",
        "calendarName",
        "calendarType",
        "year",
        "countryCode",
        "currencyCode",
    ),
    notes=(
        "Nested day lists make individual records large; the record count,"
        " not the payload size, is the primary coverage measure.",
        _PAGE_ECHO_NOTE,
        _NULL_NOTE,
    ),
)

LIST_SPECS: tuple[ListSpec, ...] = (
    CASH_ACCOUNTS,
    CASH_WATERLEVELS,
    CASH_STATEMENTS_INTRADAY,
    FORECAST_CASHFLOWS,
    FORECAST_ADJUSTMENTS,
    OPERATIONS_FORWARDS,
    OPERATIONS_ASSET_TRADES,
    OPERATIONS_PREFUNDS,
    INVESTMENT_PRODUCTS,
    INVESTMENT_HOLDINGS,
    INVESTMENT_TRANSACTIONS,
    INVESTMENT_INTEREST_RATES,
    INVESTMENT_STRATEGIES,
    INVESTMENT_BENCHMARKS,
    INVESTMENT_COMPOUND_LEDGER,
    INVESTMENT_RETURNS_ACCRUAL,
    INVESTMENT_RETURNS_CASH,
    RISK_METRICS,
    RISK_THRESHOLDS,
    RULES_FUNDING,
    RULES_OPERATION,
    RULES_REALTIME,
    RULES_ACTION_MAPPING,
    RULES_FX_SETTLEMENT,
    RULES_NOTIFICATION,
    RULES_FORECAST,
    RULES_WATERLEVEL,
    NETWORK_BANK_BASELINES,
    NETWORK_ACCOUNT_CAPABILITIES,
    PRICING_CLIENT_PRICES,
    PRICING_COST_PRICES,
    PRICING_FACTOR_VALUES,
    PRICING_STRATEGIES,
    LEDGER_CUSTOMERS,
    LEDGER_ACCOUNTS,
    LEDGER_BALANCES,
    REFERENCE_BANKS,
    REFERENCE_BUSINESS_LINES,
    REFERENCE_CALENDARS,
    REFERENCE_ENTITIES,
)

# --- detail/history specifications -----------------------------------------

DETAIL_SPECS: tuple[DetailSpec, ...] = (
    DetailSpec(
        path=("operations", "decisions"),
        action="get",
        kind=RUNTIMES,
        title="operation decision detail",
        endpoint="/api/ai/decision/report/getDetail.json",
        method="POST",
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "id", "id", "Decision report id from the list.", "int", "id"
            ),
        ),
        list_leaf=("operations", "decisions"),
        notes=("The decision list stays deferred; acquire details by id.",),
    ),
    DetailSpec(
        path=("operations", "decisions"),
        action="history",
        kind=RUNTIMES,
        title="operation decision history",
        endpoint="/api/ai/decision/report/getHistory.json",
        method="POST",
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "id", "id", "Decision report id from the list.", "int", "id"
            ),
        ),
        list_leaf=("operations", "decisions"),
    ),
    DetailSpec(
        path=("operations", "transfers"),
        action="get",
        kind=RUNTIMES,
        title="transfer order detail",
        endpoint="/transferOrderQueryDetail.json",
        method="POST",
        encoding=ENC_FORM,
        envelope=ENV_BASE_RESULT,
        container=("baseResult", "data"),
        identity=(
            IdentityOption(
                "order_no", "orderNo", "Transfer order number.", "str", "orderNo"
            ),
        ),
        list_leaf=("operations", "transfers"),
        notes=("The transfer list stays deferred; acquire details by orderNo.",),
    ),
    DetailSpec(
        path=("operations", "forwards"),
        action="get",
        kind=RUNTIMES,
        title="forward order detail",
        endpoint="/forwardOrderDetail.json",
        method="POST",
        encoding=ENC_FORM,
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "order_no",
                "forwardId",
                "Forward order number; sent as forwardId.",
                "str",
                "orderNo",
            ),
        ),
        list_leaf=("operations", "forwards"),
    ),
    DetailSpec(
        path=("operations", "prefunds"),
        action="get",
        kind=RUNTIMES,
        title="pre-funding order detail",
        endpoint="/queryPreFundingOrderDetail.json",
        method="GET",
        envelope=ENV_RESULT_FLAG,
        container=("result", "data"),
        identity=(
            IdentityOption(
                "id", "preFundingId", "Pre-funding id from the list.", "str", "id"
            ),
        ),
        list_leaf=("operations", "prefunds"),
    ),
    DetailSpec(
        path=("investment", "products"),
        action="get",
        kind=SETTINGS,
        title="product definition detail",
        endpoint="/incrementProductDetail.json",
        method="POST",
        encoding=ENC_FORM,
        envelope=ENV_SUCCESS,
        container=("data",),
        tenant_field=True,
        identity=(
            IdentityOption(
                "product_id",
                "incrementProductId",
                "Product id from the list.",
                "str",
                "incrementProductId",
            ),
        ),
        list_leaf=("investment", "products"),
    ),
    DetailSpec(
        path=("investment", "products"),
        action="history",
        kind=SETTINGS,
        title="product definition version history",
        endpoint="/incrementProductHistoryQuery.json",
        method="POST",
        encoding=ENC_FORM,
        envelope=ENV_SUCCESS,
        container=("data",),
        tenant_field=True,
        container_list=True,
        echo_list_field="incrementProductCode",
        identity=(
            IdentityOption(
                "product_code",
                "incrementProductCode",
                "Product code from the list.",
                "str",
                "incrementProductCode",
            ),
        ),
        list_leaf=("investment", "products"),
        notes=(
            "Configuration versions are settings history, not runtime observations.",
        ),
    ),
    DetailSpec(
        path=("investment", "holdings"),
        action="get",
        kind=RUNTIMES,
        title="holding detail",
        endpoint="/queryIncrementOrderDetail.json",
        method="POST",
        encoding=ENC_FORM,
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "investment_no",
                "orderId",
                "Native investmentNo; sent as orderId.",
                "str",
                "orderId",
            ),
        ),
        list_leaf=("investment", "holdings"),
    ),
    DetailSpec(
        path=("investment", "transactions"),
        action="get",
        kind=RUNTIMES,
        title="investment transaction detail",
        endpoint="/queryIncrementOrderDetail.json",
        method="POST",
        encoding=ENC_FORM,
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "order_id",
                "orderId",
                "Order id from the transaction list.",
                "str",
                "orderId",
            ),
        ),
        list_leaf=("investment", "transactions"),
    ),
    DetailSpec(
        path=("investment", "compound-ledger"),
        action="get",
        kind=RUNTIMES,
        title="compound order detail",
        endpoint="/compoundOrderDetail.json",
        method="POST",
        encoding=ENC_FORM,
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "order_no",
                "compoundOrderNo",
                "Native orderNo; sent as compoundOrderNo.",
                "str",
                "orderNo",
            ),
        ),
        list_leaf=("investment", "compound-ledger"),
    ),
    DetailSpec(
        path=("investment", "strategies"),
        action="get",
        kind=SETTINGS,
        title="strategy rule detail",
        endpoint="/queryIncrementStrategyRuleDetail.json",
        method="POST",
        encoding=ENC_FORM,
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "strategy_rule_code",
                "strategyRuleCode",
                "Strategy rule code from the list.",
                "str",
                "strategyRuleCode",
            ),
        ),
        list_leaf=("investment", "strategies"),
    ),
    DetailSpec(
        path=("risk", "thresholds"),
        action="get",
        kind=SETTINGS,
        title="risk threshold detail",
        endpoint="/api/risk/benchmark/riskEventBenchmarkDetailDetail.json",
        method="POST",
        encoding=ENC_FORM,
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "benchmark_id",
                "benchmarkId",
                "Benchmark id from the list.",
                "str",
                "benchmarkId",
            ),
        ),
        list_leaf=("risk", "thresholds"),
    ),
    DetailSpec(
        path=("risk", "sla"),
        action="get",
        kind=SETTINGS,
        title="risk SLA configuration detail",
        endpoint="/api/risk/sla/slaConfigDetailQuery.json",
        method="POST",
        encoding=ENC_FORM,
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "sla_config_id",
                "slaConfigId",
                "SLA configuration id.",
                "str",
                "slaConfigId",
            ),
        ),
        list_leaf=("risk", "sla"),
        notes=("The SLA list stays deferred; acquire details by slaConfigId.",),
    ),
    DetailSpec(
        path=("rules", "transfer"),
        action="get",
        kind=SETTINGS,
        title="transfer rule detail",
        endpoint="/queryTransferRuleDetail.json",
        method="GET",
        envelope=ENV_RESULT_SUCCESS,
        container=("result", "transferRuleVO"),
        identity=(
            IdentityOption("rule_id", "ruleId", "Transfer rule id.", "str", "ruleId"),
        ),
        list_leaf=("rules", "transfer"),
        notes=("The transfer-rule list stays deferred; acquire details by ruleId.",),
    ),
    DetailSpec(
        path=("rules", "operation"),
        action="get",
        kind=SETTINGS,
        title="operation rule detail",
        endpoint="/riskActionRuleDetail.json",
        method="GET",
        envelope=ENV_RESULT_FLAG,
        container=("result", "data"),
        identity=(
            IdentityOption(
                "rule_id", "ruleId", "Operation rule id from the list.", "str", "ruleId"
            ),
        ),
        list_leaf=("rules", "operation"),
    ),
    DetailSpec(
        path=("rules", "realtime"),
        action="get",
        kind=SETTINGS,
        title="realtime rule detail",
        endpoint="/api/realtime/rule/getDetail.json",
        method="POST",
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "id",
                "Id",
                "Realtime rule id; sent as the capital native parameter Id.",
                "str",
                "id",
            ),
        ),
        list_leaf=("rules", "realtime"),
    ),
    DetailSpec(
        path=("rules", "notification"),
        action="get",
        kind=SETTINGS,
        title="notification rule detail",
        endpoint="/messageNoticeConfigDetail.json",
        method="GET",
        envelope=ENV_RESULT_FLAG,
        container=("result", "data"),
        identity=(
            IdentityOption(
                "id", "id", "Notification configuration id from the list.", "str", "id"
            ),
        ),
        list_leaf=("rules", "notification"),
    ),
    DetailSpec(
        path=("rules", "waterlevel"),
        action="get",
        kind=SETTINGS,
        title="water level rules of one account",
        endpoint="/bankAccountBufferListByAliasName.json",
        method="GET",
        envelope=ENV_RESULT_FLAG,
        container=("result", "dataValue"),
        container_list=True,
        echo_list_field="aliasName",
        identity=(
            IdentityOption(
                "account",
                "aliasName",
                "Account alias from the waterlevel list.",
                "str",
                "aliasName",
            ),
        ),
        list_leaf=("rules", "waterlevel"),
        notes=(
            "The detail payload is the account's buffer row list; the"
            " envelope's count=0 never means the detail is absent.",
        ),
    ),
    DetailSpec(
        path=("network", "bank-baselines"),
        action="get",
        kind=SETTINGS,
        title="bank account baseline detail",
        endpoint="/bankAccountBaseLineDetail.json",
        method="GET",
        envelope=ENV_RESULT_FLAG,
        container=("result", "data"),
        identity=(
            IdentityOption(
                "account",
                "aliasName",
                "Account alias from the baseline list.",
                "str",
                "aliasName",
            ),
        ),
        list_leaf=("network", "bank-baselines"),
    ),
    DetailSpec(
        path=("network", "account-capabilities"),
        action="get",
        kind=SETTINGS,
        title="account service capability detail",
        endpoint="/serviceInfoDetail.json",
        method="POST",
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption("id", "id", "Service info id from the list.", "int", "id"),
        ),
        list_leaf=("network", "account-capabilities"),
    ),
    DetailSpec(
        path=("ledger", "customers"),
        action="get",
        kind=REFERENCE,
        title="ledger customer detail",
        endpoint="/bookCustomer/detail.json",
        method="GET",
        envelope=ENV_SUCCESS,
        container=("data",),
        identity=(
            IdentityOption(
                "customer_no",
                "customerNo",
                "Customer number from the list.",
                "str",
                "customerNo",
            ),
            IdentityOption(
                "version",
                "version",
                "Customer version from the list; required compound identity,"
                " not echoed by the detail.",
                "str",
                None,
            ),
        ),
        list_leaf=("ledger", "customers"),
    ),
)

# --- deferrals with evidence ------------------------------------------------

# Short status reasons from the #71 audit ("Deferred boundaries"); the full
# per-leaf evidence lives in docs/research/general/2026-10-01-liquidity-live-probes.md.
_FAILED = "business failure or transport timeout in the audited scope"
_EMPTY = (
    "query succeeded only for tested dates/scopes; row schema and identity unverified"
)
_UNVERIFIED = (
    "no verified independent native contract (caller, safe payload and identity)"
)
_IDENTITY = (
    "native getter reviewed, but no usable observed parent row with its typed identity"
)
_PROJECTION = "mixed native response needs validated settings/runtime projections first"

_AUDIT_DEFERRED: tuple[DeferredLeaf, ...] = (
    DeferredLeaf(
        ("cash", "accounts", "get"), REFERENCE, "failed", f"Account detail: {_FAILED}."
    ),
    DeferredLeaf(
        ("cash", "statements", "end-of-day", "list"),
        RUNTIMES,
        "empty-scope",
        f"End-of-day statements: {_EMPTY}.",
    ),
    DeferredLeaf(
        ("cash", "groups", "list"),
        SETTINGS,
        "projection-pending",
        f"Account groups: {_PROJECTION}.",
    ),
    DeferredLeaf(
        ("cash", "groups", "get"),
        SETTINGS,
        "unverified",
        f"Account group detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("cash", "group-balances", "list"),
        RUNTIMES,
        "projection-pending",
        f"Group balances: {_PROJECTION}.",
    ),
    DeferredLeaf(
        ("cash", "wallets", "list"),
        REFERENCE,
        "filter-unverified",
        "Wallets: the native wallet flag returned identical first-page account"
        " data; wallet membership is not established.",
    ),
    DeferredLeaf(
        ("cash", "wallets", "get"),
        REFERENCE,
        "filter-unverified",
        "Wallet detail: wallet membership is not established.",
    ),
    DeferredLeaf(
        ("cash", "wallet-balances", "list"),
        RUNTIMES,
        "unverified",
        f"Wallet balances: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("cash", "pools", "list"),
        SETTINGS,
        "projection-pending",
        f"Cash pools: {_PROJECTION}.",
    ),
    DeferredLeaf(
        ("cash", "pools", "get"),
        SETTINGS,
        "projection-pending",
        f"Cash pool detail: {_PROJECTION}.",
    ),
    DeferredLeaf(
        ("cash", "pool-balances", "list"),
        RUNTIMES,
        "projection-pending",
        f"Pool balances: {_PROJECTION}.",
    ),
    DeferredLeaf(
        ("cash", "credit-lines", "list"),
        SETTINGS,
        "failed",
        f"Credit lines: {_FAILED}.",
    ),
    DeferredLeaf(
        ("cash", "credit-lines", "get"),
        SETTINGS,
        "unverified",
        f"Credit-line detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("cash", "credit-usage", "list"),
        RUNTIMES,
        "unverified",
        f"Credit usage: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("forecast", "results", "get"),
        RUNTIMES,
        "unverified",
        f"Forecast result detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("forecast", "accuracy", "list"),
        RUNTIMES,
        "semantics-pending",
        "Forecast accuracy: populated native query observed, but accuracy"
        " measure and time semantics are not established.",
    ),
    DeferredLeaf(
        ("operations", "demands", "list"),
        RUNTIMES,
        "empty-scope",
        f"Funding demands: {_EMPTY}.",
    ),
    DeferredLeaf(
        ("operations", "demands", "get"),
        RUNTIMES,
        "identity-unavailable",
        f"Demand detail: {_IDENTITY}.",
    ),
    DeferredLeaf(
        ("operations", "executions", "list"),
        RUNTIMES,
        "empty-scope",
        f"Executions: {_EMPTY}.",
    ),
    DeferredLeaf(
        ("operations", "executions", "get"),
        RUNTIMES,
        "identity-unavailable",
        f"Execution detail: {_IDENTITY}.",
    ),
    DeferredLeaf(
        ("operations", "rule-status", "list"),
        RUNTIMES,
        "unverified",
        f"Rule status: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("operations", "swaps", "list"),
        RUNTIMES,
        "empty-scope",
        f"Swap orders: {_EMPTY}.",
    ),
    DeferredLeaf(
        ("operations", "swaps", "get"),
        RUNTIMES,
        "unverified",
        "Swap detail: the UI detail is a local copy of the list row, not a"
        " backend getter.",
    ),
    DeferredLeaf(
        ("operations", "asset-trades", "get"),
        RUNTIMES,
        "unverified",
        f"Asset-trade detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("investment", "offers", "list"),
        RUNTIMES,
        "unverified",
        f"Offers: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("investment", "investable-funds", "list"),
        RUNTIMES,
        "empty-scope",
        f"Investable funds: {_EMPTY}.",
    ),
    DeferredLeaf(
        ("investment", "interest-rates", "get"),
        RUNTIMES,
        "unverified",
        f"Interest-rate detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("investment", "rfqs", "list"), RUNTIMES, "failed", f"RFQs: {_FAILED}."
    ),
    DeferredLeaf(
        ("investment", "rfqs", "get"),
        RUNTIMES,
        "identity-unavailable",
        f"RFQ detail: {_IDENTITY}.",
    ),
    DeferredLeaf(
        ("investment", "quotes", "list"), RUNTIMES, "empty-scope", f"Quotes: {_EMPTY}."
    ),
    DeferredLeaf(
        ("investment", "quotes", "get"),
        RUNTIMES,
        "unverified",
        f"Quote detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("investment", "quote-groups", "get"),
        SETTINGS,
        "failed",
        f"Quote-group detail: {_FAILED}.",
    ),
    DeferredLeaf(
        ("investment", "quote-sessions", "list"),
        RUNTIMES,
        "unverified",
        f"Quote sessions: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("investment", "benchmarks", "get"),
        SETTINGS,
        "unverified",
        f"Benchmark detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("investment", "benchmark-values", "list"),
        RUNTIMES,
        "empty-scope",
        f"Benchmark values: {_EMPTY}.",
    ),
    DeferredLeaf(
        ("investment", "strategy-results", "list"),
        RUNTIMES,
        "empty-scope",
        f"Strategy results: {_EMPTY}.",
    ),
    DeferredLeaf(
        ("investment", "strategy-results", "get"),
        RUNTIMES,
        "identity-unavailable",
        f"Strategy-result detail: {_IDENTITY}.",
    ),
    DeferredLeaf(
        ("risk", "events", "list"), RUNTIMES, "empty-scope", f"Risk events: {_EMPTY}."
    ),
    DeferredLeaf(
        ("risk", "events", "get"),
        RUNTIMES,
        "identity-unavailable",
        f"Risk event detail: {_IDENTITY}.",
    ),
    DeferredLeaf(
        ("risk", "anomalies", "list"),
        RUNTIMES,
        "empty-scope",
        f"Risk anomalies: {_EMPTY}.",
    ),
    DeferredLeaf(
        ("risk", "anomalies", "get"),
        RUNTIMES,
        "identity-unavailable",
        f"Risk anomaly detail: {_IDENTITY}.",
    ),
    DeferredLeaf(
        ("risk", "account-capacity", "list"),
        RUNTIMES,
        "failed",
        f"Per-account capacity: {_FAILED}.",
    ),
    DeferredLeaf(
        ("rules", "treasury-transfer", "list"),
        SETTINGS,
        "failed",
        f"Treasury-transfer rules: {_FAILED} (missing privilege observed).",
    ),
    DeferredLeaf(
        ("rules", "treasury-transfer", "get"),
        SETTINGS,
        "identity-unavailable",
        f"Treasury-transfer rule detail: {_IDENTITY}.",
    ),
    DeferredLeaf(
        ("rules", "funding", "get"),
        SETTINGS,
        "unverified",
        f"Funding relation detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("rules", "action-mapping", "get"),
        SETTINGS,
        "unverified",
        f"Action-mapping detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("rules", "fx-settlement", "get"),
        SETTINGS,
        "unverified",
        f"FX-settlement rule detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("rules", "forecast", "get"),
        SETTINGS,
        "unverified",
        f"Forecast rule detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("rules", "monitoring", "list"),
        SETTINGS,
        "empty-scope",
        f"Monitoring rules: {_EMPTY}.",
    ),
    DeferredLeaf(
        ("rules", "monitoring", "get"),
        SETTINGS,
        "identity-unavailable",
        f"Monitoring rule detail: {_IDENTITY}.",
    ),
    DeferredLeaf(
        ("network", "routes", "list"),
        SETTINGS,
        "unverified",
        "Network routes: route semantics unverified; the verified native"
        " inquiries are network realtime list/get, which must not masquerade"
        " as generic routes.",
    ),
    DeferredLeaf(
        ("network", "routes", "get"),
        SETTINGS,
        "unverified",
        "Network route detail: route semantics unverified.",
    ),
    DeferredLeaf(
        ("network", "realtime", "list"),
        SETTINGS,
        "observed-overlap",
        "Realtime network list: offset pages overlapped exact row objects on"
        " 2026-10-01; complete acquisition is unprovable.",
    ),
    DeferredLeaf(
        ("network", "realtime", "get"),
        SETTINGS,
        "observed-overlap",
        "Realtime network detail: its parent list cannot prove complete coverage.",
    ),
    DeferredLeaf(
        ("network", "product-baselines", "list"),
        SETTINGS,
        "empty-scope",
        f"Product baselines: {_EMPTY}.",
    ),
    DeferredLeaf(
        ("network", "product-baselines", "get"),
        SETTINGS,
        "unverified",
        f"Product baseline detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("ledger", "accounts", "get"),
        REFERENCE,
        "unverified",
        f"Ledger account detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("pricing", "client-prices", "get"),
        RUNTIMES,
        "unverified",
        f"Client-price detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("pricing", "factors", "list"),
        SETTINGS,
        "unverified",
        f"Pricing factors: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("pricing", "factors", "get"),
        SETTINGS,
        "unverified",
        f"Pricing factor detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("pricing", "strategies", "get"),
        SETTINGS,
        "unverified",
        f"Pricing strategy detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("pricing", "valuations", "list"),
        RUNTIMES,
        "empty-scope",
        f"Valuations: {_EMPTY}.",
    ),
    DeferredLeaf(
        ("pricing", "valuations", "get"),
        RUNTIMES,
        "unverified",
        f"Valuation detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("pricing", "bills", "list"), RUNTIMES, "empty-scope", f"Bills: {_EMPTY}."
    ),
    DeferredLeaf(
        ("pricing", "bills", "get"),
        RUNTIMES,
        "unverified",
        f"Bill detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("reference", "entities", "get"),
        SETTINGS,
        "unverified",
        f"Entity detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("reference", "banks", "get"),
        REFERENCE,
        "unverified",
        f"Bank detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("reference", "areas", "list"),
        REFERENCE,
        "partial-permission",
        "Areas: cities and countries queried; province is denied"
        " (ILIQUIDITY_PARA_PROVINCE_QUERY).",
    ),
    DeferredLeaf(
        ("reference", "calendars", "get"),
        REFERENCE,
        "unverified",
        f"Calendar detail: {_UNVERIFIED}.",
    ),
)

_OVERLAP = (
    "offset pages overlapped exact row objects on 2026-10-01; a stable"
    " identity/ordering/convergence contract does not exist, so complete"
    " acquisition is unprovable"
)

_TICKET_DEFERRED: tuple[DeferredLeaf, ...] = (
    DeferredLeaf(
        ("cash", "balances", "list"),
        RUNTIMES,
        "observed-overlap",
        f"Latest balances: {_OVERLAP} (page 2 repeated a page-1 row:"
        " 11 unique of 12 reported).",
    ),
    DeferredLeaf(
        ("forecast", "results", "list"),
        RUNTIMES,
        "observed-overlap",
        f"Forecast results: {_OVERLAP} (page 2 repeated a page-1 row).",
    ),
    DeferredLeaf(
        ("operations", "decisions", "list"),
        RUNTIMES,
        "pagination-unverified",
        "Decision list: populated previous-day scope observed, but no offset"
        " pagination evidence exists and the current-day scope was empty;"
        " complete acquisition is unverified. get/history remain available.",
    ),
    DeferredLeaf(
        ("operations", "transfers", "list"),
        RUNTIMES,
        "pagination-unverified",
        "Transfer list: populated previous-day scope observed, but no offset"
        " pagination evidence exists; complete acquisition is unverified."
        " get remains available.",
    ),
    DeferredLeaf(
        ("risk", "sla", "list"),
        SETTINGS,
        "observed-overlap",
        f"Risk SLA list: {_OVERLAP} (page 2 repeated a page-1 row)."
        " get remains available.",
    ),
    DeferredLeaf(
        ("rules", "transfer", "list"),
        SETTINGS,
        "observed-overlap-no-total",
        f"Transfer-rule list: {_OVERLAP}, and the response reports no total."
        " get remains available.",
    ),
    DeferredLeaf(
        ("investment", "quote-groups", "list"),
        SETTINGS,
        "total-unverified",
        "Quote-group list: 54 rows arrived in one response that reports no"
        " total, and the effect of rowStart is unverified; completeness is"
        " unprovable.",
    ),
)

# Every audited deferred leaf stays discoverable: the seven ticket-level
# deferrals from the 67-candidate catalog plus the rest of the #71 audit.
DEFERRED: tuple[DeferredLeaf, ...] = (*_TICKET_DEFERRED, *_AUDIT_DEFERRED)


# --- leaf registry -----------------------------------------------------------


def _merged_options(variants: tuple[ListSpec, ...]) -> tuple[ScopeOption, ...]:
    merged: dict[str, ScopeOption] = {}
    for variant in variants:
        for option in variant.scope_options:
            merged.setdefault(option.flag, option)
    return tuple(merged.values())


@dataclass(frozen=True)
class ResolvedScope:
    spec: ListSpec
    request_values: dict[str, Any]
    window: tuple[str | None, str | None]
    scope_key: str
    request_scope: str


class ListLeaf:
    """One list leaf, possibly with contract variants behind a virtual option."""

    def __init__(self, variants: tuple[ListSpec, ...]) -> None:
        self.variants = variants
        self.path = variants[0].path
        self.options = _merged_options(variants)
        self._capabilities = {
            id(variant): LiquidityListCapability(variant) for variant in variants
        }

    @property
    def kind(self) -> str:
        return self.variants[0].kind

    @property
    def title(self) -> str:
        return self.variants[0].title

    def capability(self, variant: ListSpec) -> LiquidityListCapability:
        return self._capabilities[id(variant)]

    def resolve(self, provided: dict[str, Any]) -> ResolvedScope:
        candidates = []
        for variant in self.variants:
            matched = True
            for option in variant.scope_options:
                if option.virtual and option.match:
                    raw = provided.get(option.flag)
                    if raw is None and option.default is not None:
                        raw = option.default
                    if raw != option.match:
                        matched = False
            if matched:
                candidates.append(variant)
        if len(candidates) != 1:
            raise CliError(
                INVALID_ARGUMENT,
                "exactly one contract variant must match the scope options",
            )
        variant = candidates[0]
        request_values, window = scope_values(variant.scope_options, provided)
        window_fields = {
            option.field for option in variant.scope_options if option.window
        }
        scope_key = encode_scope(
            {
                field: value
                for field, value in request_values.items()
                if field not in window_fields
            }
        )
        return ResolvedScope(
            spec=variant,
            request_values=request_values,
            window=window,
            scope_key=scope_key,
            request_scope=encode_scope(request_values),
        )


class DetailLeaf:
    def __init__(self, detail_spec: DetailSpec) -> None:
        self.spec = detail_spec
        self.path = (*detail_spec.path, detail_spec.action)
        self.capability = LiquidityDetailCapability(detail_spec)

    @property
    def kind(self) -> str:
        return self.spec.kind


def _build_registry() -> tuple[
    dict[tuple[str, ...], ListLeaf], dict[tuple[str, ...], DetailLeaf]
]:
    grouped: dict[tuple[str, ...], list[ListSpec]] = {}
    for list_spec in LIST_SPECS:
        grouped.setdefault(list_spec.path, []).append(list_spec)
    lists = {path: ListLeaf(tuple(variants)) for path, variants in grouped.items()}
    details = {
        (*detail.path, detail.action): DetailLeaf(detail) for detail in DETAIL_SPECS
    }
    return lists, details


LIST_LEAVES, DETAIL_LEAVES = _build_registry()
DEFERRED_BY_PATH = {leaf.path: leaf for leaf in DEFERRED}


def list_leaf(path: tuple[str, ...]) -> ListLeaf:
    try:
        return LIST_LEAVES[path]
    except KeyError as error:
        raise CliError(
            INVALID_ARGUMENT, f"unknown liquidity leaf: {' '.join(path)}"
        ) from error


def detail_leaf(path: tuple[str, ...]) -> DetailLeaf:
    try:
        return DETAIL_LEAVES[path]
    except KeyError as error:
        raise CliError(
            INVALID_ARGUMENT, f"unknown liquidity leaf: {' '.join(path)}"
        ) from error


# --- help/refresh node builders -----------------------------------------------

QUERY_ERRORS = (
    "INVALID_ARGUMENT",
    "CONFIG_ERROR",
    "CACHE_MISS",
    "CACHE_STALE",
    "INCOMPLETE_RESULT",
    "UNSUPPORTED_CAPABILITY",
    "AUTH_REQUIRED",
    "BROWSER_UNAVAILABLE",
    "LOCKED",
    "TIMEOUT",
    "BUSINESS_QUERY_FAILED",
    "INVALID_RESPONSE",
)

_SCOPE_CONSTRAINTS = (
    "Scope options are source filters: they select what an explicit refresh"
    " acquires and which retained capture a query reads; they never filter"
    " other scopes' caches.",
    "Values marked live-verified were exercised on 2026-10-01; other valid"
    " values pass through with the same verified request shape.",
)


def _option_spec(option: ScopeOption) -> OptionSpec:
    summary = option.summary
    if option.verified:
        summary += f" Live-verified: {option.verified}."
    kind = "append" if option.repeat else "str"
    return OptionSpec(
        option.flag,
        "--" + option.flag.replace("_", "-"),
        summary,
        kind,
        required=option.required,
        default=option.default,
        choices=option.choices,
    )


def _filter_option(flag: str, field: str) -> OptionSpec:
    return opt(flag, f"Exact local match on {field}.", "append")


def list_query_node(leaf: ListLeaf) -> BizNode:
    variant = leaf.variants[0]
    path = ("liquidity", *leaf.path, "list")
    return BizNode(
        path,
        f"List {leaf.title} from the local cache (default) or the backend"
        f" with --live. Kind: {leaf.kind}.",
        options=(
            *(_option_spec(option) for option in leaf.options),
            *(_filter_option(flag, field) for flag, field in variant.filters),
            LIMIT,
            OFFSET,
            ALL,
            LIVE,
            *CACHE_FLAGS,
            FORMAT_TABLE,
            FIELDS,
        ),
        constraints=(
            CACHE_SEMANTICS,
            DISPLAY_WINDOW,
            *_SCOPE_CONSTRAINTS,
            *variant.notes,
        ),
        effects_variants=QUERY_EFFECTS_VARIANTS,
        output=QUERY_OUTPUT,
        kind=leaf.kind,
        errors=QUERY_ERRORS,
        examples=("dogopencli " + " ".join(path),),
        next=("dogopencli help refresh liquidity " + " ".join(leaf.path),),
        handler="cmd_liquidity_list",
    )


def detail_query_node(leaf: DetailLeaf) -> BizNode:
    detail = leaf.spec
    path = ("liquidity", *leaf.path)
    parent = (
        f"dogopencli help liquidity {' '.join(detail.list_leaf)} list"
        if detail.list_leaf is not None
        else None
    )
    return BizNode(
        path,
        f"Show the genuine native {detail.title} from the detail cache"
        f" (default) or the backend with --live; a list row is never"
        f" substituted. Kind: {leaf.kind}.",
        options=(
            *(
                OptionSpec(
                    option.flag,
                    "--" + option.flag.replace("_", "-"),
                    option.summary,
                    "str",
                    required=True,
                )
                for option in detail.identity
            ),
            LIVE,
            *CACHE_FLAGS,
            FORMAT_TABLE,
            FIELDS,
        ),
        constraints=(
            CACHE_SEMANTICS,
            "Offline get reads only the per-object detail cache; a missing"
            " cached detail is a coverage miss with a refresh hint, never"
            " proof that the business object does not exist.",
            *detail.notes,
        ),
        effects_variants=QUERY_EFFECTS_VARIANTS,
        output=QUERY_OUTPUT,
        kind=leaf.kind,
        errors=QUERY_ERRORS,
        examples=("dogopencli " + " ".join(path) + " --help",),
        next=(
            *(() if parent is None else (parent,)),
            "dogopencli help refresh liquidity "
            + " ".join(detail.path)
            + " detail "
            + detail.action,
        ),
        handler="cmd_liquidity_detail",
    )


def refresh_list_node(leaf: ListLeaf) -> BizNode:
    path = ("refresh", "liquidity", *leaf.path)
    return BizNode(
        path,
        f"Refresh the {leaf.title} cache for the given scope through the"
        f" existing CDP session; kind {leaf.kind}. Incomplete acquisition"
        " preserves the previous cache.",
        options=tuple(_option_spec(option) for option in leaf.options),
        constraints=(
            "Requires an existing authenticated CDP session for the liquidity"
            " origin; only the local cache changes.",
            "Progress diagnostics go to stderr; the result envelope goes to stdout.",
            "Retention: at most 1,000,000 primary records per business leaf;"
            " time-series overflow evicts oldest records with a stderr"
            " warning, other overflow rejects the refresh (ADR 0017).",
        ),
        effects=dict(REFRESH_CDP_EFFECTS),
        output=REFRESH_OUTPUT,
        kind=leaf.kind,
        errors=(
            "INVALID_ARGUMENT",
            "CONFIG_ERROR",
            "INVALID_RESPONSE",
            "INCOMPLETE_RESULT",
            "AUTH_REQUIRED",
            "BROWSER_UNAVAILABLE",
            "LOCKED",
            "TIMEOUT",
            "BUSINESS_QUERY_FAILED",
        ),
        examples=("dogopencli " + " ".join(path),),
        next=(f"dogopencli help liquidity {' '.join(leaf.path)} list",),
        handler="cmd_refresh_liquidity_list",
    )


def refresh_detail_node(leaf: DetailLeaf) -> BizNode:
    detail = leaf.spec
    path = ("refresh", "liquidity", *detail.path, "detail", detail.action)
    return BizNode(
        path,
        f"Acquire the genuine native {detail.title} into the per-object"
        " detail cache; independent of list refresh (ADR 0016).",
        options=tuple(
            OptionSpec(
                option.flag,
                "--" + option.flag.replace("_", "-"),
                option.summary,
                "str",
                required=True,
            )
            for option in detail.identity
        ),
        constraints=(
            "Requires an existing authenticated CDP session for the liquidity"
            " origin; only the local cache changes.",
            "A failed detail refresh preserves the prior valid detail and"
            " never invalidates a separately successful list refresh.",
        ),
        effects=dict(REFRESH_CDP_EFFECTS),
        output=REFRESH_OUTPUT,
        kind=leaf.kind,
        errors=(
            "INVALID_ARGUMENT",
            "CONFIG_ERROR",
            "INVALID_RESPONSE",
            "AUTH_REQUIRED",
            "BROWSER_UNAVAILABLE",
            "LOCKED",
            "TIMEOUT",
            "BUSINESS_QUERY_FAILED",
        ),
        examples=(
            "dogopencli "
            + " ".join(path)
            + " "
            + " ".join(
                f"--{option.flag.replace('_', '-')} <{option.flag.upper()}>"
                for option in detail.identity
            ),
        ),
        next=(f"dogopencli help liquidity {' '.join(leaf.path)}",),
        handler="cmd_refresh_liquidity_detail",
    )


def unsupported_node(leaf: DeferredLeaf) -> BizNode:
    path = ("liquidity", *leaf.path)
    return BizNode(
        path,
        f"Unsupported ({leaf.status}): {leaf.reason}",
        constraints=(
            "This audited leaf is deferred; its evidence status is recorded"
            " in issue #71 and docs/research/general/"
            "2026-10-01-liquidity-live-probes.md.",
            "It never returns placeholder or empty datasets. Execution fails"
            " with UNSUPPORTED_CAPABILITY.",
        ),
        output=QUERY_OUTPUT,
        kind=leaf.kind,
        errors=("UNSUPPORTED_CAPABILITY",),
        handler="cmd_liquidity_unsupported",
    )


_GROUP_TITLES: dict[tuple[str, ...], str] = {
    ("cash",): "Cash accounts, balances, statements and water levels.",
    ("cash", "statements"): "Cash statement inquiries.",
    ("forecast",): "Forecast results, cash flows and adjustments.",
    ("operations",): "Liquidity operation orders, decisions and pre-funding.",
    ("investment",): "Investment products, holdings, transactions and returns.",
    ("risk",): "Risk metrics, thresholds and SLA.",
    ("rules",): "Liquidity routing, risk and notification rules.",
    ("network",): "Account network baselines and capabilities.",
    ("ledger",): "Ledger customers, accounts and balances.",
    ("pricing",): "Client/cost prices, factor values and pricing strategies.",
    ("reference",): "Reference banks, business lines, calendars and entities.",
}


def group_nodes() -> tuple[BizNode, ...]:
    """Group nodes for liquidity query and refresh subtrees (deduplicated)."""
    groups: dict[tuple[str, ...], BizNode] = {}

    def add_query_group(path: tuple[str, ...]) -> None:
        full = ("liquidity", *path)
        if full not in groups:
            groups[full] = BizNode(
                full,
                _GROUP_TITLES.get(path, "Liquidity inquiries."),
                next=(f"dogopencli help liquidity {' '.join(path)} list",),
            )

    def add_refresh_group(path: tuple[str, ...]) -> None:
        full = ("refresh", "liquidity", *path)
        if full not in groups:
            groups[full] = BizNode(
                full,
                f"Rebuild {_GROUP_TITLES.get(path, 'liquidity')} caches.",
            )

    list_paths = {list_spec.path for list_spec in LIST_SPECS}
    for list_spec in LIST_SPECS:
        # Query tree: only list/get/history words are executable, so every
        # prefix including the resource itself is a navigation group.
        for depth in range(1, len(list_spec.path) + 1):
            add_query_group(list_spec.path[:depth])
        # Refresh tree: the resource path is the executable list refresh.
        for depth in range(1, len(list_spec.path)):
            add_refresh_group(list_spec.path[:depth])
    for detail in DETAIL_SPECS:
        for depth in range(1, len(detail.path) + 1):
            prefix = detail.path[:depth]
            add_query_group(prefix)
            if depth == len(detail.path) and prefix in list_paths:
                # The executable list refresh node owns this path.
                continue
            add_refresh_group(prefix)
        add_refresh_group((*detail.path, "detail"))
    for leaf in DEFERRED:
        # Deferred paths include their action; every shorter prefix is a
        # navigation group.
        for depth in range(1, len(leaf.path)):
            add_query_group(leaf.path[:depth])
    return tuple(groups.values())
