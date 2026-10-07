"""Offline data descriptions for liquidity leaves (describe).

Every description exposes the leaf's mandatory kind, its verified source
contract, typed identity, offline profile and the sampled field/type
evidence of 2026-10-01. Sampled types are observations, never validation
assertions: unknown units stay unknown, and null/empty/zero remain distinct
source states.
"""

from typing import Any

from ...annotations import schema_annotations
from ...helpspec import BizNode
from . import spec
from .decision_list import DECISIONS
from .decision_list import VERIFIED_DATE as DECISION_VERIFIED_DATE
from .fields import (
    CANDIDATE_SAMPLED_FIELDS,
    QUOTATION_DETAIL_FIELDS,
    QUOTATION_PRODUCT_FIELDS,
    RFQ_DETAIL_ORDER_FIELDS,
    SAMPLED_FIELDS,
    VARIANT_SAMPLED_FIELDS,
)
from .investment_batch import VERSION as INVESTMENT_VERSION
from .leaves import DEFERRED_BY_PATH, DETAIL_LEAVES
from .operations_batch import SWAP_ORDERS


def _field_schema(fields: dict[str, str]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for name, observed in sorted(fields.items()):
        properties[name] = {
            "x-observed-type": observed,
            "x-evidence": {
                "type": "observed",
                "presence": "observed",
                "nullability": "unknown",
                "unit": "unknown",
                "meaning": "unknown",
            },
        }
    return {
        "type": "object",
        "additionalProperties": True,
        "properties": properties,
        **schema_annotations(),
    }


def _source_guide(
    capability: str, contract: dict[str, Any], verified_date: str = "2026-10-01"
) -> dict[str, Any]:
    return {
        "capability": capability,
        "source_origin": f"https://{spec.HOST}",
        "tenant": spec.TENANT,
        "request": contract,
        "live_verified": verified_date,
    }


def _list_schema(item: spec.ListSpec, fields: dict[str, str]) -> dict[str, Any]:
    schema = _field_schema(fields)
    if item.projection == "risk_sla":
        schema["additionalProperties"] = False
        schema["x-business-validation"] = "none; source values preserved"
        schema["x-source-timezone"] = "unknown"
        schema["x-coverage"] = (
            "one fixed response; arrivals = unique slaConfigId = totalCount"
        )
        meanings = {
            "slaConfigId": (
                "Native configuration identity within the application tenant "
                "and source scope."
            ),
            "version": (
                "Native string configuration version; distinct from identity "
                "and cache schema."
            ),
            "riskEventType": "Raw native risk event type; no inferred rule.",
            "effectiveStatus": (
                "Raw configuration status; alert effectiveness is not inferred."
            ),
            "processStatus": "Raw workflow state; no inferred processing outcome.",
            "gmtCreate": (
                "Configuration creation time; timezone unknown; not capture time."
            ),
            "gmtModified": (
                "Configuration modification time; timezone unknown; "
                "not runtime observation."
            ),
        }
        for field, meaning in meanings.items():
            schema["properties"][field]["description"] = meaning
        return schema
    if item.projection == "forecast_accuracy":
        from .forecast_accuracy import METRIC_FIELDS

        schema["additionalProperties"] = False
        schema["x-source-timezone"] = (
            "unknown; GMT Create Date/Time is the native label"
        )
        schema["x-business-validation"] = (
            "none; raw native metrics without formula checks or scaling"
        )
        schema["x-metric-association"] = (
            "native request binding; no required backend record echo"
        )
        schema["properties"]["accuracy"] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                field: {"x-observed-type": "str", "x-unit": "unknown"}
                for field in METRIC_FIELDS
            },
        }
        return schema
    if item.projection == "account_capacity":
        schema["additionalProperties"] = False
        schema["x-business-validation"] = "none; source values preserved"
        schema["x-source-timezone"] = "unknown"
        schema["x-coverage"] = "exact explicit requested alias set, never all accounts"
        meanings = {
            "aliasName": "Native identity within the authorized tenant and origin.",
            "currency": "Separate native currency attribute; no currency audit.",
            "accountAvailableBalance": "Native UI Avl Bal; raw value preserved.",
            "availableIod": "Native UI Avl IOD; raw value preserved.",
            "availableResource": "Native UI Outflow Capacity; raw value preserved.",
            "outFlowCapacity": (
                "Native field with unknown business definition; separate from "
                "availableResource, without substitution or calculation."
            ),
            "cashPoolSupportAvailableResource": (
                "Native field with unknown business definition; no inferred formula."
            ),
            "valueTime": (
                "Original source-time string; unknown timezone, separate from "
                "fetched_at capture time."
            ),
        }
        for field, meaning in meanings.items():
            schema["properties"][field]["description"] = meaning
        schema["properties"]["valueTime"]["x-timezone"] = "unknown"
        return schema
    if item.projection == "transfer_rules":
        schema["additionalProperties"] = False
        schema["x-business-validation"] = "none; source values preserved"
        schema["x-source-timezone"] = "unknown unless provided by native timeZone"
        schema["x-coverage"] = (
            "one fixed response; arrivals = unique ruleId = ruleCount"
        )
        meanings = {
            "ruleId": "Native identity in the fixed tenant and default entity scope.",
            "ruleNo": "Native rule number; distinct from ruleId.",
            "version": (
                "Native configuration version; not a local cache schema version."
            ),
            "paymentAmount": (
                "Raw configuration value; unit unknown; no arithmetic validation."
            ),
            "gmtModified": (
                "Configuration modification time; not runtime "
                "observation or capture time."
            ),
            "effectiveTime": (
                "Raw configured effective time; no inferred "
                "timezone or validity arithmetic."
            ),
            "expiryTime": (
                "Raw configured expiry time; no inferred timezone "
                "or validity arithmetic."
            ),
            "bizConditions": (
                "Allowlisted nested configuration; personnel, "
                "contacts, notification recipients and URLs excluded."
            ),
        }
        for field, meaning in meanings.items():
            schema["properties"][field]["description"] = meaning
        return schema
    if item.projection == "rfq_subtasks":
        schema["additionalProperties"] = False
        schema["x-source-timezone"] = "unknown"
        schema["x-boundary-semantics"] = "unknown"
        schema["x-business-validation"] = "none; source values preserved"
        schema["x-coverage"] = (
            "one fixed response; arrivals = unique inquirySubTaskId = totalCount"
        )
        properties = schema["properties"]
        properties["inquirySubTaskId"]["description"] = (
            "Native subtask string identity in exact tenant, TARGET_RFQ and date scope."
        )
        properties["inquiryTaskId"]["description"] = (
            "Parent task reference; never a subtask identity or inferred quote session."
        )
        properties["inquiryType"]["description"] = "Fixed TARGET_RFQ response echo."
        for field in ("inquiryStartTime", "inquiryEndTime", "modifyTime"):
            properties[field]["x-timezone"] = "unknown"
            properties[field]["description"] = (
                "Raw source time; distinct from fetched_at."
            )
        return schema
    if item.projection == "quotes":
        schema["additionalProperties"] = False
        schema["x-source-timezone"] = "UTC+08:00"
        schema["x-coverage"] = (
            "single response for the exact requested value-date scope"
        )
        schema["x-business-validation"] = "none; source values preserved"
        properties = schema["properties"]
        meanings = {
            "quotationOrderId": "Native quotation identity; no inferred revision.",
            "inquiryId": "Inquiry reference; not the identity of a quote.",
            "quote": "Native percent value, preserved without scaling or calculation.",
            "tenor": (
                "Native tenor; O/N means Overnight. No date arithmetic is checked."
            ),
            "ticketSize": "Minimum deposit amount in the source currency.",
            "curMaxLimitAvailable": (
                "Native source field; business definition remains unconfirmed."
            ),
            "valueDate": (
                "Native value date, distinct from capture time and request bounds."
            ),
        }
        for field, meaning in meanings.items():
            properties[field]["description"] = meaning
        for field in ("quote", "tenor", "ticketSize"):
            properties[field]["x-evidence"]["meaning"] = "operator confirmed 2026-10-05"
        properties["quote"]["x-unit"] = "percent"
        properties["quote"]["x-evidence"]["unit"] = "operator confirmed 2026-10-05"
        properties["ticketSize"]["x-currency"] = "currency"
        for field in ("quotationTime", "inquiryTime"):
            properties[field]["x-timezone"] = "UTC+08:00"
            properties[field]["description"] = (
                "Native time string, interpreted in operator-confirmed UTC+08:00;"
                " not converted or replaced by capture time."
            )
        return schema
    if item.projection == "credit_usage":
        schema["additionalProperties"] = False
        schema["x-member-identity"] = ["id", "bankAccountCreditLineList[].id"]
        schema["x-usage-observation-time"] = "unknown"
        schema["x-business-validation"] = "none; source values preserved"
        meanings = {
            "currency": "Native Credit CCY for the parent credit line.",
            "amount": "Native parent Credit Amt; no allocation audit.",
            "usedAmount": "Native parent Credit Used Amt.",
            "availableAmount": "Native parent Credit Avl Amt.",
            "shareTag": (
                "Source sharing flag; shared lines need no assigned account cap."
            ),
            "bankAccountCreditLineList[].creditCurrency": (
                "Native CreditLine CCY; blanks remain unknown."
            ),
            "bankAccountCreditLineList[].currency": (
                "Native account currency; no guessed conversion."
            ),
            "bankAccountCreditLineList[].creditAmount": "Native member Credit Amt.",
            "bankAccountCreditLineList[].usedCreditAmount": (
                "Native member Credit Used Amt."
            ),
            "bankAccountCreditLineList[].availableCreditAmount": (
                "Native member Credit Avl Amt."
            ),
            "bankAccountCreditLineList[].equvAmount": (
                "Native member Equv Amt (Orig); not locally converted."
            ),
            "bankAccountCreditLineList[].usedAmount": (
                "Native member Equv Used Amt (Orig)."
            ),
            "bankAccountCreditLineList[].availableAmount": (
                "Native member Equv Avl Amt (Orig)."
            ),
            "bankAccountCreditLineList[].mergeFlag": (
                "Native UI display grouping; every member remains separate."
            ),
            "bankAccountCreditLineList[].isMasterAccount": "Native main-account flag.",
        }
        for field, meaning in meanings.items():
            schema["properties"][field]["description"] = meaning
            schema["properties"][field]["x-evidence"]["meaning"] = (
                "native UI and operator clarification 2026-10-05"
            )
        return schema
    if item.projection == "pool_balances":
        schema["additionalProperties"] = False
        properties = schema["properties"]
        meanings = {
            "mainCurrency": (
                "Native pool configuration currency; not the pool summary unit."
            ),
            "valueDate": (
                "Pool balance date only; member observation times remain unknown."
            ),
            "cashPoolMemberVOS[].currency": (
                "Account currency for original member balances; empty is unknown."
            ),
            "cashPoolMemberVOS[].bankCurrency": (
                "Bank conversion currency for equv balances; empty is unknown."
            ),
            "cashPoolMemberVOS[].masterAccount": (
                "Native main-account flag; no universal sweep schedule inferred."
            ),
            "cashPoolMemberVOS[].isShare": (
                "Native member balance-sharing flag; N can still permit concentration."
            ),
        }
        for prefix in ("", "cashPoolMemberVOS[]."):
            for field, meaning in {
                "currentBalance": "Current book balance",
                "currentAviBalance": "Current available funds for payment",
                "closeBalance": "Book closing balance on the previous statement day",
                "closeAviBalance": (
                    "Available closing balance on the previous statement day"
                ),
            }.items():
                key = prefix + field
                meanings[key] = meaning + "; independent native amount, not recomputed."
                unit = "currency" if prefix else "USD (native UI pool summary display)"
                properties[key]["x-currency"] = unit
                properties[key]["x-evidence"]["unit"] = (
                    "operator confirmed 2026-10-05"
                    if prefix
                    else "native UI USD summary label"
                )
                if prefix:
                    equivalent = prefix + "equv" + field[0].upper() + field[1:]
                    meanings[equivalent] = "Bank-converted " + meaning.lower() + "."
                    properties[equivalent]["x-currency"] = "bankCurrency"
                    properties[equivalent]["x-evidence"]["unit"] = (
                        "operator confirmed 2026-10-05"
                    )
        for field, meaning in meanings.items():
            properties[field]["description"] = meaning
            properties[field]["x-evidence"]["meaning"] = "operator confirmed 2026-10-05"
        properties["valueDate"]["x-format"] = "YYYY-MM-DD"
        schema["x-member-identity"] = ["id", "cashPoolMemberVOS[].id"]
        schema["x-member-observation-time"] = "unknown"
        return schema
    if item.projection == "benchmark_values":
        properties = schema["properties"]
        properties["effectiveDate"]["x-format"] = "YYYYMMDD"
        properties["value"]["x-unit"] = "percent"
        properties["value"]["x-evidence"]["unit"] = "native UI percent suffix"
        meanings = {
            "effectiveDate": "market benchmark business day in native GMT+08",
            "strategyBenchmarkType": "investment strategy: passive interest or tenor",
            "currency": "benchmark currency",
            "colorType": "fund nature: red, yellow or green",
            "value": "daily market interest benchmark",
        }
        for field, meaning in meanings.items():
            properties[field]["description"] = meaning
            properties[field]["x-evidence"]["meaning"] = "operator confirmed 2026-10-04"
        properties["primaryId"] = {
            "type": "string",
            "description": "Local stable reference: bmv1:<tenant>:<effectiveDate>:"
            "<strategyBenchmarkType>:<currency>:<colorType>; each UTF-8 component "
            "is percent-encoded, leaving only RFC 3986 unreserved characters literal.",
            "x-origin": "local derivation",
            "x-derived-from": ["tenant", *item.identity],
            "x-evidence": {
                "type": "derived",
                "presence": "guaranteed",
                "nullability": "non-null",
                "unit": "not applicable",
                "meaning": "single-field reference to the confirmed business identity",
            },
        }
        return schema
    if item.projection == "fee_orders":
        properties = schema["properties"]
        properties["serviceDate"]["x-format"] = "YYYYMMDD"
        properties["serviceDate"]["description"] = (
            "Inclusive native Service Date query day; fixed query zone GMT+08"
        )
        for field in ("serviceTime", "gmtCreate", "gmtModified"):
            properties[field]["x-format"] = "YYYY-MM-DD HH:mm:ss"
            properties[field]["description"] = (
                "Naive source timestamp; no inferred UTC offset or conversion"
            )
        for field, currency in (
            ("feeAmount", "pricingCurrency"),
            ("transAmount", "currency"),
        ):
            properties[field]["x-currency-field"] = currency
            properties[field]["x-evidence"]["unit"] = "native UI currency column"
        properties["feeAmount"]["description"] = "Fee(Pricing CCY)"
        properties["transAmount"]["description"] = "Transaction Amount"
        return schema
    if item.projection == "rule_status":
        properties = schema["properties"]
        for field in (
            "expectTriggerTime",
            "realTriggerTime",
            "gmtCreate",
            "gmtModified",
        ):
            properties[field]["x-unit"] = "epoch milliseconds"
        properties["expectTriggerTime"]["x-evidence"]["unit"] = (
            "native momentFormatTimeUtc renderer"
        )
        properties["expectTriggerTime"]["description"] = (
            "Expected trigger time; the native renderer is explicitly UTC;"
            " scope dimension of the required trigger bounds"
        )
        properties["realTriggerTime"]["description"] = (
            "Nullable actual trigger time; null stays null and never"
            " substitutes the expected time or the capture time"
        )
        properties["gmtCreate"]["description"] = "Record creation timestamp"
        properties["gmtModified"]["description"] = "Record modification timestamp"
        return schema
    if item.projection != "strategy_results":
        return schema
    properties = schema["properties"]
    for field in ("triggerDate", "resultTime"):
        properties[field]["x-unit"] = "epoch milliseconds"
        properties[field]["x-evidence"]["unit"] = "native UI timestamp renderer"
    for field in ("valueDate", "expectedInvestStartDate", "expectedInvestEndDate"):
        properties[field]["x-format"] = "YYYYMMDD"
    properties["investmentAmount"]["x-unit"] = "equivalent USD"
    properties["investmentAmount"]["x-evidence"]["unit"] = "native UI label"
    if item.template["taskType"] == "PRODUCT_DECISION_TASK":
        properties["maximumExceptedIncome"]["x-unit"] = "equivalent USD"
        properties["maximumExceptedIncome"]["x-evidence"]["unit"] = (
            "native product UI label"
        )
    return schema


