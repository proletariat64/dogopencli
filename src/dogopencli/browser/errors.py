"""Authentication-domain error shared by the browser layer and the auth CLI.

Ported from DI ``diexporter.model.CommandError`` and ``di.cli.errors.CLIError``
(baseline commit 8eb163c6d140554ca167bd50349a85ca224ac342); one error type
carries the stable machine code, retryable flag, details and next steps.
"""

from typing import Any

INVALID_ARGUMENTS = "invalid_arguments"
AUTH_REQUIRED = "auth_required"
BROWSER_UNAVAILABLE = "browser_unavailable"
SERVICE_FAILURE = "service_failure"
LOGIN_IN_PROGRESS = "login_in_progress"
BROWSER_BUSY = "browser_busy"
CONFIG_INVALID = "config_invalid"
LOGOUT_UNVERIFIED = "logout_unverified"

RETRYABLE_CODES = {
    AUTH_REQUIRED,
    BROWSER_UNAVAILABLE,
    BROWSER_BUSY,
    LOGIN_IN_PROGRESS,
    SERVICE_FAILURE,
}


class AuthError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool | None = None,
        details: dict[str, Any] | None = None,
        next: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = code in RETRYABLE_CODES if retryable is None else retryable
        self.details = details or {}
        self.next = list(next)


def invalid(message: str) -> AuthError:
    return AuthError(INVALID_ARGUMENTS, message)
