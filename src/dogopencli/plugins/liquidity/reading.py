"""Offline data descriptions for liquidity leaves (describe).

Every description exposes the leaf's mandatory kind, its verified source
contract, typed identity, offline profile and the sampled field/type
evidence of 2026-10-01. Sampled types are observations, never validation
assertions: unknown units stay unknown, and null/empty/zero remain distinct
source states.
"""

from collections.abc import Mapping
from typing import Any, TypeVar

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

_FieldName = TypeVar("_FieldName", bound=str)


def _field_schema(fields: Mapping[_FieldName, str]) -> dict[str, Any]:
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


def _balance_schema(item: spec.ListSpec, schema: dict[str, Any]) -> dict[str, Any]:
    from dogopencli.plugins.liquidity.balance_view import export_field_name

    daily = item.endpoint == "/balStatisticalQuery.json"
    properties = {}
    for native, definition in schema["properties"].items():
        if daily and native == "data":
            continue
        properties[export_field_name(native, daily=daily)] = {
            **definition,
            "x-native-field": native,
        }
    schema["properties"] = properties
    schema["x-output-naming"] = "readable snake_case; native cache values unchanged"
    if not daily:
        schema["x-statement-selection"] = (
            "One latest statement per account/currency/business day; statement"
            " creation time, then update time. Amount changes are normal bank"
            " updates and informational only; acquisition completeness is unchanged."
        )
    return schema


def _public_balance_field(item: spec.ListSpec, field: str) -> str:
    if item.path != ("cash", "balances"):
        return field
    from dogopencli.plugins.liquidity.balance_view import export_field_name

    return export_field_name(field, daily=item.endpoint == "/balStatisticalQuery.json")