def _list_description(node: BizNode) -> dict[str, Any]:
    from .leaves import list_leaf

    path = node.path[1:-1]  # after `liquidity`, without `list`
    leaf = list_leaf(path)
    variant = leaf.variants[0]
    capability = variant.name
    # A private UAT registry can install a candidate explicitly. Its observed
    # fields are available here without advertising it as a shipped capability.
    sampled_fields = CANDIDATE_SAMPLED_FIELDS | SAMPLED_FIELDS
    contract: dict[str, Any] = {
        "method": variant.method,
        "path": variant.endpoint,
        "encoding": "query" if variant.method == "GET" else variant.encoding,
        "envelope": variant.envelope,
        "record_container": "$." + ".".join(variant.container),
        "reported_total": (
            "$." + ".".join(variant.total) if variant.total is not None else None
        ),
        "pagination": variant.pagination,
        "page_size": variant.page_size if variant.paged_request else None,
    }
    variants = []
    for item in leaf.variants:
        variants.append(
            {
                "request": {
                    "method": item.method,
                    "path": item.endpoint,
                    "encoding": "query" if item.method == "GET" else item.encoding,
                    "envelope": item.envelope,
                    "record_container": "$." + ".".join(item.container),
                    "reported_total": "$." + ".".join(item.total)
                    if item.total
                    else None,
                    "pagination": item.pagination,
                    "page_size": item.page_size if item.paged_request else None,
                },
                "data_schema": _list_schema(
                    item,
                    VARIANT_SAMPLED_FIELDS.get(item.name, {}).get(
                        item.endpoint, sampled_fields.get(item.name, {})
                    ),
                ),
                "selectors": {
                    option.flag: option.match
                    for option in item.scope_options
                    if option.match
                },
                "identity": list(item.identity),
                "series_time": item.series_field,
                "scope_defaults": {
                    option.flag: option.default
                    for option in item.scope_options
                    if option.default is not None
                },
            }
        )
    return {
        "schema_version": 1,
        "data_schema": _list_schema(variant, sampled_fields.get(capability, {})),
        "read_guide": {
            **_source_guide(
                capability,
                contract,
                "2026-10-06"
                if variant.projection == "rule_status"
                else "2026-10-05"
                if variant.projection
                in {
                    "pool_balances",
                    "credit_usage",
                    "quotes",
                    "rfq_subtasks",
                    "realtime_network",
                    "account_capacity",
                    "transfer_rules",
                    "risk_sla",
                    "factor_definitions",
                    "forecast_accuracy",
                }
                else DECISION_VERIFIED_DATE
                if variant.name == DECISIONS.name
                else "2026-10-04"
                if variant.projection
                in {
                    "transfer_orders",
                    "risk_events",
                    "risk_anomalies",
                    "benchmark_values",
                    "fee_orders",
                }
                or variant.schema_version == INVESTMENT_VERSION
                else "2026-10-03"
                if variant.name == SWAP_ORDERS.name
                else ("2026-10-02" if variant.schema_version else "2026-10-01"),
            ),
            "projection": variant.projection or None,
            "schema_version": variant.schema_version or None,
            "variants": variants,
            "kind": variant.kind,
            "offline_profile": variant.profile,
            "identity": list(variant.identity),
            "series_time": variant.series_field,
            "notes": list(variant.notes),
            "freshness": (
                "stale measures capture age (fetched_at plus the configured"
                " TTL); source observation age is separate and unknown unless"
                " the record carries its own business time"
            ),
        },
    }


