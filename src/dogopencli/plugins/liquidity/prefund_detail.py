"""Bounded same-business prefund associations; no publication or detail crawl."""

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ... import collect as collect_mod
from ...errors import INVALID_RESPONSE, CliError
from ...jsonutil import canonical
from ...result_policy import AcquisitionEvidence
from .capability import (
    LiquidityDetailCapability,
    LiquidityListCapability,
    decode_scope,
    encode_scope,
)
from .collect import collect_liquidity_scope
from .common import now
from .envelope import dig, envelope_document
from .spec import (
    ENV_RESULT_FLAG,
    RUNTIMES,
    TENANT,
    DetailSpec,
    IdentityOption,
    ScopeOption,
)

if TYPE_CHECKING:
    from .leaves import DetailLeaf

ASSOCIATIONS = ("historyApplications", "drawdownDetails")
TRANSACTIONS = DetailSpec(
    path=("operations", "prefunds", "drawdown-details"),
    action="get",
    kind=RUNTIMES,
    title="same-business prefund transactions",
    endpoint="/queryPreFundingUseDetailList.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    tenant_field=True,
    identity=(
        IdentityOption("business", "prefundingBizNo", "Validated business identity."),
    ),
    container_list=True,
    schema_version="prefund-drawdown-native-array-v1",
)


def _invalid(message: str) -> None:
    raise CliError(INVALID_RESPONSE, message)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _tenant(row: dict[str, Any]) -> None:
    if row.get("tntInstId") not in (None, "", TENANT):
        _invalid("prefund tenant contradicts requested source")


def validate_root(root: dict[str, Any], identity: str) -> None:
    if type(root.get("id")) is not str or root["id"] != identity:
        _invalid("prefund detail identity does not match typed request")
    _tenant(root)
    if set(ASSOCIATIONS).intersection(root):
        _invalid("native prefund payload collides with reserved association fields")
    if not _text(root.get("prefundingBizNo")):
        _invalid("prefund detail has no native business identity")
    if not _text(root.get("instId")):
        _invalid("prefund detail has no native entity identity")
    if type(root.get("version")) is not int or root["version"] < 0:
        _invalid("prefund detail has no valid native version")


def _component(
    scope: dict[str, Any],
    captured_at: str,
    reported: Any,
    count: int,
    unit: str,
    contract: str,
    reasons: list[str],
    *,
    arrivals: int | None = None,
) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "identity": scope,
        "native_contract": contract,
        "request_scope": scope,
        "captured_at": captured_at,
        "reported_count": reported,
        "reported_count_unit": unit,
        "count_unit": unit,
        "collected_count": count if arrivals is None else arrivals,
        "unique_count": count,
        "returned_count": count,
        "complete": not reasons,
        "reasons": reasons,
    }


class ApplicationCapability(LiquidityListCapability):
    """Validate each private status/business scope before accepting rows."""

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        values = decode_scope(scope)
        for row in rows:
            _tenant(row)
            if (
                not _text(row.get("id"))
                or type(row.get("version")) is not int
                or row["version"] < 0
                or row.get("status") not in values["statusList"]
                or row.get("prefundingBizNo") != values["prefundingBizNo"]
            ):
                _invalid("prefund application identity or business scope is invalid")


def fetch_selected(
    session: Any, leaf: "DetailLeaf", values: dict[str, str], *, deadline: float
) -> tuple[dict[str, Any], int]:
    """Keep the native detail counter separate from application cardinality."""
    response = collect_mod.execute_bounded(
        leaf.capability,
        session.transport(leaf.capability),
        leaf.capability.detail_body(values),
        deadline,
    )
    root = leaf.capability.parse_detail(response.body, values)
    validate_root(root, values["id"])
    reported = dig(
        envelope_document(response.body, ENV_RESULT_FLAG), ("result", "count")
    )
    if type(reported) is not int or reported < 0:
        _invalid("prefund detail counter is not a nonnegative integer")
    return root, reported


