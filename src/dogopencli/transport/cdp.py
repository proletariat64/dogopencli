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

from typing import Any

from ..browser.cdp import CdpError, CdpSession, CdpTransport
from ..errors import REQUEST_NOT_ALLOWED, CliError
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

    def execute(self, request: QueryRequest) -> TransportResponse:
        if request.capability != self._capability.name:
            raise CliError(
                REQUEST_NOT_ALLOWED,
                "CDP transport only serves its registered capability",
            )
        validate_request(request, self._capability.contract)
        session = self._ensure_session()
        expression = _fetch_expression(request, self._query_timeout)
        try:
            result = session.evaluate(expression, self._command_budget)
        except CdpError as error:
            raise FetchFailed(f"business fetch failed in page: {error}") from error
        if not isinstance(result, dict):
            raise FetchFailed("business fetch returned an unusable value")
        if result.get("error") is not None:
            raise FetchFailed(f"business fetch failed in page: {result['error']}")
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

    def _ensure_session(self) -> CdpSession:
        if self._session is None:
            self._target = self._cdp.new_target(self._page_url)
            ws_url = self._target.get("webSocketDebuggerUrl")
            if not isinstance(ws_url, str) or not ws_url:
                raise FetchFailed("CDP target response missing webSocketDebuggerUrl")
            self._session = self._cdp.open_session(ws_url)
        return self._session

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
        if self._target is not None:
            target_id = self._target.get("id")
            if isinstance(target_id, str) and target_id:
                self._cdp.close_target(target_id)
            self._target = None
