"""Structured business errors and exit codes (ADR 0004)."""

import re
from typing import Any, Literal

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130

CACHE_MISS = "CACHE_MISS"
CACHE_STALE = "CACHE_STALE"
INCOMPLETE_RESULT = "INCOMPLETE_RESULT"
NOT_FOUND = "NOT_FOUND"
AUTH_REQUIRED = "AUTH_REQUIRED"
BROWSER_UNAVAILABLE = "BROWSER_UNAVAILABLE"
REQUEST_NOT_ALLOWED = "REQUEST_NOT_ALLOWED"
BUSINESS_QUERY_FAILED = "BUSINESS_QUERY_FAILED"
TIMEOUT = "TIMEOUT"
INVALID_RESPONSE = "INVALID_RESPONSE"
LOCKED = "LOCKED"
SOURCE_DATA_MISSING = "SOURCE_DATA_MISSING"
SOURCE_DATA_INVALID = "SOURCE_DATA_INVALID"
SOURCE_SCOPE_UNAVAILABLE = "SOURCE_SCOPE_UNAVAILABLE"
LIVE_SOURCE_UNAVAILABLE = "LIVE_SOURCE_UNAVAILABLE"
CONFIG_ERROR = "CONFIG_ERROR"
INVALID_ARGUMENT = "INVALID_ARGUMENT"
UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"


def error_exit_code(code: str | None) -> int:
    """Map a public outcome to its process status; adapters do not choose it."""
    if code is None:
        return EXIT_OK
    if code == INVALID_ARGUMENT:
        return EXIT_USAGE
    if code == "INTERRUPTED":
        return EXIT_INTERRUPTED
    return EXIT_FAILURE


_DIAGNOSTIC_CONTEXT = {
    INVALID_ARGUMENT: ("input", "validation", "Correct the arguments and retry."),
    AUTH_REQUIRED: ("authentication", "authentication", "Run dogopencli login."),
    BROWSER_UNAVAILABLE: (
        "host",
        "browser",
        "Run dogopencli login, then verify with dogopencli auth check.",
    ),
    LOCKED: ("host", "coordination", "Retry after the active operation finishes."),
    BUSINESS_QUERY_FAILED: ("backend", "query", None),
    SOURCE_DATA_MISSING: (
        "source",
        "resolution",
        "Supply or refresh the required source data and retry.",
    ),
    CONFIG_ERROR: ("host", "configuration", "Correct the configuration and retry."),
    "INTERRUPTED": ("host", "execution", "Run the inquiry again when ready."),
}


def diagnostic(
    code: str,
    message: str,
    *,
    severity: Literal["error", "warning"] = "error",
    retryable: bool | None = None,
    origin: str | None = None,
    stage: str | None = None,
    component: str | None = None,
    scope: str | None = None,
    native_code: str | int | None = None,
    consequence: str | None = None,
    action: str | None = None,
    reason_codes: list[str] | tuple[str, ...] | None = None,
    count: int | None = None,
) -> dict[str, Any]:
    """Normalize safe facts once for SDK, CLI, and other result consumers.

    Unknown causes and remedies stay null. Only an endpoint's already qualified
    native code belongs here; native messages and response bodies do not.
    """
    default_origin, default_stage, default_action = _DIAGNOSTIC_CONTEXT.get(
        code, (None, None, None)
    )
    safe_native = (
        native_code
        if type(native_code) in (str, int)
        and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", str(native_code))
        else None
    )
    if code == INCOMPLETE_RESULT:
        default_action = (
            "Inspect coverage reasons or use --require-complete."
            if severity == "warning"
            else "Inspect coverage reasons; narrow the scope or repair the source."
        )
    result: dict[str, Any] = {
        "code": code,
        "message": message,
        "severity": severity,
        "origin": origin if origin is not None else default_origin,
        "stage": stage if stage is not None else default_stage,
        "component": component,
        "scope": scope,
        "retryable": retryable,
        "native_code": safe_native,
        "consequence": consequence,
        "action": action if action is not None else default_action,
    }
    if reason_codes is not None:
        result["reason_codes"] = list(dict.fromkeys(reason_codes))
    if count is not None:
        result["count"] = count
    return result


def normalize_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep warning facts and aggregate repeated reasons per affected component."""
    grouped: dict[tuple, dict[str, Any]] = {}
    for warning in warnings:
        if (
            not isinstance(warning, dict)
            or not isinstance(warning.get("code"), str)
            or not isinstance(warning.get("message"), str)
        ):
            raise CliError(INVALID_RESPONSE, "invalid result warning")
        reasons = warning.get("reason_codes")
        if reasons is not None and (
            not isinstance(reasons, (list, tuple))
            or any(not isinstance(reason, str) for reason in reasons)
        ):
            raise CliError(INVALID_RESPONSE, "invalid warning reasons")
        count = warning.get("count", 1)
        if type(count) is not int or count < 1:
            raise CliError(INVALID_RESPONSE, "invalid warning count")
        facts = {
            key: warning[key]
            for key in (
                "retryable",
                "origin",
                "stage",
                "component",
                "scope",
                "native_code",
                "consequence",
                "action",
            )
            if key in warning
        }
        for field, value in facts.items():
            if field == "native_code":
                continue
            if field == "retryable":
                valid = value is None or isinstance(value, bool)
            else:
                valid = value is None or isinstance(value, str)
            if not valid:
                raise CliError(INVALID_RESPONSE, "invalid warning context")
        value = diagnostic(
            warning["code"],
            warning["message"],
            severity="warning",
            reason_codes=reasons,
            count=count,
            **facts,
        )
        key = (
            value["code"],
            value["origin"],
            value["stage"],
            value["component"],
            value["scope"],
            value["native_code"],
            tuple(value.get("reason_codes", ())),
        )
        if key in grouped:
            grouped[key]["count"] += count
        else:
            grouped[key] = value
    return list(grouped.values())


class CliError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool = False,
        exit_code: int = EXIT_FAILURE,
        meta: dict | None = None,
        *,
        command_path: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.exit_code = exit_code
        self.meta = meta
        self.command_path = command_path

    def diagnostic(self, *, component: str | None = None) -> dict[str, Any]:
        """Expose qualified safe cause facts without copying arbitrary metadata."""
        facts = self.meta or {}
        supplied = facts.get("diagnostic", {})
        context = (
            {
                key: value
                for key, value in supplied.items()
                if key
                in {"origin", "stage", "component", "scope", "consequence", "action"}
                and isinstance(value, str)
            }
            if isinstance(supplied, dict)
            else {}
        )
        context.setdefault("component", component)
        context.setdefault("consequence", "The requested result was not accepted.")
        reasons = supplied.get("reason_codes") if isinstance(supplied, dict) else None
        if isinstance(reasons, (list, tuple)) and all(
            isinstance(reason, str) for reason in reasons
        ):
            context["reason_codes"] = reasons
        native_code = facts.get("native_code")
        if native_code is None and isinstance(supplied, dict):
            native_code = supplied.get("native_code")
        return diagnostic(
            self.code,
            self.message,
            retryable=self.retryable,
            native_code=native_code,
            **context,
        )
