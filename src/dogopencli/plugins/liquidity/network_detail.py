"""Bounded realtime network associations with separate identity and coverage."""

from typing import Any

from ...errors import INVALID_RESPONSE, CliError
from ...result_policy import AcquisitionEvidence
from .capability import LiquidityDetailCapability, envelope_document
from .leaves import DetailLeaf
from .qualified_getters import CONTEXT_FIELDS, QUOTA_DETAIL, STATIC_FIELDS
from .realtime_network import project_network, validate_native_rows
from .spec import ENV_SUCCESS, SETTINGS, TENANT, DetailSpec, IdentityOption

HISTORY_SCOPE = ("creditAliasName", "debitAliasName", "fundAction")
HISTORY_SPEC = DetailSpec(
    path=("network", "realtime", "operation-history"),
    action="get",
    kind=SETTINGS,
    title="network configuration history",
    endpoint="/api/ai/decision/network/queryLog.json",
    method="POST",
    envelope=ENV_SUCCESS,
    container=("data",),
    tenant_field=False,
    identity=tuple(
        IdentityOption(field, field, "Validated selected root scope.")
        for field in HISTORY_SCOPE
    ),
    container_list=True,
    schema_version="realtime-network-history-v1",
)


class HistoryCapability(LiquidityDetailCapability):
    def detail_body(self, values: dict[str, str]) -> dict[str, Any]:
        body = super().detail_body(values)
        for field in HISTORY_SCOPE[:2]:
            body[field] = [body[field]]
        return body

    def parse_detail(self, body: bytes, values: dict[str, str]) -> list[dict[str, Any]]:
        rows = super().parse_detail(body, values)
        validate_native_rows(rows)
        for row in rows:
            if type(row.get("version")) is not int or row.get("scene") != "REALTIME":
                raise CliError(
                    INVALID_RESPONSE, "network history version or scene is invalid"
                )
            if any(row.get(field) != values[field] for field in HISTORY_SCOPE):
                raise CliError(
                    INVALID_RESPONSE, "network history scope contradicts selected root"
                )
            tenant = row.get("tntInstId")
            if tenant not in (None, "", TENANT):
                raise CliError(
                    INVALID_RESPONSE, "network history tenant contradicts request"
                )
        return [project_network(row) for row in rows]


SLICE_FIELDS = (
    "beginFromPreviousDay",
    "beginTime",
    "endTime",
    "holidayTypeCode",
    "timeSliceId",
    "timeUnit",
    "timeValue",
    "timeZone",
)


def _project_object(value: Any, fields: tuple[str, ...]) -> Any:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CliError(INVALID_RESPONSE, "route nested value is not an object")
    return {field: value[field] for field in fields if field in value}


def _slices(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise CliError(
            INVALID_RESPONSE, "route service windows are not an array of objects"
        )
    return [_project_object(row, SLICE_FIELDS) for row in value]


def project_route(row: dict[str, Any]) -> dict[str, Any]:
    """Apply B02's safe nested projection after existing quota validation."""
    result = {field: row[field] for field in CONTEXT_FIELDS if field in row}
    dynamic = []
    for item in row["dynamicQuotas"]:
        projected = {}
        for field, fields in (
            ("dateRange", ("begin", "end")),
            ("individualLimit", ("currency", "hasLimit", "limit")),
            ("remainLimit", ("currency", "hasLimit", "limit")),
            ("totalLimit", ("currency", "hasLimit", "limit")),
        ):
            if field in item:
                projected[field] = _project_object(item[field], fields)
        dynamic.append(projected)
    static = []
    for item in row["staticQuotas"]:
        projected = {field: item[field] for field in STATIC_FIELDS if field in item}
        if "updateTimeSliceConfig" in item:
            projected["updateTimeSliceConfig"] = _slices(item["updateTimeSliceConfig"])
        if "serviceWindowIntersection" in item:
            groups = item["serviceWindowIntersection"]
            if groups is None:
                projected["serviceWindowIntersection"] = None
            else:
                if not isinstance(groups, list) or any(
                    not isinstance(group, dict) for group in groups
                ):
                    raise CliError(
                        INVALID_RESPONSE, "route service window groups are invalid"
                    )
                projected_groups = []
                for group in groups:
                    output = (
                        {"timeSliceGroupId": group["timeSliceGroupId"]}
                        if "timeSliceGroupId" in group
                        else {}
                    )
                    if "timeSliceInfoList" in group:
                        output["timeSliceInfoList"] = _slices(
                            group["timeSliceInfoList"]
                        )
                    projected_groups.append(output)
                projected["serviceWindowIntersection"] = projected_groups
        static.append(projected)
    result.update(dynamicQuotas=dynamic, staticQuotas=static)
    return result


class RouteCapability(LiquidityDetailCapability):
    def parse_detail(
        self, body: bytes, values: dict[str, str]
    ) -> tuple[dict[str, Any], Any]:
        row = super().parse_detail(body, values)
        reported = envelope_document(body, self._spec.envelope)["result"].get("count")
        return project_route(row), reported


def _component(root: dict[str, Any], captured_at: str) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "applicability": "applicable",
        "identity": {"id": root["id"]},
        "source_version": root.get("version"),
        "request_scope": {"id": root["id"]},
        "native_contract": "realtime-network-detail-v1",
        "captured_at": captured_at,
        "returned_count": 1,
        "reported_count": None,
        "count_unit": "network",
        "complete": True,
        "reasons": [],
    }


