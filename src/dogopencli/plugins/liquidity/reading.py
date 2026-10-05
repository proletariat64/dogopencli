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
from .fields import CANDIDATE_SAMPLED_FIELDS, SAMPLED_FIELDS, VARIANT_SAMPLED_FIELDS
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
                "2026-10-05"
                if variant.projection == "pool_balances"
                else DECISION_VERIFIED_DATE
                if variant.name == DECISIONS.name
                else "2026-10-04"
                if variant.projection
                in {
                    "transfer_orders",
                    "risk_events",
                    "risk_anomalies",
                    "benchmark_values",
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
            }
            for option in detail.identity
        ],
    }
    return {
        "schema_version": 1,
        "data_schema": _field_schema(SAMPLED_FIELDS.get(detail.name, {})),
        "read_guide": {
            **_source_guide(
                detail.name,
                contract,
                "2026-10-02" if detail.schema_version else "2026-10-01",
            ),
            "projection": detail.projection or None,
            "schema_version": detail.schema_version or None,
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
