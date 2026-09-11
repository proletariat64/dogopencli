"""CDP transport and the bounded navigation-probe primitives.

Ported from DI ``src/diexporter/browser_cdp.py`` at baseline commit
8eb163c6d140554ca167bd50349a85ca224ac342, reduced to the authentication
surface: endpoint discovery, one temporary target per probe, settle
classification by the caller, and the test transport seam. The session also
carries one raw page-level command primitive for the logout cookie clearing
(``browser/cookies.py``, issue #8). Worker/export machinery is not ported here.
"""

import contextlib
import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlparse


def url_origin(url: str) -> str:
    """scheme://netloc of a URL (``ParseResult.origin`` is Python 3.13+)."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


class CdpError(Exception):
    """A transport-level CDP failure (unreachable endpoint, dead target)."""


class PageNotReady(CdpError):
    """A target stayed non-ready until its bounded startup deadline."""

    def __init__(self, ready_state: str) -> None:
        super().__init__(f"target page never became ready (readyState={ready_state!r})")
        self.ready_state = ready_state


class BrowserLoss(Exception):
    """The browser became unavailable or navigation failed outright."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class CdpSession(ABC):
    """One open DevTools session on a target's websocket."""

    @abstractmethod
    def evaluate(self, expression: str, timeout: float) -> Any:
        """``Runtime.evaluate`` (awaitPromise, returnByValue) on this session."""

    @abstractmethod
    def navigate(self, url: str, timeout: float) -> None:
        """Navigate this target explicitly and reject immediate navigation errors."""

    def command(self, method: str, params: Mapping[str, Any], timeout: float) -> Any:
        """Run one raw page-level CDP command (e.g. ``Network.deleteCookies``).

        Concrete default (not abstract) so probe-only sessions stay valid;
        sessions that support raw commands override it.
        """
        raise CdpError(f"{type(self).__name__} does not support raw CDP commands")

    @abstractmethod
    def close(self) -> None:
        """Close the underlying websocket (best effort, idempotent)."""


class CdpTransport(ABC):
    """Minimal CDP endpoint abstraction (attach-only; never launches Chrome).

    The production implementation speaks HTTP + websocket to the Chrome
    DevTools endpoint; tests inject a fake via ``set_transport_factory``.
    """

    @abstractmethod
    def version(self) -> dict[str, Any]:
        """``/json/version``; raises ``CdpError`` when unreachable."""

    @abstractmethod
    def new_target(self, url: str, *, timeout: float | None = None) -> dict[str, Any]:
        """Create one dedicated page target; returns id/url/websocket keys."""

    @abstractmethod
    def close_target(self, target_id: str) -> None:
        """Close a probe-created target (best effort)."""

    @abstractmethod
    def open_session(self, ws_url: str, *, timeout: float | None = None) -> CdpSession:
        """Open the websocket session for one target."""


class HttpCdpSession(CdpSession):
    """Persistent websocket session on one target."""

    def __init__(self, ws_url: str, *, timeout: float) -> None:
        import websocket

        try:
            self._ws = websocket.create_connection(ws_url, timeout=timeout)
        except Exception as exc:  # websocket-client raises assorted socket errors
            raise CdpError(f"cannot open target websocket: {exc}") from exc
        self._next_id = 0
        self._closed = False

    def _command(self, method: str, params: Mapping[str, Any], timeout: float) -> Any:
        self._next_id += 1
        message_id = self._next_id
        deadline = time.monotonic() + timeout
        try:
            self._ws.settimeout(timeout)
            self._ws.send(
                json.dumps({"id": message_id, "method": method, "params": dict(params)})
            )
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CdpError(f"{method} exceeded its {timeout:g}s deadline")
                self._ws.settimeout(remaining)
                message = json.loads(self._ws.recv())
                if message.get("id") != message_id:
                    continue  # skip CDP events until our response arrives
                if "error" in message:
                    raise CdpError(f"{method} failed: {message['error']}")
                return message.get("result", {})
        except CdpError:
            raise
        except Exception as exc:  # websocket-client timeout/socket hierarchy varies
            raise CdpError(f"target websocket failure: {exc}") from exc

    def evaluate(self, expression: str, timeout: float) -> Any:
        result = self._command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
            timeout,
        )
        if "exceptionDetails" in result:
            raise CdpError("evaluate raised in page")
        return result.get("result", {}).get("value")

    def navigate(self, url: str, timeout: float) -> None:
        result = self._command("Page.navigate", {"url": url}, timeout)
        if result.get("errorText"):
            raise CdpError(f"navigation failed: {result['errorText']}")

    def command(self, method: str, params: Mapping[str, Any], timeout: float) -> Any:
        return self._command(method, params, timeout)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            with contextlib.suppress(Exception):
                self._ws.close()


