"""Shared success envelope validation for verified inquiry contracts."""

from typing import Any

from ..errors import BUSINESS_QUERY_FAILED, INVALID_RESPONSE, CliError
from ..jsonutil import parse


def success_document(body: bytes) -> dict[str, Any]:
    """Reject invalid/business-failure envelopes without exposing backend context."""
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict):
        raise CliError(INVALID_RESPONSE, "response envelope is not an object")
    # Success responses also carry errorContext; only the boolean decides success.
    if document.get("success") is not True:
        raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
    return document
