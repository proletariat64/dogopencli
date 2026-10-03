"""Liquidity response envelope parsing for the observed families.

Observed 2026-10-01 (docs/research/general/2026-10-01-liquidity-live-probes.md):

- ``success``: ``{success: true, data: ..., errorCode, errorMessage, ...}``
- ``baseResult``: ``{baseResult: {success: true, data: ...}}`` (transfer detail)
- ``resultFlag``: ``{resultFlag: true, result: {...}}``; a present inner
  ``result.success`` must also be true (permission failures carry both false)
- ``resultSuccess``: ``{success: true, result: {...}}`` (transfer rule detail)

Business failures arrive as HTTP 200 with the marker false; they are never
tolerated as empty datasets. Messages stay generic: backend error context
can carry request data.
"""

from typing import Any

from ...errors import BUSINESS_QUERY_FAILED, INVALID_RESPONSE, CliError
from ...jsonutil import parse
from . import spec


def _is_true(value: Any) -> bool:
    """Strict success marker: only the genuine boolean true counts."""
    return isinstance(value, bool) and value


def _is_false(value: Any) -> bool:
    """Strict refusal marker: only the genuine boolean false counts."""
    return isinstance(value, bool) and not value


def _document(body: bytes) -> dict[str, Any]:
    try:
        document = parse(body)
    except ValueError as error:
        raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
    if not isinstance(document, dict):
        raise CliError(INVALID_RESPONSE, "response envelope is not an object")
    return document


def envelope_document(body: bytes, style: str) -> dict[str, Any]:
    """Validate the envelope success markers and return the full document.

    Callers descend with their registered container/total paths from the
    document root (``result``/``baseResult`` segments included).
    """
    document = _document(body)
    if style == spec.ENV_SUCCESS:
        if not _is_true(document.get("success")):
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        return document
    if style == spec.ENV_BASE_RESULT:
        node = document.get("baseResult")
        if not isinstance(node, dict) or not _is_true(node.get("success")):
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        return document
    if style in (spec.ENV_RESULT_FLAG, spec.ENV_RESULT_SUCCESS):
        marker = "resultFlag" if style == spec.ENV_RESULT_FLAG else "success"
        if not _is_true(document.get(marker)):
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        node = document.get("result")
        if not isinstance(node, dict):
            raise CliError(INVALID_RESPONSE, "response result is not an object")
        if _is_false(node.get("success")):
            raise CliError(BUSINESS_QUERY_FAILED, "backend reported a business failure")
        return document
    raise CliError(INVALID_RESPONSE, f"unknown envelope style {style}")


def dig(node: dict[str, Any], path: tuple[str, ...]) -> Any:
    """Descend an exact key path; a missing step is an invalid response."""
    current: Any = node
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise CliError(
                INVALID_RESPONSE,
                "response is missing the registered record path",
            )
        current = current[key]
    return current
