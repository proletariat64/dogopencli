"""Named interest-rate contracts and source-specific inquiry validation."""

from datetime import datetime
from typing import Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from .spec import (
    ENV_SUCCESS,
    PROFILE_DATED,
    RUNTIMES,
    TENANT,
    DetailSpec,
    IdentityOption,
    ListSpec,
    ScopeOption,
)

SOURCES = ("market", "bank", "expectation-rule", "expection")
PATH = ("investment", "interest-rates")
UNIT_NOTE = (
    "Raw rateValue/ruleValue units are source-specific and unconfirmed;"
    " no scale conversion."
)


def source_option(source: str) -> ScopeOption:
    return ScopeOption(
        "source",
        "source",
        "Explicit source: market/bank runtimes; expectation-rule/expection settings.",
        required=True,
        choices=SOURCES,
        virtual=True,
        match=source,
    )


BANK_RATES = ListSpec(
    path=PATH,
    kind=RUNTIMES,
    title="bank interest rates",
    endpoint="/queryEnquireRateList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("bankId", "currency", "productTerm", "productType", "quoteDate"),
    profile=PROFILE_DATED,
    series_field="quoteDate",
    series_format="%Y%m%d",
    template={"currentArea": "3", "tntInstId": TENANT},
    page_size=1000,
    scope_options=(
        source_option("bank"),
        ScopeOption(
            "timezone",
            "timeZone",
            "Verified source timezone.",
            choices=("GMT+08",),
            default="GMT+08",
        ),
        ScopeOption(
            "from_date",
            "beginDate",
            "First quote date; required together with --to-date.",
            required=True,
            date=True,
            window="from",
        ),
        ScopeOption(
            "to_date",
            "endDate",
            "Last quote date; required together with --from-date.",
            required=True,
            date=True,
            window="to",
        ),
    ),
    filters=(("currency", "currency"),),
    table_columns=(
        "bankId",
        "currency",
        "productTerm",
        "productType",
        "quoteDate",
        "rateValue",
    ),
    notes=(
        UNIT_NOTE,
        "Reported total counts quote-date groups, not product rows."
        " Verified rowStart/pageSize count descending quote-date groups;"
        " product rows per group vary.",
    ),
    schema_version="interest-bank-v1",
)


def validate_source_options(variant: ListSpec, provided: dict[str, Any]) -> None:
    allowed = {option.flag for option in variant.scope_options}
    unsupported = {
        key for key, value in provided.items() if value is not None and value != []
    } - allowed
    if unsupported:
        raise CliError(
            INVALID_ARGUMENT,
            "arguments unavailable for selected source: "
            + ", ".join(sorted(unsupported)),
            exit_code=EXIT_USAGE,
        )


def wire_dates(body: dict[str, Any]) -> None:
    for key in ("beginDate", "endDate"):
        value = body[key]
        body[key] = datetime.strptime(value, "%Y%m%d").strftime("%Y-%m-%d")


def validate_bank_scope(rows: list[dict[str, Any]], values: dict[str, Any]) -> None:
    for row in rows:
        raw = row.get("quoteDate")
        try:
            day = datetime.strptime(raw, "%Y%m%d").strftime("%Y%m%d")
        except (TypeError, ValueError) as error:
            raise CliError(
                INVALID_RESPONSE, "bank quoteDate is not a native compact date"
            ) from error
        if not values["beginDate"] <= day <= values["endDate"]:
            raise CliError(
                INVALID_RESPONSE, "bank quote date is outside the requested window"
            )


def metadata(variant: ListSpec) -> dict[str, Any]:
    source = next(
        option.match for option in variant.scope_options if option.flag == "source"
    )
    return {
        "rate_source": source,
        "contract": variant.endpoint,
        "reported_total_unit": "quote_date_groups"
        if source == "bank"
        else "unique_objects",
        "raw_rate_units": "unconfirmed; no scale conversion",
    }


CUSTOM_EXPECTATION_RULES = ListSpec(
    path=PATH,
    kind="settings",
    title="customized expected market rules",
    endpoint="/queryMarketRateRuleList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("ruleId",),
    template={
        "currentArea": "1",
        "timeZone": "GMT+08",
        "tntInstId": TENANT,
        "rateCategory": "CUSTOMER_TYPE",
        "beginDate": "",
        "endDate": "",
    },
    page_size=1000,
    scope_options=(source_option("expectation-rule"),),
    filters=(("currency", "currency"),),
    table_columns=(
        "ruleId",
        "currency",
        "customizedMarketRateName",
        "ruleStatus",
        "ruleValue",
        "effectiveDate",
        "expireDate",
    ),
    notes=(
        UNIT_NOTE,
        "Effective/expiry dates are rule validity, not observation"
        " windows. All statuses are retained.",
    ),
    schema_version="interest-custom-rules-v1",
)

