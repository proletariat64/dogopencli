"""Qualified RFQ child and account-context route quota inquiries (#139)."""

from typing import Any

from ...errors import INVALID_RESPONSE, CliError
from .spec import (
    ENV_RESULT_FLAG,
    ENV_SUCCESS,
    RUNTIMES,
    TENANT,
    DetailSpec,
    IdentityOption,
)

RFQ_FIELDS = (
    "currency",
    "expectMaturityEndDate",
    "expectMaturityStartDate",
    "inquiryEndDate",
    "inquiryEntity",
    "inquiryOrderListVOList",
    "inquiryStartDate",
    "inquiryTaskId",
    "inquiryType",
    "productType",
    "redemptionFeature",
    "tenor",
    "tenorDays",
    "ticketSize",
    "valueDate",
)
RFQ_ORDER_FIELDS = (
    "bankId",
    "department",
    "inquiryId",
    "inquiryStatus",
    "inquiryTime",
    "processStatus",
    "quotationGroupName",
    "quotationNum",
    "quotationStatus",
    "winNum",
    "winStatus",
)
RFQ_DETAIL = DetailSpec(
    path=("investment", "rfqs"),
    action="get",
    kind=RUNTIMES,
    title="TARGET_RFQ child inquiry detail",
    endpoint="/rfq/subInquiryTask/queryInquiryTaskDetail.json",
    method="GET",
    envelope=ENV_SUCCESS,
    container=("data",),
    tenant_field=False,
    identity=(
        IdentityOption(
            "inquiry_sub_task_id",
            "inquiryTaskId",
            "Native child inquirySubTaskId; wire inquiryTaskId does not take "
            "the parent ID.",
            echo="inquiryTaskId",
        ),
    ),
    list_leaf=("investment", "rfqs"),
    projection="rfq_child_detail",
    schema_version="rfq-child-detail-v1",
    table_columns=("inquiryTaskId", "inquiryType", "currency", "ticketSize"),
    notes=(
        "Native wire inquiryTaskId receives the child inquirySubTaskId, "
        "not parent inquiryTaskId.",
        "TARGET_RFQ root and its native institution inquiry members are "
        "one independent detail.",
        "Native values, precision, dates, unknown statuses, absent and "
        "null fields stay unchanged.",
    ),
)


def project_rfq_detail(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("inquiryType") != "TARGET_RFQ":
        raise CliError(INVALID_RESPONSE, "RFQ detail type is not TARGET_RFQ")
    orders = row.get("inquiryOrderListVOList")
    if not isinstance(orders, list):
        raise CliError(INVALID_RESPONSE, "RFQ detail inquiry members must be an array")
    seen: set[str] = set()
    projected = []
    for order in orders:
        if not isinstance(order, dict):
            raise CliError(INVALID_RESPONSE, "RFQ inquiry member is not an object")
        identity = order.get("inquiryId")
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise CliError(INVALID_RESPONSE, "RFQ inquiry member identity is invalid")
        seen.add(identity)
        projected.append(
            {field: order[field] for field in RFQ_ORDER_FIELDS if field in order}
        )
    result = {field: row[field] for field in RFQ_FIELDS if field in row}
    result["inquiryOrderListVOList"] = projected
    return result


DYNAMIC_FIELDS = ("dateRange", "individualLimit", "remainLimit", "totalLimit")
STATIC_FIELDS = (
    "bic",
    "chainId",
    "currency",
    "individualLimit",
    "quotaId",
    "quotaSide",
    "serviceWindowIntersection",
    "tokenName",
    "tokenTransactionType",
    "totalLimit",
    "updateTimeSliceConfig",
    "usedQuota",
)
CONTEXT_FIELDS = ("routeId", "aliasName", "tntInstId")
QUOTA_DETAIL = DetailSpec(
    path=("network", "route-quotas"),
    action="get",
    kind=RUNTIMES,
    title="account-context route quota aggregate",
    endpoint="/queryWhaleRouteDetail.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "data"),
    identity=(
        IdentityOption("route_id", "routeId", "Nonempty native route reference."),
        IdentityOption(
            "account_alias", "aliasName", "Nonempty native account alias context."
        ),
    ),
    projection="route_quota_detail",
    schema_version="route-quota-detail-v1",
    require_inner_success=True,
    table_columns=("dynamicQuotas", "staticQuotas"),
    notes=(
        "One aggregate for exact routeId/aliasName/GUAPW3SG request "
        "context, not global routes.",
        "Native context echoes may be absent; request_scope metadata "
        "never fabricates native identity.",
        "Both quota arrays are required; order, duplicates, blank quotaId "
        "and precision stay native.",
        "result.count is unrelated to quota array coverage; no quota item "
        "identity is inferred.",
    ),
)


def validate_quota_context(row: dict[str, Any], request: dict[str, Any]) -> None:
    for field in CONTEXT_FIELDS:
        if field in row and row[field] not in (None, ""):
            if type(row[field]) is not str or row[field] != request[field]:
                raise CliError(
                    INVALID_RESPONSE, "quota detail context contradicts request"
                )


def project_quota_detail(row: dict[str, Any]) -> dict[str, Any]:
    result = {field: row[field] for field in CONTEXT_FIELDS if field in row}
    for section in ("dynamicQuotas", "staticQuotas"):
        items = row.get(section)
        if not isinstance(items, list) or any(
            not isinstance(item, dict) for item in items
        ):
            raise CliError(
                INVALID_RESPONSE,
                "quota aggregate requires both native arrays of objects",
            )
        result[section] = [dict(item) for item in items]
    return result


def detail_context_meta(
    detail: DetailSpec, values: dict[str, str], payload: Any
) -> dict[str, Any]:
    if detail.projection in {"asset_trade_detail", "quotation_group_detail"}:
        return {
            "scope_tenant": TENANT,
            "request_scope": {
                option.field: values[option.flag] for option in detail.identity
            },
            "native_context_echo": {
                "tntInstId": "present" if "tntInstId" in payload else "absent"
            },
        }
    if detail.projection == "route_quota_detail":
        return {
            "request_scope": {
                "routeId": values["route_id"],
                "aliasName": values["account_alias"],
                "tntInstId": TENANT,
            },
            "native_context_echo": {
                field: "present" if field in payload else "absent"
                for field in CONTEXT_FIELDS
            },
        }
    if detail.projection == "rfq_child_detail":
        return {
            "request_scope": {"inquiryTaskId": values["inquiry_sub_task_id"]},
            "scope_tenant": TENANT,
        }
    return {}


QUALIFIED_GETTERS = (RFQ_DETAIL, QUOTA_DETAIL)
