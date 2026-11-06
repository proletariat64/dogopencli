"""Shared import-qualification declaration and operation contracts."""

import re
from typing import Any


def safe_native(value: Any) -> str | None:
    if (
        type(value) not in (str, int)
        or re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", str(value)) is None
    ):
        return None
    return str(value)


def validate_import_qualification(contract: Any) -> list[dict[str, Any]]:
    if (
        not isinstance(contract, dict)
        or set(contract) != {"version", "rules"}
        or type(contract["version"]) is not int
        or contract["version"] != 1
        or not isinstance(contract["rules"], list)
    ):
        raise ValueError("import qualification contract is invalid")
    rules = contract["rules"]
    if not rules:
        raise ValueError("import qualification requires at least one rule")
    identifiers = set()
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {
            "id",
            "action",
            "reason_codes",
            "retained_errors",
        }:
            raise ValueError("import qualification rule is empty, duplicate or invalid")
        identifier = rule["id"]
        reasons = rule["reason_codes"]
        matchers = rule["retained_errors"]
        if (
            not isinstance(identifier, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", identifier) is None
            or identifier in identifiers
            or rule["action"] != "preserve"
            or not isinstance(reasons, list)
            or not isinstance(matchers, list)
            or not reasons
            and not matchers
            or any(
                not isinstance(reason, str)
                or re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", reason) is None
                for reason in reasons
            )
            or len(reasons) != len(set(reasons))
        ):
            raise ValueError("import qualification rule is empty, duplicate or invalid")
        identifiers.add(identifier)
        encoded = set()
        for matcher in matchers:
            if (
                not isinstance(matcher, dict)
                or set(matcher)
                - {"component", "retention", "diagnostic_code", "native_code"}
                or not {"component", "retention", "diagnostic_code"} <= set(matcher)
                or not isinstance(matcher["component"], str)
                or re.fullmatch(r"[a-z][a-z0-9_]{0,79}", matcher["component"]) is None
                or not isinstance(matcher["retention"], str)
                or matcher["retention"] not in {"failed", "refused"}
                or not isinstance(matcher["diagnostic_code"], str)
                or re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", matcher["diagnostic_code"])
                is None
                or "native_code" in matcher
                and safe_native(matcher["native_code"]) is None
            ):
                raise ValueError("import qualification diagnostic matcher is invalid")
            identity = (
                matcher["component"],
                matcher["retention"],
                matcher["diagnostic_code"],
                safe_native(matcher.get("native_code"))
                if "native_code" in matcher
                else None,
                "native_code" in matcher,
            )
            if identity in encoded:
                raise ValueError(
                    "import qualification diagnostic matchers must be unique"
                )
            encoded.add(identity)
    return rules


def eligible_full_list(record: dict[str, Any]) -> bool:
    return (
        record.get("operation") == "list"
        and record.get("mode") == "full"
        and record.get("with_detail") is False
        and "history_plan" not in record
        and "repair_plan" not in record
    )
