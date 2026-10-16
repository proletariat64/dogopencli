"""Shared acquisition evidence and result decisions, independent of storage.

Only validated candidates reach this policy. Domain failures are never caught
or converted to partial success here; publishing remains a domain transaction.
"""

import sys
from dataclasses import dataclass
from typing import Any

from .errors import INCOMPLETE_RESULT, INVALID_RESPONSE, CliError
from .execution import observe_result

BANK_ROW_OCCURRENCES = "bank_row_occurrences_latest_gmtCreate"


@dataclass(frozen=True)
class AcquisitionEvidence:
    scope_complete: bool
    dataset_complete: bool
    collected_total: int
    reported_total: int | None = None
    arrivals: int | None = None
    unique_count: int | None = None
    duplicate_count: int | None = None
    total_semantics: str = "unknown"
    reasons: tuple[str, ...] = ()
    attempts: tuple[dict[str, Any], ...] = ()
    requested_count: int | None = None
    resolved_count: int | None = None

    @classmethod
    def for_collection(
        cls,
        *,
        complete: bool,
        reported_total: int | None,
        collected_total: int,
        arrivals: int | None = None,
        has_identity: bool = True,
        total_semantics: str | None = None,
        duplicate_policy: str = "conservative",
        reasons: tuple[str, ...] = (),
        attempts: tuple[dict[str, Any], ...] = (),
    ) -> "AcquisitionEvidence":
        # Bank's native total counts date groups while collected_total counts rows.
        comparable = total_semantics != "quote_date_groups"
        if (
            comparable
            and reported_total is not None
            and collected_total > reported_total
        ):
            raise CliError(INVALID_RESPONSE, "unique records exceed reported total")
        codes = list(reasons)
        duplicate_count = (
            arrivals - collected_total
            if has_identity and arrivals is not None
            else None
        )
        if duplicate_count is not None and duplicate_count < 0:
            raise CliError(INVALID_RESPONSE, "invalid acquisition arrival count")
        semantics = total_semantics or (
            "unique_objects" if has_identity else "occurrences"
        )
        if (
            comparable
            and reported_total is not None
            and collected_total < reported_total
        ):
            codes.append("COUNT_SHORTFALL")
            complete = False
        if duplicate_count:
            codes.append("DUPLICATE_ROWS")
            if duplicate_policy != "allow_identical_overlap":
                codes.append("UNEXPECTED_DUPLICATE_ROWS")
                complete = False
            elif semantics != "unique_objects":
                raise CliError(
                    INVALID_RESPONSE, "duplicate tolerance needs unique total"
                )
        if not complete and not codes:
            codes.append("COVERAGE_UNPROVEN")
        return cls(
            scope_complete=complete,
            dataset_complete=complete,
            reported_total=reported_total,
            collected_total=collected_total,
            arrivals=arrivals,
            unique_count=collected_total if has_identity else None,
            duplicate_count=duplicate_count,
            total_semantics=semantics,
            reasons=tuple(dict.fromkeys(codes)),
            attempts=attempts,
        )

    def record(self) -> dict[str, Any]:
        record = {
            "scope_complete": self.scope_complete,
            "dataset_complete": self.dataset_complete,
            "reported_total": self.reported_total,
            "collected_total": self.collected_total,
            "arrivals": self.arrivals,
            "unique_count": self.unique_count,
            "duplicate_count": self.duplicate_count,
            "total_semantics": self.total_semantics,
            "reasons": list(self.reasons),
            "attempts": list(self.attempts),
        }
        if self.requested_count is not None:
            record["requested_count"] = self.requested_count
            record["resolved_count"] = self.resolved_count
        return record

    @classmethod
    def from_record(cls, record: Any) -> "AcquisitionEvidence":
        if not isinstance(record, dict):
            raise CliError(INVALID_RESPONSE, "cached acquisition evidence is invalid")
        for flag in ("scope_complete", "dataset_complete"):
            if not isinstance(record.get(flag), bool):
                raise CliError(INVALID_RESPONSE, "cached acquisition flags are invalid")
        for key in (
            "collected_total",
            "reported_total",
            "arrivals",
            "unique_count",
            "duplicate_count",
            "requested_count",
            "resolved_count",
        ):
            value = record.get(key)
            if value is None and key != "collected_total":
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CliError(
                    INVALID_RESPONSE, "cached acquisition counts are invalid"
                )
        reasons = record.get("reasons", [])
        attempts = record.get("attempts", [])
        if (
            not isinstance(reasons, list)
            or any(not isinstance(code, str) for code in reasons)
            or not isinstance(attempts, list)
            or any(not isinstance(item, dict) for item in attempts)
            or not isinstance(record.get("total_semantics", "unknown"), str)
        ):
            raise CliError(INVALID_RESPONSE, "cached acquisition reasons are invalid")
        evidence = cls(
            scope_complete=record["scope_complete"],
            dataset_complete=record["dataset_complete"],
            collected_total=record["collected_total"],
            reported_total=record.get("reported_total"),
            arrivals=record.get("arrivals"),
            unique_count=record.get("unique_count"),
            duplicate_count=record.get("duplicate_count"),
            total_semantics=record.get("total_semantics", "unknown"),
            reasons=tuple(reasons),
            attempts=tuple(attempts),
            requested_count=record.get("requested_count"),
            resolved_count=record.get("resolved_count"),
        )
        if (evidence.requested_count is None) != (evidence.resolved_count is None) or (
            evidence.requested_count is not None
            and evidence.resolved_count is not None
            and (
                evidence.resolved_count > evidence.requested_count
                or evidence.resolved_count != evidence.collected_total
                or (
                    evidence.scope_complete
                    and evidence.resolved_count != evidence.requested_count
                )
            )
        ):
            raise CliError(INVALID_RESPONSE, "cached requested scope counts conflict")
        if (
            (
                evidence.unique_count is not None
                and evidence.unique_count != evidence.collected_total
            )
            or (
                evidence.arrivals is not None
                and evidence.arrivals < evidence.collected_total
            )
            or (
                evidence.duplicate_count is not None
                and (
                    evidence.arrivals is None
                    or evidence.unique_count is None
                    or evidence.duplicate_count
                    != evidence.arrivals - evidence.unique_count
                )
            )
            or (
                evidence.total_semantics != "quote_date_groups"
                and evidence.reported_total is not None
                and evidence.collected_total > evidence.reported_total
            )
            or (
                evidence.scope_complete
                and evidence.total_semantics
                not in ("quote_date_groups", BANK_ROW_OCCURRENCES)
                and evidence.reported_total is not None
                and evidence.collected_total != evidence.reported_total
            )
            or (
                evidence.scope_complete
                and "UNEXPECTED_DUPLICATE_ROWS" in evidence.reasons
            )
        ):
            raise CliError(INVALID_RESPONSE, "cached acquisition evidence conflicts")
        if evidence.total_semantics == BANK_ROW_OCCURRENCES:
            selections = [
                item
                for item in attempts
                if item.get("contract") == "bank-blacklist-latest-gmtCreate-v1"
            ]
            if (
                evidence.reported_total is None
                or evidence.arrivals is None
                or evidence.arrivals > evidence.reported_total
                or evidence.unique_count is None
                or evidence.duplicate_count is None
                or evidence.dataset_complete is not evidence.scope_complete
                or (
                    evidence.scope_complete
                    and evidence.arrivals != evidence.reported_total
                )
                or len(selections) != 1
                or type(selections[0].get("raw_rows")) is not int
                or type(selections[0].get("selected_banks")) is not int
                or selections[0].get("raw_rows") != evidence.arrivals
                or selections[0].get("selected_banks") != evidence.collected_total
                or selections[0].get("raw_coverage_complete")
                is not evidence.scope_complete
                or bool(evidence.duplicate_count)
                != ("BANK_LATEST_CREATED_SELECTED" in evidence.reasons)
            ):
                raise CliError(
                    INVALID_RESPONSE, "cached bank selection evidence conflicts"
                )
        return evidence

    def meta(self) -> dict[str, Any]:
        comparable = self.reported_total is not None and self.total_semantics in (
            "unique_objects",
            "occurrences",
        )
        missing = (
            max(0, self.reported_total - self.collected_total) if comparable else None
        )
        ratio = (
            self.collected_total / self.reported_total
            if comparable and self.reported_total
            else None
        )
        if (
            self.total_semantics == BANK_ROW_OCCURRENCES
            and self.reported_total is not None
        ):
            missing = max(0, self.reported_total - (self.arrivals or 0))
            ratio = self.arrivals / self.reported_total if self.reported_total else None
        result = {
            "complete": self.scope_complete,
            "dataset_complete": self.dataset_complete,
            "reported_total": self.reported_total,
            "collected_total": self.collected_total,
            "missing_count": missing,
            "coverage_ratio": ratio,
            "acquisition": self.record(),
        }
        if self.requested_count is not None:
            result["requested_count"] = self.requested_count
            result["resolved_count"] = self.resolved_count
        return result