def _detail_schema(detail: spec.DetailSpec) -> dict[str, Any]:
    schema = _field_schema(SAMPLED_FIELDS.get(detail.name, {}))
    if detail.projection == "rfq_child_detail":
        schema["additionalProperties"] = False
        schema["required"] = ["inquiryTaskId", "inquiryType", "inquiryOrderListVOList"]
        schema["properties"]["inquiryTaskId"]["description"] = (
            "Native child inquirySubTaskId echoed under wire name "
            "inquiryTaskId; not parent identity."
        )
        schema["properties"]["inquiryType"]["const"] = "TARGET_RFQ"
        orders = _field_schema(RFQ_DETAIL_ORDER_FIELDS)
        orders["additionalProperties"] = False
        orders["required"] = ["inquiryId"]
        schema["properties"]["inquiryOrderListVOList"] = {
            "type": "array",
            "items": orders,
        }
        schema["x-source-timezone"] = "unknown"
        return schema
    if detail.projection == "route_quota_detail":
        from .qualified_getters import DYNAMIC_FIELDS, STATIC_FIELDS

        schema["additionalProperties"] = False
        schema["required"] = ["dynamicQuotas", "staticQuotas"]
        for component, fields in (
            ("dynamicQuotas", DYNAMIC_FIELDS),
            ("staticQuotas", STATIC_FIELDS),
        ):
            item = _field_schema(dict.fromkeys(fields, "unknown"))
            item["additionalProperties"] = True
            schema["properties"][component] = {"type": "array", "items": item}
        dynamic = schema["properties"]["dynamicQuotas"]["items"]["properties"]
        dynamic["dateRange"] = _field_schema({"begin": "int", "end": "int"})
        for field in ("individualLimit", "remainLimit", "totalLimit"):
            dynamic[field] = _field_schema(
                {"currency": "str", "hasLimit": "bool", "limit": "int"}
            )
        time_slice = _field_schema(
            {
                "beginFromPreviousDay": "bool",
                "beginTime": "str",
                "endTime": "str",
                "holidayTypeCode": "str",
                "timeSliceId": "str",
                "timeUnit": "str",
                "timeValue": "list",
                "timeZone": "str",
            }
        )
        static = schema["properties"]["staticQuotas"]["items"]["properties"]
        static["updateTimeSliceConfig"] = {"type": "array", "items": time_slice}
        group = _field_schema({"timeSliceGroupId": "str", "timeSliceInfoList": "list"})
        group["properties"]["timeSliceInfoList"] = {
            "type": "array",
            "items": time_slice,
        }
        static["serviceWindowIntersection"] = {"type": "array", "items": group}
        schema["x-identity"] = (
            "request-scoped aggregate; member IDs may be blank or duplicate"
        )
        schema["x-context-echo"] = "optional native fields; absence is not fabricated"
        return schema
    if detail.schema_version not in {
        "funding-demand-detail-v1",
        "realtime-network-detail-v1",
        "quotation-detail-v1",
    }:
        return schema
    schema["additionalProperties"] = False
    schema["x-business-validation"] = "native identity and scope; values preserved"
    if detail.projection == "funding_demand_detail":
        schema["required"] = ["taskId", "source"]
        schema["properties"]["source"]["const"] = "FUND_REQUIRE"
        for field in ("createTime", "updateTime"):
            schema["properties"][field]["x-timezone"] = "unknown"
    elif detail.projection == "realtime_network":
        schema["required"] = ["id"]
        schema["properties"]["version"]["description"] = (
            "Native source configuration version; no version-pinned request."
        )
    elif detail.projection == "quotation_detail":
        quotation = _field_schema(QUOTATION_DETAIL_FIELDS)
        quotation["additionalProperties"] = False
        quotation["required"] = ["quotationId"]
        quotation["properties"]["quotationId"]["description"] = (
            "Native identity echo of requested quotationOrderId."
        )
        quotation["properties"]["quotationTime"]["x-timezone"] = "UTC+08:00"
        product = _field_schema(QUOTATION_PRODUCT_FIELDS)
        product["type"] = ["object", "null"]
        product["additionalProperties"] = False
        for section in (quotation, product):
            section["properties"]["quote"]["x-unit"] = "percent"
        product["properties"]["tenor"]["description"] = (
            "Native investment tenor, including O/N; no derived date equality."
        )
        schema["required"] = ["quotationDetail"]
        schema["properties"] = {"quotationDetail": quotation, "productDetail": product}
    return schema


