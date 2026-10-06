"""The liquidity leaf catalog: shipped contracts and evidence-based deferrals.

Every leaf in issue #72's populated candidate catalog appears here exactly
once. Shipped leaves carry the verified contract observed on 2026-10-01
(exact method/path/encoding/payload, envelope, container/total paths, typed
identity, offline profile). Deferred leaves stay discoverable as unsupported
commands whose execution fails with their evidence reason; they never return
placeholder datasets. Evidence:
docs/research/general/2026-10-01-liquidity-live-probes.md.
"""

from dataclasses import dataclass, replace
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
    contract,
    filter_modes,
    opt,
    scope_modes,
    variant_modes,
)
from .account_capacity import ACCOUNT_CAPACITY, validate_capacity_query
from .capability import (
    LiquidityDetailCapability,
    LiquidityListCapability,
    encode_scope,
    scope_values,
)
from .cash_forecast import (
    ACCEPTED_DETAIL_SPECS,
    ACCEPTED_LIST_SPECS,
    CI_BLOCKER,
    RELEASED,
    UAT_BLOCKERS,
    UAT_PASSED,
    WITHDRAWN_GETTERS,
)
from .decision_list import DECISIONS, validate_decision_query
from .decision_list import RELEASED as DECISIONS_RELEASED
from .fee_orders import FEE_ORDERS, validate_fee_query
from .forecast_accuracy import FORECAST_ACCURACY
from .forecast_accuracy import validate_query as validate_accuracy_query
from .funding_demands import DEMANDS, validate_demand_query
from .investment_batch import CANDIDATES as INVESTMENT_CANDIDATES
from .investment_batch import RELEASED as INVESTMENT_RELEASED
from .investment_batch import validate_quote_query, validate_strategy_query
from .operations_batch import RELEASED as OPERATIONS_RELEASED
from .operations_batch import SWAP_ORDERS, validate_swap_query
from .realtime_network import REALTIME_NETWORK
from .rfqs import RFQS, validate_rfq_query
from .risk_batch import ACCEPTED_LIST_SPECS as RISK_LIST_SPECS
from .risk_batch import RELEASED as RISK_RELEASED
from .risk_detail import RISK_DETAIL_SPECS
from .risk_sla import RISK_SLA
from .rule_status import RULE_STATUS, validate_rule_status_query
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
from .strategy_detail import STRATEGY_DETAIL
from .transfer_list import RELEASED as TRANSFERS_RELEASED
from .transfer_list import TRANSFER_ORDERS, map_transfer_query
from .transfer_rules import TRANSFER_RULES

