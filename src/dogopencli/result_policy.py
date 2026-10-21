"""Shared acquisition evidence and result decisions, independent of storage.

Only validated candidates reach this policy. Domain failures are never caught
or converted to partial success here; publishing remains a domain transaction.
"""

import sys
from dataclasses import dataclass
from typing import Any

from .errors import INCOMPLETE_RESULT, INVALID_RESPONSE, CliError

SOURCE_ROW_OCCURRENCES = "source_row_occurrences"


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
    coverage_basis: str | None = None
    sources: dict[str, dict[str, Any]] | None = None

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
        coverage_basis: str | None = None,
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
            elif semantics != "unique_objects" and not (
                semantics == "unknown"
                and reported_total is None
                and coverage_basis == "accepted_short_page"
            ):
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
            coverage_basis=coverage_basis,
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
        if self.coverage_basis is not None:
            record["coverage_basis"] = self.coverage_basis
        if self.sources is not None:
            record["sources"] = self.sources
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
        coverage_basis = record.get("coverage_basis")
        sources = record.get("sources")
        if (
            not isinstance(reasons, list)
            or any(not isinstance(code, str) for code in reasons)
            or not isinstance(attempts, list)
            or any(not isinstance(item, dict) for item in attempts)
            or not isinstance(record.get("total_semantics", "unknown"), str)
            or coverage_basis
            not in (
                None,
                "qualified_single_response",
                "qualified_short_page",
                "accepted_short_page",
                "validated_sources",
            )
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
            coverage_basis=coverage_basis,
            sources=sources,
        )
        if coverage_basis in {
            "qualified_single_response",
            "qualified_short_page",
            "accepted_short_page",
        } and (
            evidence.reported_total is not None
            or evidence.total_semantics != "unknown"
            or evidence.unique_count is None
            or sources is not None
            or evidence.dataset_complete is not evidence.scope_complete
            or (
                coverage_basis != "accepted_short_page"
                and evidence.scope_complete
                and evidence.duplicate_count != 0
            )
        ):
            raise CliError(
                INVALID_RESPONSE, "cached single-response coverage conflicts"
            )
        if (
            coverage_basis in {"qualified_short_page", "accepted_short_page"}
            and evidence.scope_complete
        ):
            last = next(
                (
                    attempt
                    for attempt in reversed(attempts)
                    if attempt.get("kind") != "custom_query"
                ),
                {},
            )
            if coverage_basis == "accepted_short_page" and (
                "IDENTITY_CONTENT_CONFLICT" in reasons
                or last.get("conflict_count") != 0
            ):
                raise CliError(
                    INVALID_RESPONSE, "cached accepted traversal has conflicts"
                )
            terminal = last.get("terminal_batches")
            size = last.get("page_size")
            if (
                last.get("termination_reason")
                not in {"two_empty_batches", "two_clamped_batches"}
                or not isinstance(terminal, list)
                or len(terminal) != 2
                or type(size) is not int
                or size < 1
                or any(
                    not isinstance(item, dict)
                    or type(item.get("start")) is not int
                    or item["start"] < 0
                    or item.get("size") != size
                    for item in terminal
                )
                or terminal[1]["start"] != terminal[0]["start"] + size
            ):
                raise CliError(
                    INVALID_RESPONSE, "cached short-page termination is missing"
                )
            clamped = last["termination_reason"] == "two_clamped_batches"
            for item in terminal:
                witness = item.get("native_terminal")
                if not clamped:
                    if witness is not None:
                        raise CliError(
                            INVALID_RESPONSE, "cached terminal kind conflicts"
                        )
                    continue
                if (
                    not isinstance(witness, dict)
                    or witness.get("kind") != "repeated_short_page"
                    or type(witness.get("requested_page")) is not int
                    or type(witness.get("native_page")) is not int
                    or witness["native_page"] < 1
                    or witness["requested_page"] != item["start"] // size + 1
                    or witness["requested_page"] <= witness["native_page"]
                    or type(witness.get("native_rows")) is not int
                    or not 0 < witness["native_rows"] < size
                    or last.get("source_end")
                    != (witness["native_page"] - 1) * size + witness["native_rows"]
                ):
                    raise CliError(
                        INVALID_RESPONSE, "cached clamped terminal is invalid"
                    )
            holes = last.get("holes")
            end = last.get("source_end")
            if (
                not isinstance(holes, list)
                or type(end) is not int
                or end < 0
                or end > terminal[0]["start"]
                or any(
                    not isinstance(hole, dict)
                    or type(hole.get("start")) is not int
                    or type(hole.get("end")) is not int
                    or not 0 <= hole["start"] < hole["end"] <= end
                    or hole.get("kind") not in ("empty", "error")
                    for hole in holes
                )
                or last.get("hole_count")
                != sum(hole["end"] - hole["start"] for hole in holes)
                or any(
                    a["end"] > b["start"]
                    for a, b in zip(holes, holes[1:], strict=False)
                )
                or bool(holes) != ("PAGINATION_HOLES_BYPASSED" in reasons)
            ):
                raise CliError(INVALID_RESPONSE, "cached short-page holes are invalid")
        if (
            sources is not None
            or coverage_basis == "validated_sources"
            or evidence.total_semantics == "assembled_roots"
        ):
            if (
                coverage_basis != "validated_sources"
                or not isinstance(sources, dict)
                or not sources
                or evidence.reported_total is not None
                or evidence.total_semantics != "assembled_roots"
                or not evidence.scope_complete
                or not evidence.dataset_complete
                or evidence.unique_count != evidence.collected_total
                or evidence.duplicate_count != 0
            ):
                raise CliError(INVALID_RESPONSE, "cached source evidence is invalid")
            for name, source in sources.items():
                if (
                    not isinstance(name, str)
                    or not name
                    or not isinstance(source, dict)
                    or set(source) != {"scope", "acquisition"}
                    or not isinstance(source["scope"], str)
                    or not isinstance(source["acquisition"], dict)
                    or "sources" in source["acquisition"]
                ):
                    raise CliError(
                        INVALID_RESPONSE, "cached source evidence is invalid"
                    )
                child = cls.from_record(source["acquisition"])
                if (
                    not child.scope_complete
                    or not child.dataset_complete
                    or (
                        child.reported_total is None
                        and child.coverage_basis
                        not in {"qualified_single_response", "qualified_short_page"}
                    )
                ):
                    raise CliError(
                        INVALID_RESPONSE, "cached required source is incomplete"
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
                not in ("quote_date_groups", SOURCE_ROW_OCCURRENCES)
                and evidence.reported_total is not None
                and evidence.collected_total != evidence.reported_total
            )
            or (
                evidence.scope_complete
                and "UNEXPECTED_DUPLICATE_ROWS" in evidence.reasons
            )
        ):
            raise CliError(INVALID_RESPONSE, "cached acquisition evidence conflicts")
        if evidence.total_semantics == SOURCE_ROW_OCCURRENCES:
            selections = [
                item for item in attempts if item.get("kind") == "source_selection"
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
                or any(
                    not isinstance(selections[0].get(field), list)
                    or not selections[0][field]
                    or any(
                        not isinstance(value, str) or not value.strip()
                        for value in selections[0][field]
                    )
                    for field in ("selection_fields", "selection_order")
                )
                or type(selections[0].get("raw_rows")) is not int
                or type(selections[0].get("selected_records")) is not int
                or selections[0].get("raw_rows") != evidence.arrivals
                or selections[0].get("selected_records") != evidence.collected_total
                or selections[0].get("raw_coverage_complete")
                is not evidence.scope_complete
                or bool(evidence.duplicate_count)
                != ("SOURCE_ROWS_SELECTED" in evidence.reasons)
            ):
                raise CliError(
                    INVALID_RESPONSE, "cached source selection evidence conflicts"
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
            self.total_semantics == SOURCE_ROW_OCCURRENCES
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
            if evidence.total_semantics == SOURCE_ROW_OCCURRENCES:
                if evidence.duplicate_count:
                    warning_code = "SOURCE_ROWS_SELECTED"
                    warning_message = (
                        "selected records from independently covered native rows; "
                        f"{evidence.duplicate_count} additional source rows omitted"
                    )
                else:
                    warning_code = reasons[0]
                    warning_message = "source acquisition warnings: " + ", ".join(
                        reasons
                    )
            else:
                if "PAGINATION_HOLES_BYPASSED" in reasons:
                    warning_code = "PAGINATION_HOLES_BYPASSED"
                    warning_message = (
                        "query completed after bypassing verified pagination holes"
                    )
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
    return output