class HttpCdpTransport(CdpTransport):
    """Real CDP transport over HTTP discovery endpoints and websocket sessions."""

    def __init__(self, cdp_url: str, *, timeout: float = 5.0) -> None:
        self._base = cdp_url.rstrip("/")
        self._timeout = timeout

    def version(self) -> dict[str, Any]:
        return self._get_json("/json/version")

    def new_target(self, url: str, *, timeout: float | None = None) -> dict[str, Any]:
        import urllib.error
        import urllib.parse
        import urllib.request

        deadline = time.monotonic() + (
            self._timeout if timeout is None else min(timeout, self._timeout)
        )
        quoted = urllib.parse.quote(url, safe="")
        req = urllib.request.Request(f"{self._base}/json/new?{quoted}", method="PUT")
        try:
            with urllib.request.urlopen(
                req, timeout=max(0.001, deadline - time.monotonic())
            ) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError:
            # Older Chrome exposes /json/new as GET.
            req = urllib.request.Request(
                f"{self._base}/json/new?{quoted}", method="GET"
            )
            try:
                with urllib.request.urlopen(
                    req, timeout=max(0.001, deadline - time.monotonic())
                ) as resp:
                    data = json.loads(resp.read())
            except (OSError, ValueError) as exc:
                raise CdpError(f"cannot create target: {exc}") from exc
        except (OSError, ValueError) as exc:
            raise CdpError(f"cannot create target: {exc}") from exc
        if not isinstance(data, dict) or "id" not in data:
            raise CdpError("unexpected /json/new response")
        return data

    def close_target(self, target_id: str) -> None:
        try:
            self._get_json(f"/json/close/{target_id}")
        except CdpError:
            return None  # best effort: the target may already be gone

    def open_session(self, ws_url: str, *, timeout: float | None = None) -> CdpSession:
        return HttpCdpSession(
            ws_url,
            timeout=self._timeout if timeout is None else min(timeout, self._timeout),
        )

    def _get_json(self, path: str) -> Any:
        import urllib.request

        req = urllib.request.Request(f"{self._base}{path}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read())
        except (OSError, ValueError) as exc:
            raise CdpError(f"CDP endpoint failure at {path}: {exc}") from exc


_TRANSPORT_FACTORY: Callable[[str], CdpTransport] | None = None


def set_transport_factory(factory: Callable[[str], CdpTransport] | None) -> None:
    """Install (or clear) an injected transport factory for tests."""
    global _TRANSPORT_FACTORY
    _TRANSPORT_FACTORY = factory


def make_transport(cdp_url: str) -> CdpTransport:
    """Build the transport for the dedicated browser endpoint."""
    if _TRANSPORT_FACTORY is not None:
        return _TRANSPORT_FACTORY(cdp_url)
    return HttpCdpTransport(cdp_url)


def _await_target_settled(session: CdpSession, *, timeout: float = 15.0) -> str:
    """Wait for navigation to settle and return the final href (any origin).

    The auth probe classifies the final origin itself, so an SSO redirect must
    be reported rather than raised. Readiness/stability rules are unchanged
    from the DI probe: skip initial blank states, require two stable ready
    samples.
    """
    deadline = time.monotonic() + timeout
    previous_href: str | None = None
    stable_samples = 0
    last_ready_state = ""
    expression = "({ready_state: document.readyState, href: location.href})"
    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        raw = session.evaluate(expression, min(5.0, remaining))
        if not isinstance(raw, Mapping):
            raise CdpError("target readiness probe returned an unusable value")
        ready_state = str(raw.get("ready_state") or "")
        last_ready_state = ready_state
        href = str(raw.get("href") or "")
        if href in {"", "about:blank"}:
            previous_href = None
            stable_samples = 0
            time.sleep(0.25)
            continue
        if href.startswith("chrome-error://"):
            raise BrowserLoss("target navigation failed", reason="navigation_error")
        if ready_state in {"interactive", "complete"}:
            stable_samples = stable_samples + 1 if href == previous_href else 1
            if stable_samples >= 2:
                return href
        else:
            stable_samples = 0
        previous_href = href
        time.sleep(0.25)
    raise PageNotReady(last_ready_state)


#: UAT 2026-09-12: with the authentication cookies cleared, the payment
#: entry page still settles on its own URL first and only redirects to the
#: login page through a JS-driven navigation seconds later. A probe that
#: settles on the entry URL therefore keeps polling for this short window; a
#: URL change re-enters the bounded settle wait. Kept short so healthy
#: sessions are not slowed beyond necessity.
ENTRY_STABILITY_SECONDS = 5.0


def probe_final_url(transport: CdpTransport, url: str, *, timeout: float = 15.0) -> str:
    """Create, navigate, settle, and close one target; return the final href.

    The bounded authentication-probe primitive: exactly one temporary target
    and one navigation; the caller classifies the final origin. A settle on
    the entry URL is confirmed against late JS-driven redirects for up to
    ``ENTRY_STABILITY_SECONDS``, bounded by ``timeout``.
    """
    target: dict[str, Any] | None = None
    session: CdpSession | None = None
    try:
        target = transport.new_target(url)
        session = transport.open_session(_target_field(target, "webSocketDebuggerUrl"))
        session.navigate(url, timeout)
        deadline = time.monotonic() + timeout
        try:
            href = _await_target_settled(session, timeout=timeout)
        except PageNotReady:
            # Chrome can expose a cold target before its navigation task starts.
            href = _await_target_settled(session, timeout=timeout)
        return _confirm_entry_stability(session, url, href, deadline=deadline)
    finally:
        if session is not None:
            session.close()
        if target is not None:
            target_id = target.get("id")
            if isinstance(target_id, str) and target_id:
                transport.close_target(target_id)


def _confirm_entry_stability(
    session: CdpSession, url: str, href: str, *, deadline: float
) -> str:
    """Confirm an entry-URL settle against late JS-driven redirects.

    Only a settle on the entry origin is suspect (see
    ``ENTRY_STABILITY_SECONDS``); any other origin is returned immediately.
    Polling stops at the earlier of the window and the probe deadline; a URL
    change re-enters the bounded settle wait.
    """
    if url_origin(href) != url_origin(url):
        return href
    expression = "({ready_state: document.readyState, href: location.href})"
    window_end = min(time.monotonic() + ENTRY_STABILITY_SECONDS, deadline)
    while time.monotonic() < window_end:
        time.sleep(min(0.25, max(0.0, window_end - time.monotonic())))
        remaining = max(0.1, deadline - time.monotonic())
        try:
            raw = session.evaluate(expression, min(5.0, remaining))
        except CdpError:
            # A navigation starting mid-poll can break the evaluation.
            return _await_target_settled(session, timeout=remaining)
        if not isinstance(raw, Mapping):
            raise CdpError("target readiness probe returned an unusable value")
        current = str(raw.get("href") or "")
        if current != href:
            return _await_target_settled(session, timeout=remaining)
    return href


def _target_field(target: Mapping[str, Any], field: str) -> str:
    value = target.get(field)
    if not isinstance(value, str) or not value:
        raise CdpError(f"CDP target response missing {field}")
    return value