def _unknown(name: str) -> dict[str, Any]:
    return {
        "status": "unverified",
        "applicability": "unverified",
        "identity": None,
        "request_scope": None,
        "native_contract": None,
        "captured_at": None,
        "returned_count": None,
        "reported_count": None,
        "count_unit": "history_record"
        if name == "operationHistory"
        else "quota_member",
        "complete": False,
        "reasons": [
            "HISTORY_CONTEXT_UNVERIFIED"
            if name == "operationHistory"
            else "ROUTE_ASSOCIATION_UNVERIFIED"
        ],
    }


def component_result(
    session: Any,
    root: dict[str, Any],
    captured_at: str,
    *,
    deadline: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """History is alias/action scoped, not a network ID or version-pinned read."""
    from .common import now
    from .query import fetch_detail

    components = {"network": _component(root, captured_at)}
    history = None
    history_component = _unknown("operationHistory")
    if root.get("scene") == "REALTIME" and all(
        isinstance(root.get(field), str) and root[field].strip()
        for field in HISTORY_SCOPE
    ):
        leaf = DetailLeaf(HISTORY_SPEC)
        leaf.capability = HistoryCapability(HISTORY_SPEC)
        scope = {field: root[field] for field in HISTORY_SCOPE}
        history = fetch_detail(
            session.transport(leaf.capability), leaf, scope, deadline=deadline
        )
        history_component = {
            "status": "succeeded",
            "applicability": "applicable",
            "identity": None,
            "request_scope": leaf.capability.detail_body(scope),
            "native_contract": HISTORY_SPEC.schema_version,
            "captured_at": now().isoformat(),
            "returned_count": len(history),
            "reported_count": None,
            "count_unit": "history_record",
            "complete": False,
            "reasons": ["HISTORY_COVERAGE_UNPROVEN"],
            "binding": (
                "selected root aliases and fundAction; "
                "records retain their own id/version"
            ),
            "pagination": "native array; no total or exhaustion proof",
        }
    if history is not None:
        from ...jsonutil import canonical

        matching = [row for row in history if row["id"] == root["id"]]
        changed = any(canonical(row) != canonical(root) for row in matching)
        history_component["selected_root_relation"] = (
            "changed" if changed else "matched" if matching else "not_present"
        )
        if changed:
            history_component["reasons"].append("SOURCE_CHANGED")
    components["operationHistory"] = history_component
    route = None
    route_component = _unknown("routeDetails")
    if "routeId" in root and root["routeId"] in (None, ""):
        route_component.update(
            status="inapplicable",
            applicability="inapplicable",
            complete=True,
            reasons=[],
            count_unit=None,
        )
    elif (
        isinstance(root.get("routeId"), str)
        and root["routeId"].strip()
        and isinstance(root.get("debitAliasName"), str)
        and root["debitAliasName"].strip()
    ):
        leaf = DetailLeaf(QUOTA_DETAIL)
        leaf.capability = RouteCapability(QUOTA_DETAIL)
        values = {"route_id": root["routeId"], "account_alias": root["debitAliasName"]}
        route, reported = fetch_detail(
            session.transport(leaf.capability), leaf, values, deadline=deadline
        )
        route_component = {
            "status": "succeeded",
            "applicability": "applicable",
            "identity": {
                "routeId": root["routeId"],
                "aliasName": root["debitAliasName"],
                "tntInstId": TENANT,
            },
            "binding": (
                "selected root routeId and debitAliasName; request-scoped aggregate"
            ),
            "request_scope": leaf.capability.detail_body(values),
            "native_contract": QUOTA_DETAIL.schema_version,
            "captured_at": now().isoformat(),
            "returned_count": 1,
            "reported_count": reported,
            "reported_count_unit": "unknown",
            "count_unit": "route_aggregate",
            "complete": True,
            "reasons": [],
            "member_counts": {
                name: len(route[name]) for name in ("dynamicQuotas", "staticQuotas")
            },
            "native_context_echo": {
                field: "present" if field in route else "absent"
                for field in CONTEXT_FIELDS
            },
        }
    components["routeDetails"] = route_component
    reasons = tuple(
        reason for component in components.values() for reason in component["reasons"]
    )
    evidence = AcquisitionEvidence(
        scope_complete=not reasons,
        dataset_complete=not reasons,
        collected_total=1,
        reported_total=1,
        total_semantics="networks",
        reasons=reasons,
    )
    return {**root, "operationHistory": history, "routeDetails": route}, {
        **evidence.meta(),
        "components": components,
        "snapshot_consistency": "sequential source reads; no atomic snapshot guarantee",
        "request_budget": {"components": 3, "history_pages": 1, "route_aggregates": 1},
    }
