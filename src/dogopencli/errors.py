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
