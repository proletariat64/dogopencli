"""Bounded native account-capacity inquiry for issue #111."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ...errors import EXIT_USAGE, INVALID_ARGUMENT, INVALID_RESPONSE, CliError
from ...result_policy import AcquisitionEvidence
from .spec import (
    ENV_SUCCESS,
    PAGE_SINGLE,
    PROFILE_HISTORY,
    RUNTIMES,
    ListSpec,
    ScopeOption,
)

if TYPE_CHECKING:
    from ...collect import CollectedScope

FIELDS = (
    "aliasName",
    "currency",
    "accountAvailableBalance",
    "availableIod",
    "availableResource",
    "cashPoolSupportAvailableResource",
    "outFlowCapacity",
    "totalIod",
    "usedIod",
    "valueTime",
)
# Native probes observed strings for all ten fields. These sampled types
# describe evidence; optional value types are not business validation rules.
SAMPLED_FIELDS = dict.fromkeys(FIELDS, "str")
MAX_ACCOUNTS = 10

ACCOUNT_CAPACITY = ListSpec(
    path=("risk", "account-capacity"),
    kind=RUNTIMES,
    title="capacity snapshots for an explicit account set",
    endpoint="/api/fund/capacity/queryFundCapacityByAliasName.json",
    method="GET",
    envelope=ENV_SUCCESS,
    container=("data",),
    identity=("aliasName",),
    pagination=PAGE_SINGLE,
    paged_request=False,
    profile=PROFILE_HISTORY,
    projection="account_capacity",
    schema_version="account-capacity-runtimes-v1",
    scope_options=(
        ScopeOption(
            "account",
            "aliasName",
            "Explicit native account alias; repeat for 1–10 distinct accounts.",
            required=True,
            repeat=True,
            canonical_flag="--account-alias",
            min_values=1,
            max_values=10,
        ),
    ),
    table_columns=("aliasName", "currency", "availableResource", "valueTime"),
    notes=(
        "One GET per explicit alias, with only aliasName; no dates, tenant "
        "parameter, pagination or automatic account discovery.",
        "Aliases form a sorted exact cache scope. The 10-account fan-out "
        "budget is a client bound; --all affects only display.",
        "Complete means one validated native object for every requested alias; "
        "requested_count/resolved_count describe this set, reported_total is "
        "null because there is no native global account total.",
        "Any failed request or alias echo invalidates the entire candidate; "
        "no skipped accounts, synthetic empty rows or capacity fallback.",
        "aliasName is native identity within the authorized tenant/origin; "
        "currency and valueTime are separate native attributes.",
        "UI labels accountAvailableBalance as Avl Bal, availableIod as Avl IOD "
        "and availableResource as Outflow Capacity. outFlowCapacity and "
        "cashPoolSupportAvailableResource keep their native names and unknown "
        "business definitions; neither substitutes for availableResource.",
        "Native amounts, precision, null, empty, zero, negative and unknown "
        "values remain unchanged; no arithmetic, currency audit or scaling.",
        "valueTime stays the original source-time string; its timezone is "
        "unknown and fetched_at is independent capture time.",
        "Independent history captures cover only the exact requested account "
        "set; no account enumeration, detail or history command is enabled.",
    ),
)


def validate_capacity_query(values: dict[str, Any]) -> None:
    aliases = values.get("aliasName")
    if (
        not isinstance(aliases, list)
        or not 1 <= len(aliases) <= MAX_ACCOUNTS
        or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
        or len(set(aliases)) != len(aliases)
    ):
        raise CliError(
            INVALID_ARGUMENT,
            "--account-alias needs 1–10 distinct nonempty native aliases",
            exit_code=EXIT_USAGE,
        )
    values["aliasName"] = sorted(aliases)


def project_capacity(row: dict[str, Any]) -> dict[str, Any]:
    alias = row.get("aliasName")
    if not isinstance(alias, str) or not alias.strip():
        raise CliError(INVALID_RESPONSE, "capacity aliasName must be a native string")
    return {field: row[field] for field in FIELDS if field in row}


def collect_capacity(
    capability: Any,
    transport: Any,
    scope: str,
    deadline: float,
    progress: Callable[[int, int], None] | None,
) -> CollectedScope:
    # Imported lazily: built-in registration can occur while core collect
    # is still initializing during a fresh public CLI process.
    from ... import collect as collect_mod
    from ...collect import CollectedScope
    from .capability import decode_scope

    values = decode_scope(scope)
    validate_capacity_query(values)
    aliases = values["aliasName"]
    records = []
    for alias in aliases:
        response = collect_mod.execute_bounded(
            capability, transport, {"aliasName": alias}, deadline
        )
        rows, _ = capability.parse_rows(response.body)
        if len(rows) != 1 or rows[0].get("aliasName") != alias:
            raise CliError(INVALID_RESPONSE, "capacity aliasName echo mismatch")
        records.extend(rows)
        if progress is not None:
            progress(len(records), len(aliases))
    collect_mod.remaining_seconds(deadline)
    evidence = replace(
        AcquisitionEvidence.for_collection(
            complete=True,
            reported_total=None,
            collected_total=len(records),
            arrivals=len(records),
            total_semantics="requested_accounts",
        ),
        requested_count=len(aliases),
        resolved_count=len(records),
    )
    return CollectedScope(
        records=records,
        complete=True,
        total_count=None,
        page_size=1,
        pages=len(records),
        rebuilt=False,
        deadline=deadline,
        evidence=evidence,
    )
