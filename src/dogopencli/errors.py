"""Structured business errors and exit codes (ADR 0004)."""

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
