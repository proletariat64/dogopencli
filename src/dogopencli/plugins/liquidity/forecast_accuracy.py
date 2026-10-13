"""One native creation-query day and account, with required metric composition."""

from __future__ import annotations

import json
import re
import time
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ... import collect as collect_mod
from ...browser.environment import LIQUIDITY_STARTUP_URL
from ...errors import (
    EXIT_USAGE,
    INCOMPLETE_RESULT,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    CliError,
)
from ...jsonutil import canonical
from ...result_policy import AcquisitionEvidence
from .. import EndpointContract
from .envelope import dig, envelope_document
from .spec import (
    ENV_RESULT_FLAG,
    HOST,
    PAGE_SINGLE,
    PROFILE_HISTORY,
    RUNTIMES,
    TENANT,
    ListSpec,
    ScopeOption,
)

if TYPE_CHECKING:
    from ...collect import CollectedScope


BASE_FIELDS = (
    "id",
    "bankAccountAliasName",
    "currency",
    "valueDate",
    "baseValueDate",
    "recordCreateTime",
    "forecastBalance",
    "cashFlowTransIn",
    "cashFlowTransOut",
    "forecastTaskId",
    "forecastBatchNo",
    "forecastRuleId",
)
METRIC_FIELDS = (
    "cashFlowAccuracy",
    "cashFlowInflow",
    "cashFlowOutflow",
    "flowAccuracy",
    "inflowAccuracy",
    "outflowAccuracy",
    "realTrafficAmount",
    "realizedBalance",
    "realizedInflow",
    "realizedOutflow",
    "trafficForecastAmount",
)
BINDING_FIELDS = ("valueDate", "accountNo", "instId", "currency", "bankId")
BASE_LIMIT = 100
FORECAST_ACCURACY = ListSpec(
    path=("forecast", "accuracy"),
    kind=RUNTIMES,
    title="bounded native forecast accuracy snapshots",
    endpoint="/bankCashForecastRecordAccuracyQuery.json",
    method="GET",
    envelope=ENV_RESULT_FLAG,
    container=("result", "dataValue"),
    total=("result", "count"),
    require_inner_success=True,
    identity=("id",),
    pagination=PAGE_SINGLE,
    profile=PROFILE_HISTORY,
    page_size=5000,
    vo_field="bankCashForecastRecordQueryVo",
    template={
        "tntInstId": TENANT,
        "bankCashForecastRecordQueryVo": {
            "tntInstId": TENANT,
            "recordStartTime": "000000",
            "recordEndTime": "235959",
        },
    },
    scope_options=(
        ScopeOption(
            "account",
            "aliasName",
            "One native account alias.",
            required=True,
            repeat=True,
            canonical_flag="--account-alias",
            min_values=1,
            max_values=1,
        ),
        ScopeOption(
            "record_date",
            "recordDate",
            "Native GMT Create Date/Time query day (YYYY-MM-DD); server "
            "timezone unknown.",
            required=True,
            virtual=True,
            iso_date=True,
        ),
    ),
    table_columns=(
        "id",
        "bankAccountAliasName",
        "currency",
        "valueDate",
        "forecastBalance",
        "accuracy",
    ),
    projection="forecast_accuracy",
    schema_version="forecast-accuracy-composition-v1",
    notes=(
        "Required one account and one record-date (YYYY-MM-DD); fixed native "
        "query day and full creation time range. GMT is a UI label, not a "
        "verified server timezone.",
        "valueDate and baseValueDate remain distinct from record-date. "
        "Acquisition scope remains visible; one temporary result replaces "
        "the previous account/day query.",
        "One base response must prove arrivals = unique id = reported count "
        "before any metric requests; client scope budget is 100 base records, "
        "not a backend capacity rule.",
        "Every base record requires native GET /cashFlowDetailDay.json "
        "metrics bound to this acquisition's row. Missing metrics or bindings "
        "fail the entire inquiry; no base-only publication.",
        "accuracy metrics are raw native values, without ratios, scaling, "
        "formula checks or zero replacement. The backend metric object has no "
        "required record echo: association is native request binding.",
        "Composition shares the existing acquisition deadline and request "
        "retry budget. No new getter or detail cache is created; live never "
        "writes cache.",
    ),
)


def validate_query(values: dict[str, Any]) -> None:
    day = values.get("recordDate")
    try:
        if (
            not isinstance(day, str)
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day) is None
        ):
            raise ValueError
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError as error:
        raise CliError(
            INVALID_ARGUMENT,
            "--record-date must be a valid YYYY-MM-DD",
            exit_code=EXIT_USAGE,
        ) from error
    aliases = values.get("aliasName")
    if (
        not isinstance(aliases, list)
        or len(aliases) != 1
        or not isinstance(aliases[0], str)
        or not aliases[0].strip()
    ):
        raise CliError(
            INVALID_ARGUMENT,
            "--account-alias requires one nonempty alias",
            exit_code=EXIT_USAGE,
        )


def base_body(values: dict[str, Any]) -> dict[str, Any]:
    validate_query(values)
    day = values["recordDate"].replace("-", "")
    vo_field = FORECAST_ACCURACY.vo_field
    if vo_field is None:
        raise CliError(
            INVALID_RESPONSE, "forecast accuracy: missing vo_field declaration"
        )
    vo = {
        **FORECAST_ACCURACY.template[vo_field],
        "rowStart": 0,
        "pageSize": 5000,
        "aliasName": values["aliasName"],
        "valueStartDay": day,
        "valueEndDay": day,
    }
    return {"tntInstId": TENANT, vo_field: json.dumps(vo)}


def _invalid(message: str) -> CliError:
    return CliError(INVALID_RESPONSE, "forecast accuracy: " + message)


