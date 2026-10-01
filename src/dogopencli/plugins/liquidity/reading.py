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
from .fields import SAMPLED_FIELDS, VARIANT_SAMPLED_FIELDS
from .leaves import DEFERRED_BY_PATH, DETAIL_LEAVES


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


def _source_guide(capability: str, contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "capability": capability,
        "source_origin": f"https://{spec.HOST}",
        "tenant": spec.TENANT,
        "request": contract,
        "live_verified": "2026-10-01",
    }


def _list_description(node: BizNode) -> dict[str, Any]:
    from .leaves import list_leaf

    path = node.path[1:-1]  # after `liquidity`, without `list`
    leaf = list_leaf(path)
    variant = leaf.variants[0]
    capability = variant.name
    contract: dict[str, Any] = {
        "method": variant.method,
        "path": variant.endpoint,
        "encoding": variant.encoding,
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
                    "encoding": item.encoding,
                    "envelope": item.envelope,
                    "record_container": "$." + ".".join(item.container),
                    "reported_total": "$." + ".".join(item.total)
                    if item.total
                    else None,
                    "pagination": item.pagination,
                    "page_size": item.page_size if item.paged_request else None,
                },
                "data_schema": _field_schema(
                    VARIANT_SAMPLED_FIELDS.get(item.name, {}).get(
                        item.endpoint, SAMPLED_FIELDS.get(item.name, {})
                    )
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
        "data_schema": _field_schema(SAMPLED_FIELDS.get(capability, {})),
        "read_guide": {
            **_source_guide(capability, contract),
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
        "encoding": detail.encoding,
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
            **_source_guide(detail.name, contract),
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