def component_result(
    session: Any,
    root: dict[str, Any],
    captured_at: str,
    *,
    deadline: float,
    application_reported: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from .leaves import OPERATIONS_PREFUNDS

    business = root["prefundingBizNo"]
    history_spec = replace(
        OPERATIONS_PREFUNDS,
        scope_options=(
            ScopeOption(
                "status", "statusList", "Private historical status.", repeat=True
            ),
            ScopeOption("business", "prefundingBizNo", "Validated business identity."),
        ),
    )
    capability = ApplicationCapability(history_spec)
    scope = {"statusList": ["APPROVED_FINAL"], "prefundingBizNo": business}
    history = collect_liquidity_scope(
        capability,
        session.transport(capability),
        encode_scope(scope),
        deadline=deadline,
    )
    history_captured_at = now().isoformat()
    current_scope = {"statusList": ["APPROVED", "CLOSED"], "prefundingBizNo": business}
    current = collect_liquidity_scope(
        capability,
        session.transport(capability),
        encode_scope(current_scope),
        deadline=deadline,
    )
    current_captured_at = now().isoformat()
    if {row["id"] for row in history.records}.intersection(
        row["id"] for row in current.records
    ):
        _invalid("prefund application appears in conflicting historical/current scopes")
    members = {root["id"]: root["version"]}
    versions = {root["version"]: root["id"]}
    for row in [*history.records, *current.records]:
        _tenant(row)
        if (
            not _text(row.get("id"))
            or type(row.get("version")) is not int
            or row["version"] < 0
            or row.get("status") not in ("APPROVED_FINAL", "APPROVED", "CLOSED")
            or row.get("prefundingBizNo") != business
        ):
            _invalid("historical prefund identity or business scope is invalid")
        if row.get("instId") != root["instId"]:
            _invalid("prefund application entity contradicts selected business")
        identity, version = row["id"], row["version"]
        if (identity in members and members[identity] != version) or (
            version in versions and versions[version] != identity
        ):
            _invalid("conflicting prefund application identity or version")
        members[identity] = version
        versions[version] = identity
    components = {
        "application": _component(
            {"preFundingId": root["id"], "tntInstId": TENANT},
            captured_at,
            application_reported,
            1,
            "application",
            "prefund-selected-native-detail-v1",
            [],
        ),
        "historyApplications": _component(
            {"tntInstId": TENANT, **scope},
            history_captured_at,
            history.total_count,
            len(history.records),
            "application",
            "prefund-approved-final-offset-v1",
            list(history.evidence.reasons),
            arrivals=history.evidence.arrivals,
        ),
    }
    components["application"]["reported_count_unit"] = "unknown"
    selected = [
        row for row in [*history.records, *current.records] if row["id"] == root["id"]
    ]
    consistency_fields = (
        "id",
        "version",
        "status",
        "prefundingBizNo",
        "instId",
        "currency",
        "bizLine",
        "bizProject",
        "amount",
        "allowUseAmount",
        "usedAmount",
        "gmtModified",
    )
    changed = any(
        any(
            field in root and field in row and root[field] != row[field]
            for field in consistency_fields
        )
        for row in selected
    )
    if not selected and root.get("status") in ("APPROVED_FINAL", "APPROVED", "CLOSED"):
        changed = True
    components["application"]["selected_version_relation"] = (
        "changed"
        if changed
        else "matched"
        if selected
        else "not_in_final_version_scopes"
    )
    if changed:
        components["application"]["reasons"].append("SOURCE_CHANGED")
        components["application"]["complete"] = False
    components["historyApplications"]["version_membership"] = _component(
        {"tntInstId": TENANT, **current_scope},
        current_captured_at,
        current.total_count,
        len(current.records),
        "application",
        "prefund-current-business-offset-v1",
        list(current.evidence.reasons),
        arrivals=current.evidence.arrivals,
    )
    components["historyApplications"]["reasons"].extend(current.evidence.reasons)
    components["historyApplications"]["complete"] = not components[
        "historyApplications"
    ]["reasons"]
    capability = LiquidityDetailCapability(TRANSACTIONS)
    values = {"business": business}
    body = capability.detail_body(values)
    response = collect_mod.execute_bounded(
        capability, session.transport(capability), body, deadline
    )
    rows = capability.parse_detail(response.body, values)
    document = envelope_document(response.body, TRANSACTIONS.envelope)
    reported = dig(document, ("result", "count"))
    if type(reported) is not int or reported < 0:
        _invalid("prefund transaction count is not a nonnegative integer")
    seen: dict[str, str] = {}
    transactions = []
    for row in rows:
        if row.get("tntInstId") != TENANT:
            _invalid("prefund transaction tenant does not match requested source")
        if not _text(row.get("preFundingUseDetailId")):
            _invalid("prefund transaction has no native identity")
        if row.get("prefundingBizNo") not in (None, "", business):
            _invalid("prefund transaction business scope contradicts request")
        if (
            not _text(row.get("preFundingOrderId"))
            or row["preFundingOrderId"] not in members
        ):
            _invalid(
                "prefund transaction application is outside validated business versions"
            )
        relations = row.get("useRevertRelationVOList")
        if relations is not None and (
            not isinstance(relations, list)
            or any(not isinstance(item, dict) for item in relations)
        ):
            _invalid("prefund exchange relations are not an array of objects")
        identity = row["preFundingUseDetailId"]
        content = canonical(row)
        if identity in seen:
            if seen[identity] != content:
                _invalid("conflicting prefund transaction identity")
            continue
        seen[identity] = content
        transactions.append(row)
    reasons = ["DRAWDOWN_COVERAGE_UNPROVEN"]
    if reported == 0 and rows:
        reasons.append("ZERO_COUNT_NONEMPTY")
    elif reported != len(rows):
        reasons.append("COUNT_MISMATCH")
    if len(rows) != len(transactions):
        reasons.append("DUPLICATE_IDENTITIES")
    components["drawdownDetails"] = _component(
        body,
        now().isoformat(),
        reported,
        len(transactions),
        "transaction",
        TRANSACTIONS.schema_version,
        reasons,
        arrivals=len(rows),
    )
    components["drawdownDetails"]["reported_count_unit"] = "unknown"
    components["drawdownDetails"]["pagination"] = (
        "native array; server pagination, truncation and exhaustion are unproven"
    )
    collect_mod.remaining_seconds(deadline)
    reasons = tuple(
        reason for item in components.values() for reason in item["reasons"]
    )
    evidence = AcquisitionEvidence(
        scope_complete=not reasons,
        dataset_complete=not reasons,
        collected_total=1,
        reported_total=1,
        total_semantics="applications",
        reasons=reasons,
    )
    return {
        **root,
        "historyApplications": history.records,
        "drawdownDetails": transactions,
    }, {
        **evidence.meta(),
        "components": components,
        "snapshot_consistency": "sequential source reads; no atomic snapshot guarantee",
        "validated_application_ids": list(members),
        "request_budget": {
            "shared_timeout_seconds": collect_mod.REFRESH_BUDGET_SECONDS,
            "max_history_pages": collect_mod.MAX_PAGES,
            "max_current_membership_pages": collect_mod.MAX_PAGES,
            "transaction_requests": 1,
        },
    }