def _list_schema(item: spec.ListSpec, fields: dict[str, str]) -> dict[str, Any]:
    if item.path == ("investment", "interest-rates"):
        from .interest_rates import SOURCE_FIELDS

        fields = SOURCE_FIELDS.get(item.endpoint, fields)
    schema = _field_schema(fields)
    if item.schema_version == "access-lists-v1":
        properties = schema["properties"]
        meanings = {
            "id": "Observed dummy integer; not the native row identity.",
            "status": "Raw configuration status; no activation semantics inferred.",
            "gmtCreate": "Native creation timestamp in epoch milliseconds;"
            " not capture time.",
            "gmtModified": "Native modification timestamp in epoch milliseconds;"
            " not capture time.",
        }
        for field, meaning in meanings.items():
            if field in properties:
                properties[field]["description"] = meaning
        for field in item.identity:
            properties[field]["description"] = "Verified nonempty native row identity."
        if item.path == ("reference", "blacklist", "bank"):
            schema["required"] = ["bankId", "gmtCreate"]
            properties["bankId"]["description"] = (
                "Business bank identity; retain greatest gmtCreate"
                " before local filters."
            )
            properties["gmtCreate"]["type"] = "integer"
            properties["gmtCreate"]["minimum"] = 0
            properties["gmtCreate"]["x-unit"] = "epoch milliseconds"
        for field in ("pageNo", "pageSize", "rowStart", "startindex", "totalSize"):
            properties[field]["description"] = (
                "Native default field; not pagination or coverage evidence."
            )
    if item.path == ("investment", "interest-rates"):
        value = "ruleValue" if item.kind == spec.SETTINGS else "rateValue"
        schema["properties"][value]["x-unit"] = "unknown; raw value preserved"
        schema["properties"][value]["description"] = (
            "Source-specific raw rate string; precision and empty/null values"
            " retained without scaling."
        )
        if item.kind == spec.SETTINGS:
            for name in ("effectiveDate", "expireDate"):
                schema["properties"][name]["description"] = (
                    "Native configuration validity date; not an observation window."
                )
        return schema
    if item.path == ("cash", "accounts"):
        source_fields = {
            "cash": fields,
            "baseline": SAMPLED_FIELDS.get("liquidity.network.bank-baselines.list", {}),
            "detail": SAMPLED_FIELDS.get("liquidity.network.bank-baselines.get", {}),
        }
        schema = _field_schema(
            {
                **source_fields["detail"],
                **source_fields["cash"],
                **source_fields["baseline"],
                "detail_state": "str",
                "source_metadata": "object",
            }
        )
        for field, definition in schema["properties"].items():
            owner = next(
                (
                    source
                    for source in ("baseline", "cash", "detail")
                    if field in source_fields[source]
                ),
                "diagnostic",
            )
            if field in {"gmtModified", "operator"} and field in fields:
                owner = "cash"
            definition["x-source"] = owner
        for field in ("accountType", "status"):
            schema["properties"][field]["description"] = (
                "Baseline list only, without cash fallback; "
                "native empty and unexpected values preserved."
            )
        schema["properties"]["detail_state"]["enum"] = [
            "succeeded",
            "refused",
            "missing",
        ]
        schema["x-source-contracts"] = [
            "/queryintnalbkactlist.json",
            "/bankAccountBaseLineQuery.json",
            "/bankAccountBaseLineDetail.json",
        ]
        schema["x-field-ownership"] = (
            "Baseline list owns common fields; cash owns gmtModified/operator. "
            "Complementary fields enrich rows; source_metadata carries raw source "
            "values, provenance, conflicts, presence and detail refusal evidence. "
            "Unknown fields remain supported; collisions never silently overwrite data."
        )
        return schema
    if item.endpoint == "/balStatisticalQuery.json":
        schema = _field_schema(
            dict.fromkeys(
                (
                    "id",
                    "data",
                    "statisticalDate",
                    "balance",
                    "aliasName",
                    "entity",
                    "currency",
                ),
                "str",
            )
        )
        schema["additionalProperties"] = False
        schema["x-source-timezone"] = "GMT+08"
        schema["x-balance-subtype"] = (
            "closing book balance; confirmed business convention"
        )
        schema["properties"]["id"]["description"] = (
            "Native chart attribute; repeats across dates, not the daily identity."
        )
        schema["properties"]["statisticalDate"]["description"] = (
            "Source business day, YYYY-MM-DD; inclusive query axis, not capture time."
        )
        for key in ("entity", "aliasName", "currency"):
            schema["properties"][key]["description"] = (
                "Frozen current-roster request binding;"
                " historical ownership is unproven."
            )
        return _balance_schema(item, schema)
    if item.projection == "balances":
        return _balance_schema(item, schema)
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
                "kind": item.kind,
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
                "selectors": (
                    {
                        "date_bounds": "paired"
                        if item.profile == spec.PROFILE_DATED
                        else "absent"
                    }
                    if item.path == ("cash", "balances")
                    else {
                        option.flag: option.match
                        for option in item.scope_options
                        if option.match
                    }
                ),
                "identity": [
                    _public_balance_field(item, field) for field in item.identity
                ],
                **(
                    {"native_identity": list(item.identity)}
                    if item.path == ("cash", "balances")
                    else {}
                ),
                "series_time": (
                    _public_balance_field(item, item.series_field)
                    if item.series_field
                    else None
                ),
                "offline_profile": "single temporary leaf result",
                "notes": list(item.notes),
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
                "2026-10-15"
                if variant.schema_version == "access-lists-v1"
                else "2026-10-06"
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
            "offline_profile": "single temporary leaf result",
            "identity": [
                _public_balance_field(variant, field) for field in variant.identity
            ],
            **(
                {"native_identity": list(variant.identity)}
                if variant.path == ("cash", "balances")
                else {}
            ),
            "series_time": (
                _public_balance_field(variant, variant.series_field)
                if variant.series_field
                else None
            ),
            "notes": list(variant.notes),
            "freshness": (
                "stale measures capture age (fetched_at plus the configured"
                " TTL); source observation age is separate and unknown unless"
                " the record carries its own business time"
            ),
        },
    }