def _detail_description(node: BizNode) -> dict[str, Any]:
    from .leaves import detail_leaf

    leaf = detail_leaf(node.path[1:])
    detail = leaf.spec
    contract = {
        "method": detail.method,
        "path": detail.endpoint,
        "encoding": "query" if detail.method == "GET" else detail.encoding,
        "fixed_fields": detail.template,
        "envelope": detail.envelope,
        "detail_container": "$." + ".".join(detail.container),
        "identity": [
            {
                "option": option.flag,
                "native_field": option.field,
                "type": option.kind,
                "response_echo": option.echo,
                "virtual": option.virtual,
                "choices": list(option.choices),
            }
            for option in detail.identity
        ],
    }
    return {
        "schema_version": 1,
        "data_schema": _detail_schema(detail),
        "read_guide": {
            **_source_guide(
                detail.name,
                contract,
                "2026-10-07"
                if detail.schema_version
                in {
                    "funding-demand-detail-v1",
                    "realtime-network-detail-v1",
                    "quotation-detail-v1",
                    "rfq-child-detail-v1",
                    "route-quota-detail-v1",
                }
                else "2026-10-04"
                if detail.projection == "strategy_detail"
                or detail.schema_version == "risk-detail-v1"
                else "2026-10-02"
                if detail.schema_version
                else "2026-10-01",
            ),
            "projection": detail.projection or None,
            "schema_version": detail.schema_version or None,
            "identity": [option.field for option in detail.identity],
            "kind": detail.kind,
            "offline_profile": "per-object detail cache (ADR 0016)",
            "notes": list(detail.notes),
            "freshness": (
                "each cached detail carries its own fetched_at; it is never"
                " implied to belong to a newer list capture"
            ),
        },
    }


def _deferred_description(node: BizNode) -> dict[str, Any]:
    leaf = DEFERRED_BY_PATH[node.path[1:]]
    return {
        "schema_version": 1,
        "data_schema": {
            "type": "object",
            "x-evidence": "unsupported leaf: no registered schema",
            **schema_annotations(),
        },
        "read_guide": {
            "capability": "liquidity." + ".".join(leaf.path),
            "kind": leaf.kind,
            "release_status": "deferred",
            "evidence_status": leaf.status,
            "reason": leaf.reason,
        },
    }


def description(node: BizNode) -> dict[str, Any]:
    """Provider registered for every liquidity command node."""
    path = node.path[1:]  # strip the `liquidity` prefix
    if path in DEFERRED_BY_PATH:
        return _deferred_description(node)
    if path in DETAIL_LEAVES:
        return _detail_description(node)
    return _list_description(node)