VERIFIED_DATE = "2026-10-01"
_PAGE_ECHO_NOTE = (
    "Pagination: rowStart offset collection at the leaf's configured page size"
    " against the reported total; any changed total, identity conflict or coverage gap"
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
        "account",
        field,
        summary,
        required=True,
        list_of_one=True,
        canonical_flag="--account-alias",
        **kwargs,
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
    page_size=1000,
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
    page_size=1000,
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
    page_size=1000,
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
    identity=(),
    profile=PROFILE_DATED,
    series_field="expectValueDateTime",
    series_format="%Y%m%d%H%M",
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
        "expectValueDateTime",
    ),
    notes=(
        "No reported total exists; the single response is the complete"
        " scoped set. Record schema is live-verified on a populated"
        " previous-day scope.",
        "Value Date uses expectValueDateTime (YYYYMMDDHHmm), as in the native"
        " UI; queries and retention compare its calendar day without a"
        " timezone conversion. No native unique key is established: all row"
        " occurrences are preserved within a response; overlapping captures"
        " match identical content by occurrence count.",
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
    page_size=500,
    profile=PROFILE_HISTORY,
    template={"tntInstId": TENANT, "status": ["ACTIVE", "INACTIVE"]},
    scope_options=(
        ScopeOption(
            "date",
            "date",
            f"Native query date for the holdings snapshot. {_DATE_FMT}",
            required=True,
            date=True,
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
        "The request date scopes the complete portfolio snapshot; native"
        " row valueDate is not that snapshot date and is never used to discard"
        " its holdings. Each query date has an independent cache scope."
        " Retained snapshot history orders by capture time, not row valueDate.",
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
    page_size=5000,
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
    series_format="%Y-%m-%d",
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
    page_size=5000,
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
    page_size=5000,
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
    series_format="%Y-%m-%d",
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

PRICING_FACTORS = ListSpec(
    path=("pricing", "factors"),
    kind=REFERENCE,
    title="pricing factor type definitions",
    endpoint="/getPriceEnv.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data", "factorTypes"),
    identity=("code",),
    pagination=PAGE_SINGLE,
    paged_request=False,
    profile=PROFILE_SNAPSHOT,
    template={"tntInstId": TENANT},
    table_columns=("code", "description", "englishName"),
    projection="factor_definitions",
    require_inner_success=True,
    schema_version="factor-definitions-v1",
    notes=(
        "Native factor type definitions are reference dimensions, not maintained"
        " pricing rules or observed factor values. Labels remain raw; missing,"
        " null and empty labels stay distinct. Native code is the identity.",
        "Observed 2026-10-05: single unpaginated factorTypes enumeration;"
        " no native total or definition timestamp. New codes are accepted.",
        "Only getPriceEnv factorTypes is read; queryCostParameters is not a"
        " fallback. Factor-values keeps its independent runtime contract/cache.",
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
    page_size=5000,
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
    page_size=5000,
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
    page_size=5000,
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
    page_size=5000,
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
    page_size=5000,
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
    identity=("aliasName", "currency"),
    profile=PROFILE_SNAPSHOT,
    page_size=5000,
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
        ("alias", "aliasName", "--account-alias"),
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
        "Account list identity uses aliasName and currency; the observed id"
        " is shared by different accounts and cannot identify list rows.",
        "Incomplete account lists return available rows with INCOMPLETE_RESULT"
        " and a nonzero exit; refresh retains the previous complete cache."
        " --require-complete rejects partial live data.",
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
    page_size=5000,
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
    page_size=5000,
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
    page_size=5000,
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
    REALTIME_NETWORK,
    ACCOUNT_CAPACITY,
    NETWORK_BANK_BASELINES,
    NETWORK_ACCOUNT_CAPABILITIES,
    PRICING_CLIENT_PRICES,
    PRICING_COST_PRICES,
    PRICING_FACTOR_VALUES,
    PRICING_FACTORS,
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
        container_list=True,
        identity=(IdentityOption("id", "id", "Current decision report id.", "int"),),
        list_leaf=("operations", "decisions"),
        schema_version="decision-history-lineage-v1",
        notes=(
            "Native history is a list of versions with distinct row ids.",
            "Each acquisition verifies the current native getDetail id and"
            " binds every history row to its reportId, groupId and tenant.",
        ),
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
        notes=(
            "SLA summaries and these explicit rule details use independent caches.",
        ),
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
        notes=(
            "List and genuine detail inquiries use independent caches; "
            "acquire details by ruleId.",
        ),
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
        ("cash", "accounts", "get"),
        REFERENCE,
        "backend-blocked",
        "Native account detail returns business error 999; list ids are shared."
        " Backend identity/detail repair and typed echo evidence are required.",
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
        "Wallets: wallet=true/false returned identical ordered account rows at"
        " pageSize 1000/5000; wallet membership is not established.",
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
        "Wallet balances: no verified independent native wallet-balance caller"
        " bound to wallet membership; normal-account balances are not renamed.",
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
        ("forecast", "results", "get"),
        RUNTIMES,
        "unverified",
        f"Forecast result detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("forecast", "accuracy", "list"),
        RUNTIMES,
        "backend-blocked",
        "Forecast accuracy: 1000-width offset pages contain cross-page duplicate"
        " ids (4416 unique of 4419 reported). Backend pagination repair and"
        " nonzero accuracy/formula/day-boundary evidence are required.",
    ),
    DeferredLeaf(
        ("operations", "demands", "list"),
        RUNTIMES,
        "uat-blocked",
        "Spec #82 funding demands: current one-day inquiries succeed empty;"
        " native week/30-day scopes return error 099 (database exception). Usable"
        " nonempty schema, identity, date scope, complete pagination and"
        " independent production UAT remain unverified; no backend repair"
        " is included in this batch.",
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
        "uat-blocked",
        "Spec #82 executions: both native task-type variants succeed empty"
        " in current one-day scopes; week/30-day scopes return error 099"
        " (database exception). Nonempty schema, identity, native status"
        " meanings, date scope, complete pagination and independent"
        " production UAT remain unverified.",
    ),
    DeferredLeaf(
        ("operations", "executions", "get"),
        RUNTIMES,
        "identity-unavailable",
        f"Execution detail: {_IDENTITY}.",
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
        "Offers (#118): the current ProductPoolView, RFQMgmt and"
        " QuotationGroupMgmt pages do not prove an independent native runtime"
        " offers object; RFQ and quote-group lists must not be renamed as"
        f" offers; {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("investment", "investable-funds", "list"),
        RUNTIMES,
        "empty-scope",
        "Investable funds (#82/#118): the native JSON list inquiry"
        " /queryInvestableFundList.json contract is known (JSON POST; native"
        " tenant, timeZone, reportDate, startForecastDate, endForecastDate,"
        " rowStart, pageSize, optional native currency), but 28 bounded"
        " probes across 7 report dates, 1000/5000 page widths and two"
        " forecast ranges all returned zero rows (totalCount=0). Successful"
        " empty scopes do not establish a nonempty record schema, unique"
        " identity, amount and currency semantics, or report/forecast date"
        " meaning. Enablement gates on a populated positive sample proving"
        " nonempty rows, identity and amount/date semantics; standalone"
        " production UAT has not passed; list, live acquisition and refresh"
        " remain unavailable.",
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
        "Quote sessions (#118): no independent session granularity or native"
        " session identity is proven; RFQ and quote-group records are not"
        f" sessions and must not be renamed; {_UNVERIFIED}.",
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
        "identity-unavailable",
        "Benchmark values (#89): current non-empty rows have blank native id. "
        "valueDate/timeZone map to effectiveDate and GMT+08; the UI value unit "
        "is percent. Native identity across benchmarks remains unverified; "
        "complete acquisition and production UAT are blocked. No guessed "
        "composite identity or partial policy lowers this gate.",
    ),
    DeferredLeaf(
        ("investment", "strategy-results", "list"),
        RUNTIMES,
        "empty-scope",
        "Strategy results (#89): FUND_DECISION_TASK and PRODUCT_DECISION_TASK "
        "each require a non-empty contract, native task identity, trigger "
        "scope, status, complete acquisition and production UAT. Neither "
        "variant's empty query releases the other. Task status is not proof "
        "of investment execution; partial policy does not lower this gate.",
    ),
    DeferredLeaf(
        ("investment", "strategy-results", "get"),
        RUNTIMES,
        "identity-unavailable",
        f"Strategy-result detail: {_IDENTITY}.",
    ),
    DeferredLeaf(
        ("risk", "events", "list"),
        RUNTIMES,
        "empty-scope",
        "Risk events: historical UI caller uses riskMode=RISK_EVENT;"
        " only empty responses observed. Release requires current native scope"
        " verification, nonempty record types and identity, event observation"
        " dates/timezone, complete acquisition and production UAT (#88).",
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
        "Risk anomalies: historical UI caller uses riskMode=RISK_ALERT;"
        " no local anomaly classification. Only empty responses observed."
        " Release requires current native scope distinction from events,"
        " nonempty record types and identity, observation dates/timezone,"
        " complete acquisition and production UAT (#88).",
    ),
    DeferredLeaf(
        ("risk", "anomalies", "get"),
        RUNTIMES,
        "identity-unavailable",
        f"Risk anomaly detail: {_IDENTITY}.",
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
        "Monitoring rules are settings, not observed risk events. Current"
        " native queryRules also returned zero records (2026-10-04);"
        " monitoring rule-type filter"
        " unverified. Release requires current native scope verification,"
        " nonempty record types and rule identity, configuration status/time"
        " semantics, complete acquisition and production UAT (#88).",
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
        "Network routes: no native global routes-list caller exists (#119);"
        " RealTimeNetwork is a network configuration object with its own"
        " native network id and its routeId values are references, not"
        " routes; the discovered queryWhaleRouteDetail caller is a"
        " network-scoped per-route quota detail"
        " (dynamicQuotas/staticQuotas), not a global routes list with"
        " pagination, so the verified realtime network records must not"
        " masquerade as routes acceptance.",
    ),
    DeferredLeaf(
        ("network", "routes", "get"),
        SETTINGS,
        "unverified",
        "Network route detail: the discovered queryWhaleRouteDetail caller"
        " (routeId/aliasName/tntInstId; dynamicQuotas/staticQuotas quota"
        " detail) was never executed and no get is in scope this batch"
        " (#119).",
    ),
    DeferredLeaf(
        ("network", "realtime", "get"),
        SETTINGS,
        "observed-overlap",
        "Realtime network detail: its native detail contract remains unverified "
        "(#104 enables only the settings list).",
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
        "naming-conflict",
        "Valuations (#89): current non-empty source records are fee-order "
        "objects under the native Efficient Service tab, with feeAmount and "
        "pricingCurrency. These semantics do not establish investment valuation. "
        "Resolve the naming/compatibility decision separately before complete "
        "acquisition and production UAT can release this leaf.",
    ),
    DeferredLeaf(
        ("pricing", "valuations", "get"),
        RUNTIMES,
        "unverified",
        f"Valuation detail: {_UNVERIFIED}.",
    ),
    DeferredLeaf(
        ("pricing", "bills", "list"),
        RUNTIMES,
        "empty-scope",
        "Bills (#89): current DEPOSIT and LOAN inquiries returned empty scopes; "
        "this does not establish support for either bill type. First release "
        "requires a "
        "non-empty contract, native bill identity, verified type/period, "
        "amount/currency, complete acquisition and production UAT; partial "
        "policy does not lower this gate.",
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
        "production-uat-pending",
        "Decision list: bounded native offset acquisition verified on 2026-10-04"
        " (264 arrivals, 264 unique ids, total 264); registered production CLI"
        " UAT is pending. get/history remain independently available.",
    ),
    DeferredLeaf(
        ("operations", "transfers", "list"),
        RUNTIMES,
        "pagination-unverified",
        "Transfer list: nonempty native rows and offset queries observed;"
        " complete acquisition and registered production CLI UAT remain"
        " unverified. Native transaction query bounds and displayed gmtCreate"
        " have no verified time mapping. get remains independently available.",
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
        "Quote-group list: offsets 0 and 10 return identical 54 rows without"
        " a total or verified ending protocol; full-response completeness"
        " is unproven. quotationGroupId repeats across versions.",
    ),
)

if TRANSFER_ORDERS.name in TRANSFERS_RELEASED:
    LIST_SPECS += (TRANSFER_ORDERS,)
    _TICKET_DEFERRED = tuple(
        item
        for item in _TICKET_DEFERRED
        if item.path != (*TRANSFER_ORDERS.path, "list")
    )
if DECISIONS.name in DECISIONS_RELEASED:
    LIST_SPECS += (DECISIONS,)
    _TICKET_DEFERRED = tuple(
        item for item in _TICKET_DEFERRED if item.path != (*DECISIONS.path, "list")
    )

# Spec #82 swap declaration stays non-executing until its own UAT/CI gate.
if SWAP_ORDERS.name in OPERATIONS_RELEASED:
    LIST_SPECS += (SWAP_ORDERS,)
_AUDIT_DEFERRED = tuple(
    item for item in _AUDIT_DEFERRED if item.path != (*SWAP_ORDERS.path, "list")
)
if SWAP_ORDERS.name not in OPERATIONS_RELEASED:
    _AUDIT_DEFERRED += (
        DeferredLeaf(
            (*SWAP_ORDERS.path, "list"),
            SWAP_ORDERS.kind,
            "uat-pending",
            "Spec #82 swap orders: nonempty native records observed; candidate"
            " identity, full pagination, date scope, CLI production UAT and"
            " local Kimi CLI CI/review must pass before release.",
        ),
    )

# Issue #97 independently verified event and alert native details.
DETAIL_SPECS += RISK_DETAIL_SPECS
_AUDIT_DEFERRED = tuple(
    item
    for item in _AUDIT_DEFERRED
    if item.path not in {(*spec.path, spec.action) for spec in RISK_DETAIL_SPECS}
)

LIST_SPECS += (FEE_ORDERS, RISK_SLA)
_TICKET_DEFERRED = tuple(
    item for item in _TICKET_DEFERRED if item.path != (*RISK_SLA.path, "list")
)

# Spec #88 releases only the independently verified bounded risk list scopes.
LIST_SPECS += tuple(item for item in RISK_LIST_SPECS if item.name in RISK_RELEASED)
# Spec #89 registers only the independently accepted investment list variants.
LIST_SPECS += tuple(
    item for item in INVESTMENT_CANDIDATES if item.name in INVESTMENT_RELEASED
)
_AUDIT_DEFERRED = tuple(
    item
    for item in _AUDIT_DEFERRED
    if item.path
    not in {
        (*spec.path, "list") for spec in RISK_LIST_SPECS if spec.name in RISK_RELEASED
    }
    | {
        (*candidate.path, "list")
        for candidate in INVESTMENT_CANDIDATES
        if candidate.name in INVESTMENT_RELEASED
    }
)

DETAIL_SPECS += (STRATEGY_DETAIL,)
_AUDIT_DEFERRED = tuple(
    item
    for item in _AUDIT_DEFERRED
    if item.path != (*STRATEGY_DETAIL.path, STRATEGY_DETAIL.action)
)

# Spec #76 replaces old cash/forecast deferrals, not other domains' contracts.
_ACCEPTED_PATHS = {(*item.path, "list") for item in ACCEPTED_LIST_SPECS} | {
    (*item.path, item.action) for item in ACCEPTED_DETAIL_SPECS
}
LIST_SPECS += tuple(item for item in ACCEPTED_LIST_SPECS if item.name in RELEASED)
DETAIL_SPECS += tuple(item for item in ACCEPTED_DETAIL_SPECS if item.name in RELEASED)
DEFERRED: tuple[DeferredLeaf, ...] = (
    tuple(
        item
        for item in (*_TICKET_DEFERRED, *_AUDIT_DEFERRED)
        if item.path not in _ACCEPTED_PATHS and item.path not in WITHDRAWN_GETTERS
    )
    + tuple(
        DeferredLeaf(
            (*item.path, "list"),
            item.kind,
            "uat-blocked"
            if item.name in UAT_BLOCKERS
            else ("ci-pending" if item.name in UAT_PASSED else "uat-pending"),
            UAT_BLOCKERS.get(
                item.name,
                CI_BLOCKER
                if item.name in UAT_PASSED
                else (
                    "Spec #76 implementation candidate: focused SIT and per-leaf CLI"
                    " production inquiry UAT must pass before execution is released."
                ),
            ),
        )
        for item in ACCEPTED_LIST_SPECS
        if item.name not in RELEASED
    )
    + tuple(
        DeferredLeaf(
            (*item.path, item.action),
            item.kind,
            "ci-pending" if item.name in UAT_PASSED else "uat-pending",
            CI_BLOCKER
            if item.name in UAT_PASSED
            else (
                "Spec #76 native detail candidate: focused SIT and per-leaf CLI"
                " production inquiry UAT must pass before execution is released."
            ),
        )
        for item in ACCEPTED_DETAIL_SPECS
        if item.name not in RELEASED
    )
)


LIST_SPECS += (FORECAST_ACCURACY,)
DEFERRED = tuple(
    item for item in DEFERRED if item.path != (*FORECAST_ACCURACY.path, "list")
)

LIST_SPECS += (TRANSFER_RULES,)
DEFERRED = tuple(
    item for item in DEFERRED if item.path != (*TRANSFER_RULES.path, "list")
)


LIST_SPECS += (RFQS,)
DEFERRED = tuple(item for item in DEFERRED if item.path != (*RFQS.path, "list"))

# --- leaf registry -----------------------------------------------------------

LIST_SPECS += (DEMANDS,)
DEFERRED = tuple(item for item in DEFERRED if item.path != (*DEMANDS.path, "list"))

LIST_SPECS += (RULE_STATUS,)
DEFERRED = tuple(item for item in DEFERRED if item.path != (*RULE_STATUS.path, "list"))


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
        if variant.projection == "funding_demands":
            validate_demand_query(request_values)
        if variant.projection == "rule_status":
            validate_rule_status_query(request_values)
        if variant.projection == "decision_reports":
            validate_decision_query(request_values)
        if variant.projection == "swap_orders":
            validate_swap_query(request_values)
        if variant.projection in {"risk_events", "risk_anomalies"}:
            from .risk_batch import validate_risk_query

            validate_risk_query(request_values)
        if variant.projection == "transfer_orders":
            map_transfer_query(request_values)
        if variant.projection == "forecast_accuracy":
            validate_accuracy_query(request_values)
        if variant.projection == "fee_orders":
            validate_fee_query(request_values)
        if variant.projection == "strategy_results":
            validate_strategy_query(request_values)
        if variant.projection == "quotes":
            validate_quote_query(request_values)
        if variant.projection == "account_capacity":
            validate_capacity_query(request_values)
        if variant.projection == "rfq_subtasks":
            validate_rfq_query(request_values)
        window_fields = {
            option.field for option in variant.scope_options if option.window
        }
        cache_values = {
            field: value
            for field, value in request_values.items()
            if field not in window_fields
        }
        if variant.schema_version:
            cache_values["__contract"] = {
                "origin": "iliquidity.alipay.com",
                "tenant": TENANT,
                "kind": variant.kind,
                "endpoint": variant.endpoint,
                "method": variant.method,
                "schema_version": variant.schema_version,
                "projection": variant.projection,
                "template": variant.template,
            }
        scope_key = encode_scope(cache_values)
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


def _scope_contract(option: ScopeOption) -> dict[str, Any]:
    """Machine-readable contract derived from the scope declaration (#127)."""
    if option.iso_date:
        value_type = "date"
        preferred = "YYYY-MM-DD"
        accepted = ["YYYY-MM-DD"]
        timezone = None
    elif option.date:
        value_type = "date"
        preferred = "YYYY-MM-DD"
        accepted = ["YYYY-MM-DD", "YYYYMMDD"]
        timezone = None
    elif option.time:
        value_type = "time"
        preferred = "HH:mm:ss"
        accepted = ["HH:mm:ss", "HHmmss"]
        timezone = None
    elif option.datetime_zone == "utc":
        value_type = "datetime"
        preferred = "YYYY-MM-DDTHH:mm:ssZ"
        accepted = [
            "YYYY-MM-DDTHH:mm:ssZ",
            "YYYY-MM-DDTHH:mm:ss±hh:mm",
            "YYYY-MM-DD HH:mm:ss",
        ]
        timezone = "utc"
    elif option.datetime_zone == "unknown":
        value_type = "datetime"
        preferred = "YYYY-MM-DDTHH:mm:ss"
        accepted = ["YYYY-MM-DDTHH:mm:ss", "YYYY-MM-DD HH:mm:ss"]
        timezone = "unknown"
    elif option.choices:
        value_type = "enum"
        preferred = None
        accepted = []
        timezone = None
    else:
        value_type = "string"
        preferred = None
        accepted = []
        timezone = None
    cardinality: dict[str, Any] | None = None
    if option.repeat:
        cardinality = {
            "min": option.min_values if option.min_values is not None else 0,
            "max": option.max_values,
        }
    constraints: list[dict[str, Any]] = []
    if option.window == "from":
        constraints.append({"kind": "ordered-pair", "role": "lower"})
    elif option.window == "to":
        constraints.append({"kind": "ordered-pair", "role": "upper"})
    elif option.window == "both":
        constraints.append({"kind": "single-day"})
    if option.virtual:
        constraints.append({"kind": "contract-variant-selector"})
    # Virtual options select a contract variant and shape the scope identity;
    # they are never sent to the backend.
    modes = variant_modes(cardinality) if option.virtual else scope_modes(cardinality)
    return contract(
        value_type,
        preferred_format=preferred,
        accepted_formats=tuple(accepted),
        modes=modes,
        constraints=tuple(constraints),
        timezone=timezone,
    )


def _option_spec(option: ScopeOption) -> OptionSpec:
    summary = option.summary
    if option.verified:
        summary += f" Live-verified: {option.verified}."
    if option.repeat and option.default is not None:
        summary += f" Default native scope when omitted: {option.default}."
    kind = "append" if option.repeat else "str"
    return OptionSpec(
        option.flag,
        option.public_flag,
        summary,
        kind,
        required=option.required,
        default=None if option.repeat else option.default,
        choices=option.choices,
        legacy_flags=option.legacy_flags,
        argument_contract=_scope_contract(option),
    )


def _filter_option(entry: tuple[str, ...]) -> OptionSpec:
    flag, field = entry[0], entry[1]
    # Liquidity filters are applied locally after acquisition in every mode;
    # the native request never carries them (verified request shapes).
    option = opt(
        flag,
        f"Exact local match on {field}.",
        "append",
        argument_contract=contract(
            "string", modes=filter_modes(repeatable=True, live_native=False)
        ),
    )
    if len(entry) > 2:
        option = replace(option, flag=entry[2], legacy_flags=(option.flag,))
    return option


def list_query_node(leaf: ListLeaf) -> BizNode:
    variant = leaf.variants[0]
    path = ("liquidity", *leaf.path, "list")
    return BizNode(
        path,
        f"List {leaf.title} from the local cache (default) or the backend"
        f" with --live. Kind: {leaf.kind}.",
        options=(
            *(_option_spec(option) for option in leaf.options),
            *(_filter_option(entry) for entry in variant.filters),
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
                    choices=option.choices,
                    argument_contract=contract(
                        "string",
                        preferred_format="nonempty native identifier",
                        modes=scope_modes(None),
                    ),
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
                choices=option.choices,
                argument_contract=contract(
                    "string",
                    preferred_format="nonempty native identifier",
                    modes=scope_modes(None),
                ),
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
    ("pricing",): (
        "Client/cost prices, factor type definitions, factor values and"
        " pricing strategies."
    ),
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


class UnsupportedLeafHandle:
    """Registry handle for a deferred leaf; no inquiry contract."""

    def __init__(self, node: BizNode) -> None:
        self.name = "liquidity." + ".".join(node.path[1:]) + ".unsupported"