def _detail_schema(detail: spec.DetailSpec) -> dict[str, Any]:
    if detail.path == ("investment", "interest-rates"):
        from .interest_rates import EXTERNAL_DETAIL_FIELDS

        schema = _field_schema(EXTERNAL_DETAIL_FIELDS)
        schema["properties"]["ruleValue"]["x-unit"] = "unknown; raw value preserved"
        schema["x-nested-values"] = (
            "Arrays/maps/objects/null retained as native;"
            " no recursive reads or downloads."
        )
        return schema
    schema = _field_schema(SAMPLED_FIELDS.get(detail.name, {}))
    if detail.projection in {"asset_trade_detail", "quotation_group_detail"}:
        from .versioned_getters import CONTACT_FIELDS, PRODUCT_FIELDS

        schema["additionalProperties"] = False
        if detail.projection == "asset_trade_detail":
            schema["required"] = ["orderNo"]
            product = _field_schema(dict.fromkeys(PRODUCT_FIELDS, "str"))
            product["additionalProperties"] = False
            product["type"] = ["object", "null"]
            schema["properties"]["assetProductVo"] = product
            schema["x-excluded"] = ["transFerOrderLogVoList"]
        else:
            schema["required"] = ["id", "quotationGroupId", "tntInstId", "version"]
            schema["properties"]["id"]["description"] = (
                "Physical version-row id, supplied as --quotation-group-row-id."
            )
            schema["properties"]["quotationGroupId"]["description"] = (
                "Native business group identity; never request identity."
            )
            schema["properties"]["version"]["description"] = (
                "Selected native integer version; not inferred latest version."
            )
            contacts = _field_schema(dict.fromkeys(CONTACT_FIELDS, "str"))
            contacts["additionalProperties"] = True
            schema["properties"]["contactInfoList"] = {
                "type": ["array", "null"],
                "items": contacts,
            }
            history = _field_schema(SAMPLED_FIELDS[detail.name])
            history["additionalProperties"] = False
            history["required"] = list(schema["required"])
            history["properties"]["contactInfoList"] = schema["properties"][
                "contactInfoList"
            ]
            history["properties"]["operationHistoryList"] = {
                "type": ["array", "null"],
                "maxItems": 0,
            }
            schema["properties"]["operationHistoryList"] = {
                "type": ["array", "null"],
                "items": history,
            }
        schema["x-source-timezone"] = "unknown; native times remain unchanged"
        return schema
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
    if detail.name == "liquidity.operations.prefunds.get":
        history = _field_schema(SAMPLED_FIELDS[detail.name])
        history["required"] = ["id", "version", "status", "prefundingBizNo"]
        schema["properties"]["historyApplications"] = {
            "type": "array",
            "items": history,
            "x-cli-association": True,
            "description": "Same-business APPROVED_FINAL native application rows. "
            "Current-version membership evidence is separate in meta.components.",
        }
        transaction = _field_schema(
            {
                "preFundingUseDetailId": "str",
                "preFundingOrderId": "str",
                "prefundingBizNo": "str",
                "tntInstId": "str",
                "useDirection": "str",
                "status": "str",
                "currency": "str",
                "amount": "str",
                "applyCurrency": "str",
                "exchangeAmount": "str",
                "useRevertRelationVOList": "list",
            }
        )
        transaction["required"] = ["preFundingUseDetailId", "preFundingOrderId"]
        transaction["properties"]["useRevertRelationVOList"] = {
            "type": ["array", "null"],
            "items": {"type": "object"},
            "description": "Unflattened native exchange relations; native decimals "
            "and source dates remain unchanged.",
        }
        schema["properties"]["drawdownDetails"] = {
            "type": "array",
            "items": transaction,
            "x-cli-association": True,
            "description": "Business-scoped native USE/REVERT rows, including FAIL. "
            "Blank business echoes stay blank; application-version membership binds "
            "rows. Native count is evidence, not a trustworthy exhaustion proof.",
        }
        schema["x-component-quality"] = (
            "meta.components; --fields selects whole top-level collections only, "
            "not dotted paths; projection never changes quality or request scope"
        )
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
        from .native_getters import NETWORK_DETAIL
        from .qualified_getters import QUOTA_DETAIL

        history = _field_schema(SAMPLED_FIELDS[NETWORK_DETAIL.name])
        history["additionalProperties"] = False
        history["required"] = [
            "id",
            "version",
            "scene",
            "creditAliasName",
            "debitAliasName",
            "fundAction",
        ]
        history["properties"]["scene"]["const"] = "REALTIME"
        history["properties"]["version"].update(
            type="integer", **{"x-observed-type": "int"}
        )
        schema["properties"]["operationHistory"] = {
            "type": ["array", "null"],
            "items": history,
            "x-cli-association": True,
            "description": "Alias/action-scoped versions; independent native "
            "id/version. Null is unverified; empty array has no exhaustion "
            "proof. See meta.components.",
        }
        route = _detail_schema(QUOTA_DETAIL)

        def safe_nested(definition: dict[str, Any], *, nullable: bool = True) -> None:
            if definition.get("type") == "object":
                definition["additionalProperties"] = False
                if nullable:
                    definition["type"] = ["object", "null"]
            elif definition.get("type") == "array" and nullable:
                definition["type"] = ["array", "null"]
            for child in definition.get("properties", {}).values():
                safe_nested(child)
            if "items" in definition:
                safe_nested(definition["items"], nullable=False)

        safe_nested(route)
        for section in ("dynamicQuotas", "staticQuotas"):
            route["properties"][section]["type"] = "array"
        route["x-safe-projection"] = (
            "B02 known quota/window fields only; unknown fields excluded"
        )
        route["type"] = ["object", "null"]
        route["x-cli-association"] = True
        route["description"] = (
            "Selected root routeId and debit alias context. Null may be "
            "inapplicable or unverified; see meta.components."
        )
        schema["properties"]["routeDetails"] = route
        schema["x-component-quality"] = (
            "meta.components; projection does not change coverage"
        )
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
                "2026-10-15"
                if detail.path == ("investment", "interest-rates")
                else "2026-10-07"
                if detail.schema_version
                in {
                    "funding-demand-detail-v1",
                    "realtime-network-detail-v1",
                    "quotation-detail-v1",
                    "rfq-child-detail-v1",
                    "route-quota-detail-v1",
                    "asset-trade-detail-v1",
                    "quotation-group-row-detail-v1",
                }
                else "2026-10-04"
                if detail.projection == "strategy_detail"
                or detail.schema_version == "risk-detail-v1"
                else "2026-10-02"
                if detail.schema_version
                else "2026-10-01",
            ),
            **(
                {"rate_source": "expection"}
                if detail.path == ("investment", "interest-rates")
                else {}
            ),
            "projection": detail.projection or None,
            "schema_version": detail.schema_version or None,
            "identity": [option.field for option in detail.identity],
            "kind": detail.kind,
            "offline_profile": "online only; no cache",
            "notes": list(detail.notes),
            "freshness": (
                "Native detail acquired online on each invocation; never stored."
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
    from .retirement import retired_command, retirement_reason

    if retired_command(node.path):
        return {
            "schema_version": 1,
            "data_schema": {
                "type": "object",
                "x-evidence": "retired capability: no executable schema",
                **schema_annotations(),
            },
            "read_guide": {
                "capability": " ".join(node.path),
                "kind": node.kind,
                "release_status": "retired",
                "reason": retirement_reason(node.path),
                "quality": "No acquisition, cache replay, or publication is available.",
                "projection": "Projection options are accepted for refusal only.",
                "pagination": "Legacy display options are accepted only for refusal.",
                "envelope": {
                    "data": "Always null on retirement refusal.",
                    "error": "UNSUPPORTED_CAPABILITY, exit status 1.",
                },
            },
        }
    path = node.path[1:]  # strip the `liquidity` prefix
    if path in DEFERRED_BY_PATH:
        return _deferred_description(node)
    if path in DETAIL_LEAVES:
        return _detail_description(node)
    return _list_description(node)
