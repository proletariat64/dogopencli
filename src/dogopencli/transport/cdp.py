"""CDP QueryTransport: allowlisted business queries through the authenticated
dedicated browser session (issue #5).

One temporary target on the payment application page issues the registered
request via ``fetch`` with ``credentials: "include"``; POST bodies go in the
request body, GET payloads serialize into the URL query. The session cookie
and the ``ctoken`` query parameter stay inside the browser and never enter
the request construction, cache, output or logs. The transport never launches
Chrome, never repairs sessions and never classifies authentication; callers
run the bounded auth probe first and own retry/budget decisions.
"""

import time
from typing import Any

from ..browser.cdp import (
    BrowserLoss,
    CdpError,
    CdpSession,
    CdpTransport,
    probe_final_url,
)
from ..browser.probe import is_login_landing
from ..errors import AUTH_REQUIRED, INVALID_RESPONSE, REQUEST_NOT_ALLOWED, CliError
from ..jsonutil import canonical
from ..plugins import Capability
from . import OriginMetadata, QueryRequest, TransportResponse, validate_request

QUERY_TIMEOUT_SECONDS = 60.0
COMMAND_BUDGET_SECONDS = 65.0

ORIGIN_CDP = OriginMetadata(
    backend="cdp",
    simulated=False,
    dataset_id=None,
    dataset_complete=None,
    backend_complete=None,
    source_observed_from=None,
    source_observed_to=None,
)


class FetchFailed(Exception):
    """Network-level failure of the in-page fetch (timeout, reset, abort)."""


def _fetch_expression(request: QueryRequest, timeout_seconds: float) -> str:
    url = f"https://{request.host}{request.path}"
    payload = canonical(request.body)
    timeout_ms = int(timeout_seconds * 1000)
    if request.method == "GET":
        # GET carries no body: the validated payload keys serialize into the
        # URL query (they already passed the contract allowlist).
        prepare = "const params = new URLSearchParams(payload).toString();"
        target = (
            f'"{url}?ctoken=" + encodeURIComponent(ctoken)'
            ' + (params ? "&" + params : "")'
        )
        options = (
            f'method: "{request.method}", credentials: "include", '
            "signal: controller.signal"
        )
    else:
        prepare = ""
        target = f'"{url}?ctoken=" + encodeURIComponent(ctoken)'
        options = (
            f'method: "{request.method}", credentials: "include", '
            'headers: {"Content-Type": "application/json"}, '
            "body: JSON.stringify(payload), signal: controller.signal"
        )
    return (
        "(async (payload) => {"
        "const match = document.cookie.match(/(?:^|;\\s*)ctoken=([^;]*)/);"
        "const ctoken = match ? match[1] : '';"
        "const controller = new AbortController();"
        f"const timer = setTimeout(() => controller.abort(), {timeout_ms});"
        "try {"
        f"{prepare}"
        f"const response = await fetch({target}, {{{options}}});"
        "const text = await response.text();"
        "return {status: response.status, body: text, "
        "finalUrl: response.url, redirected: response.redirected, "
        'retryAfter: response.headers.get("retry-after")};'
        "} catch (error) {"
        'return {status: 0, body: "", retryAfter: null, error: String(error)};'
        "} finally { clearTimeout(timer); }"
        f"}})({payload})"
    )


class CdpQueryTransport:
    """QueryTransport over one dedicated CDP target of the logged-in session."""

    def __init__(
        self,
        cdp: CdpTransport,
        capability: Capability,
        *,
        page_url: str,
        query_timeout: float = QUERY_TIMEOUT_SECONDS,
        command_budget: float = COMMAND_BUDGET_SECONDS,
    ) -> None:
        self._cdp = cdp
        self._capability = capability
        self._page_url = page_url
        self._query_timeout = query_timeout
        self._command_budget = command_budget
        self._target: dict[str, Any] | None = None
        self._session: CdpSession | None = None

    def execute(
        self, request: QueryRequest, *, timeout: float | None = None
    ) -> TransportResponse:
        try:
            return self._execute(request, timeout=timeout)
        except FetchFailed:
            self.close()
            raise

    def _execute(
        self, request: QueryRequest, *, timeout: float | None = None
    ) -> TransportResponse:
        if request.capability != self._capability.name:
            raise CliError(
                REQUEST_NOT_ALLOWED,
                "CDP transport only serves its registered capability",
            )
        validate_request(request, self._capability.contract)
        deadline = time.monotonic() + (
            self._command_budget
            if timeout is None
            else min(timeout, self._command_budget)
        )
        try:
            session = self._ensure_session(deadline)
        except CdpError as error:
            raise FetchFailed("business query session setup failed") from error
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchFailed("business query budget exhausted during session setup")
        expression = _fetch_expression(request, min(self._query_timeout, remaining))
        try:
            result = session.evaluate(expression, remaining)
        except CdpError as error:
            raise FetchFailed(f"business fetch failed in page: {error}") from error
        if not isinstance(result, dict):
            raise FetchFailed("business fetch returned an unusable value")
        if result.get("error") is not None:
            # A cross-origin login redirect may surface only as a fetch/CORS
            # error. Re-probe within this request's remaining budget; do not
            # infer expiration from a generic network error alone.
            remaining = deadline - time.monotonic()
            if remaining > 0:
                try:
                    landing = probe_final_url(
                        self._cdp, self._page_url, timeout=min(15.0, remaining)
                    )
                except (CdpError, BrowserLoss):
                    pass
                else:
                    if is_login_landing(landing):
                        raise CliError(
                            AUTH_REQUIRED, "session expired; run dogopencli login"
                        )
            raise FetchFailed(f"business fetch failed in page: {result['error']}")
        final_url = result.get("finalUrl")
        if isinstance(final_url, str) and is_login_landing(final_url):
            raise CliError(
                AUTH_REQUIRED, "backend redirected to login; run dogopencli login"
            )
        if result.get("redirected") is True:
            raise CliError(
                INVALID_RESPONSE,
                "business query redirected to an unverified destination",
            )
        status = result.get("status")
        body = result.get("body")
        retry_after = result.get("retryAfter")
        if (
            isinstance(status, bool)
            or not isinstance(status, int)
            or not isinstance(body, str)
        ):
            raise FetchFailed("business fetch returned an unusable value")
        return TransportResponse(
            status=status,
            body=body.encode(),
            origin=ORIGIN_CDP,
            retry_after=retry_after if isinstance(retry_after, str) else None,
        )

    def _ensure_session(self, deadline: float) -> CdpSession:
        if self._session is None:
            self._target = self._cdp.new_target(
                self._page_url, timeout=max(0.001, deadline - time.monotonic())
            )
            ws_url = self._target.get("webSocketDebuggerUrl")
            if not isinstance(ws_url, str) or not ws_url:
                raise FetchFailed("CDP target response missing webSocketDebuggerUrl")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FetchFailed(
                    "business query budget exhausted during target creation"
                )
            self._session = self._cdp.open_session(ws_url, timeout=remaining)
        return self._session

    def close(self) -> None:
        session, target = self._session, self._target
        self._session = None
        self._target = None
        if session is not None:
            try:
                session.close()
            except CdpError:
                pass
        if target is not None:
            target_id = target.get("id")
            if isinstance(target_id, str) and target_id:
                try:
                    self._cdp.close_target(target_id)
                except CdpError:
                    pass