def evidence_for(result: Any) -> AcquisitionEvidence:
    """Compatibility adapter for existing registered collectors."""
    evidence = getattr(result, "evidence", None)
    if evidence is not None:
        return evidence
    return AcquisitionEvidence.for_collection(
        complete=result.complete,
        reported_total=result.total_count,
        collected_total=len(result.records),
    )


@dataclass(frozen=True)
class ResultDecision:
    expose_data: bool
    publishable: bool
    warnings: tuple[dict[str, Any], ...]
    error: dict[str, Any] | None
    exit_code: int


def evaluate_result(
    evidence: AcquisitionEvidence,
    *,
    mode: str,
    require_complete: bool = False,
    complete_only: bool = False,
) -> ResultDecision:
    incomplete = not (evidence.scope_complete and evidence.dataset_complete)
    reasons = list(evidence.reasons)
    if incomplete and not reasons:
        reasons = ["COVERAGE_UNPROVEN"]
    warnings: tuple[dict[str, Any], ...] = ()
    message = (
        f"result is incomplete (collected {evidence.collected_total},"
        f" reported {evidence.reported_total}); reasons: {', '.join(reasons)}"
    )
    if incomplete or reasons:
        warning_code = INCOMPLETE_RESULT
        warning_message = message
        if not incomplete:
            if evidence.total_semantics == BANK_ROW_OCCURRENCES:
                if evidence.duplicate_count:
                    warning_code = "BANK_LATEST_CREATED_SELECTED"
                    warning_message = (
                        "selected latest gmtCreate per bankId; "
                        f"{evidence.duplicate_count} additional native bank rows"
                        " omitted"
                    )
                else:
                    warning_code = reasons[0]
                    warning_message = "bank acquisition warnings: " + ", ".join(reasons)
            else:
                warning_code = "DUPLICATE_ROWS"
                warning_message = "identical duplicate rows removed"
        warnings = (
            {
                "code": warning_code,
                "message": warning_message,
                "reason_codes": reasons,
                "retryable": False,
            },
        )
    rejected = incomplete and (require_complete or complete_only)
    error = (
        {"code": INCOMPLETE_RESULT, "message": message, "retryable": False}
        if rejected
        else None
    )
    return ResultDecision(
        expose_data=not rejected,
        publishable=mode == "refresh" and not rejected,
        warnings=warnings,
        error=error,
        exit_code=1 if rejected else 0,
    )


