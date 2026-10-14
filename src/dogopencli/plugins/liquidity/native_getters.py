"""Bounded native demand, realtime network and quotation detail contracts (#136)."""

from typing import Any

from ...errors import INVALID_RESPONSE, CliError
from .spec import (
    ENC_FORM,
    ENV_BASE_RESULT,
    ENV_RESULT_FLAG,
    ENV_SUCCESS,
    RUNTIMES,
    SETTINGS,
    TENANT,
    DetailSpec,
    IdentityOption,
)

DEMAND_FIELDS = (
    "taskId",
    "tntInstId",
    "source",
    "actionType",
    "amount",
    "amountElement",
    "currency",
    "decisionAmount",
    "operationAmount",
    "instructionStatus",
    "needReview",
    "status",
    "createTime",
    "updateTime",
    "version",
)

DEMAND_DETAIL = DetailSpec(
    path=("operations", "demands"),
    action="get",
    kind=RUNTIMES,
    title="funding demand core detail",
    endpoint="/riskActionTaskQueryDetail.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "riskActionVO"),
    identity=(
        IdentityOption(
            "task_id", "taskId", "Nonempty native FUND_REQUIRE task ID.", echo="taskId"
        ),
    ),
    list_leaf=("operations", "demands"),
    projection="funding_demand_detail",
    schema_version="funding-demand-detail-v1",
    require_inner_success=True,
    table_columns=("taskId", "source", "amount", "currency", "status"),
    notes=(
        "Request tenant is GUAPW3SG; native blank tntInstId stays blank, "
        "never inferred.",
        "Demand core only; nested decision/execution reports and "
        "account/personnel/free text are excluded.",
        "createTime/updateTime are native source times with unknown "
        "timezone, not execution or capture time.",
    ),
)


def project_demand_detail(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("source") != "FUND_REQUIRE":
        raise CliError(INVALID_RESPONSE, "detail source is not FUND_REQUIRE")
    tenant = row.get("tntInstId")
    if tenant is not None and tenant != "" and tenant != TENANT:
        raise CliError(INVALID_RESPONSE, "detail tenant is outside requested scope")
    return {field: row[field] for field in DEMAND_FIELDS if field in row}


NETWORK_DETAIL = DetailSpec(
    path=("network", "realtime"),
    action="get",
    kind=SETTINGS,
    title="realtime network configuration detail",
    endpoint="/api/ai/decision/network/detail.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data",),
    tenant_field=False,
    identity=(
        IdentityOption(
            "network_id",
            "id",
            "Nonempty native network ID; routeId is a reference.",
            echo="id",
        ),
    ),
    list_leaf=("network", "realtime"),
    projection="realtime_network",
    schema_version="realtime-network-detail-v1",
    table_columns=(
        "id",
        "routeId",
        "version",
        "networkStatus",
        "runStatus",
        "operationHistory",
        "routeDetails",
    ),
    notes=(
        "Latest object JSON POST with only id; no tenant or version-pinned read.",
        "Native version is source configuration version, independent of "
        "capture and list generation.",
        "26 native settings fields retained; dynamic statistics, personnel, "
        "free text and actions are excluded.",
        "operationHistory queries selected root credit/debit aliases and fundAction; "
        "historical IDs/versions stay independent. No native total/exhaustion proof, "
        "so history coverage remains incomplete even for an empty successful array.",
        "routeDetails queries root routeId with debitAliasName/GUAPW3SG only; "
        "empty/null native routeId is inapplicable. Missing context stays unverified "
        "with null data and explicit meta.components status.",
        "Sequential inquiries share one deadline; no atomic snapshot guarantee. "
        "Root cardinality stays one; association counts and provenance are separate.",
        "Default safe incomplete results warn; --require-complete withholds "
        "business data.",
    ),
)

QUOTATION_FIELDS = (
    "quotationId",
    "bankId",
    "quotationStatus",
    "quotationTime",
    "quote",
    "valueDate",
    "effectiveEndDate",
    "quotationGroupNameByInquiry",
    "quotationGroupNameByQuotation",
)
PRODUCT_FIELDS = (
    "accountType",
    "actualMaturityDate",
    "curMaxLimitAvailable",
    "currency",
    "productType",
    "quote",
    "redemptionFeature",
    "tenor",
)
QUOTE_DETAIL = DetailSpec(
    path=("investment", "quotes"),
    action="get",
    kind=RUNTIMES,
    title="quotation and product conditions detail",
    endpoint="/queryQuotationOrder.json",
    method="POST",
    encoding=ENC_FORM,
    envelope=ENV_BASE_RESULT,
    container=("baseResult", "data"),
    tenant_field=False,
    identity=(
        IdentityOption(
            "quotation_order_id",
            "quotationOrderId",
            "Nonempty native quotation order ID; never parent inquiry ID.",
            echo=("quotationDetail", "quotationId"),
        ),
    ),
    list_leaf=("investment", "quotes"),
    projection="quotation_detail",
    schema_version="quotation-detail-v1",
    table_columns=("quotationDetail", "productDetail"),
    notes=(
        "Form POST sends only quotationOrderId; native "
        "quotationDetail.quotationId must match exactly.",
        "quotationDetail/productDetail are independent native "
        "projections; no root native ID is fabricated.",
        "Quote rates are percentages; O/N tenor and UTC+08:00 source "
        "interpretation stay native without arithmetic or timestamp conversion.",
        "Comparison/approval/log/attachment/personnel/free-text sections "
        "are excluded; no quote action is enabled.",
    ),
)


def project_quotation_detail(row: dict[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for section, fields in (
        ("quotationDetail", QUOTATION_FIELDS),
        ("productDetail", PRODUCT_FIELDS),
    ):
        if section not in row:
            continue
        value = row[section]
        if value is None:
            projected[section] = None
        elif isinstance(value, dict):
            projected[section] = {
                field: value[field] for field in fields if field in value
            }
        else:
            raise CliError(INVALID_RESPONSE, f"detail {section} is not an object")
    return projected


NATIVE_GETTERS = (DEMAND_DETAIL, NETWORK_DETAIL, QUOTE_DETAIL)
