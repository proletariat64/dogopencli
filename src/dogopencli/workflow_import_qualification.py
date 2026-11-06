"""Fail-closed import admission from frozen contracts and host acquisition evidence."""

from .errors import CliError
from .import_qualification import (
    eligible_full_list,
    safe_native,
    validate_import_qualification,
)
from .result_policy import (
    AcquisitionEvidence,
    has_identity_conflict,
    has_unrecovered_timeout,
)

SUMMARY_DIAGNOSTIC_LIMIT = 20


def reject(*reason_codes: str) -> None:
    raise CliError(
        "WORKFLOW_IMPORT_NOT_QUALIFIED",
        "Exact export is not qualified for the requested import action",
        meta={"diagnostic": {"reason_codes": list(dict.fromkeys(reason_codes))}},
    )


def contract_rules(artifact: dict) -> list[dict]:
    contract = artifact.get("import_qualification")
    if contract is None:
        reject("MISSING_IMPORT_CONTRACT")
    try:
        return validate_import_qualification(contract)
    except ValueError:
        reject("INSUFFICIENT_EVIDENCE")


def retained_diagnostics(evidence: AcquisitionEvidence) -> list[dict]:
    grouped: dict[tuple[str, str, str, str | None], int] = {}
    for attempt in evidence.attempts:
        if attempt.get("kind") != "custom_query":
            continue
        if attempt.get("operation") != "list" or not isinstance(
            attempt.get("queries"), dict
        ):
            reject("INSUFFICIENT_EVIDENCE")
        for query in attempt["queries"].values():
            if not isinstance(query, dict):
                reject("INSUFFICIENT_EVIDENCE")
            counters = {
                retention: query.get(retention, 0)
                for retention in ("failed", "refused")
            }
            if any(type(count) is not int or count < 0 for count in counters.values()):
                reject("INSUFFICIENT_EVIDENCE")
            diagnostics = query.get("diagnostics")
            if diagnostics is None:
                if any(counters.values()):
                    reject("INSUFFICIENT_EVIDENCE")
                diagnostics = []
            if not isinstance(diagnostics, list):
                reject("INSUFFICIENT_EVIDENCE")
            retained_counts = {"failed": 0, "refused": 0}
            for item in diagnostics:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("component"), str)
                    or not item["component"]
                    or not isinstance(item.get("retention"), str)
                    or item["retention"] not in {"failed", "refused"}
                    or not isinstance(item.get("code"), str)
                    or not item["code"]
                    or type(item.get("count")) is not int
                    or item["count"] < 1
                    or "native_code" not in item
                    or item["native_code"] is not None
                    and safe_native(item["native_code"]) is None
                ):
                    reject("INSUFFICIENT_EVIDENCE")
                native = safe_native(item["native_code"])
                key = (item["component"], item["retention"], item["code"], native)
                grouped[key] = grouped.get(key, 0) + item["count"]
                retained_counts[item["retention"]] += item["count"]
            if retained_counts != counters:
                reject("INSUFFICIENT_EVIDENCE")
    return [
        {
            "component": component,
            "retention": retention,
            "diagnostic_code": code,
            "native_code": native,
            "count": count,
        }
        for (component, retention, code, native), count in sorted(
            grouped.items(), key=lambda item: tuple(str(value) for value in item[0])
        )
    ]


def diagnostic_matches(diagnostic: dict, matcher: dict) -> bool:
    return (
        diagnostic["component"] == matcher["component"]
        and diagnostic["retention"] == matcher["retention"]
        and diagnostic["diagnostic_code"] == matcher["diagnostic_code"]
        and (
            "native_code" not in matcher
            or diagnostic["native_code"] == safe_native(matcher["native_code"])
        )
    )


def covers(rule: dict, reasons: list[str], diagnostics: list[dict]) -> bool:
    matched = [
        diagnostic
        for diagnostic in diagnostics
        if any(
            diagnostic_matches(diagnostic, matcher)
            for matcher in rule["retained_errors"]
        )
    ]
    return (
        set(reasons) <= set(rule["reason_codes"])
        and len(matched) == len(diagnostics)
        and (not rule["retained_errors"] or bool(matched))
    )


def qualify(artifact: dict, action: str) -> tuple[str, dict | None]:
    if artifact["state"] in {"complete_empty", "complete_nonempty"}:
        return "complete", None
    if action != "preserve":
        reject("UNSUPPORTED_ACTION")
    if not eligible_full_list(artifact):
        reject("UNSUPPORTED_OPERATION")
    rules = contract_rules(artifact)
    metadata = artifact.get("metadata")
    try:
        evidence = AcquisitionEvidence.from_record(metadata.get("acquisition"))
    except (CliError, AttributeError, KeyError, TypeError, ValueError) as error:
        raise CliError(
            "WORKFLOW_IMPORT_NOT_QUALIFIED",
            "Exact export lacks usable host acquisition evidence",
            meta={"diagnostic": {"reason_codes": ["INSUFFICIENT_EVIDENCE"]}},
        ) from error
    evidence_record = evidence.record()
    if has_identity_conflict(evidence_record) or has_unrecovered_timeout(
        evidence_record
    ):
        reject("EXPORT_NOT_USABLE")
    if (
        not evidence.usable_incomplete
        or evidence.scope_complete
        and evidence.dataset_complete
        or not evidence.reasons
        or len(evidence.reasons) != len(set(evidence.reasons))
    ):
        reject("INSUFFICIENT_EVIDENCE")
    reasons = list(evidence.reasons)
    diagnostics = retained_diagnostics(evidence)
    matching = [rule for rule in rules if covers(rule, reasons, diagnostics)]
    if len(matching) > 1:
        reject("AMBIGUOUS_QUALIFICATION")
    if not matching:
        reason_uncovered = not any(
            set(reasons) <= set(rule["reason_codes"]) for rule in rules
        )
        diagnostic_uncovered = any(
            not any(
                diagnostic_matches(diagnostic, matcher)
                for rule in rules
                for matcher in rule["retained_errors"]
            )
            for diagnostic in diagnostics
        )
        reject(
            *(["UNCOVERED_ACQUISITION_REASON"] if reason_uncovered else []),
            *(["UNCOVERED_RETAINED_DIAGNOSTIC"] if diagnostic_uncovered else []),
            *(
                []
                if reason_uncovered or diagnostic_uncovered
                else ["NO_MATCHING_IMPORT_RULE"]
            ),
        )
    rule = matching[0]
    summary = {
        "contract_version": 1,
        "rule_id": rule["id"],
        "action": action,
        "reason_codes": reasons,
        "retained_diagnostics": diagnostics[:SUMMARY_DIAGNOSTIC_LIMIT],
        "retained_diagnostic_count": sum(item["count"] for item in diagnostics),
    }
    if len(diagnostics) > SUMMARY_DIAGNOSTIC_LIMIT:
        summary["retained_diagnostic_group_count"] = len(diagnostics)
        summary["retained_diagnostics_truncated"] = True
    return "incomplete", summary