EXTERNAL_EXPECTATION_RULES = ListSpec(
    path=PATH,
    kind="settings",
    title="external institution expected market rules",
    endpoint="/queryFinancialMarketRateRuleList.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data", "data"),
    total=("data", "totalCount"),
    identity=("ruleId",),
    template={
        "rateCategory": "FINANCIAL_INST_TYPE",
        "rateProvide": "",
        "productTerm": "",
        "isPage": "Y",
        "customizedMarketRateName": "",
        "expectedRateProvider": "",
        "currency": "",
        "rateType": "",
        "ruleStatus": "",
    },
    page_size=1000,
    scope_options=(source_option("expection"),),
    filters=(("currency", "currency"),),
    table_columns=(
        "ruleId",
        "version",
        "currency",
        "expectedRateProvider",
        "ruleStatus",
        "ruleValue",
        "effectiveDate",
        "expireDate",
    ),
    notes=(
        UNIT_NOTE,
        "Expection spelling is intentional. All statuses retained;"
        " validity dates are configuration fields.",
    ),
    schema_version="interest-external-rules-v1",
)


def validate_rules(rows: list[dict[str, Any]], category: str) -> None:
    for row in rows:
        if row.get("rateCategory") != category:
            raise CliError(
                INVALID_RESPONSE, "interest rule category contradicts selected source"
            )
        if row.get("tntInstId") not in (None, "", TENANT):
            raise CliError(
                INVALID_RESPONSE, "interest rule tenant contradicts registered context"
            )


EXTERNAL_EXPECTATION_DETAIL = DetailSpec(
    path=PATH,
    action="get",
    kind="settings",
    title="external institution expected market rule",
    endpoint="/queryFinancialInstRateRuleDetail.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data",),
    identity=(
        IdentityOption("id", "id", "Native external ruleId from list.", echo="ruleId"),
    ),
    encoding="post-query",
    tenant_field=False,
    template={"_output_charset": "utf-8"},
    list_leaf=PATH,
    schema_version="interest-external-detail-v1",
    table_columns=(
        "ruleId",
        "version",
        "currency",
        "ruleStatus",
        "ruleValue",
        "effectDateList",
        "operationLogDetailList",
        "financialInstFilesMap",
    ),
    notes=(
        UNIT_NOTE,
        "Only expection supports genuine get. One inquiry; nested detail"
        " preserved without attachment downloads or recursive reads.",
    ),
)


BANK_FIELDS = dict.fromkeys(
    (
        "bankId",
        "bestExcellent",
        "currency",
        "gmtModified",
        "inquiryAmount",
        "lastOperator",
        "maxPurchaseAmount",
        "productTerm",
        "productType",
        "quoteDate",
        "rateValue",
    ),
    "str",
)
CUSTOM_RULE_FIELDS = dict.fromkeys(
    (
        "currency",
        "customizedMarketRateName",
        "effectiveDate",
        "expireDate",
        "gmtCreate",
        "gmtModify",
        "lastOperator",
        "operator",
        "rateBasicType",
        "rateCategory",
        "ratePeriod",
        "rateProvideCode",
        "rateType",
        "ruleId",
        "ruleStatus",
        "ruleType",
        "ruleValue",
    ),
    "str",
)
EXTERNAL_RULE_FIELDS = {
    **CUSTOM_RULE_FIELDS,
    **dict.fromkeys(
        ("approveState", "expectedRateProvider", "processId", "reason", "version"),
        "str",
    ),
}
EXTERNAL_DETAIL_FIELDS = {
    **EXTERNAL_RULE_FIELDS,
    "effectDateList": "object",
    "financialInstFiles": "list",
    "financialInstFilesMap": "object",
    "oldIncrementFinancialRateRuleDetail": "object|null",
    "operationLogDetailList": "list",
}
SOURCE_FIELDS = {
    BANK_RATES.endpoint: BANK_FIELDS,
    CUSTOM_EXPECTATION_RULES.endpoint: CUSTOM_RULE_FIELDS,
    EXTERNAL_EXPECTATION_RULES.endpoint: EXTERNAL_RULE_FIELDS,
}