def check_complete(
    evidence: AcquisitionEvidence, *, require_complete: bool, mode: str = "live"
) -> None:
    decision = evaluate_result(evidence, mode=mode, require_complete=require_complete)
    if decision.error is not None:
        meta = evidence.meta()
        meta["warnings"] = list(decision.warnings)
        if mode == "refresh":
            meta["published"] = False
        raise CliError(INCOMPLETE_RESULT, decision.error["message"], meta=meta)


def prepare_result(
    meta: dict[str, Any], *, require_complete: bool = False, mode: str = "cache"
) -> dict[str, Any]:
    """Apply one decision and render its diagnostics at the output boundary."""
    if "complete" not in meta:
        return meta
    if meta.get("acquisition") is not None:
        evidence = AcquisitionEvidence.from_record(meta["acquisition"])
        if meta["complete"] is not evidence.scope_complete or (
            meta.get("dataset_complete") is not None
            and meta["dataset_complete"] is not evidence.dataset_complete
        ):
            raise CliError(INVALID_RESPONSE, "output acquisition evidence conflicts")
    else:
        evidence = AcquisitionEvidence(
            scope_complete=meta["complete"],
            dataset_complete=meta.get("dataset_complete") is not False,
            collected_total=meta.get("collected_total", meta.get("matched_total", 0)),
        )
    check_complete(evidence, require_complete=require_complete, mode=mode)
    decision = evaluate_result(evidence, mode=mode)
    output = {**meta, **evidence.meta()}
    if decision.warnings:
        output["warnings"] = list(decision.warnings)
        for warning in decision.warnings:
            print(f"warning: {warning['code']}: {warning['message']}", file=sys.stderr)
    observe_result(output)
    return output