def _identity(row: dict[str, Any]) -> str:
    value = row.get("id")
    if not isinstance(value, str) or not value.strip():
        raise _invalid("record id must be a nonempty native string")
    return value


def project_accuracy(row: dict[str, Any]) -> dict[str, Any]:
    _identity(row)
    metrics = row.get("accuracy")
    if not isinstance(metrics, dict):
        raise _invalid("required accuracy composition is missing")
    for source, fields in ((row, BASE_FIELDS), (metrics, METRIC_FIELDS)):
        if any(isinstance(source.get(field), (dict, list)) for field in fields):
            raise _invalid("projected native field must be a scalar or unknown")
    return {
        **{field: row.get(field) for field in BASE_FIELDS},
        "accuracy": {field: metrics.get(field) for field in METRIC_FIELDS},
    }


class BoundInquiry:
    """Exact inquiry payload; dynamic VO values are bound before transport."""

    page_url = LIQUIDITY_STARTUP_URL
    source_config_key = "liquidity"

    def __init__(self, name: str, path: str, body: dict[str, Any]) -> None:
        self.name = name
        self.body = body
        self.contract = EndpointContract(
            method="GET",
            host=HOST,
            path=path,
            page_size=0,
            one_based=False,
            allowed_body_keys=frozenset(body),
            fixed_body_values=tuple(body.items()),
            encoding="query",
            single_page=True,
        )


def metric_body(row: dict[str, Any], account: str) -> dict[str, Any]:
    _identity(row)
    if row.get("bankAccountAliasName") != account:
        raise _invalid("base account echo does not match requested account")
    for field in BINDING_FIELDS:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            raise _invalid("required native metric binding is missing: " + field)
    balance = row.get("forecastBalance")
    if balance is None or isinstance(balance, (dict, list, bool)):
        raise _invalid("required native metric binding is missing: forecastBalance")
    vo = {field: row[field] for field in BINDING_FIELDS}
    vo.update(
        forecastRecordId=row["id"],
        aliasName=account,
        forecastBalance="0"
        if isinstance(balance, str) and balance in ("0.0", "0.00")
        else balance,
    )
    return {"tntInstId": TENANT, "bankAccountDetailCashFlowQueryVO": canonical(vo)}


def collect_accuracy(
    session: Any,
    capability: Any,
    scope: str,
    *,
    budget_seconds: float | None = None,
    progress: Any = None,
) -> CollectedScope:
    from ...collect import CollectedScope
    from .capability import decode_scope

    budget = (
        collect_mod.REFRESH_BUDGET_SECONDS if budget_seconds is None else budget_seconds
    )
    deadline = time.monotonic() + budget
    values = decode_scope(scope)
    body = base_body(values)
    base = BoundInquiry(capability.name, FORECAST_ACCURACY.endpoint, body)
    response = collect_mod.execute_bounded(
        base, session.transport(base), body, deadline
    )
    # A raw descriptor preserves private request bindings only inside this call.
    from .capability import LiquidityListCapability

    parser = LiquidityListCapability(replace(FORECAST_ACCURACY, projection=""))
    rows, total = parser.parse_rows(response.body)
    seen: dict[str, str] = {}
    for row in rows:
        identity = _identity(row)
        content = canonical(
            {field: row.get(field) for field in (*BASE_FIELDS, *BINDING_FIELDS)}
        )
        if identity in seen and seen[identity] != content:
            raise _invalid("conflicting base content for native record identity")
        seen[identity] = content
        if row.get("bankAccountAliasName") != values["aliasName"][0]:
            raise _invalid("base account echo does not match requested account")
        if "tntInstId" in row and row["tntInstId"] != TENANT:
            raise _invalid("base tenant echo does not match request")
    if len(rows) != len(seen) or len(seen) != total:
        raise CliError(
            INCOMPLETE_RESULT,
            "forecast accuracy base scope coverage is unproven; no composed candidate",
        )
    if len(rows) > BASE_LIMIT:
        raise CliError(
            INCOMPLETE_RESULT,
            "forecast accuracy client scope budget exceeds 100 base records; "
            "no composed candidate",
        )
    # Validate every binding before starting fan-out.
    bodies = [metric_body(row, values["aliasName"][0]) for row in rows]
    composed = []
    for index, (row, metric_request) in enumerate(zip(rows, bodies, strict=True)):
        metric = BoundInquiry(
            capability.name + ".native-metric",
            "/cashFlowDetailDay.json",
            metric_request,
        )
        transport = session.transport(metric)
        try:
            response = collect_mod.execute_bounded(
                metric, transport, metric_request, deadline
            )
        finally:
            transport.close()
        document = envelope_document(response.body, ENV_RESULT_FLAG)
        inner_success = dig(document, ("result", "success"))
        if not isinstance(inner_success, bool) or not inner_success:
            raise _invalid("metric inner success marker is not true")
        metrics = dig(document, ("result", "bankAccountDetailDayVO"))
        if not isinstance(metrics, dict):
            raise _invalid("metric container must be an object")
        composed.append(project_accuracy({**row, "accuracy": metrics}))
        if progress is not None:
            progress(index + 1, len(rows))
    collect_mod.remaining_seconds(deadline)
    evidence = AcquisitionEvidence.for_collection(
        complete=True,
        reported_total=total,
        collected_total=len(composed),
        arrivals=len(rows),
        attempts=(
            {
                "composition": "native-request-binding",
                "base_arrivals": len(rows),
                "base_unique": len(seen),
                "base_reported_total": total,
                "metric_succeeded": len(composed),
                "client_base_limit": BASE_LIMIT,
                "shared_budget_seconds": budget,
                "backend_metric_echo": "not-required",
            },
        ),
    )
    return CollectedScope(composed, True, total, 5000, 1, False, deadline, evidence)
